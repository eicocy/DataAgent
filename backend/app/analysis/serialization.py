import math
from datetime import date, datetime
from decimal import Decimal
import pandas as pd
from app.execution.validators import ResultValidationError


def json_value(value):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if hasattr(value,'item'):
        value=value.item()
    if isinstance(value,(pd.Timestamp,datetime,date)):
        return value.isoformat()
    if isinstance(value,Decimal):
        if not value.is_finite():
            raise ResultValidationError('RESULT_NON_FINITE')
        return str(value)
    if isinstance(value,float) and not math.isfinite(value):
        if math.isnan(value): return None
        raise ResultValidationError('RESULT_NON_FINITE')
    if isinstance(value,(str,int,float,bool)): return value
    return str(value)


def records(frame):
    return [{str(key):json_value(value) for key,value in row.items()} for row in frame.to_dict(orient='records')]
