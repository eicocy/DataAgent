from app.analysis.models import EDAResult,EDASection
from app.analysis.registry import ToolOutput
from app.analysis.errors import ToolError


class EDAPipeline:
    def execute(self,context,args):
        numeric=[column.name for column in context.schema.columns if column.role=='Metric']
        categorical=[column.name for column in context.schema.columns if column.role=='Dimension']
        time_columns=[column.name for column in context.schema.columns if column.role=='TimeDimension']
        requests=[('dataset_overview',{}),('missing_value_analysis',{}),('duplicate_analysis',{}),('constant_column_analysis',{}),('cardinality_analysis',{})]
        requests.extend([('descriptive_statistics',{'columns':numeric}),('outlier_analysis',{'columns':numeric}),('correlation',{'columns':numeric[:context.correlation_columns]}),('chart_recommendations',{})])
        requests.append(('column_summary',{'columns':time_columns}))
        requests.extend(('value_counts',{'columns':[name],'limit':args.limit}) for name in categorical)
        sections=[]
        for name,parameters in requests:
            if parameters.get('columns')==[]:
                sections.append(EDASection(tool_name=name,status='skipped'));continue
            try:
                output=context.registry.calculate(name,context,parameters)
                sections.append(EDASection(tool_name=name,status='succeeded',data=output.data))
            except ToolError as exc:
                sections.append(EDASection(tool_name=name,status='failed',error_code=exc.code))
        return ToolOutput(EDAResult(sections=sections))
