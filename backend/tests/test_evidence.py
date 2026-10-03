import pytest
from app.execution.evidence import ReportContent, render_report
from app.agent.executor import WorkflowExecutor
from app.agent.schemas import ExecutionPlan
from app.services.analysis_tools import DatasetTools
from test_planner import Adapter, plan, total_step


def report(template='{total}', **changes):
    return {'template': template, 'facts': [{'key': 'total', 'step_id': 'total', 'path': ['metric_values', 'sales_sum']}], 'evidence_refs': ['total'], **changes}


def test_server_uses_real_value():
    assert render_report(ReportContent.model_validate(report()), {'total': {'metric_values': {'sales_sum': 30}}}) == '30'


@pytest.mark.parametrize('payload', [report('合计999999，{total}'), report('合计九，{total}'), report('合计叁拾，{total}'), report('合计⑨，{total}'), report(facts=[{'key': 'total', 'step_id': 'absent', 'path': ['x']}]), report(facts=[{'key': 'total', 'step_id': 'total', 'path': ['x.__class__']}])])
def test_invalid_summary_keeps_real_computation(payload):
    adapter = Adapter([payload])
    tools = DatasetTools.from_frame(1, [{'sales': 10}, {'sales': 20}])
    result = WorkflowExecutor(tools, adapter.settings, adapter).execute(ExecutionPlan.model_validate(plan([total_step()])), '合计')
    assert result.status == 'partial'
    assert result.answer is None
    assert result.tables[0]['metric_values']['sales_sum'] == 30
    assert result.warnings


def test_percent_rounding_and_digit_label_explicit_context():
    content = ReportContent(template='{label}：{rate}', facts=[{'key': 'label', 'step_id': 's', 'path': ['label'], 'format': 'text'}, {'key': 'rate', 'step_id': 's', 'path': ['rate'], 'format': 'percent', 'decimals': 2}], evidence_refs=['s'])
    assert render_report(content, {'s': {'label': '2026-01 产品001', 'rate': 0.123456}}) == '2026-01 产品001：12.35%'
    assert render_report(ReportContent.model_validate(report('进一步核验，一共{total}')), {'total': {'metric_values': {'sales_sum': 30}}}) == '进一步核验，一共30'


def test_executor_renders_bound_summary():
    adapter = Adapter([report('合计为{total}')])
    result = WorkflowExecutor(DatasetTools.from_frame(1, [{'sales': 30}]), adapter.settings, adapter).execute(ExecutionPlan.model_validate(plan([total_step()])), '合计')
    assert result.status == 'succeeded'
    assert result.answer == '合计为30'
    assert result.findings[0]['reference']['path'] == ['metric_values', 'sales_sum']


def test_raw_filtered_samples_are_not_sent_to_model():
    adapter = Adapter([report()])
    tools = DatasetTools.from_frame(1, [{'sales': 30, 'label': 'private-example'}])
    steps = [{'step_id': 'filtered', 'tool_name': 'filter_data', 'arguments': {'conditions': [{'column': 'sales', 'operator': 'eq', 'value': 30}]}}, total_step(source_ref='filtered', depends_on=['filtered'])]
    result = WorkflowExecutor(tools, adapter.settings, adapter).execute(ExecutionPlan.model_validate(plan(steps)), '合计')
    assert result.status == 'succeeded'
    assert 'private-example' not in str(adapter.requests)
    assert 'preview_rows' in tools.call_results['filtered']


def test_sql_aggregate_remains_visible_and_raw_sql_rows_are_private():
    from sqlalchemy import create_engine, text
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE dataset_1 (sales BIGINT)'))
        connection.execute(text('INSERT INTO dataset_1 VALUES (10), (20)'))
    tools = DatasetTools.from_frame(1, [{'sales': 10}, {'sales': 20}])
    tools.readonly_bind = engine
    adapter = Adapter([report(facts=[{'key': 'total', 'step_id': 'total', 'path': ['rows', 0, 'total']}])])
    step = {'step_id': 'total', 'tool_name': 'sql_query', 'arguments': {'query': 'SELECT SUM(sales) AS total FROM dataset_1'}}
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    result = executor.execute(ExecutionPlan.model_validate(plan([step])), '合计')
    assert result.answer == '30'
    assert result.status == 'succeeded'
    tools.execute('sql_query', {'query': 'SELECT sales FROM dataset_1'}, call_id='raw')
    executor.calls.append({'step_id': 'raw', 'tool_name': 'sql_query', 'parameters': {'query': 'SELECT sales FROM dataset_1'}, 'status': 'succeeded'})
    executor.results['raw'] = tools.call_results['raw']
    assert 'rows' not in executor._model_results()['raw']
    engine.dispose()


def test_grouped_sql_labels_and_decimal_metrics_keep_typed_evidence():
    from decimal import Decimal
    import pandas as pd
    adapter = Adapter([])
    tools = DatasetTools.from_frame(1, [{'sales': 10}])
    executor = WorkflowExecutor(tools, adapter.settings, adapter)
    executor.calls = [{'step_id': 'group', 'tool_name': 'sql_query', 'parameters': {'query': 'SELECT category, SUM(amount) AS total FROM dataset_1 GROUP BY category'}, 'status': 'succeeded'}]
    executor.results = {'group': {'rows': [{'category': 'A001', 'total': '12.25'}]}}
    tools.frame_results['group'] = pd.DataFrame([{'category': 'A001', 'total': Decimal('12.25')}])
    visible = executor._model_results()
    content = ReportContent(template='{label}:{total}', facts=[{'key': 'label', 'step_id': 'group', 'path': ['rows', 0, 'category'], 'format': 'text'}, {'key': 'total', 'step_id': 'group', 'path': ['rows', 0, 'total']}], evidence_refs=['group'])
    assert render_report(content, visible) == 'A001:12.25'
    executor.calls[0]['parameters']['query'] = 'SELECT COALESCE(SUM(amount), category) AS total FROM dataset_1'
    assert 'rows' not in executor._model_results()['group']
