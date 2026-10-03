import numpy as np
import pandas as pd
from app.analysis.models import AggregationResult, StatisticsResult, StatisticValue
from app.analysis.registry import ToolOutput
from app.analysis.data_tools import table_output
from app.analysis.operations import aggregate_series, filtered, sorted_frame
from app.analysis.errors import ToolInputError, ToolResultError
from app.analysis.serialization import json_value
from app.execution.validators import ResultWarning, validate_value


def aggregate(context,args,grouped=False):
    context.columns(args.dimensions)
    context.columns(list(dict.fromkeys(m.column for m in args.metrics)))
    if grouped and not args.dimensions:
        raise ToolInputError('DIMENSIONS_REQUIRED')
    aliases=[m.alias or f'{m.column}_{m.aggregation.value}' for m in args.metrics]
    if len(aliases)!=len(set(aliases)) or set(aliases)&set(args.dimensions):
        raise ToolInputError('METRIC_ALIAS_CONFLICT')
    frame=filtered(context.frame,args.filters,args.logic)
    groups=frame.groupby(args.dimensions,dropna=args.drop_missing,sort=False,observed=True) if args.dimensions else [((),frame)]
    if args.dimensions and groups.ngroups>context.max_rows:
        raise ToolResultError('RESULT_BUDGET_EXCEEDED')
    rows=[]
    missing=0
    for keys,group in groups:
        keys=keys if isinstance(keys,tuple) else (keys,)
        row=dict(zip(args.dimensions,keys))
        for metric,alias in zip(args.metrics,aliases):
            raw=aggregate_series(group[metric.column],metric.aggregation)
            validate_value(raw)
            row[alias]=json_value(raw)
            missing+=raw is None
        rows.append(row)
    output=pd.DataFrame(rows,columns=[*args.dimensions,*aliases])
    # Construct nullable integer columns from source scalars before pandas can
    # round BIGINT values through an inferred float column.
    for alias in aliases:
        values=[row[alias] for row in rows]
        valid=[value for value in values if value is not None]
        if valid and all(isinstance(value,int) and not isinstance(value,bool) for value in valid):
            output[alias]=pd.array(values,dtype='Int64')
    output=sorted_frame(output,args.sort)
    notes=[ResultWarning(code='NO_VALID_STATISTIC',message='部分指标无有效样本或样本不足',count=missing)] if missing else []
    return table_output(context,output,args.limit,AggregationResult,notes)


def pivot(context,args,cross=False):
    context.columns([*args.index,args.column]+([args.value] if args.value else []))
    if not cross and not args.value: raise ToolInputError('VALUE_COLUMN_REQUIRED')
    frame=filtered(context.frame,args.filters,args.logic)
    left=int(frame[args.index].drop_duplicates().shape[0])
    if not args.drop_missing:
        left=1
        for field in args.index: left*=int(frame[field].nunique(dropna=False))
    left+=1 if args.margins else 0
    right=int(frame[args.column].nunique(dropna=False))+(1 if args.margins else 0)
    if left*right>context.max_cells or left>context.max_rows or right+len(args.index)>context.max_columns:
        raise ToolResultError('MATRIX_BUDGET_EXCEEDED')
    if cross:
        matrix=pd.crosstab([frame[c] for c in args.index],frame[args.column],margins=args.margins,dropna=args.drop_missing)
        matrix=matrix.mask(matrix.eq(0))
        if args.fill_value is not None:matrix=matrix.fillna(args.fill_value)
    else:
        matrix=pd.pivot_table(frame,index=args.index,columns=args.column,values=args.value,aggfunc=lambda values:aggregate_series(values,args.aggregation),fill_value=args.fill_value,margins=args.margins,dropna=args.drop_missing,observed=True)
    if matrix.size>context.max_cells:raise ToolResultError('MATRIX_BUDGET_EXCEEDED')
    original_columns=list(matrix.columns)
    labels=[]
    for i in range(len(matrix.columns)):
        label=f'value_{i}'
        while label in args.index or label in labels: label='_'+label
        labels.append(label)
    matrix.columns=labels
    output=matrix.reset_index()
    # Labels are retained as column metadata, without interpolating business keys.
    result=table_output(context,output,args.limit,AggregationResult)
    for spec,label in zip(result.data.columns[len(args.index):],original_columns):
        spec.label=str(label)
    return result


def rank(context,args,operation):
    context.columns([args.column,*args.group_by],numeric=False)
    frame=filtered(context.frame,args.filters,args.logic)
    if operation=='rank':
        frame=frame.copy()
        if '__rank' in frame: raise ToolInputError('OUTPUT_COLUMN_CONFLICT')
        group=frame.groupby(args.group_by,dropna=False,sort=False)[args.column] if args.group_by else frame[args.column]
        frame['__rank']=group.rank(method=args.method,ascending=args.direction=='asc',na_option='keep')
    else:
        frame=frame.sort_values(args.column,ascending=operation=='bottom_n',kind='stable',na_position='last')
        frame=frame.groupby(args.group_by,dropna=False,sort=False).head(args.n) if args.group_by else frame.head(args.n)
    return table_output(context,frame,args.limit)


def ratio(context,args,weighted=False):
    context.columns([args.column],numeric=True)
    context.columns(args.group_by)
    if weighted:
        if not args.weight_column: raise ToolInputError('WEIGHT_COLUMN_REQUIRED')
        context.columns([args.weight_column],numeric=True)
    frame=filtered(context.frame,args.filters,args.logic)
    groups=frame.groupby(args.group_by,dropna=False,sort=False,observed=True) if args.group_by else [((),frame)]
    if not weighted:
        output=frame.copy()
        alias=args.column+'_share'
        if alias in output: raise ToolInputError('OUTPUT_COLUMN_CONFLICT')
        output[alias]=np.nan
        notes=[]
        for _,group in groups:
            denominator=aggregate_series(group[args.column],'sum')
            if denominator is None or denominator==0:
                notes.append(ResultWarning(code='ZERO_DENOMINATOR',message='份额分母为空或零',count=len(group)))
            else:
                output.loc[group.index,alias]=group[args.column]/denominator
        return table_output(context,output,args.limit,AggregationResult,notes)
    rows=[]
    for keys,group in groups:
        valid=group[[args.column,args.weight_column]].dropna()
        if (valid[args.weight_column]<0).any(): raise ToolInputError('NEGATIVE_WEIGHT')
        denominator=aggregate_series(valid[args.weight_column],'sum')
        value=None
        if denominator:
            products=valid[args.column].astype(float)*valid[args.weight_column].astype(float)
            value=aggregate_series(products,'sum')/denominator
        keys=keys if isinstance(keys,tuple) else (keys,)
        rows.append(StatisticValue(column=args.column,statistic='weighted_average',value=value,valid_count=len(valid),status='valid' if value is not None else 'zero_denominator',dimensions={name:json_value(key) for name,key in zip(args.group_by,keys)}))
    return ToolOutput(StatisticsResult(values=rows))


def sequence(context,args,operation):
    context.columns([args.column],numeric=True)
    context.columns(args.group_by)
    context.columns([item.column for item in args.order_by])
    frame=sorted_frame(filtered(context.frame,args.filters,args.logic),args.order_by)
    groups=frame.groupby(args.group_by,dropna=False,sort=False,observed=True) if args.group_by else [((),frame)]
    if operation=='growth_rate':
        if set(args.group_by)&{'start','end','growth_rate','status'}:raise ToolInputError('OUTPUT_COLUMN_CONFLICT')
        rows=[];notes=[]
        for keys,group in groups:
            keys=keys if isinstance(keys,tuple) else (keys,)
            values=group[args.column]
            start,end=(values.iloc[0],values.iloc[-1]) if len(values) else (None,None)
            defined=start is not None and end is not None and pd.notna(start) and pd.notna(end) and start!=0
            if defined:
                rate=(int(end)-int(start))/int(start) if pd.api.types.is_integer_dtype(values.dtype) else (float(end)-float(start))/float(start)
                status='valid'
            else:
                rate=None;status='zero_denominator' if start is not None and pd.notna(start) and start==0 else 'missing_endpoint'
                notes.append(ResultWarning(code=status.upper(),message='增长率基期为零或起止值缺失',count=len(values)))
            rows.append(dict(zip(args.group_by,keys),start=json_value(start),end=json_value(end),growth_rate=rate,status=status))
        output=pd.DataFrame(rows,columns=[*args.group_by,'start','end','growth_rate','status'])
        for column in ('start','end'):
            valid=[row[column] for row in rows if row[column] is not None]
            if valid and all(isinstance(value,int) for value in valid):output[column]=pd.array([row[column] for row in rows],dtype='Int64')
        return table_output(context,output,args.limit,AggregationResult,notes)
    output=frame.copy()
    alias=args.column+'_'+operation
    if alias in output: raise ToolInputError('OUTPUT_COLUMN_CONFLICT')
    output[alias]=pd.Series(index=output.index,dtype='object')
    notes=[]
    for _,group in groups:
        values=group[args.column]
        if operation=='cumulative_sum':
            total=0; result=[]
            for value in values:
                if pd.isna(value): result.append(None); continue
                total+=int(value) if pd.api.types.is_integer_dtype(values.dtype) else float(value)
                if pd.api.types.is_integer_dtype(values.dtype) and not -(2**63)<=total<2**63:
                    raise ToolResultError('INTEGER_OVERFLOW')
                result.append(total)
        elif operation=='percentage_change':
            previous=values.shift(args.periods)
            if pd.api.types.is_integer_dtype(values.dtype):
                result=[None if pd.isna(current) or pd.isna(prior) or prior==0 else (int(current)-int(prior))/int(prior) for current,prior in zip(values,previous)]
            else:result=(values.astype(float)-previous.astype(float))/previous.where(previous.ne(0)).astype(float)
            if previous.eq(0).any(): notes.append(ResultWarning(code='ZERO_DENOMINATOR',message='零基期增长率未定义',count=int(previous.eq(0).sum())))
        else:
            window=values.rolling(args.window,min_periods=args.min_periods or args.window)
            if args.aggregation in {'sum','min','max','median'} and pd.api.types.is_integer_dtype(values.dtype):
                result=[]
                if args.aggregation=='sum':
                    from collections import deque
                    queue=deque();total=0;count=0
                    for value in values:
                        value=None if pd.isna(value) else int(value)
                        queue.append(value)
                        if value is not None:total+=value;count+=1
                        if len(queue)>args.window:
                            expired=queue.popleft()
                            if expired is not None:total-=expired;count-=1
                        if count>=(args.min_periods or args.window):
                            if not -(2**63)<=total<2**63:raise ToolResultError('INTEGER_OVERFLOW')
                            result.append(total)
                        else:result.append(None)
                else:
                    for end in range(1,len(values)+1):
                        samples=values.iloc[max(0,end-args.window):end]
                        result.append(aggregate_series(samples,args.aggregation) if samples.count()>=(args.min_periods or args.window) else None)
            else: result=getattr(window,args.aggregation)()
        output.loc[group.index,alias]=list(result)
    return table_output(context,output,args.limit,AggregationResult,notes)
