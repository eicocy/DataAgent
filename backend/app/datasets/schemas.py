from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class SchemaColumn(BaseModel):
    name: str
    original_name: str
    dtype: str
    storage_type: Literal['integer','decimal','boolean','date','datetime','string'] | None=None
    semantic_type: Literal['Numeric', 'Categorical', 'Datetime', 'Boolean', 'Identifier', 'Text', 'Unknown']
    role: Literal['Metric', 'Dimension', 'TimeDimension', 'Identifier']
    confidence: float = Field(ge=0, le=1)
    inference_reason: str

class DatasetSchema(BaseModel):
    schema_version: str = '1.0'
    columns: list[SchemaColumn]

class NumericStatistics(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    status: Literal['valid', 'no_valid_samples', 'overflow']
    valid_count: int
    mean: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    median: float | None = None
    std: float | None = None
    quantiles: dict[str, float | None] = Field(default_factory=dict)

class ColumnProfile(BaseModel):
    name: str
    missing_count: int
    missing_rate: float
    unique_count: int
    unique_rate: float
    non_finite_count: int = 0
    numeric: NumericStatistics | None = None

class DatasetProfile(BaseModel):
    schema_version: str = '1.0'
    row_count: int
    column_count: int
    memory_bytes: int
    columns: list[ColumnProfile]
    warnings: list[dict] = Field(default_factory=list)


def column_storage_type(column: SchemaColumn) -> str:
    """Restore older version types exclusively from that version's schema."""
    import pandas as pd
    if column.storage_type: return column.storage_type
    dtype=pd.api.types.pandas_dtype(column.dtype)
    if pd.api.types.is_datetime64_any_dtype(dtype): return 'datetime'
    if pd.api.types.is_bool_dtype(dtype): return 'boolean'
    if pd.api.types.is_integer_dtype(dtype): return 'integer'
    if pd.api.types.is_numeric_dtype(dtype): return 'decimal'
    if column.semantic_type=='Datetime': return 'datetime'
    return 'string'
