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
