"""Validate numerical values before serialization can erase their provenance."""
from decimal import Decimal
import math
from numbers import Integral, Real
from typing import Mapping

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError


class ResultValidationError(ValueError):
    """A non-retryable data/calculation failure with a safe public code."""

    def __init__(self, code: str, recoverable: bool = False):
        super().__init__(code)
        self.code = code
        self.recoverable = recoverable
        self.public_message = '计算结果未通过可靠性校验，请检查数值范围及输入数据'


class ResultWarning(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str
    message: str
    count: int = 0


def validate_numeric_series(series: pd.Series) -> None:
    """Missing values are legitimate; infinite numeric inputs are not."""
    for value in series.dropna():
        if isinstance(value, (Real, Decimal)) and not math.isfinite(value):
            raise ResultValidationError('INPUT_NON_FINITE')


def checked_integer_sum(series: pd.Series) -> int | None:
    """Sum with Python integers, rejecting overflow of the signed SQL contract."""
    values = series.dropna()
    if values.empty:
        return None
    total = sum(int(value) for value in values)
    if not -(2**63) <= total < 2**63:
        raise ResultValidationError('INTEGER_OVERFLOW')
    return total


def validate_value(value: object, *, allow_missing: bool = True) -> int:
    """Recursively reject non-finite values, returning the missing value count."""
    if value is None or value is pd.NA or value is pd.NaT:
        return 1
    if isinstance(value, Mapping):
        return sum(validate_value(item, allow_missing=allow_missing) for item in value.values())
    if isinstance(value, (list, tuple)):
        return sum(validate_value(item, allow_missing=allow_missing) for item in value)
    if isinstance(value, (Real, Decimal)) and not isinstance(value, (bool, Integral)):
        if math.isnan(value) and allow_missing:
            return 1
        if not math.isfinite(value):
            raise ResultValidationError('RESULT_NON_FINITE')
    return 0


def _typed_missing_statistics(data: dict) -> int | None:
    """Count statistical nulls only for complete, validated Phase 3 contracts.

    Optional provenance/diagnostics are not statistics. Unrecognized or invalid
    direct-call shapes retain the generic recursive missing-value behavior.
    """
    from app.analysis.models import ForecastResult, KPIResult, PeriodComparisonResult, ContributionResult
    if not isinstance(data.get('kind'), str):
        return None
    schema = {'forecast': ForecastResult, 'kpi': KPIResult,
              'period_comparison': PeriodComparisonResult, 'contribution': ContributionResult}.get(data.get('kind'))
    if schema is None:
        return None
    try:
        result = schema.model_validate(data)
    except ValidationError:
        return None
    if isinstance(result, ForecastResult):
        missing = validate_value(result.metrics.model_dump())
        for candidate in [result.baseline, *result.candidates]:
            # Failed/skipped models have no score by contract, not a missing
            # selected statistic. Any available fold scores still participate.
            if candidate.metrics is not None:
                missing += validate_value(candidate.metrics.model_dump())
            for fold in candidate.folds:
                missing += validate_value(fold.metrics.model_dump())
                missing += validate_value(fold.predictions)
        return missing + validate_value([point.model_dump() for point in result.points])
    if isinstance(result, KPIResult):
        return sum(validate_value(metric.value) for metric in result.metrics.values())
    missing = sum(validate_value(getattr(result, key).value)
                  for key in ('current', 'previous', 'delta', 'growth_rate'))
    if isinstance(result, ContributionResult):
        missing += validate_value([group.model_dump() for group in result.groups])
    return missing


def validate_result(data: dict, frame: pd.DataFrame | None = None, *, result_type: str | None = None, parameters: dict | None = None) -> list[ResultWarning]:
    """Validate structured results and full frames before they are published."""
    if not isinstance(data, dict):
        raise ResultValidationError('RESULT_SCHEMA_INVALID')
    missing = validate_value(data)
    statistical_missing = _typed_missing_statistics(data)
    if statistical_missing is not None:
        missing = statistical_missing
    if frame is not None:
        for column in frame.columns:
            validate_numeric_series(frame[column])
        missing = max(missing, int(frame.isna().sum().sum()))
    notes = []
    if missing:
        notes.append(ResultWarning(code='RESULT_MISSING_VALUES', message='结果包含缺失或无法定义的统计值，未补零', count=missing))
    if frame is not None and frame.empty:
        notes.append(ResultWarning(code='RESULT_EMPTY', message='没有符合条件的数据，空结果不支持确定性结论'))
    if result_type == 'generate_chart':
        series = data.get('series')
        if not isinstance(series, list) or not series or not any(item.get('data') for item in series if isinstance(item, dict)):
            raise ResultValidationError('CHART_EMPTY', recoverable=True)
        if data.get('type') == 'line' and (data.get('dimension') or {}).get('type') not in {'time', 'datetime', 'date'}:
            raise ResultValidationError('CHART_TIME_AXIS_INVALID', recoverable=True)
    if result_type in {'time_group_analysis', 'growth_analysis'} and frame is not None and not frame.empty:
        if not any(pd.api.types.is_datetime64_any_dtype(frame[column]) or 'date' in str(column).lower() or 'time' in str(column).lower()
                   for column in frame.columns):
            notes.append(ResultWarning(code='TIME_AXIS_UNVERIFIED', message='时间序列结果需核对时间字段的解析情况'))
    if result_type == 'aggregate_data':
        metric_values = data.get('metric_values', {})
        empty_metrics = 0
        if metric_values:
            for metric in (parameters or {}).get('metrics', []):
                key = f"{metric['column']}_{metric['aggregation']}"
                if metric['aggregation'] not in {'count', 'count_distinct'} and metric_values.get(key) is None:
                    empty_metrics += 1
        if empty_metrics:
            notes.append(ResultWarning(code='RESULT_NO_VALID_SAMPLES', message='部分指标没有有效样本，聚合结果保留为空', count=empty_metrics))
    elif result_type == 'describe_data':
        rows = data.get('rows', [])
        empty = sum(row.get('count') == 0 for row in rows)
        insufficient = sum(row.get('count') == 1 and row.get('std') is None for row in rows)
        if empty:
            notes.append(ResultWarning(code='RESULT_NO_VALID_SAMPLES', message='部分描述统计没有有效样本', count=empty))
        if insufficient:
            notes.append(ResultWarning(code='RESULT_INSUFFICIENT_SAMPLES', message='部分字段只有一个有效样本，标准差无法定义', count=insufficient))
    columns = data.get('columns')
    rows = data.get('rows')
    if columns is not None and rows is not None:
        if not isinstance(columns, list) or not isinstance(rows, list) or any(not isinstance(column, str) for column in columns) or len(columns) != len(set(columns)):
            raise ResultValidationError('RESULT_SCHEMA_INVALID')
        if any(not isinstance(row, dict) or set(row) != set(columns) for row in rows):
            raise ResultValidationError('RESULT_SCHEMA_INVALID')
    return notes
