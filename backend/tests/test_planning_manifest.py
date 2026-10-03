"""A model must receive complete schemas for the operations it plans."""
import json
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from app.agent.context import ContextBuilder, ConversationContext
from app.agent.model_adapter import ModelAdapter
from app.agent.providers import load_prompt
from app.analysis.models import Permission
from app.services.analysis_tools import model_tool_schemas


def test_chart_context_keeps_complete_plot_and_compute_schemas_within_budget():
    manifests = [item['function'] for item in model_tool_schemas(frozenset({Permission.READ_DATA}))]
    context = ConversationContext(conversation_id=1, user_id=1, current_intent='CHART_GENERATION')
    payload = ContextBuilder().build('按地区汇总并绘图', context,
        {'dataset_id': 1, 'dataset_version_id': 2, 'columns': [{'name': 'sales', 'data_type': 'float'}]}, manifests)
    assert len(json.dumps(payload, ensure_ascii=False)) <= 30000
    selected = {tool['name']: tool for tool in payload['tools']}
    for name in ('group_by_analysis', 'filter_data', 'generate_chart'):
        assert selected[name] == next(tool for tool in manifests if tool['name'] == name)


def test_context_keeps_registered_tools_used_by_previous_plan():
    manifests = [item['function'] for item in model_tool_schemas(frozenset({Permission.READ_DATA}))]
    context = ConversationContext(conversation_id=1, user_id=1, current_intent='CHART_GENERATION',
        previous_plan={'steps': [{'tool_name': 'weighted_average'}]})
    payload = ContextBuilder().build('换成柱状图', context, {'columns': []}, manifests)
    assert any(tool['name'] == 'weighted_average' for tool in payload['tools'])


def test_follow_up_can_introduce_new_analysis_families_with_complete_schemas():
    manifests = [item['function'] for item in model_tool_schemas(frozenset({Permission.READ_DATA}))]
    context = ConversationContext(conversation_id=1, user_id=1, current_intent='FOLLOW_UP_ANALYSIS',
        previous_plan={'steps': [{'tool_name': 'group_by_analysis'}]})
    payload = ContextBuilder().build('再分析销售额与利润的协方差', context,
        {'dataset_id': 1, 'dataset_version_id': 2, 'columns': []}, manifests)
    selected = {tool['name']: tool for tool in payload['tools']}
    for name in ('covariance', 'percentile', 'rolling_statistics', 'missing_value_analysis'):
        parameters = selected[name]['parameters']
        if '$ref' in parameters:
            parameters = payload['tool_parameter_schemas'][parameters['$ref'].split('/')[-1]]
        assert parameters == next(tool for tool in manifests if tool['name'] == name)['parameters']
    assert len(json.dumps(payload, ensure_ascii=False)) <= 60000
    assert {tool['name'] for tool in manifests} == set(selected)


def test_cleaning_manifest_matches_validator_policy_even_after_a_chart_plan():
    manifests = [item['function'] for item in model_tool_schemas(frozenset({Permission.READ_DATA}))]
    context = ConversationContext(conversation_id=1, user_id=1, current_intent='DATA_CLEANING',
        previous_plan={'steps': [{'tool_name': 'aggregate_data'}, {'tool_name': 'generate_chart'}]})
    payload = ContextBuilder().build('检查数据质量', context, {'columns': []}, manifests)
    assert {tool['name'] for tool in payload['tools']} == {
        'get_dataset_info', 'preview_data', 'dataset_overview', 'column_summary',
        'missing_value_analysis', 'duplicate_analysis',
        'constant_column_analysis', 'cardinality_analysis', 'invalid_numeric_analysis',
        'invalid_datetime_analysis', 'infinite_value_analysis', 'outlier_analysis'}


def test_adapter_preserves_essential_manifest_and_authorized_schema_when_history_is_long():
    class Model:
        def invoke(self, messages):
            self.payload = json.loads(messages[1].content)
            return AIMessage(content='ok')
    model = Model()
    settings = SimpleNamespace(max_model_calls=10, analysis_timeout_seconds=180)
    payload = {'question': 'plot', 'dataset': {'dataset_id': 1, 'dataset_version_id': 2,
        'columns': [{'name': f'field_{i}', 'data_type': 'number'} for i in range(200)]},
        'tools': [{'name': f'tool_{i}', 'parameters': {'description': 'x' * 1200}} for i in range(20)],
        'summary': 'history' * 10000}
    ModelAdapter(model, settings).invoke('plan', json.dumps(payload))
    assert model.payload['tools'] == payload['tools']
    assert model.payload['dataset'] == payload['dataset']
    assert model.payload['question'] == 'plot'


def test_planner_prompt_has_explicit_initial_state_and_source_contract():
    _, version, body = load_prompt('analysis_planner')
    assert version == 'v3'
    assert 'tool_parameter_schemas' in body
    assert 'result_ref' in body and 'PENDING' in body
    assert 'source_ref' in body and 'dataset' in body


def test_interpreter_prompt_requires_single_brace_fact_bindings():
    _, version, body = load_prompt('result_interpreter')
    assert version == 'v3'
    assert '{sales}' in body and 'Unused' in body
