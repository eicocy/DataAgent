"""Shared deterministic operations used by canonical and compatibility tools."""
from datetime import date, datetime
import pandas as pd
from app.analysis.errors import ToolInputError, DatasetTypeError
from app.execution.validators import checked_integer_sum, validate_numeric_series


def aggregate_series(series, operation, ddof=1):
    operation = getattr(operation, 'value', operation)
    if pd.api.types.is_numeric_dtype(series.dtype):validate_numeric_series(series)
    if operation in {'count','nunique'}:
        return int(series.count() if operation=='count' else series.nunique(dropna=True))
    values = series.dropna()
    if operation in {'first','last'}:
        return None if values.empty else values.iloc[0 if operation=='first' else -1]
    if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        raise DatasetTypeError('NUMERIC_COLUMN_REQUIRED')
    validate_numeric_series(series)
    if values.empty or operation in {'std','var'} and len(values) <= ddof:
        return None
    if operation == 'sum' and pd.api.types.is_integer_dtype(series.dtype):
        return checked_integer_sum(series)
    methods = {'sum':lambda:series.sum(min_count=1), 'mean':series.mean, 'median':series.median,
               'min':series.min,'max':series.max,'std':lambda:series.std(ddof=ddof),'var':lambda:series.var(ddof=ddof)}
    if operation not in methods:
        raise ToolInputError('AGGREGATION_NOT_SUPPORTED')
    return methods[operation]()


def filtered(frame, conditions, logic='and'):
    masks=[]
    for condition in conditions:
        if condition.column not in frame.columns:
            raise ToolInputError('COLUMN_NOT_FOUND')
        series, op, value = frame[condition.column], condition.operator, condition.value
        if op in {'is_null','not_null'}:
            mask=series.isna() if op=='is_null' else series.notna()
        else:
            if op in {'in','not_in','between'} and (not isinstance(value,list) or len(value)>100 or op=='between' and len(value)!=2):
                raise ToolInputError('FILTER_VALUE_INVALID')
            dates=pd.api.types.is_datetime64_any_dtype(series.dtype) or (series.notna().any() and isinstance(series.dropna().iloc[0], (date,datetime)))
            scalar_values=value if isinstance(value,list) else [value]
            if op=='contains' and (not isinstance(value,str) or pd.api.types.is_numeric_dtype(series.dtype) or dates):
                raise ToolInputError('FILTER_VALUE_INVALID')
            if pd.api.types.is_bool_dtype(series.dtype) and any(not isinstance(v,bool) for v in scalar_values):
                raise ToolInputError('FILTER_VALUE_INVALID')
            if dates and op!='contains':
                if any(not isinstance(v,(str,date,datetime,pd.Timestamp)) for v in scalar_values):raise ToolInputError('FILTER_VALUE_INVALID')
                series=pd.to_datetime(series)
                value=[pd.Timestamp(v) for v in value] if isinstance(value,list) else pd.Timestamp(value)
            elif pd.api.types.is_numeric_dtype(series.dtype) and not pd.api.types.is_bool_dtype(series.dtype) and op!='contains':
                value=[pd.to_numeric(v,errors='raise') for v in value] if isinstance(value,list) else pd.to_numeric(value,errors='raise')
                import math
                if any(isinstance(v,bool) or v is None or not math.isfinite(float(v)) for v in (value if isinstance(value,list) else [value])):raise ToolInputError('FILTER_VALUE_INVALID')
            elif not dates and not pd.api.types.is_numeric_dtype(series.dtype) and any(v is not None and not isinstance(v,str) for v in scalar_values):
                raise ToolInputError('FILTER_VALUE_INVALID')
            comparisons={'eq':series.eq,'ne':series.ne,'gt':series.gt,'gte':series.ge,'lt':series.lt,'lte':series.le}
            if op in comparisons: mask=comparisons[op](value)
            elif op in {'in','not_in'}: mask=series.isin(value) if op=='in' else ~series.isin(value)
            elif op=='contains': mask=series.astype('string').str.contains(str(value),regex=False,na=False)
            elif op=='between': mask=series.between(*value)
            else: raise ToolInputError('FILTER_OPERATOR_INVALID')
            if op in {'ne','not_in'}: mask=mask & series.notna()
        masks.append(mask.fillna(False))
    if not masks: return frame
    mask=masks[0]
    for item in masks[1:]: mask=mask & item if logic=='and' else mask | item
    return frame.loc[mask]


def sorted_frame(frame, sort):
    if not sort: return frame
    if any(item.column not in frame for item in sort):
        raise ToolInputError('COLUMN_NOT_FOUND')
    return frame.sort_values([s.column for s in sort],ascending=[s.direction=='asc' for s in sort],kind='stable',na_position='last')
