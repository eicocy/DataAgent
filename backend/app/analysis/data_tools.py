from functools import partial
import pandas as pd
from app.analysis.models import ColumnSpec, TableResult, OverviewResult
from app.analysis.registry import ToolOutput
from app.analysis.operations import filtered, sorted_frame
from app.analysis.serialization import records
from app.analysis.errors import ToolInputError


def table_output(context, frame, limit=None, model=TableResult, warnings=None):
    context.check_size(frame)
    limit=min(context.preview_rows if limit is None else limit, 500)
    columns=[ColumnSpec(name=str(name),dtype=str(frame[name].dtype)) for name in frame]
    return ToolOutput(model(columns=columns,rows=records(frame.head(limit)),row_count=len(frame),truncated=len(frame)>limit),frame,warnings or [])


def overview(context,args):
    return ToolOutput(OverviewResult(row_count=len(context.frame),column_count=len(context.frame.columns),memory_bytes=int(context.frame.memory_usage(deep=True).sum()),columns=[ColumnSpec(name=c.name,label=c.original_name,dtype=c.dtype) for c in context.schema.columns]))


def column_summary(context,args):
    names=context.columns(args.columns)
    rows=[item.model_dump(exclude={'numeric'}) for item in context.profile.columns if item.name in names]
    return table_output(context,pd.DataFrame(rows),args.limit)


def rows_tool(context,args,operation):
    names=context.columns(args.columns)
    frame=filtered(context.frame,args.filters,args.logic)
    if operation=='select_columns' and args.columns is None:
        raise ToolInputError('COLUMNS_REQUIRED')
    if operation=='filter_rows' and not args.filters:
        raise ToolInputError('FILTERS_REQUIRED')
    if operation=='sort_rows' and not args.sort:
        raise ToolInputError('SORT_REQUIRED')
    frame=sorted_frame(frame,args.sort).loc[:,names]
    if operation=='sample_rows': frame=frame.sample(n=min(args.limit,len(frame)),random_state=args.seed)
    elif args.offset: frame=frame.iloc[args.offset:]
    return table_output(context,frame,args.limit)


def categories(context,args,operation):
    names=context.columns(args.columns)
    if len(names)!=1:
        raise ToolInputError('ONE_COLUMN_REQUIRED')
    name=names[0]
    series=filtered(context.frame,args.filters,args.logic)[name]
    if args.drop_missing: series=series.dropna()
    if operation=='unique_values':
        frame=pd.DataFrame({name:series.drop_duplicates().tolist()})
    else:
        output_name='__count'
        if name==output_name: output_name='__frequency'
        frame=series.value_counts(dropna=args.drop_missing,sort=False).rename_axis(name).reset_index(name=output_name).sort_values(output_name,ascending=False,kind='stable')
    return table_output(context,frame,args.limit)
