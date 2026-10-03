import time
import warnings
import re
from dataclasses import dataclass, field, replace
from typing import Callable, Protocol
import pandas as pd
from pydantic import BaseModel, ValidationError
from app.analysis.context import DatasetContext
from app.analysis.models import AnalysisResult, Permission, ToolCategory, TableResult
from app.analysis.errors import ToolError, ToolInputError, ToolExecutionError, ToolResultError
from app.execution.validators import validate_value, validate_numeric_series, ResultWarning


@dataclass(frozen=True)
class ToolMetadata:
    name: str
    description: str
    category: ToolCategory
    capabilities: tuple[str, ...]
    permissions: frozenset[Permission]=frozenset({Permission.READ_DATA})
    modifies_dataset: bool=False
    requires_dataset: bool=True
    timeout_seconds: int=10
    version: str='3.0'
    enabled: bool=True
    exposes_rows: bool=False
    chat_enabled: bool=True
    risk_level: str='read_only'
    parallel_safe: bool=False
    provides_frame: bool=False


@dataclass
class ToolOutput:
    data: BaseModel
    frame: pd.DataFrame | None=None
    warnings: list[ResultWarning]=field(default_factory=list)


class AnalysisTool(Protocol):
    metadata: ToolMetadata
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    def execute(self, context: DatasetContext, parameters: BaseModel) -> ToolOutput: ...


@dataclass(frozen=True)
class FunctionTool:
    metadata: ToolMetadata
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    calculate: Callable
    def execute(self, context, parameters):
        return self.calculate(context, parameters)


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool: AnalysisTool):
        meta = tool.metadata
        if meta.name in self._tools:
            raise ToolInputError('TOOL_ALREADY_REGISTERED')
        if not all(isinstance(schema,type) and issubclass(schema,BaseModel) for schema in (tool.input_schema,tool.output_schema)):
            raise ToolInputError('TOOL_SCHEMA_REQUIRED')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',meta.name) or not meta.description.strip() or not meta.version or not isinstance(meta.category,ToolCategory) or any(not isinstance(p,Permission) for p in meta.permissions) or meta.modifies_dataset != (Permission.TRANSFORM_DATA in meta.permissions) or meta.timeout_seconds <= 0:
            raise ToolInputError('TOOL_METADATA_INVALID')
        self._tools[meta.name] = tool
        return tool

    def get(self, name):
        if name not in self._tools or not self._tools[name].metadata.enabled:
            raise ToolInputError('TOOL_NOT_FOUND')
        return self._tools[name]

    def exists(self, name):
        return name in self._tools and self._tools[name].metadata.enabled

    def list_tools(self):
        return [tool for tool in self._tools.values() if tool.metadata.enabled]

    def list_by_category(self, category):
        return [tool for tool in self.list_tools() if tool.metadata.category == category]

    def search_by_capability(self, capability):
        return [tool for tool in self.list_tools() if capability in tool.metadata.capabilities]

    def validate_input(self, name, parameters):
        try:
            return self.get(name).input_schema.model_validate(parameters)
        except ValidationError as exc:
            raise ToolInputError('TOOL_INPUT_INVALID', details={'fields': ['.'.join(map(str,e['loc'])) for e in exc.errors(include_input=False)[:10]]}) from None

    def get_llm_tool_manifest(self, permissions=frozenset({Permission.READ_DATA})):
        return [dict(name=t.metadata.name, description=t.metadata.description, category=t.metadata.category.value,
                     modifies_dataset=False, provides_frame=t.metadata.provides_frame, parameters=t.input_schema.model_json_schema())
                for t in self.list_tools() if not t.metadata.modifies_dataset and t.metadata.chat_enabled and t.metadata.permissions<=permissions]

    def calculate(self, name, context, parameters, permissions=frozenset({Permission.READ_DATA})):
        tool = self.get(name)
        if not tool.metadata.permissions <= permissions:
            raise ToolInputError('TOOL_PERMISSION_DENIED')
        parsed = self.validate_input(name, parameters)
        from app.analysis.inputs import DataInput
        if isinstance(parsed,DataInput) and 'limit' not in parameters:
            parsed.limit=min(context.preview_rows,500)
        started = time.perf_counter()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', RuntimeWarning)
                output = tool.execute(replace(context, registry=self), parsed)
            if (time.perf_counter() - started) > tool.metadata.timeout_seconds:
                raise ToolExecutionError('TOOL_TIMEOUT')
            return self.validate_output(tool, context, output)
        except ToolError:
            raise
        except ValidationError:
            raise ToolResultError('RESULT_SCHEMA_INVALID') from None
        except RuntimeWarning:
            raise ToolResultError('CALCULATION_OVERFLOW') from None
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise ToolExecutionError(getattr(exc, 'code', 'TOOL_CALCULATION_FAILED')) from None
        except Exception:
            raise ToolExecutionError('TOOL_EXECUTION_FAILED') from None

    def execute(self, name, context, parameters, permissions=frozenset({Permission.READ_DATA})):
        started = time.perf_counter()
        output = self.calculate(name, context, parameters, permissions)
        return AnalysisResult(tool_name=name, data=output.data, dataset_version=context.dataset_version,
                              warnings=output.warnings, execution_time_ms=int((time.perf_counter()-started)*1000),
                              status='partial' if getattr(output.data, 'kind', None)=='eda' and any(s.status=='failed' for s in output.data.sections) else 'succeeded')

    def validate_output(self, tool, context, output):
        output.data = tool.output_schema.model_validate(output.data)
        validate_value(output.data.model_dump())
        if output.frame is not None:
            context.check_size(output.frame)
            for column in output.frame:
                validate_numeric_series(output.frame[column])
        if isinstance(output.data, TableResult):
            names = [column.name for column in output.data.columns]
            if len(names) != len(set(names)) or any(set(row) != set(names) for row in output.data.rows):
                raise ToolResultError('RESULT_SCHEMA_INVALID')
            if output.frame is not None and (output.data.row_count!=len(output.frame) or names!=list(output.frame.columns)):
                raise ToolResultError('RESULT_SCHEMA_INVALID')
        return output
