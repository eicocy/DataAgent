"""Bounded explicit joins over trusted fixed-version contexts only."""
from collections import Counter
from datetime import date,datetime
from decimal import Decimal
from numbers import Integral,Real
import math
import sys
import pandas as pd
from app.analysis.errors import ToolInputError,ToolResultError
from app.analysis.models import JoinResult,ColumnSpec
from app.analysis.registry import ToolOutput
from app.analysis.serialization import records


def _family(value):
    if isinstance(value,(bool,)) or pd.api.types.is_bool(value): return 'boolean'
    if isinstance(value,Integral): return 'integer'
    if isinstance(value,Decimal):
        if not value.is_finite(): raise ToolInputError('JOIN_KEY_TYPE_MISMATCH')
        return 'decimal'
    if isinstance(value,Real):
        if not math.isfinite(value): raise ToolInputError('JOIN_KEY_TYPE_MISMATCH')
        return 'real'
    if isinstance(value,str): return 'text'
    if isinstance(value,(datetime,pd.Timestamp)): return 'datetime:'+str(value.tzinfo)
    if isinstance(value,date): return 'date'
    raise ToolInputError('JOIN_KEY_TYPE_MISMATCH')


def _row_bytes(frame):
    # A worst-case row, including object payload, not an average that can hide
    # amplification of a particularly large matched row.
    return 32+sum(max((sys.getsizeof(v)+8 for v in frame[c]),default=8) for c in frame)


def join_data(context,args):
    right_context=context.related_inputs.get(args.right_alias)
    if right_context is None: raise ToolInputError('JOIN_INPUT_UNAVAILABLE')
    left,right=context.frame,right_context.frame
    context.check_size(left);context.check_size(right)
    context.columns(args.left_on);right_context.columns(args.right_on)
    if not left.columns.is_unique or not right.columns.is_unique: raise ToolInputError('JOIN_COLUMN_AMBIGUOUS')
    for l,r in zip(args.left_on,args.right_on):
        if left[l].isna().any() or right[r].isna().any(): raise ToolInputError('JOIN_NULL_KEYS')
        lf={_family(v) for v in left[l]};rf={_family(v) for v in right[r]}
        if len(lf)>1 or len(rf)>1 or (lf and rf and lf!=rf): raise ToolInputError('JOIN_KEY_TYPE_MISMATCH')
    lk=list(left[args.left_on].itertuples(index=False,name=None))
    rk=list(right[args.right_on].itertuples(index=False,name=None))
    lc,rc=Counter(lk),Counter(rk)
    if (args.relationship in {'one_to_one','one_to_many'} and any(n>1 for n in lc.values())) or (args.relationship in {'one_to_one','many_to_one'} and any(n>1 for n in rc.values())):
        raise ToolInputError('JOIN_RELATIONSHIP_INVALID')
    shared={l for l,r in zip(args.left_on,args.right_on) if l==r}
    overlaps=set(left.columns)&set(right.columns)-shared
    labels=[c+'_left' if c in overlaps else c for c in left]+[c+'_right' if c in overlaps else c for c in right if c not in shared]
    if len(set(labels))!=len(labels): raise ToolInputError('JOIN_COLUMN_AMBIGUOUS')
    estimated=sum(n*(rc.get(k,0) or (1 if args.how=='left' else 0)) for k,n in lc.items())
    if estimated>context.max_rows or len(labels)>context.max_columns or estimated*(_row_bytes(left)+_row_bytes(right))>context.max_bytes:
        raise ToolResultError('RESULT_BUDGET_EXCEEDED')
    frame=left.copy(deep=True).merge(right.copy(deep=True),left_on=args.left_on,right_on=args.right_on,how=args.how,validate=args.relationship,suffixes=('_left','_right'),sort=False).reset_index(drop=True)
    # pandas may carry equal source attrs into a wider joined frame. Original
    # source labels no longer align after suffixing/combining both schemas.
    frame.attrs['original_columns']=list(frame.columns)
    context.check_size(frame)
    preview=frame.head(min(context.preview_rows,max(1,context.max_cells//max(1,len(labels)))))
    ml=sum(n for k,n in lc.items() if k in rc);mr=sum(n for k,n in rc.items() if k in lc)
    return ToolOutput(JoinResult(columns=[ColumnSpec(name=c,dtype=str(frame[c].dtype)) for c in frame],rows=records(preview),row_count=len(frame),truncated=len(preview)<len(frame),preview_truncated_count=len(frame)-len(preview),left_rows=len(left),right_rows=len(right),left_key_cardinality=len(lc),right_key_cardinality=len(rc),matched_left_rows=ml,unmatched_left_rows=len(left)-ml,matched_right_rows=mr,unmatched_right_rows=len(right)-mr,source_versions={'left':context.dataset_version,'right':right_context.dataset_version},limitations=['Null keys are rejected; key value families and timezone semantics must match without coercion.','Overlapping non-shared columns use _left and _right suffixes.','Conservative worst-case byte estimates may reject a join whose actual allocation would be smaller.','Reproduction requires both immutable source versions, not the left original file alone.']),frame)
