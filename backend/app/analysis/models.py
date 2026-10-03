from enum import Enum
from typing import Literal, TypeAlias
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.execution.validators import ResultWarning
from app.tools.schemas import ChartSpec as LegacyChartSpec


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class ToolCategory(str, Enum):
    DATA='data'; CLEANING='cleaning'; AGGREGATION='aggregation'; STATISTICS='statistics'
    EDA='eda'; TIME_SERIES='time_series'; BUSINESS='business'; VISUALIZATION='visualization'
    MACHINE_LEARNING='machine_learning'; SQL='sql'; REPORT='report'; FILE='file'


class Permission(str, Enum):
    READ_DATA='read_data'; TRANSFORM_DATA='transform_data'; GENERATE_FILE='generate_file'
    EXECUTE_CODE='execute_code'; READ_DATABASE='read_database'


Scalar: TypeAlias = str | int | float | bool | None


class LegacyDatasetInfo(StrictModel):
    id: int
    name: str
    row_count: int | None
    column_count: int
    file_type: str


class LegacyColumnInfo(StrictModel):
    name: str
    label: str
    data_type: str
    nullable: bool
    missing_count: int
    unique_count: int | None
    sample_values: list[Scalar] | None=None


class LegacyFilterCondition(StrictModel):
    source_ref: str='dataset'
    column: str
    operator: str
    value: Scalar | list[Scalar]=None


class LegacyData(StrictModel):
    columns: list[str] | list[LegacyColumnInfo] | None=None
    rows: list[dict[str,Scalar]] | None=None
    row_count: int | None=None
    truncated: bool | None=None
    metric_values: dict[str,Scalar] | None=None
    preview_rows: list[dict[str,Scalar]] | None=None
    sorted_rows: list[dict[str,Scalar]] | None=None
    matched_count: int | None=None
    total_after_filter: int | None=None
    group_count: int | None=None
    value_label: str | None=None
    frequency: str | None=None
    duration_ms: int | None=None
    selected_groups: list[Scalar] | None=None
    excluded_groups: list[Scalar] | None=None
    excluded_count: int | None=None
    invalid_date_count: int | None=None
    window_start: str | None=None
    window_end: str | None=None
    dataset: LegacyDatasetInfo | None=None
    missing_summary: dict[str,int] | None=None
    offset: int | None=None
    limit: int | None=None
    total_rows: int | None=None
    applied_conditions: list[LegacyFilterCondition] | None=None


class LegacyResult(StrictModel):
    kind: Literal['legacy']='legacy'
    payload: LegacyData


class LegacyChartResult(StrictModel):
    kind: Literal['legacy_chart']='legacy_chart'
    # The established frontend contract stays fully typed.
    payload: LegacyChartSpec


class ColumnSpec(StrictModel):
    name: str
    dtype: str
    label: str | None = None


class TableResult(StrictModel):
    kind: Literal['table']='table'
    columns: list[ColumnSpec]
    rows: list[dict[str, Scalar]]
    row_count: int = Field(ge=0)
    truncated: bool=False
    @model_validator(mode='after')
    def shape(self):
        names=[column.name for column in self.columns]
        if len(names)!=len(set(names)) or any(set(row)!=set(names) for row in self.rows):
            raise ValueError('table columns and rows disagree')
        if self.row_count<len(self.rows) or self.truncated!=(self.row_count>len(self.rows)):
            raise ValueError('table preview and total disagree')
        return self


class AggregationResult(TableResult):
    kind: Literal['aggregation']='aggregation'


class StatisticValue(StrictModel):
    column: str
    statistic: str
    value: float | int | None
    valid_count: int = Field(ge=0)
    dimensions: dict[str,Scalar]=Field(default_factory=dict)
    status: Literal['valid', 'no_valid_samples', 'insufficient_samples', 'constant', 'zero_denominator']='valid'
    @model_validator(mode='after')
    def definition(self):
        if (self.value is not None)!=(self.status=='valid'):
            raise ValueError('statistic status and value disagree')
        return self


class StatisticsResult(StrictModel):
    kind: Literal['statistics']='statistics'
    values: list[StatisticValue]


class CorrelationPair(StrictModel):
    x: str
    y: str
    coefficient: float | None = Field(default=None, ge=-1, le=1)
    sample_size: int = Field(ge=0)
    status: Literal['valid','insufficient_samples','constant']
    @model_validator(mode='after')
    def definition(self):
        if (self.coefficient is not None)!=(self.status=='valid'):
            raise ValueError('correlation status and value disagree')
        return self


class CorrelationResult(StrictModel):
    kind: Literal['correlation']='correlation'
    method: Literal['pearson','spearman']
    columns: list[str]
    matrix: list[list[float | None]]
    pairs: list[CorrelationPair]
    @model_validator(mode='after')
    def shape(self):
        size=len(self.columns)
        if len(set(self.columns))!=size or len(self.matrix)!=size or any(len(row)!=size for row in self.matrix):
            raise ValueError('correlation matrix shape invalid')
        expected={(self.columns[i],self.columns[j]) for i in range(size) for j in range(i,size)}
        if len(self.pairs)!=len(expected) or {(p.x,p.y) for p in self.pairs}!=expected:
            raise ValueError('correlation pairs incomplete')
        for pair in self.pairs:
            i,j=self.columns.index(pair.x),self.columns.index(pair.y)
            if self.matrix[i][j]!=pair.coefficient or self.matrix[j][i]!=pair.coefficient:
                raise ValueError('correlation matrix and pairs disagree')
        return self


class QualityFinding(StrictModel):
    column: str | None=None
    count: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)
    row_refs: list[int] = Field(default_factory=list)
    lower: float | None=None
    upper: float | None=None
    status: str='valid'


class DataQualityResult(StrictModel):
    kind: Literal['quality']='quality'
    check: str
    findings: list[QualityFinding]


class CleaningResult(StrictModel):
    kind: Literal['cleaning']='cleaning'
    operation: str
    source_version: int | None
    output_version: int | None=None
    row_count: int
    column_count: int
    changed_cells: int=0
    added_missing: int=0


class ChartPoint(StrictModel):
    x: Scalar=None
    y: float | None=None
    values: list[float | None]=Field(default_factory=list)


class ChartSeries(StrictModel):
    name: str
    points: list[ChartPoint]=Field(max_length=500)


class ChartOptions(StrictModel):
    stacked: bool=False
    show_legend: bool=True


class ChartResult(StrictModel):
    kind: Literal['chart']='chart'
    version: Literal['2.0']='2.0'
    chart_type: Literal['line','bar','scatter','histogram','boxplot','box','heatmap','pie','donut','area','waterfall','funnel']
    title: str=Field(default='Analysis', max_length=100)
    x: str | None=None
    y: list[str]=Field(default_factory=list)
    series: list[ChartSeries]=Field(max_length=80)
    options: ChartOptions=Field(default_factory=ChartOptions)


class ChartRecommendation(StrictModel):
    chart_type: Literal['line','bar','scatter','histogram','boxplot','box','heatmap','pie','donut','area','waterfall','funnel']
    columns: list[str]
    reason: str


class RecommendationResult(StrictModel):
    kind: Literal['recommendations']='recommendations'
    recommendations: list[ChartRecommendation]


class OverviewResult(StrictModel):
    kind: Literal['overview']='overview'
    row_count: int
    column_count: int
    memory_bytes: int
    columns: list[ColumnSpec]


class ForecastMetrics(StrictModel):
    mae: float=Field(ge=0)
    rmse: float=Field(ge=0)
    mape: float | None=Field(default=None, ge=0)
    mape_coverage: float=Field(ge=0, le=1)
    mape_explanation: str


class ForecastFold(StrictModel):
    fold_id: int=Field(ge=0, le=2)
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_size: int=Field(ge=3)
    test_size: int=Field(ge=1, le=24)


class ForecastFoldScore(StrictModel):
    fold_id: int=Field(ge=0, le=2)
    predictions: list[float]=Field(min_length=1, max_length=24)
    metrics: ForecastMetrics


class ForecastCandidate(StrictModel):
    model: Literal['naive','moving_average','linear_trend','exponential_smoothing','arima']
    status: Literal['succeeded','failed','skipped']
    metrics: ForecastMetrics | None=None
    folds: list[ForecastFoldScore]=Field(default_factory=list, max_length=3)
    error_code: str | None=None
    validation_error_code: str | None=None
    final_fit_error_code: str | None=None
    @model_validator(mode='after')
    def consistency(self):
        if self.status == 'succeeded' and (self.metrics is None or len(self.folds) != 3 or self.error_code is not None):
            raise ValueError('successful candidate requires three fold scores')
        if self.status != 'succeeded' and self.error_code is None:
            raise ValueError('unsuccessful candidate requires a reason')
        return self


class ForecastPoint(StrictModel):
    time: str
    value: float
    lower: float
    upper: float
    @model_validator(mode='after')
    def bounds(self):
        if not self.lower <= self.value <= self.upper:
            raise ValueError('forecast interval must contain the point')
        return self


class ForecastUncertainty(StrictModel):
    method: Literal['held_out_absolute_residual_quantile']='held_out_absolute_residual_quantile'
    residual_quantile: float=Field(gt=0, lt=1)
    residual_count: int=Field(ge=3)
    calibrated: Literal[False]=False
    limitations: str


class ForecastResult(StrictModel):
    kind: Literal['forecast']='forecast'
    dataset_id: int
    dataset_version: int | None
    source_ref: str
    time_column: str
    target_column: str
    aggregation: Literal['sum','mean','median','min','max']
    granularity: Literal['day','week','month','quarter','year']
    frequency: str
    history_start: str
    history_end: str
    observation_count: int=Field(ge=12, le=1000)
    input_row_count: int=Field(ge=12)
    horizon: int=Field(ge=1, le=24)
    selected_model: str
    metrics: ForecastMetrics
    folds: list[ForecastFold]=Field(min_length=3, max_length=3)
    baseline: ForecastCandidate
    candidates: list[ForecastCandidate]=Field(min_length=5, max_length=5)
    points: list[ForecastPoint]=Field(min_length=1, max_length=24)
    uncertainty: ForecastUncertainty
    limitations: list[str]
    @model_validator(mode='after')
    def consistency(self):
        selected=[c for c in self.candidates if c.model == self.selected_model and c.status == 'succeeded']
        if len(selected)!=1 or selected[0].metrics != self.metrics or len(self.points)!=self.horizon:
            raise ValueError('forecast selection or horizon disagrees')
        if self.baseline.model != 'naive' or self.baseline != self.candidates[0]:
            raise ValueError('forecast must retain its naive baseline')
        if len({c.model for c in self.candidates}) != 5 or [f.fold_id for f in self.folds] != [0,1,2]:
            raise ValueError('forecast candidates or folds incomplete')
        return self


SimpleResult = TableResult | AggregationResult | StatisticsResult | CorrelationResult | DataQualityResult | CleaningResult | ChartResult | RecommendationResult | OverviewResult | LegacyResult | LegacyChartResult | ForecastResult


class EDASection(StrictModel):
    tool_name: str
    status: Literal['succeeded','failed','skipped']
    data: SimpleResult | None=None
    error_code: str | None=None


class EDAResult(StrictModel):
    kind: Literal['eda']='eda'
    sections: list[EDASection]


class AnalysisResult(StrictModel):
    tool_name: str
    status: Literal['succeeded','partial','failed']='succeeded'
    data: SimpleResult | EDAResult
    dataset_version: int | None=None
    warnings: list[ResultWarning]=Field(default_factory=list)
    execution_time_ms: int=0
    artifact_ref: int | None=None


class ToolExecutionRequest(StrictModel):
    tool_name: str
    dataset_id: int=Field(gt=0)
    dataset_version: int | None=Field(default=None, gt=0)
    parameters: dict=Field(default_factory=dict)
    request_id: str=Field(min_length=1, max_length=64)
    task_id: int | None=None
