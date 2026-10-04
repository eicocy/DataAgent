"""Generic profiling without value samples or mutations of the input frame."""
import math
import re
from datetime import date, datetime
import numpy as np
import pandas as pd
from app.analysis.precision import decimal_series
from app.datasets.schemas import DatasetSchema, DatasetProfile, SchemaColumn, ColumnProfile, NumericStatistics


def build_profile(frame: pd.DataFrame) -> tuple[DatasetSchema, DatasetProfile]:
    columns, profiles = [], []
    labels = frame.attrs.get('original_columns', list(frame.columns))
    count = len(frame)
    for position, name in enumerate(frame.columns):
        series = frame[name]
        values = series.dropna()
        identifier = bool(re.search(r'(^|_)(id|code|identifier)($|_)', str(name), re.I) or any(part in str(labels[position]) for part in ('编号', '编码')))
        leading_zero = not values.empty and values.astype(str).str.fullmatch(r'0\d+').any()
        exact = decimal_series(series)
        numeric = exact or (pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype))
        if identifier or leading_zero:
            semantic, role, reason = 'Identifier', 'Identifier', 'identifier label or preserved leading zero'
        elif values.empty:
            semantic, role, reason = 'Unknown', 'Dimension', 'no valid samples'
        elif pd.api.types.is_bool_dtype(series.dtype):
            semantic, role, reason = 'Boolean', 'Dimension', 'boolean dtype'
        elif pd.api.types.is_datetime64_any_dtype(series.dtype) or values.map(lambda value: isinstance(value, (date, datetime))).all():
            semantic, role, reason = 'Datetime', 'TimeDimension', 'date dtype or date objects'
        elif numeric:
            semantic, role, reason = 'Numeric', 'Metric', 'numeric dtype'
        else:
            semantic = 'Categorical' if values.nunique() <= max(20, count * .2) else 'Text'
            role, reason = 'Dimension', 'text cardinality'
        storage = 'boolean' if pd.api.types.is_bool_dtype(series.dtype) else 'integer' if pd.api.types.is_integer_dtype(series.dtype) else 'decimal' if numeric else 'datetime' if pd.api.types.is_datetime64_any_dtype(series.dtype) else 'date' if not values.empty and values.map(lambda v:isinstance(v,date) and not isinstance(v,datetime)).all() else 'string'
        columns.append(SchemaColumn(name=str(name), original_name=str(labels[position]), dtype=str(series.dtype), storage_type=storage, semantic_type=semantic, role=role, confidence=.9 if identifier or leading_zero else .8, inference_reason=reason))
        stats, non_finite = None, 0
        if numeric and not exact:
            finite = values[np.isfinite(values.astype(float))]
            non_finite = len(values) - len(finite)
            if finite.empty:
                stats = NumericStatistics(status='no_valid_samples', valid_count=0)
            else:
                with np.errstate(over='ignore', invalid='ignore'):
                    raw = {'mean': finite.mean(), 'minimum': finite.min(), 'maximum': finite.max(), 'median': finite.median(), 'std': finite.std() if len(finite) > 1 else None}
                    quantiles = {str(q): finite.quantile(q) for q in (.25, .5, .75)}
                overflow = any(value is not None and not math.isfinite(float(value)) for value in [*raw.values(), *quantiles.values()])
                safe = lambda value: float(value) if value is not None and math.isfinite(float(value)) else None
                stats = NumericStatistics(status='overflow' if overflow else 'valid', valid_count=len(finite), **{key: safe(value) for key, value in raw.items()}, quantiles={key: safe(value) for key, value in quantiles.items()})
        missing, unique = int(series.isna().sum()), int(series.nunique(dropna=True))
        profiles.append(ColumnProfile(name=str(name), missing_count=missing, missing_rate=missing / count if count else 0, unique_count=unique, unique_rate=unique / count if count else 0, non_finite_count=non_finite, numeric=stats))
    return DatasetSchema(columns=columns), DatasetProfile(row_count=count, column_count=len(frame.columns), memory_bytes=int(frame.memory_usage(deep=True).sum()), columns=profiles, warnings=frame.attrs.get('quality_warnings', []))


def model_summary(schema: DatasetSchema, profile: DatasetProfile) -> dict:
    """Value-free model view; original rows and category samples are never included."""
    return {'schema_version': schema.schema_version, 'row_count': profile.row_count, 'columns': [{'name': column.name, 'label': column.original_name, 'semantic_type': column.semantic_type, 'role': column.role, 'missing_count': item.missing_count, 'non_finite_count': item.non_finite_count} for column, item in zip(schema.columns, profile.columns)]}
