"""Explicit registrations: adding a tool does not change Agent core logic."""
from functools import partial
from app.analysis.registry import ToolRegistry, ToolMetadata, FunctionTool
from app.analysis.models import ToolCategory, TableResult, OverviewResult, AggregationResult, StatisticsResult, CorrelationResult
from app.analysis.inputs import DataInput, AggregationInput, PivotInput, RankInput, RatioInput, SequenceInput, StatisticsInput
from app.analysis import data_tools as data, aggregation_tools as aggregate, statistics_tools as stats


def build_registry(include_legacy=False):
    registry=ToolRegistry()
    def register(name,category,schema,output,function,raw=False,**metadata):
        metadata['provides_frame'] = issubclass(output,TableResult)
        if name in {'dataset_overview', 'column_summary', 'aggregate', 'multi_aggregate', 'groupby_aggregate', 'descriptive_statistics', 'missing_value_analysis', 'duplicate_analysis', 'constant_column_analysis', 'cardinality_analysis'}:
            metadata['parallel_safe'] = True
        registry.register(FunctionTool(ToolMetadata(name=name,description=name.replace('_',' '),category=category,capabilities=(category.value,name),exposes_rows=raw,**metadata),schema,output,function))
    register('dataset_overview',ToolCategory.DATA,DataInput,OverviewResult,data.overview)
    register('column_summary',ToolCategory.DATA,DataInput,TableResult,data.column_summary)
    for name in ('select_columns','filter_rows','sort_rows','sample_rows'):
        register(name,ToolCategory.DATA,DataInput,TableResult,partial(data.rows_tool,operation=name),True)
    for name in ('unique_values','value_counts'):
        register(name,ToolCategory.DATA,DataInput,TableResult,partial(data.categories,operation=name),name=='unique_values')
    for name in ('aggregate','multi_aggregate','groupby_aggregate'):
        register(name,ToolCategory.AGGREGATION,AggregationInput,AggregationResult,partial(aggregate.aggregate,grouped=name=='groupby_aggregate'))
    register('pivot_table',ToolCategory.AGGREGATION,PivotInput,AggregationResult,aggregate.pivot)
    register('crosstab',ToolCategory.AGGREGATION,PivotInput,AggregationResult,partial(aggregate.pivot,cross=True))
    for name in ('rank','top_n','bottom_n'):
        register(name,ToolCategory.AGGREGATION,RankInput,TableResult,partial(aggregate.rank,operation=name),True)
    register('percentage_share',ToolCategory.AGGREGATION,RatioInput,AggregationResult,aggregate.ratio,True)
    register('weighted_average',ToolCategory.AGGREGATION,RatioInput,StatisticsResult,partial(aggregate.ratio,weighted=True))
    for name in ('cumulative_sum','percentage_change','growth_rate','rolling_statistics'):
        register(name,ToolCategory.TIME_SERIES,SequenceInput,AggregationResult,partial(aggregate.sequence,operation=name),name!='growth_rate')
    for name in ('descriptive_statistics','percentile','quantile','variance','standard_deviation','skewness','kurtosis'):
        register(name,ToolCategory.STATISTICS,StatisticsInput,StatisticsResult,partial(stats.statistics,operation=name))
    register('correlation',ToolCategory.STATISTICS,StatisticsInput,CorrelationResult,stats.correlation)
    register('covariance',ToolCategory.STATISTICS,StatisticsInput,StatisticsResult,partial(stats.correlation,covariance=True))
    from app.analysis.inputs import KPIInput, PeriodComparisonInput, ContributionInput
    from app.analysis.models import KPIResult, PeriodComparisonResult, ContributionResult
    from app.analysis.business_tools import kpi_analysis, period_comparison, contribution_analysis
    register('kpi_analysis',ToolCategory.BUSINESS,KPIInput,KPIResult,kpi_analysis)
    register('period_comparison',ToolCategory.BUSINESS,PeriodComparisonInput,PeriodComparisonResult,period_comparison)
    register('contribution_analysis',ToolCategory.BUSINESS,ContributionInput,ContributionResult,contribution_analysis)
    from app.analysis.inputs import ForecastInput
    from app.analysis.models import ForecastResult
    from app.analysis.forecast_tools import forecast
    register('forecast',ToolCategory.TIME_SERIES,ForecastInput,ForecastResult,forecast,timeout_seconds=30)
    from app.analysis.models import DataQualityResult,CleaningResult,Permission
    from app.analysis.inputs import QualityInput,CleaningInput
    from app.analysis.quality_tools import quality
    from app.analysis.cleaning_tools import clean
    for name in ('missing_value_analysis','duplicate_analysis','constant_column_analysis','cardinality_analysis','invalid_numeric_analysis','invalid_datetime_analysis','infinite_value_analysis','outlier_analysis'):
        register(name,ToolCategory.DATA if name!='outlier_analysis' else ToolCategory.EDA,QualityInput,DataQualityResult,partial(quality,operation=name))
    for name in ('fill_missing_values','drop_missing_rows','remove_duplicates','convert_dtype','parse_datetime','replace_values','normalize_text','rename_columns','outlier_treatment'):
        register(name,ToolCategory.CLEANING,CleaningInput,CleaningResult,partial(clean,operation=name),permissions=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}),modifies_dataset=True,chat_enabled=False,risk_level='transform')
    from app.analysis.inputs import JoinInput,PublishJoinInput,QualityScoreInput,CleaningPlanInput
    from app.analysis.models import JoinResult,QualityScoreResult,CleaningPlanResult
    from app.analysis.join_tools import join_data
    from app.analysis.quality_tools import data_quality_score
    from app.analysis.transformation_tools import cleaning_plan
    register('join_data',ToolCategory.DATA,JoinInput,JoinResult,join_data,True)
    register('publish_join',ToolCategory.CLEANING,PublishJoinInput,JoinResult,join_data,True,permissions=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}),modifies_dataset=True,chat_enabled=False,risk_level='transform')
    register('data_quality_score',ToolCategory.DATA,QualityScoreInput,QualityScoreResult,data_quality_score,parallel_safe=True)
    register('cleaning_plan',ToolCategory.CLEANING,CleaningPlanInput,CleaningPlanResult,cleaning_plan,permissions=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}),modifies_dataset=True,chat_enabled=False,risk_level='transform',timeout_seconds=30)
    from app.analysis.models import ChartResult,RecommendationResult,EDAResult
    from app.analysis.inputs import ChartInput
    from app.analysis.chart_tools import chart,recommend
    from app.analysis.eda import EDAPipeline
    register('chart_spec',ToolCategory.VISUALIZATION,ChartInput,ChartResult,chart,chat_enabled=False)
    register('chart_recommendations',ToolCategory.VISUALIZATION,DataInput,RecommendationResult,recommend)
    register('eda',ToolCategory.EDA,DataInput,EDAResult,EDAPipeline().execute,timeout_seconds=30)
    if include_legacy:
        from app.analysis.legacy_adapters import register_legacy
        register_legacy(registry)
    return registry
