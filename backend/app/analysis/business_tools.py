"""Controlled Decimal business operations and explicit calendar comparisons."""
from decimal import Decimal, InvalidOperation, localcontext
from numbers import Number, Integral, Real
import pandas as pd
from app.analysis.errors import ToolInputError, DatasetTypeError, ToolResultError
from app.analysis.operations import filtered
from app.analysis.registry import ToolOutput
from app.analysis.models import (BusinessValue, KPIResult, BusinessPeriodRange,
    PeriodComparisonResult, ContributionResult, ContributionGroup)


LIMITATIONS = ['Ratios are decimal fractions, rounded to 28 significant digits; sums and differences are exact.',
               'Observed rows do not prove transaction completeness; no missing monetary values are imputed.']


def text(value):
    return format(value, 'f')


def decimal(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, Integral, Real)):
        raise DatasetTypeError('BUSINESS_NUMERIC_INVALID')
    try:
        result=Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DatasetTypeError('BUSINESS_NUMERIC_INVALID') from None
    if not result.is_finite():
        raise DatasetTypeError('BUSINESS_NUMERIC_INVALID')
    if len(result.as_tuple().digits)>1000 or abs(result.as_tuple().exponent)>1000:
        raise ToolInputError('DECIMAL_PRECISION_BUDGET_EXCEEDED')
    return result


def total(values):
    # Max 1000 coefficient digits and exponent +/-1000 plus row-count carry.
    with localcontext() as arithmetic:
        arithmetic.prec=3100
        return sum(values, Decimal(0))


def difference(a,b):
    with localcontext() as arithmetic:
        arithmetic.prec=3100
        return a-b


def ratio(a,b):
    if b==0:
        return BusinessValue(value=None,status='zero_denominator',explanation='The denominator is zero; ratio is undefined.')
    with localcontext() as arithmetic:
        arithmetic.prec=28
        return BusinessValue(value=text(a/b))


def value(v):
    return BusinessValue(value=text(v))


def prepare(context, params, columns, required_metadata=('currency','unit')):
    columns=list(dict.fromkeys(columns))
    context.check_size(context.frame)
    context.columns(columns)
    frame=filtered(context.frame,params.filters)
    if frame.empty: raise ToolInputError('BUSINESS_NO_ROWS')
    resolved=[]
    for label in ('currency','unit'):
        explicit=getattr(params,label)
        column=getattr(params,label+'_column')
        if explicit is not None and not explicit.strip(): raise ToolInputError('BUSINESS_METADATA_REQUIRED')
        if column:
            context.columns([column])
            raw=frame[column]
            if raw.isna().any() or any(not isinstance(v,str) or not v.strip() for v in raw):
                raise ToolInputError('BUSINESS_METADATA_INVALID')
            tokens=set(raw)
            if len(tokens)!=1: raise ToolInputError('BUSINESS_MIXED_'+label.upper())
            inferred=next(iter(tokens))
            if explicit is not None and explicit!=inferred: raise ToolInputError('BUSINESS_METADATA_CONFLICT')
            explicit=inferred
        if explicit is None and label in required_metadata: raise ToolInputError('BUSINESS_METADATA_REQUIRED')
        resolved.append(explicit)
    limits=list(LIMITATIONS)+list(context.frame.attrs.get('precision_limitations',[]))
    if any(isinstance(v,Real) and not isinstance(v,Integral) for c in columns for v in frame[c]):
        limits.append('Legacy float inputs were already approximated; Decimal conversion cannot restore lost precision.')
    return frame, dict(dataset_id=context.dataset_id,dataset_version=context.dataset_version,source_ref=context.source_ref,
                       currency=resolved[0],unit=resolved[1],limitations=limits)


def kpi_analysis(context, params):
    ids=[c for c in (params.order_id_column,params.customer_id_column,params.product_id_column) if c]
    frame,meta=prepare(context,params,list(params.metrics.values())+ids, required_metadata=('currency','unit') if params.metrics else ())
    sums={key:total([decimal(v) for v in frame[col]]) for key,col in params.metrics.items()}
    metrics={key:value(v) for key,v in sums.items()}
    metrics['records_count']=value(Decimal(len(frame)))
    for concept,column in [('orders_count',params.order_id_column),('customers_count',params.customer_id_column),('products_count',params.product_id_column)]:
        if column:
            if frame[column].isna().any(): raise DatasetTypeError('BUSINESS_ID_MISSING')
            metrics[concept]=value(Decimal(int(frame[column].nunique())))
    if 'revenue' in sums and 'cost' in sums:
        gross=difference(sums['revenue'],sums['cost'])
        metrics['gross_profit']=value(gross)
        metrics['gross_margin']=ratio(gross,sums['revenue'])
        if 'operating_expense' in sums:
            meta['limitations'].append('This simplified operating profit is revenue minus cost minus operating expense; it does not claim compliance with a formal financial reporting standard or represent net profit.')
            net=difference(gross,sums['operating_expense'])
            metrics['operating_profit']=value(net)
            metrics['operating_margin']=ratio(net,sums['revenue'])
    if 'profit' in sums and 'revenue' in sums:
        metrics['profit_margin']=ratio(sums['profit'],sums['revenue'])
    if 'budget' in sums and 'actual' in sums:
        variance=difference(sums['actual'],sums['budget'])
        metrics['variance']=value(variance)
        metrics['variance_rate']=ratio(variance,sums['budget'])
    return ToolOutput(KPIResult(**meta,metrics=metrics,row_count=len(frame)))


def timestamp(raw):
    if isinstance(raw,(Number,bool)) or raw is None:
        raise ToolInputError('BUSINESS_DATE_INVALID')
    try: parsed=pd.Timestamp(raw)
    except (ValueError,TypeError,OverflowError): raise ToolInputError('BUSINESS_DATE_INVALID') from None
    if pd.isna(parsed) or parsed.tzinfo is not None: raise ToolInputError('BUSINESS_DATE_INVALID')
    return parsed


def ranges(params):
    start,end=timestamp(params.start),timestamp(params.end)
    freq={'day':'D','month':'MS','quarter':'QS','year':'YS'}[params.granularity]
    def boundaries(a,b):
        if a!=a.normalize() or b!=b.normalize(): raise ToolInputError('BUSINESS_PERIOD_ALIGNMENT_REQUIRED')
        if a>=b: raise ToolInputError('BUSINESS_PERIOD_INVALID')
        dates=pd.date_range(a,b,freq=freq)
        if len(dates)<2 or dates[0]!=a or dates[-1]!=b: raise ToolInputError('BUSINESS_PERIOD_ALIGNMENT_REQUIRED')
        if len(dates)>1001: raise ToolInputError('BUSINESS_PERIOD_BUDGET_EXCEEDED')
        return dates[:-1]
    current=boundaries(start,end)
    if params.comparison=='custom':
        if params.previous_start is None or params.previous_end is None: raise ToolInputError('BUSINESS_PREVIOUS_RANGE_REQUIRED')
        ps,pe=timestamp(params.previous_start),timestamp(params.previous_end)
    else:
        if params.previous_start is not None or params.previous_end is not None: raise ToolInputError('BUSINESS_PREVIOUS_RANGE_UNEXPECTED')
        if params.comparison=='yoy': offset=pd.DateOffset(years=1)
        else: offset={'day':pd.DateOffset(days=1),'month':pd.DateOffset(months=1),'quarter':pd.DateOffset(months=3),'year':pd.DateOffset(years=1)}[params.granularity]
        ps,pe=start-offset,end-offset
    previous=boundaries(ps,pe)
    if len(current)!=len(previous): raise ToolInputError('BUSINESS_PERIOD_LENGTH_MISMATCH')
    if ps<end and start<pe: raise ToolInputError('BUSINESS_PERIOD_OVERLAP')
    return (start,end,current),(ps,pe,previous)


def compare(context,params,contribution=False):
    columns=[params.date_column,params.value_column]+([params.dimension] if contribution else [])
    frame,meta=prepare(context,params,columns, required_metadata=('currency','unit') if params.value_kind=='money' else ('unit',))
    dates=pd.Series([timestamp(v) for v in frame[params.date_column]], index=frame.index)
    amounts=pd.Series([decimal(v) for v in frame[params.value_column]],index=frame.index,dtype=object)
    windows=ranges(params)
    frequency={'day':'D','month':'M','quarter':'Q','year':'Y'}[params.granularity]
    selections=[]; descriptions=[]; sums=[]
    for start,end,expected in windows:
        mask=(dates>=start)&(dates<end)
        observed=len(set(dates.loc[mask].dt.to_period(frequency)))
        complete=observed==len(expected)
        selections.append(mask)
        descriptions.append(BusinessPeriodRange(start=start.date().isoformat(),end=end.date().isoformat(),expected_periods=len(expected),observed_periods=observed))
        sums.append(total(amounts.loc[mask]) if complete else None)
    unavailable=lambda: BusinessValue(value=None,status='insufficient_coverage',explanation='At least one requested calendar period has no observations; comparison cannot be calculated.')
    valid=all(v is not None for v in sums)
    delta=difference(*sums) if valid else None
    payload=dict(**meta,value_kind=params.value_kind,date_column=params.date_column,value_column=params.value_column,granularity=params.granularity,comparison=params.comparison,
        status='valid' if valid else 'insufficient_coverage',current_range=descriptions[0],previous_range=descriptions[1],
        current=value(sums[0]) if sums[0] is not None else unavailable(),previous=value(sums[1]) if sums[1] is not None else unavailable(),
        delta=value(delta) if valid else unavailable(),growth_rate=ratio(delta,sums[1]) if valid else unavailable())
    if not contribution: return ToolOutput(PeriodComparisonResult(**payload))
    payload['limitations'].append('Numeric contributions reconcile the change; they are not causal proof.')
    groups=[]
    if valid:
        # No top-N truncation: preserve every entering/exiting/null dimension group.
        selected=selections[0]|selections[1]
        labels=frame[params.dimension].loc[selected]
        if any(v is not None and not isinstance(v,str) for v in labels): raise DatasetTypeError('BUSINESS_DIMENSION_STRING_REQUIRED')
        keys=list(dict.fromkeys(labels))
        if len(keys)>context.max_cells//5: raise ToolResultError('RESULT_BUDGET_EXCEEDED')
        for key in keys:
            match=frame[params.dimension].isna() if key is None else frame[params.dimension].eq(key)
            a,b=[total(amounts.loc[mask&match]) for mask in selections]
            d=difference(a,b)
            groups.append(ContributionGroup(dimension=key,current=text(a),previous=text(b),delta=text(d),contribution_share=ratio(d,delta).value))
        if total([Decimal(g.delta) for g in groups])!=delta: raise ToolResultError('BUSINESS_RECONCILIATION_FAILED')
    return ToolOutput(ContributionResult(**payload,dimension=params.dimension,groups=groups))


def period_comparison(context,params): return compare(context,params)
def contribution_analysis(context,params): return compare(context,params,contribution=True)
