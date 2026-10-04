from dataclasses import dataclass, field
import pandas as pd
from app.datasets.profiler import build_profile
from app.datasets.schemas import DatasetSchema, DatasetProfile
from app.analysis.errors import DatasetColumnError, DatasetTypeError, ToolResultError
from app.execution.validators import validate_numeric_series


@dataclass(frozen=True)
class DatasetContext:
    dataset_id: int
    dataset_version: int | None
    frame: pd.DataFrame
    schema: DatasetSchema
    profile: DatasetProfile
    source_ref: str='dataset'
    max_rows: int=100000
    max_columns: int=200
    max_cells: int=40000
    preview_rows: int=100
    correlation_columns: int=50
    max_bytes: int=256*1024*1024
    registry: object | None=field(default=None, compare=False)
    legacy_calculator: object | None=field(default=None, compare=False)
    related_inputs: dict[str, 'DatasetContext']=field(default_factory=dict, compare=False)
    monetary_metadata: dict[str,str]=field(default_factory=dict, compare=False)

    @classmethod
    def from_frame(cls, frame, dataset_id=1, dataset_version=None, **kwargs):
        schema, profile = build_profile(frame)
        return cls(dataset_id, dataset_version, frame, schema, profile, **kwargs)

    def columns(self, names=None, numeric=False):
        names = list(self.frame.columns) if names is None else names
        if len(names) != len(set(names)):
            raise DatasetColumnError('DUPLICATE_COLUMNS')
        for name in names:
            if name not in self.frame.columns:
                raise DatasetColumnError('COLUMN_NOT_FOUND')
            if numeric:
                series = self.frame[name]
                if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
                    raise DatasetTypeError('NUMERIC_COLUMN_REQUIRED')
                validate_numeric_series(series)
        return names

    def check_size(self, frame):
        if len(frame) > self.max_rows or len(frame.columns) > self.max_columns or int(frame.memory_usage(deep=True).sum()) > self.max_bytes:
            raise ToolResultError('RESULT_BUDGET_EXCEEDED')
