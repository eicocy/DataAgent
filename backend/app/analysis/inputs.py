from enum import Enum
from typing import Literal
from pydantic import Field, model_validator
from app.analysis.models import StrictModel, Scalar, ChartOptions


class Aggregation(str, Enum):
    SUM='sum'; MEAN='mean'; MEDIAN='median'; COUNT='count'; NUNIQUE='nunique'
    MIN='min'; MAX='max'; STD='std'; VAR='var'; FIRST='first'; LAST='last'


class FilterCondition(StrictModel):
    column: str
    operator: Literal['eq','ne','gt','gte','lt','lte','in','not_in','contains','between','is_null','not_null']
    value: Scalar | list[Scalar]=None


class SortConfig(StrictModel):
    column: str
    direction: Literal['asc','desc']='asc'


class DataInput(StrictModel):
    columns: list[str] | None=None
    filters: list[FilterCondition]=Field(default_factory=list, max_length=20)
    logic: Literal['and','or']='and'
    sort: list[SortConfig]=Field(default_factory=list, max_length=5)
    limit: int=Field(default=100, ge=1, le=500)
    offset: int=Field(default=0, ge=0)
    seed: int=0
    drop_missing: bool=True


class MetricAggregation(StrictModel):
    column: str
    aggregation: Aggregation
    alias: str | None=Field(default=None, min_length=1, max_length=128)


class AggregationInput(DataInput):
    metrics: list[MetricAggregation]=Field(min_length=1, max_length=20)
    dimensions: list[str]=Field(default_factory=list, max_length=10)


class PivotInput(DataInput):
    index: list[str]=Field(min_length=1, max_length=5)
    column: str
    value: str | None=None
    aggregation: Aggregation='sum'
    fill_value: float | None=None
    margins: bool=False


class SequenceInput(DataInput):
    column: str
    group_by: list[str]=Field(default_factory=list, max_length=5)
    order_by: list[SortConfig]=Field(min_length=1, max_length=5)
    periods: int=Field(default=1, ge=1, le=10000)
    window: int=Field(default=3, ge=1, le=10000)
    min_periods: int | None=Field(default=None, ge=1)
    aggregation: Literal['sum','mean','median','min','max','std','var']='mean'
    @model_validator(mode='after')
    def window_bounds(self):
        if self.min_periods is not None and self.min_periods > self.window:
            raise ValueError('min_periods exceeds window')
        return self


class RatioInput(DataInput):
    column: str
    group_by: list[str]=Field(default_factory=list)
    weight_column: str | None=None


class RankInput(DataInput):
    column: str
    group_by: list[str]=Field(default_factory=list)
    direction: Literal['asc','desc']='desc'
    method: Literal['dense','min','max','first','average']='dense'
    n: int=Field(default=10, ge=1, le=500)


class StatisticsInput(StrictModel):
    columns: list[str] | None=None
    q: float=Field(default=.5, ge=0, le=1)
    percentile: float=Field(default=50, ge=0, le=100)
    ddof: int=Field(default=1, ge=0, le=1)
    method: Literal['pearson','spearman']='pearson'
    min_samples: int=Field(default=3, ge=2)


class ForecastInput(StrictModel):
    time_column: str=Field(min_length=1)
    target_column: str=Field(min_length=1)
    horizon: int=Field(ge=1, le=24, strict=True)
    granularity: Literal['day','week','month','quarter','year']
    aggregation: Literal['sum','mean','median','min','max']


class QualityInput(DataInput):
    method: Literal['iqr','zscore']='iqr'
    threshold: float | None=Field(default=None, gt=0)
    datetime_format: str | None=None


class CleaningInput(QualityInput):
    columns: list[str]=Field(min_length=1)
    strategy: Literal['constant','mean','median','mode','forward','backward','clip','drop','null']='constant'
    value: Scalar=None
    dtype: Literal['integer','decimal','string','boolean','datetime'] | None=None
    errors: Literal['raise','coerce']='raise'
    keep: Literal['first','last','none']='first'
    how: Literal['any','all']='any'
    replacements: dict[str, Scalar]=Field(default_factory=dict)
    names: dict[str, str]=Field(default_factory=dict)
    text_operations: list[Literal['strip','lower','upper','casefold','collapse_whitespace']]=Field(default_factory=lambda:['strip'])


class ChartInput(DataInput):
    chart_type: Literal['line','bar','scatter','histogram','boxplot','box','heatmap','pie','donut','area','waterfall','funnel']
    x: str | None=None
    y: list[str]=Field(min_length=1, max_length=50)
    group_by: str | None=None
    title: str=Field(default='Analysis', min_length=1, max_length=100)
    bins: int=Field(default=10, ge=1, le=50)
    options: ChartOptions=Field(default_factory=ChartOptions)


class BusinessInput(StrictModel):
    currency: str | None=Field(default=None, min_length=1, max_length=32)
    unit: str | None=Field(default=None, min_length=1, max_length=32)
    currency_column: str | None=None
    unit_column: str | None=None
    filters: list[FilterCondition]=Field(default_factory=list, max_length=20)


class KPIInput(BusinessInput):
    metrics: dict[Literal['revenue','gmv','cost','profit','operating_expense','budget','actual'], str]=Field(default_factory=dict, max_length=7)
    order_id_column: str | None=None
    customer_id_column: str | None=None
    product_id_column: str | None=None


class PeriodComparisonInput(BusinessInput):
    value_kind: Literal['money','quantity']='money'
    date_column: str=Field(min_length=1)
    value_column: str=Field(min_length=1)
    granularity: Literal['day','month','quarter','year']
    start: str=Field(min_length=1)
    end: str=Field(min_length=1)
    comparison: Literal['yoy','mom','custom']
    previous_start: str | None=None
    previous_end: str | None=None


class ContributionInput(PeriodComparisonInput):
    dimension: str=Field(min_length=1)


class JoinInput(StrictModel):
    right_alias: str=Field(min_length=1, max_length=64)
    left_on: list[str]=Field(min_length=1,max_length=10)
    right_on: list[str]=Field(min_length=1,max_length=10)
    how: Literal['inner','left']
    relationship: Literal['one_to_one','many_to_one','one_to_many']
    @model_validator(mode='after')
    def keys(self):
        if len(self.left_on)!=len(self.right_on) or len(set(self.left_on))!=len(self.left_on) or len(set(self.right_on))!=len(self.right_on):
            raise ValueError('join keys must be aligned and unique')
        return self


class PublishJoinInput(JoinInput):
    right_alias: Literal['right']='right'
    right_dataset_id: int=Field(gt=0,strict=True)
    right_version_id: int=Field(gt=0,strict=True)


class FieldRule(StrictModel):
    type: Literal['numeric','datetime']
    minimum: float | None=None
    maximum: float | None=None
    datetime_format: str | None=None
    @model_validator(mode='after')
    def bounds(self):
        if self.minimum is not None and self.maximum is not None and self.minimum>self.maximum:
            raise ValueError('minimum exceeds maximum')
        if self.type!='numeric' and (self.minimum is not None or self.maximum is not None):
            raise ValueError('range requires numeric type')
        return self


class QualityScoreInput(StrictModel):
    field_rules: dict[str,FieldRule]=Field(default_factory=dict,max_length=200)
    limit: int=Field(default=20,ge=1,le=100)


class CleaningStep(StrictModel):
    tool: Literal['rename_columns','remove_duplicates','drop_missing_rows','fill_missing_values','convert_dtype','parse_datetime','replace_values','normalize_text','outlier_treatment']
    parameters: dict
    @model_validator(mode='after')
    def explicit_arguments(self):
        parsed=CleaningInput.model_validate(self.parameters)
        requirements={'remove_duplicates':['keep'],'drop_missing_rows':['how'],'fill_missing_values':['strategy'], 'outlier_treatment':['strategy','method'],'normalize_text':['text_operations'],'replace_values':['replacements'],'rename_columns':['names'],'convert_dtype':['dtype']}
        if any(key not in self.parameters for key in requirements.get(self.tool,[])):
            raise ValueError('explicit operation parameters required')
        if self.tool=='fill_missing_values' and parsed.strategy=='constant' and 'value' not in self.parameters:
            raise ValueError('explicit fill value required')
        return self


class CleaningPlanInput(StrictModel):
    operations: list[CleaningStep]=Field(min_length=1,max_length=8)
