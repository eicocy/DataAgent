"""Typed compatibility adapters for existing public tool contracts."""
from app.analysis.registry import FunctionTool,ToolMetadata,ToolOutput
from app.analysis.models import LegacyData,LegacyResult,LegacyChartResult,ToolCategory,Permission
from app.analysis.errors import ToolInputError
from app.execution.validators import validate_result
from app.analysis.legacy_inputs import DatasetInfoArgs,PreviewArgs,FilterArgs,AggregateArgs,GroupByArgs,SortArgs,SqlQueryArgs,ChartArgs,DescribeArgs,TimeGroupArgs,GrowthArgs

TOOL_SCHEMAS = [
    ('get_dataset_info','读取当前数据集的字段、类型、行数和缺失概况。',DatasetInfoArgs),
    ('preview_data','预览当前数据集的有限行数据。',PreviewArgs),
    ('filter_data','按字段和值筛选真实数据行。',FilterArgs),
    ('aggregate_data','计算整体指标或按时间频率聚合指标。',AggregateArgs),
    ('group_by_analysis','按一至两个类别字段聚合并排序。',GroupByArgs),
    ('sort_data','按指定字段排序并查看有限行。',SortArgs),
    ('sql_query','执行当前数据集受限只读 SQL；只可查询当前数据集表。',SqlQueryArgs),
    ('generate_chart','根据已经完成的 Tool 结果创建安全 ChartSpec。',ChartArgs),
    ('describe_data','计算数值字段描述统计。',DescribeArgs),
    ('time_group_analysis','以数据最大日期为末月，按分组字段和月份聚合最近六个月指标。',TimeGroupArgs),
    ('growth_analysis','按六个月首末月增长率排名，排除缺失或非正首月。',GrowthArgs),
]


class LegacyAdapter:
    def __init__(self,name): self.name=name
    def execute(self,context,args):
        calculator=context.legacy_calculator
        if calculator is None: raise ToolInputError('COMPATIBILITY_CONTEXT_REQUIRED')
        result=getattr(calculator,self.name)(args)
        frame=calculator._output_frame
        warnings=validate_result(result,frame,result_type=self.name,parameters=args.model_dump())
        typed=LegacyChartResult(payload=result) if self.name=='generate_chart' else LegacyResult(payload=LegacyData.model_validate(result))
        return ToolOutput(typed,frame,warnings)


def register_legacy(registry):
    categories={'get_dataset_info':ToolCategory.DATA,'preview_data':ToolCategory.DATA,'filter_data':ToolCategory.DATA,'sort_data':ToolCategory.DATA,
                'aggregate_data':ToolCategory.AGGREGATION,'group_by_analysis':ToolCategory.AGGREGATION,'describe_data':ToolCategory.STATISTICS,
                'time_group_analysis':ToolCategory.TIME_SERIES,'growth_analysis':ToolCategory.TIME_SERIES,'generate_chart':ToolCategory.VISUALIZATION,'sql_query':ToolCategory.SQL}
    for name,description,schema in TOOL_SCHEMAS:
        permissions=frozenset({Permission.READ_DATA,Permission.READ_DATABASE}) if name=='sql_query' else frozenset({Permission.READ_DATA})
        # Existing compatibility computations already capture a full frame.
        registry.register(FunctionTool(ToolMetadata(name,description,categories[name],(categories[name].value,name),permissions=permissions,provides_frame=name not in {'get_dataset_info','generate_chart'},exposes_rows=name in {'preview_data','filter_data','sort_data','sql_query'}),schema,LegacyChartResult if name=='generate_chart' else LegacyResult,LegacyAdapter(name).execute))
