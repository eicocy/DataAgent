import numpy as np
import pandas as pd
from app.analysis.models import DataQualityResult, QualityFinding
from app.analysis.registry import ToolOutput
from app.analysis.errors import ToolInputError


def outlier_mask(series,method,threshold):
    if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        raise ToolInputError('NUMERIC_COLUMN_REQUIRED')
    from app.execution.validators import validate_numeric_series
    validate_numeric_series(series)
    valid=series.dropna().astype(float)
    if valid.empty: return pd.Series(False,index=series.index),None,None,'no_valid_samples'
    if method=='iqr':
        q1,q3=valid.quantile([.25,.75]); width=q3-q1
        lower,upper=q1-(threshold or 1.5)*width,q3+(threshold or 1.5)*width
    else:
        std=valid.std(ddof=0)
        if std==0: return pd.Series(False,index=series.index),float(valid.iloc[0]),float(valid.iloc[0]),'constant'
        lower,upper=valid.mean()-(threshold or 3)*std,valid.mean()+(threshold or 3)*std
    return (series.lt(lower)|series.gt(upper)).fillna(False),float(lower),float(upper),'valid'


def quality(context,args,operation):
    names=context.columns(args.columns)
    frame=context.frame
    findings=[]
    if operation=='duplicate_analysis':
        mask=frame.duplicated(subset=names,keep='first')
        findings.append(QualityFinding(count=int(mask.sum()),rate=float(mask.mean()) if len(mask) else 0,row_refs=np.flatnonzero(mask.to_numpy()).tolist()[:args.limit]))
    else:
        for name in names:
            series=frame[name]
            lower=upper=None; status='valid'
            if operation=='missing_value_analysis': mask=series.isna()
            elif operation=='constant_column_analysis': mask=series.notna() if series.nunique(dropna=True)==1 else pd.Series(False,index=frame.index)
            elif operation=='cardinality_analysis':
                count=int(series.nunique(dropna=True))
                findings.append(QualityFinding(column=name,count=count,rate=count/len(frame) if len(frame) else 0)); continue
            elif operation=='invalid_numeric_analysis': mask=series.notna() & pd.to_numeric(series,errors='coerce').isna()
            elif operation=='invalid_datetime_analysis': mask=series.notna() & pd.to_datetime(series,errors='coerce',format=args.datetime_format).isna()
            elif operation=='infinite_value_analysis':
                numeric=pd.to_numeric(series,errors='coerce')
                mask=numeric.notna() & ~np.isfinite(numeric.astype(float))
            else: mask,lower,upper,status=outlier_mask(series,args.method,args.threshold)
            count=int(mask.sum())
            findings.append(QualityFinding(column=name,count=count,rate=count/len(frame) if len(frame) else 0,row_refs=np.flatnonzero(mask.to_numpy()).tolist()[:args.limit],lower=lower,upper=upper,status=status))
    return ToolOutput(DataQualityResult(check=operation,findings=findings))


def data_quality_score(context,args):
    """Public v1 heuristic: weighted issue rates, never a business standard."""
    from app.analysis.inputs import QualityInput
    from app.analysis.models import QualityScoreResult,ScoreFinding
    frame=context.frame
    context.check_size(frame);context.columns(list(args.field_rules))
    findings=[];n=len(frame);cells=max(1,n*len(frame.columns))
    def add(issue,column,count,refs,weight,denominator,suggestion):
        findings.append(ScoreFinding(issue=issue,column=column,count=count,row_refs=refs[:args.limit],penalty=weight*count/max(1,denominator),severity='error' if issue in {'invalid_numeric','invalid_datetime','nonfinite','range'} else 'warning',suggestion=suggestion))
    for operation,issue,weight in [('missing_value_analysis','missing',30),('duplicate_analysis','duplicate',20)]:
        output=quality(context,QualityInput(limit=args.limit),operation).data
        for f in output.findings: add(issue,f.column,f.count,f.row_refs,weight,n if issue=='duplicate' else cells,'Select an explicit repair operation after inspecting source data.')
    for c in frame:
        mask=frame[c].map(lambda v:isinstance(v,str) and not v.strip())
        add('empty',c,int(mask.sum()),np.flatnonzero(mask.to_numpy()).tolist(),10,cells,'Explicitly replace or normalize empty text if appropriate.')
    rules=dict(args.field_rules)
    # Only high-confidence semantic types from the existing profiler qualify;
    # numeric-looking identifiers and arbitrary text do not become measures.
    from app.analysis.inputs import FieldRule
    for c in context.schema.columns:
        if c.name not in rules and c.semantic_type in {'NumericMeasure','Numeric','Integer','Decimal'}:
            rules[c.name]=FieldRule(type='numeric')
        if c.name not in rules and c.semantic_type in {'Date','DateTime','Datetime'}:
            rules[c.name]=FieldRule(type='datetime')
    for c,rule in rules.items():
        operation='invalid_numeric_analysis' if rule.type=='numeric' else 'invalid_datetime_analysis'
        result=quality(context,QualityInput(columns=[c],limit=args.limit,datetime_format=rule.datetime_format),operation).data.findings[0]
        add('invalid_numeric' if rule.type=='numeric' else 'invalid_datetime',c,result.count,result.row_refs,20,max(1,n*max(1,len(rules))),'Correct source values or choose explicit conversion/coercion.')
        if rule.type=='numeric':
            f=quality(context,QualityInput(columns=[c],limit=args.limit),'infinite_value_analysis').data.findings[0]
            add('nonfinite',c,f.count,f.row_refs,10,max(1,n*max(1,len(rules))),'Inspect and explicitly replace nonfinite values.')
            numeric=pd.to_numeric(frame[c],errors='coerce')
            mask=pd.Series(False,index=frame.index)
            if rule.minimum is not None: mask|=numeric.lt(rule.minimum).fillna(False)
            if rule.maximum is not None: mask|=numeric.gt(rule.maximum).fillna(False)
            add('range',c,int(mask.sum()),np.flatnonzero(mask.to_numpy()).tolist(),10,max(1,n*max(1,len(rules))),'Inspect violations of the explicitly configured range.')
    unique={c:int(frame[c].nunique(dropna=True)) for c in frame}
    return ToolOutput(QualityScoreResult(status='valid' if n else 'empty',score=round(max(0,100-sum(f.penalty for f in findings)),6) if n else None,row_count=n,findings=findings,unique_counts=unique,key_candidates=[c for c in frame if n and unique[c]==n and not frame[c].isna().any()],configured_rules={c:r.model_dump(mode='json') for c,r in rules.items()},explanation='quality-score-v1: 100 minus missing-cell rate*30, empty-cell rate*10, duplicate-row rate*20, invalid configured/inferred field rate*20, nonfinite rate*10 and explicit range rate*10; clipped at zero. A public descriptive heuristic, not an industry standard. No automatic repairs; empty datasets have no score.'))
