import time
from dataclasses import dataclass
from typing import Callable
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.analysis.models import AnalysisResult, Permission
from app.analysis.errors import ToolInputError, ToolExecutionError


@dataclass(frozen=True)
class ExecutionContext:
    user_id: int
    dataset: DatasetContext
    permissions: frozenset[Permission]=frozenset({Permission.READ_DATA})
    deadline: float | None=None
    lease_check: Callable | None=None
    publish: Callable | None=None
    persist: Callable | None=None
    capture_frame: Callable | None=None
    stage: Callable | None=None


class AnalysisEngine:
    def __init__(self,registry=None):
        self.registry=registry or build_registry(include_legacy=True)

    def execute(self,request,context: ExecutionContext):
        dataset=context.dataset
        if request.dataset_id!=dataset.dataset_id or request.dataset_version not in (None,dataset.dataset_version):
            raise ToolInputError('DATASET_CONTEXT_MISMATCH')
        tool=self.registry.get(request.tool_name)
        if tool.metadata.modifies_dataset and context.publish is None:
            raise ToolInputError('TRANSFORM_PUBLISHER_REQUIRED')
        def check():
            if context.deadline is not None and time.monotonic()>=context.deadline:
                raise ToolExecutionError('TOOL_TIMEOUT')
            if context.lease_check: context.lease_check()
        check()
        started=time.perf_counter()
        if context.stage: context.stage(min(tool.metadata.timeout_seconds,max(.001,context.deadline-time.monotonic())) if context.deadline else tool.metadata.timeout_seconds)
        output=self.registry.calculate(request.tool_name,dataset,request.parameters,context.permissions)
        check()
        if tool.metadata.modifies_dataset:
            output.data.output_version=context.publish(output.frame,request.parameters,request.tool_name)
        result=AnalysisResult(tool_name=request.tool_name,data=output.data,dataset_version=dataset.dataset_version,
                              warnings=output.warnings,execution_time_ms=int((time.perf_counter()-started)*1000),
                              status='partial' if output.data.kind=='eda' and any(s.status=='failed' for s in output.data.sections) else 'succeeded')
        if context.capture_frame: context.capture_frame(output.frame)
        if context.persist: result=context.persist(result,output.frame)
        check()
        return result
