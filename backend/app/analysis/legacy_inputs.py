from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
MAX_RESULT_ROWS=500

class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_ref: str = 'dataset'


class DatasetInfoArgs(StrictArgs):
    include_samples: bool = False


class PreviewArgs(StrictArgs):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=100)
    columns: list[str] | None = None


class FilterCondition(StrictArgs):
    column: str
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "between", "is_null"]
    value: Any = None


class FilterArgs(StrictArgs):
    conditions: list[FilterCondition] = Field(min_length=1, max_length=20)
    logic: Literal["and", "or"] = "and"
    limit: int = Field(default=100, ge=1, le=MAX_RESULT_ROWS)


class Metric(StrictArgs):
    column: str
    aggregation: Literal["sum", "avg", "min", "max", "count", "count_distinct"]


class AggregateArgs(StrictArgs):
    metrics: list[Metric] = Field(min_length=1, max_length=10)
    date_column: str | None = None
    frequency: Literal["day", "week", "month", "quarter", "year"] | None = None
    filters: list[FilterCondition] = Field(default_factory=list, max_length=20)


class GroupByArgs(StrictArgs):
    group_columns: list[str] = Field(min_length=1, max_length=2)
    value_column: str
    aggregation: Literal["sum", "avg", "min", "max", "count", "count_distinct"] = "sum"
    sort: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=20, ge=1, le=100)
    drop_missing: bool = True


class SortColumn(StrictArgs):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class SortArgs(StrictArgs):
    sort_by: list[SortColumn] = Field(min_length=1, max_length=5)
    columns: list[str] | None = None
    limit: int = Field(default=10, ge=1, le=100)
    filters: list[FilterCondition] = Field(default_factory=list, max_length=20)


class SqlQueryArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=10000)
    max_rows: int = Field(default=100, ge=1, le=MAX_RESULT_ROWS)


class ChartMetric(StrictArgs):
    field: str
    label: str | None = None
    unit: str | None = None


class ChartArgs(StrictArgs):
    source_tool_call_id: str = ''
    type: Literal["bar", "line", "pie", "scatter", "histogram"]
    dimension: str
    metrics: list[ChartMetric] = Field(min_length=1, max_length=4)
    title: str = Field(min_length=1, max_length=100)
    group_column: str | None = None
    selected_groups: list[Any] | None = None
    bins: int = Field(default=10, ge=1, le=50)


class DescribeArgs(StrictArgs):
    columns: list[str] | None = None


class TimeGroupArgs(StrictArgs):
    date_column: str
    group_column: str
    value_column: str
    months: int = Field(default=6, ge=1, le=120)


class GrowthArgs(TimeGroupArgs):
    top_n: int = Field(default=3, ge=1, le=100)
