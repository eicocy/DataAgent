"""Exact monetary storage and explicitly separate generic numeric views."""
from decimal import Decimal
import pandas as pd


def decimal_series(series):
    values=series.dropna()
    return not values.empty and values.map(lambda v:isinstance(v,Decimal)).all()


def generic_frame(frame):
    names=[name for name in frame if decimal_series(frame[name])]
    if not names: return frame
    result=frame.copy(deep=True)
    for name in names: result[name]=pd.to_numeric(result[name],errors='raise')
    return result
