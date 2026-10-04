from app.analysis.context import DatasetContext
from app.analysis.inputs import QualityScoreInput
from app.analysis.models import CleaningPlanResult,Permission
from app.analysis.registry import ToolOutput
from app.analysis.quality_tools import data_quality_score


def cleaning_plan(context,args):
    context.check_size(context.frame)
    frame=context.frame.copy(deep=True)
    before=data_quality_score(context,QualityScoreInput()).data
    steps=[];warnings=[]
    for step in args.operations:
        intermediate=DatasetContext.from_frame(frame,context.dataset_id,context.dataset_version,max_rows=context.max_rows,max_columns=context.max_columns,max_bytes=context.max_bytes,preview_rows=context.preview_rows)
        output=context.registry.calculate(step.tool,intermediate,step.parameters,frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA}))
        frame=output.frame;steps.append(output.data);warnings.extend(output.warnings)
    after=data_quality_score(DatasetContext.from_frame(frame),QualityScoreInput()).data
    return ToolOutput(CleaningPlanResult(operation='cleaning_plan',source_version=context.dataset_version,row_count=len(frame),column_count=len(frame.columns),before_rows=len(context.frame),before_quality=before,after_quality=after,steps=steps,changed_cells=sum(s.changed_cells for s in steps),added_missing=sum(s.added_missing for s in steps)),frame,warnings)
