from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.execution.validators import ResultWarning


class ToolResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['succeeded', 'failed'] = 'succeeded'
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str = ''
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    execution_time_ms: int = 0
    artifact_ref: str | None = None
    warnings: list[ResultWarning] = Field(default_factory=list)


class ChartDimension(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    label: str
    type: Literal['category', 'time', 'value']


class ChartMetricSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    label: str
    aggregation: str
    unit: str | None = None


class ChartPoint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: Any
    value: float | list[float] | None


class ChartSeries(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    data: list[ChartPoint] = Field(max_length=500)


class ChartSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['1.0'] = '1.0'
    type: Literal['bar', 'line', 'pie', 'scatter', 'histogram']
    title: str = Field(min_length=1, max_length=100)
    dimension: ChartDimension
    metrics: list[ChartMetricSpec] = Field(min_length=1, max_length=4)
    series: list[ChartSeries] = Field(min_length=1, max_length=80)
    source_tool_call_id: str
    notes: list[str] = Field(default_factory=list)
