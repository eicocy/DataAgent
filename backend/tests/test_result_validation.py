"""Real arithmetic and result publication regressions, independent of business fields."""
import pandas as pd
import pytest

from app.services.analysis_tools import DatasetTools


@pytest.mark.parametrize('values', [[1e308, 1e308], [2**63 - 1, 1], [float('inf'), 1]])
def test_invalid_arithmetic_is_rejected_before_publishing(values):
    tools = DatasetTools.from_frame(1, [{'amount': value} for value in values])
    with pytest.raises(ValueError):
        tools.execute('aggregate_data', {'metrics': [{'column': 'amount', 'aggregation': 'sum'}]}, call_id='total')
    assert 'total' not in tools.call_results
    assert 'total' not in tools.frame_results


def test_all_missing_aggregate_preserves_null_and_structured_warning():
    tools = DatasetTools.from_frame(1, [{'amount': None}, {'amount': None}])
    tools.frame['amount'] = pd.Series([float('nan'), float('nan')])
    result = tools.execute('aggregate_data', {'metrics': [{'column': 'amount', 'aggregation': 'sum'}]}, call_id='total')
    assert result.data['metric_values']['amount_sum'] is None
    assert any(warning.code == 'RESULT_MISSING_VALUES' for warning in result.warnings)
    assert any(warning.code == 'RESULT_NO_VALID_SAMPLES' for warning in result.warnings)


def test_description_single_sample_reports_undefined_spread():
    tools = DatasetTools.from_frame(1, [{'arbitrary': 12}])
    result = tools.execute('describe_data', {'columns': ['arbitrary']}, call_id='stats')
    assert result.data['rows'][0]['std'] is None
    assert any(warning.code == 'RESULT_INSUFFICIENT_SAMPLES' for warning in result.warnings)


def test_empty_filter_is_valid_but_explicit():
    tools = DatasetTools.from_frame(1, [{'amount': 1}])
    result = tools.execute('filter_data', {'conditions': [{'column': 'amount', 'operator': 'gt', 'value': 2}]}, call_id='empty')
    assert result.data['matched_count'] == 0
    assert any(warning.code == 'RESULT_EMPTY' for warning in result.warnings)


def test_integer_monthly_aggregation_cannot_wrap():
    tools = DatasetTools.from_frame(1, [{'day': '2026-01-01', 'segment': 'x', 'amount': value} for value in [2**63 - 1, 1]])
    with pytest.raises(ValueError):
        tools.execute('time_group_analysis', {'date_column': 'day', 'group_column': 'segment', 'value_column': 'amount'}, call_id='monthly')


def test_computation_overflow_blocks_dependent_step():
    from app.agent.executor import WorkflowExecutor
    from app.agent.schemas import ExecutionPlan
    from app.config import Settings
    tools = DatasetTools.from_frame(1, [{'amount': 1e308}, {'amount': 1e308}])
    plan = ExecutionPlan.model_validate({'intent': 'total', 'steps': [
        {'step_id': 'total', 'tool_name': 'aggregate_data', 'arguments': {'metrics': [{'column': 'amount', 'aggregation': 'sum'}]}},
        {'step_id': 'ordered', 'tool_name': 'sort_data', 'source_ref': 'total', 'depends_on': ['total'], 'arguments': {'sort_by': [{'column': 'amount_sum'}]}},
    ]})
    executor = WorkflowExecutor(tools, Settings(_env_file=None))
    report = executor.execute(plan, 'total')
    assert report.status == 'failed'
    assert executor.results == {}
    assert executor.calls[-1]['status'] == 'skipped'
def test_nullable_sql_integer_preserves_precision_and_detects_overflow():
    from app.execution.validators import ResultValidationError
    from types import SimpleNamespace
    from sqlalchemy import create_engine, text
    from app.services.datasets import DatasetService
    from app.services.analysis_tools import _aggregation
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE dataset_1 (value BIGINT)'))
        connection.execute(text('INSERT INTO dataset_1 VALUES (:value), (NULL), (1)'), {'value': 2**63 - 1})
    column = SimpleNamespace(name='value', data_type='integer')
    dataset = SimpleNamespace(id=1, projection_table='dataset_1')
    frame = DatasetService(None, engine).load_frame(dataset, [column])
    assert int(frame.value.iloc[0]) == 2**63 - 1
    with pytest.raises(ResultValidationError) as raised:
        _aggregation(frame.value, 'sum')
    assert raised.value.code == 'INTEGER_OVERFLOW'
    engine.dispose()


@pytest.mark.parametrize('data', ['invalid', {'columns': ['x', 'x'], 'rows': []}, {'columns': ['x'], 'rows': [{'other': 1}]}])
def test_structural_errors_have_safe_domain_code(data):
    from app.execution.validators import validate_result, ResultValidationError
    with pytest.raises(ResultValidationError) as error:
        validate_result(data)
    assert error.value.code == 'RESULT_SCHEMA_INVALID'
