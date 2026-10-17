"""Exercise the actual tool/HTTP boundaries that previously erased useful causes."""
import json
import pytest
from pydantic import BaseModel, Field
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.analysis.errors import ToolError
from app.diagnostics import error_info
from app.errors import validation_error_handler
from app.services.analysis_tools import DatasetTools


def test_movie_top_n_scope_preserves_actual_chart_limit_and_recovery():
    tools = DatasetTools.from_frame(1, [{'genres': f'category_{i}', 'movie_count': i} for i in range(902)])
    # This is the saved failing plan's shape: ten WITHIN each already unique category.
    tools.execute('top_n', {'column': 'movie_count', 'n': 10, 'group_by': ['genres']}, call_id='top10')
    assert len(tools.frame_results['top10']) == 902
    chart = {'type': 'bar', 'dimension': 'genres', 'metrics': [{'field': 'movie_count'}], 'title': '类型分布'}
    with pytest.raises(ToolError) as caught:
        tools.execute('generate_chart', chart, source_ref='top10', call_id='chart')
    info = error_info(caught.value.code, exception=caught.value, details=caught.value.details)
    assert info['reason_code'] == 'CHART_POINT_LIMIT_EXCEEDED'
    assert info['actual_count'] == 902 and info['max_count'] == 500
    assert '902' in info['reason'] and '500' in info['reason']
    assert '全局' in info['suggestion'] and 'group_by' in info['suggestion']
    # Preserve per-group top-N semantics; global top-N explicitly clears grouping.
    tools.execute('top_n', {'column': 'movie_count', 'n': 10, 'group_by': []}, call_id='global10')
    result = tools.execute('generate_chart', chart, source_ref='global10', call_id='fixed_chart')
    assert len(result.data['series'][0]['data']) == 10


def test_http_missing_and_long_fields_are_actionable_without_copying_input():
    class Input(BaseModel):
        question: str = Field(max_length=8)
        dataset_id: int
    app = FastAPI()
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    @app.post('/probe')
    def probe(body: Input):
        return {}
    response = TestClient(app).post('/probe', json={'question': 'private-business-content'})
    info = response.json()['data']['error_info']
    assert 'question' in info['reason'] and '8' in info['reason']
    assert any('dataset_id' in f['message'] and '缺少' in f['message'] for f in info['field_errors'])
    assert info['field_errors'][0]['actual_length'] == 24
    assert 'private-business-content' not in json.dumps(response.json())


def test_tool_schema_and_missing_column_keep_field_paths_and_types():
    tools = DatasetTools.from_frame(1, [{'genres': 'Drama'}])
    for arguments, expected in [({}, '缺少'), ({'column': 'missing'}, '不存在')]:
        with pytest.raises(ToolError) as caught:
            tools.execute('top_n', arguments)
        info = error_info(caught.value.code, exception=caught.value, details=caught.value.details)
        assert expected in info['reason']
        if arguments:
            assert info['column'] == 'missing'
        else:
            assert info['field_errors'][0]['path'] == 'column'


@pytest.mark.parametrize('dataset_key', ['dataset', 'datasets'])
def test_context_overflow_reports_measured_size_before_model_call(dataset_key):
    from app.agent.model_adapter import ModelAdapter
    from app.config import Settings
    model = object()  # Would fail immediately if a network/model boundary were reached.
    adapter = ModelAdapter(model, Settings(_env_file=None, deepseek_api_key=''))
    with pytest.raises(ValueError) as caught:
        adapter.invoke('probe', json.dumps({'tools': ['x'*61000], dataset_key: {}}, ensure_ascii=False))
    info = error_info('PLAN_INVALID', exception=caught.value)
    assert info['reason_code'] == 'MODEL_CONTEXT_BUDGET_EXCEEDED'
    assert info['actual_length'] > info['max_length'] == 60000
    assert '上下文' in info['reason'] and '缩小' in info['suggestion']
    assert 'x'*100 not in json.dumps(info)


def test_unknown_exception_values_cannot_become_public_validation_rules():
    info = error_info('INTERNAL_ERROR', exception=ValueError('PRIVATE_CREDENTIAL_VALUE'))
    assert 'PRIVATE_CREDENTIAL_VALUE' not in json.dumps(info)
    assert 'validation_rule' not in info


def test_planner_corrects_global_group_ranking_once_without_changing_per_group_semantics():
    from copy import deepcopy
    from app.agent.planner import Planner, validate_top_n_scope
    from app.agent.providers import FakeLLMProvider
    from app.agent.context import ConversationContext
    from app.agent.schemas import AnalysisPlanV3
    from app.analysis.models import Permission
    binding = {'alias': 'primary', 'dataset_id': 1, 'dataset_version_id': 4}
    bad = {'task_id': 'scope', 'goal': '前10组', 'intent': 'DATA_ANALYSIS', 'dataset_id': 1,
           'dataset_version_id': 4, 'inputs': [binding], 'steps': [
        {'step_id': 'count', 'tool_name': 'groupby_aggregate', 'arguments': {'dimensions': ['genres'],
         'metrics': [{'column': 'movieid', 'aggregation': 'count', 'alias': 'movie_count'}]}},
        {'step_id': 'top10', 'tool_name': 'top_n', 'source_ref': 'count', 'depends_on': ['count'],
         'arguments': {'column': 'movie_count', 'n': 10, 'group_by': ['genres']}}]}
    good = deepcopy(bad)
    good['steps'][1]['arguments']['group_by'] = []
    provider = FakeLLMProvider([bad, good])
    plan = Planner(provider).plan_v3('按 genres 统计数量，列出数量最多的前10组',
        {'primary': {'columns': [{'name':'movieid','data_type':'integer'}, {'name':'genres','data_type':'string'}]}},
        ConversationContext(conversation_id=1,user_id=1), task_id='scope', intent='DATA_ANALYSIS',
        config={'inputs':[binding], 'profiles':[], 'semantic_snapshot':[], 'semantic_version':0, 'depth':'STANDARD'},
        permissions=frozenset({Permission.READ_DATA}))
    assert plan.steps[1].arguments['group_by'] == []
    # Explicit within-group requests retain the established tool semantics.
    validate_top_n_scope(AnalysisPlanV3.model_validate(bad), '每组分别取前10组')
