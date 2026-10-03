import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from langchain_core.messages import AIMessage

from app.agent.planner import Planner
from app.agent.executor import WorkflowExecutor
from app.agent.schemas import ExecutionPlan
from app.config import Settings
from app.services.analysis_tools import DatasetTools


def test_context_budget_applies_to_large_cells_and_nested_metadata():
    from app.agent.executor import clip_context
    value = {"rows": [{"x": "龙" * 40000}] * 300, "metadata": {"description": "a" * 50000}}
    clipped = clip_context(value)
    assert len(json.dumps(clipped, ensure_ascii=False, default=str)) <= 30000
    assert value["rows"][0]["x"] == "龙" * 40000


def test_chart_request_cannot_omit_required_chart():
    payload = plan([total_step()])
    with pytest.raises(ValueError, match="PLAN_INVALID"):
        Planner(Adapter([payload, payload])).plan("生成趋势图", {})


class Adapter:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.settings = Settings()
        self.requests = []

    def invoke(self, prompt, payload, schema, name):
        self.requests.append((name, json.loads(payload)))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return AIMessage(content='', tool_calls=[{'name': name, 'args': response, 'id': 'reply'}])


def plan(steps):
    return {'intent': 'Sales', 'steps': steps}


def total_step(**changes):
    return {'step_id': 'total', 'tool_name': 'aggregate_data', 'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}, **changes}


def test_planner_repairs_invalid_static_tool_arguments_once():
    bad = plan([total_step(arguments={'metrics': [{'column': 'sales', 'aggregation': 'execute_python'}]})])
    adapter = Adapter([bad, plan([total_step()])])
    actual = Planner(adapter).plan('Sales', {})
    assert actual.steps[0].arguments['metrics'][0]['aggregation'] == 'sum'
    assert len(adapter.requests) == 2


def test_plan_correction_identifies_extra_step_fields_without_echoing_values():
    bad = plan([total_step(title='private value must never be included in validation feedback')])
    adapter = Adapter([bad, plan([total_step()])])
    Planner(adapter).plan('Sales', {})
    correction = adapter.requests[1][1]['correction']
    assert isinstance(correction, dict)
    assert correction['errors'] == [{'path': 'steps.0.title', 'type': 'extra_forbidden'}]
    assert 'private value' not in json.dumps(correction)


def test_plan_correction_distinguishes_invalid_tool_json():
    class MalformedAdapter(Adapter):
        def invoke(self, prompt, payload, schema, name):
            if not self.requests:
                self.requests.append((name, json.loads(payload)))
                return AIMessage(content='', invalid_tool_calls=[{'name': name, 'args': '{broken', 'id': 'bad', 'error': 'invalid JSON'}])
            return super().invoke(prompt, payload, schema, name)
    adapter = MalformedAdapter([plan([total_step()])])
    Planner(adapter).plan('Sales', {})
    assert adapter.requests[1][1]['correction']['code'] == 'PLAN_ARGUMENTS_INVALID_JSON'


def test_bar_chart_request_requires_a_chart_step():
    payload = plan([total_step()])
    with pytest.raises(ValueError, match='PLAN_INVALID'):
        Planner(Adapter([payload, payload])).plan('按地区汇总销售额，并生成柱状图', {})


def test_planner_rejects_undeclared_dynamic_dependency():
    invalid = plan([total_step(), {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {'type': 'bar', 'dimension': 'sales_sum', 'metrics': [{'field': 'sales_sum'}], 'title': 'Sales', 'selected_groups': {'$ref': 'missing', 'field': 'selected_groups'}}}])
    with pytest.raises(ValueError, match='PLAN_INVALID'):
        Planner(Adapter([invalid, invalid])).plan('Sales', {})


def test_six_month_workflow_dynamic_growth_winners_and_missing_chart_points():
    tools = DatasetTools.from_frame(1, [{'day': f'2026-{month:02}-01', 'product': product, 'sales': amount} for product, values in [('A', [10, 20, 30]), ('B', [20, 25, 30]), ('C', [0, 10, 90])] for month, amount in zip([1, 3, 6], values)])
    payload = plan([
        {'step_id': 'monthly', 'tool_name': 'time_group_analysis', 'arguments': {'date_column': 'day', 'group_column': 'product', 'value_column': 'sales'}},
        {'step_id': 'growth', 'tool_name': 'growth_analysis', 'arguments': {'date_column': 'day', 'group_column': 'product', 'value_column': 'sales_sum'}, 'depends_on': ['monthly'], 'source_ref': 'monthly'},
        {'step_id': 'chart', 'tool_name': 'generate_chart', 'arguments': {'type': 'line', 'dimension': 'day', 'group_column': 'product', 'metrics': [{'field': 'sales_sum'}], 'title': 'Trend', 'selected_groups': {'$ref': 'growth', 'field': 'selected_groups'}}, 'depends_on': ['monthly', 'growth'], 'source_ref': 'monthly'},
    ])
    adapter = Adapter([payload, {'template': 'A grew {rate}.', 'facts': [{'key': 'rate', 'step_id': 'growth', 'path': ['rows', 0, 'growth_rate'], 'format': 'percent'}], 'evidence_refs': ['growth', 'chart']}])
    valid = Planner(adapter).plan('Growth', {})
    result = WorkflowExecutor(tools, adapter.settings, adapter).execute(valid, 'Growth')
    assert result.status == 'succeeded'
    assert result.tables[1]['rows'][0]['growth_rate'] == 2
    assert [series['name'] for series in result.charts[0]['series']] == ['A', 'B']
    assert result.charts[0]['series'][0]['data'][1]['value'] is None


def test_executor_corrects_bad_field_once_preserving_real_result():
    tools = DatasetTools.from_frame(1, [{'sales': 10}, {'sales': 20}])
    bad = ExecutionPlan.model_validate(plan([total_step(arguments={'metrics': [{'column': 'wrong', 'aggregation': 'sum'}]})]))
    adapter = Adapter([{'arguments': {'metrics': [{'column': 'sales', 'aggregation': 'sum'}]}}, {'template': '{value}', 'facts': [{'key': 'value', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']}])
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    result = executor.execute(bad, 'Sales')
    assert result.status == 'succeeded'
    assert executor.results['total']['metric_values']['sales_sum'] == 30
    assert [call['status'] for call in executor.calls] == ['failed', 'succeeded']
    assert [call['attempt'] for call in executor.calls] == [1, 2]
    assert executor.final_plan.steps[0].arguments['metrics'][0]['column'] == 'sales'


def test_executor_one_replan_does_not_rerun_successful_compute():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    chart = {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {'type': 'bar', 'dimension': 'missing', 'metrics': [{'field': 'sales_sum'}], 'title': 'Sales'}}
    repaired = {**chart, 'arguments': {**chart['arguments'], 'dimension': 'sales_sum'}}
    adapter = Adapter([{'arguments': chart['arguments']}, plan([total_step(), repaired]), {'template': '{value}', 'facts': [{'key': 'value', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total', 'chart']}])
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    result = executor.execute(ExecutionPlan.model_validate(plan([total_step(), chart])), 'Sales')
    assert result.status == 'succeeded'
    assert len([call for call in executor.calls if call['step_id'] == 'total']) == 1
    assert len([request for request in adapter.requests if request[0] == 'submit_execution_plan']) == 1


def test_failed_required_chart_is_partial_when_budget_stops_retries():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    chart = {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {'type': 'bar', 'dimension': 'missing', 'metrics': [{'field': 'sales_sum'}], 'title': 'Sales'}}
    adapter = Adapter([{'template': '{value}', 'facts': [{'key': 'value', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']}])
    adapter.settings.max_tool_attempts = 2
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    report = executor.execute(ExecutionPlan.model_validate(plan([total_step(), chart])), 'Sales')
    assert report.status == 'partial'
    assert report.incomplete_steps == ['chart']
    assert executor.attempts == 2


def test_replan_cannot_remove_chart_completion_by_changing_tool():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    chart = {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {'type': 'bar', 'dimension': 'missing', 'metrics': [{'field': 'sales_sum'}], 'title': 'Sales'}}
    replacement = {'step_id': 'chart', 'tool_name': 'preview_data', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {}}
    adapter = Adapter([{'arguments': chart['arguments']}, plan([total_step(), replacement]), {'template': '{value}', 'facts': [{'key': 'value', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']}])
    result = WorkflowExecutor(tools, adapter.settings, adapter).execute(ExecutionPlan.model_validate(plan([total_step(), chart])), 'Chart sales')
    assert result.status == 'partial'
    assert result.incomplete_steps == ['chart']


def test_storage_failure_never_requests_paid_recomputation():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    adapter = Adapter([])

    def storage(event, payload):
        if event == 'result':
            raise ValueError('artifact budget exceeded')

    executor = WorkflowExecutor(tools, adapter.settings, adapter, storage)
    report = executor.execute(ExecutionPlan.model_validate(plan([total_step()])), 'Sales')
    assert report.status == 'failed'
    assert executor.attempts == 1
    assert adapter.requests == []


def test_unavailable_dynamic_field_fails_without_exposing_exception():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    steps = [total_step(), {'step_id': 'chart', 'tool_name': 'generate_chart', 'depends_on': ['total'], 'source_ref': 'total', 'arguments': {'type': 'bar', 'dimension': 'sales_sum', 'metrics': [{'field': 'sales_sum'}], 'title': 'Sales', 'selected_groups': {'$ref': 'total', 'field': 'missing'}}}]
    executor = WorkflowExecutor(tools, Settings(max_tool_attempts=2))
    report = executor.execute(ExecutionPlan.model_validate(plan(steps)), 'Sales')
    assert report.status == 'partial'
    assert executor.calls[-1]['error_code'] == 'TOOL_EXECUTION_FAILED'
    assert 'missing' not in executor.calls[-1]['result_summary']


def test_repeated_invalid_step_uses_one_correction_and_one_replan_only():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    bad = total_step(arguments={'metrics': [{'column': 'wrong', 'aggregation': 'sum'}]})
    adapter = Adapter([{'arguments': bad['arguments']}, plan([bad])])
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    result = executor.execute(ExecutionPlan.model_validate(plan([bad])), 'Sales')
    assert result.status == 'failed'
    assert executor.attempts == 3
    assert [request[0] for request in adapter.requests] == ['submit_step_correction', 'submit_execution_plan']


def test_tool_attempt_budget_blocks_later_steps_and_model_recovery():
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    adapter = Adapter([{'template': '{value}', 'facts': [{'key': 'value', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total']}])
    adapter.settings.max_tool_attempts = 1
    second = total_step(step_id='again')
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    result = executor.execute(ExecutionPlan.model_validate(plan([total_step(), second])), 'Sales')
    assert result.status == 'partial'
    assert result.incomplete_steps == ['again']
    assert executor.calls[-1]['status'] == 'skipped'
    assert [request[0] for request in adapter.requests] == ['submit_final_report']
