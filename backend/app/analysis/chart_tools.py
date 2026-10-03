import numpy as np
import pandas as pd
from app.analysis.models import ChartResult,ChartSeries,ChartPoint,RecommendationResult,ChartRecommendation
from app.analysis.registry import ToolOutput
from app.analysis.serialization import json_value
from app.analysis.errors import ToolInputError,ToolResultError
from app.analysis.quality_tools import outlier_mask
from app.execution.validators import ResultWarning
from app.analysis.operations import filtered,sorted_frame


def recommend(context,args):
    numeric=[column.name for column in context.schema.columns if column.role=='Metric']
    time=[column.name for column in context.schema.columns if column.role=='TimeDimension']
    dimensions=[column.name for column in context.schema.columns if column.role=='Dimension']
    recommendations=[]
    if numeric:
        recommendations.append(ChartRecommendation(chart_type='histogram',columns=numeric[:1],reason='numeric_distribution'))
        if time: recommendations.append(ChartRecommendation(chart_type='line',columns=[time[0],numeric[0]],reason='time_and_metric'))
        if dimensions: recommendations.append(ChartRecommendation(chart_type='bar',columns=[dimensions[0],numeric[0]],reason='dimension_and_metric'))
    if len(numeric)>=2: recommendations.append(ChartRecommendation(chart_type='scatter',columns=numeric[:2],reason='two_metrics'))
    return ToolOutput(RecommendationResult(recommendations=recommendations))


def chart(context,args):
    context.columns(args.y,numeric=True)
    context.columns(([args.x] if args.x else [])+([args.group_by] if args.group_by else []))
    frame=sorted_frame(filtered(context.frame,args.filters,args.logic),args.sort)
    series=[]
    if args.chart_type=='heatmap':
        if len(args.y)>context.correlation_columns or len(args.y)**2>context.max_cells:
            raise ToolResultError('CHART_BUDGET_EXCEEDED')
        from dataclasses import replace
        result=context.registry.calculate('correlation',replace(context,frame=frame),{'columns':args.y}).data
        series=[ChartSeries(name=args.y[i],points=[ChartPoint(x=j,y=float(i),values=[value]) for j,value in enumerate(row)]) for i,row in enumerate(result.matrix)]
    elif args.chart_type=='histogram':
        for name in args.y:
            valid=frame[name].dropna().astype(float)
            counts,edges=np.histogram(valid,bins=args.bins)
            series.append(ChartSeries(name=name,points=[ChartPoint(x=float((edges[i]+edges[i+1])/2),y=float(count)) for i,count in enumerate(counts)]))
    elif args.chart_type=='boxplot':
        for name in args.y:
            valid=frame[name].dropna()
            if valid.empty: continue
            _,lower,upper,_=outlier_mask(frame[name],'iqr',1.5)
            within=valid[valid.between(lower,upper)]
            values=[float(within.min()),*map(float,valid.quantile([.25,.5,.75])),float(within.max())]
            series.append(ChartSeries(name=name,points=[ChartPoint(x=name,values=values)]))
    else:
        if args.x is None: raise ToolInputError('X_COLUMN_REQUIRED')
        if args.chart_type=='scatter': context.columns([args.x],numeric=True)
        if args.chart_type in {'pie','donut'} and (frame[args.y]<0).any().any(): raise ToolInputError('NEGATIVE_PIE_VALUE')
        groups=frame.groupby(args.group_by,sort=False,dropna=False,observed=True) if args.group_by else [(None,frame)]
        group_count=groups.ngroups if args.group_by else 1
        if group_count*len(args.y)>80: raise ToolResultError('CHART_BUDGET_EXCEEDED')
        for label,group in groups:
            for name in args.y:
                points=[ChartPoint(x=json_value(x),y=json_value(y)) for x,y in zip(group[args.x].head(500),group[name].head(500))]
                series.append(ChartSeries(name=name if label is None else str(label)+':'+name,points=points))
    notes=[ResultWarning(code='CHART_TRUNCATED',message='图表点数超过预览上限',count=len(frame)-500)] if len(frame)>500 and args.chart_type not in {'heatmap','histogram','boxplot'} else []
    return ToolOutput(ChartResult(chart_type=args.chart_type,title=args.title,x=args.x,y=args.y,series=series,options=args.options),warnings=notes)
