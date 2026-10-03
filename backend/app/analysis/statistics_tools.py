import numpy as np
import pandas as pd
from app.analysis.models import StatisticsResult, StatisticValue, CorrelationResult, CorrelationPair
from app.analysis.registry import ToolOutput
from app.analysis.errors import ToolInputError, ToolResultError
from app.execution.validators import ResultWarning
from app.analysis.serialization import json_value


def numeric_columns(context,args):
    names=args.columns if args.columns is not None else list(context.frame.select_dtypes(include='number').columns)
    return context.columns(names,numeric=True)


def statistics(context,args,operation):
    names=numeric_columns(context,args)
    values=[]
    operations=['count','mean','min','max','median','std','var','quantile'] if operation=='descriptive_statistics' else [operation]
    for name in names:
        series=context.frame[name].dropna()
        count=len(series)
        for op in operations:
            minimum={'std':args.ddof+1,'var':args.ddof+1,'skewness':3,'kurtosis':4}.get(op,1)
            if op=='count': raw=count
            elif count<minimum: raw=None
            elif op in {'quantile','percentile'}: raw=series.quantile(args.q if op=='quantile' else args.percentile/100)
            else:
                method={'variance':'var','standard_deviation':'std','skewness':'skew','kurtosis':'kurt'}.get(op,op)
                minimum={'var':args.ddof+1,'std':args.ddof+1}.get(method,minimum)
                raw=None if count<minimum else getattr(series,method)(**({'ddof':args.ddof} if method in {'std','var'} else {}))
            status='valid' if raw is not None and pd.notna(raw) else 'no_valid_samples' if not count else 'insufficient_samples'
            values.append(StatisticValue(column=name,statistic=op,value=json_value(raw) if status=='valid' else None,valid_count=count,status=status))
    return ToolOutput(StatisticsResult(values=values))


def correlation(context,args,covariance=False):
    names=numeric_columns(context,args)
    if len(names)>context.correlation_columns or len(names)**2>context.max_cells:
        raise ToolResultError('MATRIX_BUDGET_EXCEEDED')
    matrix=[[None]*len(names) for _ in names]
    pairs=[]; values=[]; notes=[]
    for i,x in enumerate(names):
        for j in range(i,len(names)):
            y=names[j]
            # Selecting a duplicate label creates two identical series deliberately.
            a,b=context.frame[x],context.frame[y]
            mask=a.notna() & b.notna()
            a,b=a[mask].astype(float),b[mask].astype(float)
            size=len(a)
            status='insufficient_samples' if size<args.min_samples else 'constant' if a.nunique()<2 or b.nunique()<2 else 'valid'
            coefficient=None
            if covariance:
                coefficient=float(np.cov(a,b,ddof=args.ddof)[0,1]) if size>args.ddof else None
                values.append(StatisticValue(column=f'{x}:{y}',statistic='covariance',value=coefficient,valid_count=size,status='valid' if coefficient is not None else 'insufficient_samples'))
                continue
            if status=='valid':
                if args.method=='spearman': a,b=a.rank(method='average'),b.rank(method='average')
                # Rescale first so very large finite values do not overflow centering.
                a=a/float(a.abs().max()); b=b/float(b.abs().max())
                a=a-a.mean(); b=b-b.mean()
                coefficient=float((a*b).sum()/np.sqrt((a*a).sum()*(b*b).sum()))
                if np.isfinite(coefficient): coefficient=max(-1.,min(1.,coefficient))
            else: notes.append(ResultWarning(code=status.upper(),message='相关系数未定义',count=size))
            matrix[i][j]=matrix[j][i]=coefficient
            pairs.append(CorrelationPair(x=x,y=y,coefficient=coefficient,sample_size=size,status=status))
    return ToolOutput(StatisticsResult(values=values) if covariance else CorrelationResult(method=args.method,columns=names,matrix=matrix,pairs=pairs),warnings=notes)
