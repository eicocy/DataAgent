"""Offline acceptance paths for the multi-step, follow-up and recovery contract."""
from types import SimpleNamespace

import pytest

from app.agent.context import ConversationContext, ContextBuilder
from app.agent.executor import WorkflowExecutor
from app.agent.interpreter import ResultInterpreter
from app.agent.planner import Planner
from app.agent.providers import FakeLLMProvider
from app.agent.schemas import AnalysisPlan
from app.analysis.models import Permission
from app.services.analysis_tools import DatasetTools
from app.execution.validators import ResultValidationError, validate_result


METADATA = {'dataset_id': 2, 'dataset_version_id': 3, 'row_count': 20,
            'columns': [{'name': 'region', 'data_type': 'string'},
                        {'name': 'product', 'data_type': 'string'},
                        {'name': 'day', 'data_type': 'datetime'},
                        {'name': 'sales', 'data_type': 'integer'}]}
PERMISSIONS = frozenset({Permission.READ_DATA})


def test_scenario_a_complex_question_produces_valid_dependency_graph():
    steps = [
        {'step_id': 'inspect', 'tool_name': 'get_dataset_info', 'arguments': {}},
        {'step_id': 'this_year', 'tool_name': 'filter_data', 'depends_on': ['inspect'],
         'arguments': {'conditions': [{'column': 'day', 'operator': 'between',
                                      'value': ['2026-01-01', '2026-12-31']}]}},
        {'step_id': 'trend', 'tool_name': 'time_group_analysis', 'depends_on': ['this_year'],
         'source_ref': 'this_year',
         'arguments': {'date_column': 'day', 'group_column': 'region', 'value_column': 'sales', 'months': 12}},
        {'step_id': 'growth', 'tool_name': 'growth_analysis', 'depends_on': ['this_year', 'trend'],
         'source_ref': 'this_year',
         'arguments': {'date_column': 'day', 'group_column': 'region', 'value_column': 'sales', 'months': 12, 'top_n': 1}},
        {'step_id': 'affected', 'tool_name': 'filter_data', 'depends_on': ['this_year', 'growth'],
         'source_ref': 'this_year', 'arguments': {'conditions': [{'column': 'region', 'operator': 'in',
         'value': {'$ref': 'growth', 'field': 'selected_groups'}}]}},
        {'step_id': 'product', 'tool_name': 'group_by_analysis', 'depends_on': ['affected'],
         'source_ref': 'affected', 'arguments': {'group_columns': ['product'], 'value_column': 'sales', 'aggregation': 'sum'}},
        {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['trend'],
         'source_ref': 'trend', 'arguments': {'type': 'line', 'dimension': 'month',
         'metrics': [{'field': 'sales_sum'}], 'title': '地区销售趋势'}},
    ]
    provider = FakeLLMProvider([{'task_id': '7', 'goal': '地区趋势及产品贡献', 'intent': 'TREND_ANALYSIS',
        'dataset_id': 2, 'dataset_version_id': 3, 'steps': steps,
        'expected_outputs': ['growth', 'product', 'chart']}])
    plan = Planner(provider).plan_v2('分析各地区销售趋势及下降产品', METADATA,
        ConversationContext(conversation_id=1, user_id=1), task_id='7',
        intent='TREND_ANALYSIS', permissions=PERMISSIONS)
    assert plan.status == 'READY'
    assert len(plan.steps) == 7
    assert plan.steps[-1].depends_on == ['trend']
    assert plan.steps[5].source_ref == 'affected'


def test_scenario_b_filter_follow_up_keeps_metric_time_and_invalidates_downstream_cache():
    context = ConversationContext(conversation_id=1, user_id=1, active_dataset_id=2,
        active_dataset_version_id=3, active_metrics=['sales'],
        active_time_range={'year': 2026}, previous_plan={'goal': '整体销售趋势'})
    payload = ContextBuilder().build('只看华南', context, METADATA, [])
    assert payload['metrics'] == ['sales'] and payload['time_range'] == {'year': 2026}
    assert payload['previous_plan']['goal'] == '整体销售趋势'
    tools = DatasetTools.from_frame(2, [{'region': '华南', 'sales': 10}])
    tools.reuse_steps = {
        'source': {'step': {'tool_name': 'preview_data', 'arguments': {}, 'depends_on': [],
                            'source_ref': 'dataset', 'required': True},
                   'artifact_id': 1, 'payload': {'data': {'rows': [{'region': '华南', 'sales': 10}]},
                                                   'rows': [{'region': '华南', 'sales': 10}]}},
        'filtered': {'step': {'tool_name': 'filter_data', 'arguments': {'conditions': []},
                              'depends_on': ['source'], 'source_ref': 'dataset', 'required': True},
                     'artifact_id': 2, 'payload': {'data': {}, 'rows': [{'region': '华南', 'sales': 10}]}},
    }
    plan = AnalysisPlan(task_id='8', goal='华南销售', intent='DATA_FILTER', dataset_id=2,
        dataset_version_id=3, steps=[
            {'step_id': 'source', 'tool_name': 'preview_data', 'arguments': {}},
            {'step_id': 'filtered', 'tool_name': 'filter_data', 'depends_on': ['source'],
             'arguments': {'conditions': [{'column': 'region', 'operator': 'eq', 'value': '华南'}]}}])
    runner = WorkflowExecutor(tools, SimpleNamespace(analysis_timeout_seconds=20,
        max_tool_attempts=20, max_retries_per_step=2))
    runner._reuse_completed(plan)
    assert set(runner.results) == {'source'}
    assert plan.steps[0].result_ref == 'artifact:1'


def test_scenario_d_interpreter_uses_tool_fact_and_rejects_invented_number():
    results = {'product': {'rows': [{'product': 'A', 'sales_sum': 12}]}}
    provider = FakeLLMProvider([{'template': '产品 A 的销售额为 {amount}。',
        'facts': [{'key': 'amount', 'step_id': 'product', 'path': ['rows', 0, 'sales_sum']}],
        'evidence_refs': ['product']}])
    answer, findings = ResultInterpreter(provider).interpret(question='为什么下降',
        goal='产品贡献', results=results, incomplete_steps=[])
    assert '12' in answer and findings[0]['reference']['path'] == ['rows', 0, 'sales_sum']
    bad = FakeLLMProvider([{'template': '下降了 18%，产品 A 的销售额为 {amount}。',
        'facts': [{'key': 'amount', 'step_id': 'product', 'path': ['rows', 0, 'sales_sum']}],
        'evidence_refs': ['product']}])
    with pytest.raises(ValueError, match='Unbound numeric assertion'):
        ResultInterpreter(bad).interpret(question='为什么下降', goal='产品贡献',
            results=results, incomplete_steps=[])


def test_scenario_e_replan_repairs_failed_path_and_keeps_completed_evidence():
    tools = DatasetTools.from_frame(2, [{'sales': 10}, {'sales': 20}])
    tools.model_metadata = {'dataset_id': 2, 'dataset_version_id': 3, 'row_count': 2,
        'columns': [{'name': 'sales', 'data_type': 'integer'}]}
    tools.conversation_state = ConversationContext(conversation_id=1, user_id=1)
    original_execute = tools.execute
    def execute(name, args, **kwargs):
        if name == 'aggregate_data' and args['metrics'][0]['column'] == 'alias':
            raise ValueError('bad alias')
        return original_execute(name, args, **kwargs)
    tools.execute = execute
    plan = AnalysisPlan(task_id='9', goal='销售额', intent='DATA_AGGREGATION', dataset_id=2,
        dataset_version_id=3, steps=[
        {'step_id': 'source', 'tool_name': 'preview_data', 'arguments': {}},
        {'step_id': 'total', 'tool_name': 'aggregate_data', 'depends_on': ['source'],
         'arguments': {'metrics': [{'column': 'alias', 'aggregation': 'sum'}]}}], expected_outputs=['total'])
    provider = FakeLLMProvider([
        {'arguments': {'metrics': [{'column': 'alias', 'aggregation': 'sum'}]}},
        {'arguments': {'metrics': [{'column': 'alias', 'aggregation': 'sum'}]}},
        {'task_id': '9', 'goal': '销售额', 'intent': 'DATA_AGGREGATION', 'dataset_id': 2,
         'dataset_version_id': 3, 'steps': [
         {'step_id': 'source', 'tool_name': 'preview_data', 'arguments': {}},
         {'step_id': 'corrected_total', 'tool_name': 'aggregate_data', 'depends_on': ['source'],
         'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}], 'expected_outputs': ['corrected_total']},
        {'template': '销售额为 {total}。', 'facts': [{'key': 'total', 'step_id': 'corrected_total',
          'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['corrected_total']},
    ])
    settings = SimpleNamespace(analysis_timeout_seconds=20, max_tool_attempts=20,
        max_retries_per_step=2, max_replans=2, max_plan_steps=12)
    runner = WorkflowExecutor(tools, settings, adapter=provider)
    report = runner.execute(plan, '总销售额')
    assert runner.replanned and report.status == 'succeeded'
    assert [call['status'] for call in runner.calls] == ['succeeded', 'failed', 'failed', 'failed', 'succeeded']
    assert [call['step_id'] for call in runner.calls].count('source') == 1
    assert report.answer == '销售额为 30。'


def test_result_validator_rejects_empty_chart_as_recoverable():
    with pytest.raises(ResultValidationError) as raised:
        validate_result({'type': 'bar', 'dimension': {'type': 'category'}, 'series': []},
                        result_type='generate_chart')
    assert raised.value.code == 'CHART_EMPTY' and raised.value.recoverable
