import json
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.sandbox.validator import validate_code

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class InputSnapshot(StrictModel):
    alias: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,31}$')
    dataset_id: int = Field(gt=0)
    dataset_version_id: int = Field(gt=0)
    columns: list[str] = Field(min_length=1, max_length=256)
    rows: list[dict] = Field(max_length=50000)
    dtypes: dict[str, Literal['integer','decimal','float','boolean','string','datetime','date']] = Field(default_factory=dict)

    @model_validator(mode='after')
    def shape(self):
        names = set(self.columns)
        if len(names) != len(self.columns) or any(not name or len(name) > 256 for name in names) or not set(self.dtypes) <= names:
            raise ValueError('SANDBOX_INPUT_SCHEMA')
        if any(set(row) != names for row in self.rows):
            raise ValueError('SANDBOX_INPUT_SCHEMA')
        for row in self.rows:
            for value in row.values():
                if type(value) not in (str, int, float, bool, type(None)) or isinstance(value, float) and not math.isfinite(value):
                    raise ValueError('SANDBOX_INPUT_VALUE')
        return self


class RunRequest(StrictModel):
    protocol: Literal['1.0'] = '1.0'
    code: str
    owner: str = Field(pattern=r'^[a-f0-9]{64}$')
    inputs: list[InputSnapshot] = Field(min_length=1, max_length=10)
    timeout_seconds: int = Field(default=60, ge=1, le=60)

    @model_validator(mode='after')
    def validate(self):
        validate_code(self.code)
        if len({item.alias for item in self.inputs}) != len(self.inputs):
            raise ValueError('SANDBOX_INPUT_SCHEMA')
        if len(json.dumps(self.model_dump(), ensure_ascii=False, allow_nan=False).encode()) > MAX_INPUT_BYTES:
            raise ValueError('SANDBOX_INPUT_LIMIT')
        return self
