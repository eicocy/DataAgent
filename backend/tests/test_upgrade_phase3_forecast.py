"""Forecast contracts use real frames/models; no database or model providers."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.errors import ToolError


def context(values, dates=None):
    frame = pd.DataFrame({'when': pd.date_range('2020-01-01', periods=len(values), freq='MS') if dates is None else dates, 'amount': values})
    valid = DatasetContext.from_frame(pd.DataFrame({'when': ['2020-01-01'], 'amount': [1.0]}), dataset_id=17, dataset_version=29)
    return replace(valid, frame=frame, source_ref='primary')


def forecast(ctx, **kwargs):
    return build_registry().execute('forecast', ctx, dict(time_column='when', target_column='amount', horizon=3, granularity='month', aggregation='sum', **kwargs))


def test_linear_trend_uses_real_validation_errors_and_preserves_source():
    registry = build_registry()
    assert registry.exists('forecast'), 'forecast must be a registered reusable typed tool'
    result = forecast(context(list(range(1, 37))))
    data = result.data
    assert data.kind == 'forecast'
    assert data.selected_model == 'linear_trend'
    assert [point.value for point in data.points] == pytest.approx([37, 38, 39])
    assert data.metrics.mae < 1e-9 and data.metrics.rmse < 1e-9
    assert data.baseline.metrics.mae > 0
    assert data.dataset_id == 17 and data.dataset_version == result.dataset_version == 29
    assert data.source_ref == 'primary'
    assert data.history_start == '2020-01-01T00:00:00' and data.history_end == '2022-12-01T00:00:00'
    assert data.frequency == 'MS' and data.horizon == 3
    assert len(data.folds) == 3 and len(data.candidates) == 5
    assert all(point.lower <= point.value <= point.upper for point in data.points)
    assert data.uncertainty.calibrated is False
    assert data.uncertainty.residual_count == 9


@pytest.mark.parametrize('value', [0, 7])
def test_constant_series_retains_naive_baseline_and_zero_mape_explanation(value):
    data = forecast(context([value] * 12)).data
    assert data.selected_model == 'naive'
    assert [p.value for p in data.points] == [value] * 3
    assert data.metrics.mae == data.metrics.rmse == 0
    assert data.metrics.mape == (None if value == 0 else 0)
    assert data.metrics.mape_coverage == (0 if value == 0 else 1)
    assert data.metrics.mape_explanation
    arima = next(c for c in data.candidates if c.model == 'arima')
    assert arima.status == 'skipped' and arima.error_code


def test_shared_expanding_folds_never_train_on_validation_values():
    original = forecast(context(list(range(1, 37)))).data
    changed = forecast(context(list(range(1, 34)) + [900, 901, 902])).data
    assert [(f.train_size, f.test_size) for f in original.folds] == [(27, 3), (30, 3), (33, 3)]
    assert all(f.train_end < f.test_start <= f.test_end for f in original.folds)
    for before, after in zip(original.candidates, changed.candidates):
        if before.status == after.status == 'succeeded':
            assert before.folds[0].predictions == pytest.approx(after.folds[0].predictions)
            assert before.folds[1].predictions == pytest.approx(after.folds[1].predictions)
            assert before.folds[2].predictions == pytest.approx(after.folds[2].predictions)
            assert [f.fold_id for f in before.folds] == [0, 1, 2]


def test_duplicate_periods_aggregate_with_declared_rule_and_unsorted_rows():
    dates = list(pd.date_range('2020-01-01', periods=12, freq='MS')) * 2
    data = forecast(context([2] * 12 + [4] * 12, dates)).data
    assert data.observation_count == 12 and data.input_row_count == 24
    assert [p.value for p in data.points] == [6] * 3
    mean = build_registry().execute('forecast', context([2] * 12 + [4] * 12, dates), dict(time_column='when',target_column='amount',horizon=1,granularity='month',aggregation='mean')).data
    assert mean.points[0].value == 3


@pytest.mark.parametrize('values, dates, code', [
    ([1] * 11, None, 'FORECAST_INSUFFICIENT_OBSERVATIONS'),
    ([1] * 12, list(pd.date_range('2020-01-01', periods=13, freq='MS').delete(5)), 'FORECAST_IRREGULAR_PERIODS'),
    ([1] * 11 + [None], None, 'FORECAST_MISSING_TARGET'),
    ([1] * 11 + [np.inf], None, 'FORECAST_NON_FINITE_TARGET'),
    ([1] * 11 + ['bad'], None, 'FORECAST_INVALID_TARGET'),
    ([True] * 12, None, 'FORECAST_INVALID_TARGET'),
    ([1] * 12, ['bad'] + ['2020-01-01'] * 11, 'FORECAST_INVALID_DATE'),
    ([1] * 12, [None] + ['2020-01-01'] * 11, 'FORECAST_INVALID_DATE'),
])
def test_invalid_history_returns_structured_error_without_forecast(values, dates, code):
    with pytest.raises(ToolError) as caught:
        forecast(context(values, dates))
    assert caught.value.structured()['code'] == code


@pytest.mark.parametrize('changes,code', [
    ({'target_column': 'unknown'}, 'COLUMN_NOT_FOUND'),
    ({'time_column': 'unknown'}, 'COLUMN_NOT_FOUND'),
    ({'horizon': 25}, 'TOOL_INPUT_INVALID'),
    ({'horizon': 0}, 'TOOL_INPUT_INVALID'),
    ({'granularity': 'hour'}, 'TOOL_INPUT_INVALID'),
    ({'aggregation': 'count'}, 'TOOL_INPUT_INVALID'),
])
def test_parameters_are_bounded_and_columns_validated(changes, code):
    parameters = dict(time_column='when',target_column='amount',horizon=3,granularity='month',aggregation='sum')
    parameters.update(changes)
    with pytest.raises(ToolError) as caught:
        build_registry().execute('forecast', context([1] * 36), parameters)
    assert caught.value.code == code


def test_large_horizon_requires_enough_history_for_same_horizon_backtests():
    with pytest.raises(ToolError, match='FORECAST_INSUFFICIENT_VALIDATION_HISTORY'):
        build_registry().execute('forecast', context([1] * 36), dict(time_column='when',target_column='amount',horizon=24,granularity='month',aggregation='sum'))


def test_arima_has_real_validation_metrics_when_history_supports_it():
    data = forecast(context(10 + np.sin(np.arange(48)) + np.arange(48) * .1)).data
    arima = next(c for c in data.candidates if c.model == 'arima')
    assert arima.status == 'succeeded'
    assert len(arima.folds) == 3 and arima.metrics.mae >= 0
    assert all(np.isfinite(p.value) for p in data.points)


@pytest.mark.parametrize('values', [[1 + 2j] * 12, list(pd.date_range('2020-01-01', periods=12))])
def test_non_real_targets_do_not_turn_into_fabricated_measurements(values):
    with pytest.raises(ToolError, match='FORECAST_INVALID_TARGET'):
        forecast(context(values))


def test_series_budget_rejects_without_silent_truncation():
    with pytest.raises(ToolError, match='FORECAST_HISTORY_BUDGET_EXCEEDED'):
        forecast(context([1] * 1001, pd.date_range('2020-01-01', periods=1001, freq='MS')))


@pytest.mark.parametrize('granularity, dates, next_time', [
    ('day', pd.date_range('2020-01-01', periods=12), '2020-01-13T00:00:00'),
    ('week', pd.date_range('2020-01-06', periods=12, freq='W-MON'), '2020-03-30T00:00:00'),
    ('quarter', pd.date_range('2020-01-01', periods=12, freq='QS'), '2023-01-01T00:00:00'),
    ('year', pd.date_range('2020-01-01', periods=12, freq='YS'), '2032-01-01T00:00:00'),
])
def test_supported_calendar_granularities_emit_correct_future_period(granularity, dates, next_time):
    data = build_registry().execute('forecast', context([1] * 12, dates), dict(time_column='when',target_column='amount',horizon=1,granularity=granularity,aggregation='sum')).data
    assert data.points[0].time == next_time


def test_real_candidate_failure_is_reported_and_naive_remains_available(monkeypatch):
    from app.analysis import forecast_tools
    real = forecast_tools._predict
    def fail_arima(model, train, horizon):
        if model == 'arima':
            raise ValueError('private library diagnostic')
        return real(model, train, horizon)
    monkeypatch.setattr(forecast_tools, '_predict', fail_arima)
    data = forecast(context(list(range(1, 37)))).data
    failed = next(c for c in data.candidates if c.model == 'arima')
    assert failed.status == 'failed' and failed.validation_error_code == 'FORECAST_MODEL_FIT_FAILED'
    assert failed.final_fit_error_code is None
    assert data.baseline.status == 'succeeded'
    assert data.selected_model == 'linear_trend'
    assert 'private library diagnostic' not in data.model_dump_json()


def test_typed_forecast_rejects_nonfinite_points_and_invalid_bounds():
    from app.analysis.models import ForecastResult
    from pydantic import ValidationError
    result = forecast(context([1] * 12)).data.model_dump()
    result['points'][0]['value'] = np.inf
    with pytest.raises(ValidationError):
        ForecastResult.model_validate(result)
    result['points'][0].update(value=1, lower=2, upper=3)
    with pytest.raises(ValidationError):
        ForecastResult.model_validate(result)


def test_final_refit_failure_keeps_validation_scores_and_selects_other_candidate(monkeypatch):
    from app.analysis import forecast_tools
    real = forecast_tools._predict
    def fail_final_trend(model, train, horizon):
        if model == 'linear_trend' and len(train) == 36:
            raise ValueError('fit failed')
        return real(model, train, horizon)
    monkeypatch.setattr(forecast_tools, '_predict', fail_final_trend)
    data = forecast(context(list(range(1, 37)))).data
    failed = next(c for c in data.candidates if c.model == 'linear_trend')
    assert failed.status == 'failed' and failed.final_fit_error_code == 'FORECAST_MODEL_FIT_FAILED'
    assert failed.validation_error_code is None and len(failed.folds) == 3
    assert failed.metrics.mae < 1e-9
    assert data.selected_model != 'linear_trend'


def test_zero_mape_coverage_uses_actual_validation_targets():
    data = forecast(context([0, 1] * 18)).data
    assert data.metrics.mape is not None
    assert data.metrics.mape_coverage == pytest.approx(5/9)


def test_maximum_horizon_is_not_truncated_when_history_is_sufficient():
    data = build_registry().execute('forecast', context(list(range(1, 101))), dict(time_column='when',target_column='amount',horizon=24,granularity='month',aggregation='sum')).data
    assert len(data.points) == 24
    assert data.points[-1].value == pytest.approx(124)
    assert data.uncertainty.residual_count == 72


@pytest.mark.parametrize('bad_date', ['NaT', '', 0, 1, True])
def test_parsed_missing_dates_are_rejected_before_grouping_can_drop_rows(bad_date):
    dates = list(pd.date_range('2020-01-01', periods=12, freq='MS')) + [bad_date]
    with pytest.raises(ToolError, match='FORECAST_INVALID_DATE'):
        forecast(context([1] * 12 + [1000], dates))
