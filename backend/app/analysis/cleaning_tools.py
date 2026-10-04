import pandas as pd
from app.analysis.models import CleaningResult
from app.analysis.registry import ToolOutput
from app.analysis.quality_tools import outlier_mask
from app.analysis.errors import ToolInputError
from app.analysis.operations import aggregate_series
from app.execution.validators import ResultWarning


def clean(context,args,operation):
    names=context.columns(args.columns)
    original=context.frame
    frame=original.copy(deep=True)
    added=0
    approximated=[]
    from app.analysis.precision import decimal_series
    if operation=='rename_columns':
        if set(args.names)!=set(names) or any(not new.strip() for new in args.names.values()): raise ToolInputError('RENAME_MAPPING_INVALID')
        labels=[args.names.get(name,name) for name in frame]
        if len(labels)!=len(set(labels)): raise ToolInputError('COLUMN_NAME_CONFLICT')
        frame=frame.rename(columns=args.names)
        frame.attrs['original_columns']=[str(name) for name in frame.columns]
    elif operation=='remove_duplicates': frame=frame.drop_duplicates(subset=names,keep=False if args.keep=='none' else args.keep)
    elif operation=='drop_missing_rows': frame=frame.dropna(subset=names,how=args.how)
    else:
        for name in names:
            series=frame[name]
            if decimal_series(series) and (operation=='outlier_treatment' or operation=='fill_missing_values' and args.strategy in {'mean','median'}):
                series=pd.to_numeric(series,errors='raise')
                approximated.append(name)
            if operation=='fill_missing_values':
                if args.strategy in {'forward','backward'}: result=series.ffill() if args.strategy=='forward' else series.bfill()
                else:
                    value=args.value
                    if args.strategy in {'mean','median'}: value=aggregate_series(series,args.strategy)
                    elif args.strategy=='mode': value=series.mode().iloc[0] if not series.mode().empty else None
                    elif args.strategy!='constant': raise ToolInputError('FILL_STRATEGY_INVALID')
                    if value is None: raise ToolInputError('FILL_VALUE_UNDEFINED')
                    result=series.fillna(value)
            elif operation in {'convert_dtype','parse_datetime'}:
                dtype='datetime' if operation=='parse_datetime' else args.dtype
                if dtype is None: raise ToolInputError('DTYPE_REQUIRED')
                if dtype=='datetime': result=pd.to_datetime(series,errors=args.errors,format=args.datetime_format)
                elif dtype in {'integer','decimal'}:
                    result=pd.to_numeric(series,errors=args.errors)
                    if dtype=='integer':
                        bad=result.notna() & result.mod(1).ne(0)
                        if bad.any() and args.errors=='raise': raise ToolInputError('INTEGER_CONVERSION_LOSS')
                        result=result.mask(bad).astype('Int64')
                elif dtype=='boolean':
                    mapping={'true':True,'false':False,'1':True,'0':False}
                    result=series.astype('string').str.lower().map(mapping).astype('boolean')
                    if args.errors=='raise' and (series.notna() & result.isna()).any(): raise ToolInputError('BOOLEAN_CONVERSION_INVALID')
                else: result=series.astype('string')
                added+=int((series.notna() & result.isna()).sum())
            elif operation=='replace_values':
                # Match the actual column's scalar type without interpreting expressions.
                mapping={pd.to_numeric(key,errors='raise') if pd.api.types.is_numeric_dtype(series.dtype) else key:value for key,value in args.replacements.items()}
                result=series.replace(mapping)
            elif operation=='normalize_text':
                if not (pd.api.types.is_string_dtype(series.dtype) or series.dropna().map(lambda v:isinstance(v,str)).all()): raise ToolInputError('TEXT_COLUMN_REQUIRED')
                result=series.astype('string')
                methods={'strip':lambda s:s.str.strip(),'lower':lambda s:s.str.lower(),'upper':lambda s:s.str.upper(),'casefold':lambda s:s.str.casefold(),'collapse_whitespace':lambda s:s.str.replace(r'\s+',' ',regex=True)}
                for method in args.text_operations: result=methods[method](result)
            else:
                mask,lower,upper,_=outlier_mask(series,args.method,args.threshold)
                if args.strategy=='drop': frame=frame.loc[~mask]; continue
                if args.strategy=='clip': result=series.clip(lower,upper)
                elif args.strategy=='null': result=series.mask(mask)
                else: raise ToolInputError('OUTLIER_STRATEGY_INVALID')
            frame[name]=result
    if frame.shape[1]==original.shape[1] and frame.columns.equals(original.columns):
        common=frame.index.intersection(original.index)
        equal=frame.loc[common].eq(original.loc[common]) | (frame.loc[common].isna() & original.loc[common].isna())
        changed=int((~equal.fillna(False)).sum().sum())+(len(original)-len(frame))*len(frame.columns)
    else: changed=0
    frame=frame.reset_index(drop=True)
    notes=[ResultWarning(code='CONVERSION_ADDED_MISSING',message='显式转换产生缺失值',count=added)] if added else []
    if approximated or operation=='convert_dtype' and args.dtype in {'decimal','integer'} and any(decimal_series(original[name]) for name in names):
        notes.append(ResultWarning(code='APPROXIMATE_NUMERIC_TRANSFORMATION',message='显式数值转换可能近似所选 Decimal 字段；未选择的金额字段保持原值。'))
    return ToolOutput(CleaningResult(operation=operation,source_version=context.dataset_version,row_count=len(frame),column_count=len(frame.columns),changed_cells=changed,added_missing=added),frame,notes)
