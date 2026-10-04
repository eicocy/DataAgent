from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from app.models import Dataset, DatasetColumn
from app.tools.schemas import ToolResult


from app.analysis.legacy_inputs import *
from app.analysis.legacy_calculations import LegacyCalculations
from app.analysis.legacy_adapters import TOOL_SCHEMAS
from app.analysis.sql_safety import validate_readonly_query

from app.analysis.serialization import json_value as _json_value, records as _records
from app.analysis.operations import aggregate_series


def _aggregation(series, operation):
    return aggregate_series(series, {'avg': 'mean', 'count_distinct': 'nunique'}.get(operation, operation))


class DatasetTools(LegacyCalculations):
    """Validated, real computations over a single dataset projection."""

    def __init__(
        self,
        dataset: Dataset,
        columns: list[DatasetColumn],
        writer_bind: Engine,
        readonly_bind: Engine | None,
    ):
        self.dataset = dataset
        self.columns = columns
        self.writer_bind = writer_bind
        self.readonly_bind = readonly_bind
        self.schema = {column.name: column for column in columns}
        self.frame: pd.DataFrame | None = None
        self.call_results: dict[str, dict[str, Any]] = {}
        self.frame_results: dict[str, pd.DataFrame] = {}
        self._output_frame: pd.DataFrame | None = None
        self._active_frame: pd.DataFrame | None = None

    @classmethod
    def from_frame(cls, dataset_id: int, rows: list[dict[str, Any]]) -> DatasetTools:
        frame = pd.DataFrame(rows)
        obj = object.__new__(cls)
        obj.dataset = type("DatasetRef", (), {"id": dataset_id, "original_name": "test.csv", "row_count": len(rows), "column_count": len(frame.columns), "file_type": "csv"})()
        obj.columns = []
        obj.schema = {}
        for position, name in enumerate(frame.columns):
            series = frame[name]
            dtype = "integer" if pd.api.types.is_integer_dtype(series.dtype) else "decimal" if pd.api.types.is_numeric_dtype(series.dtype) else "string"
            column = type("DatasetColumnRef", (), {"name": str(name), "original_name": str(name), "data_type": dtype, "nullable": bool(series.isna().any()), "missing_count": int(series.isna().sum()), "unique_count": int(series.nunique(dropna=True)), "sample_values_json": []})()
            obj.columns.append(column)
            obj.schema[str(name)] = column
        obj.writer_bind = None
        obj.readonly_bind = None
        obj.frame = frame
        obj.call_results = {}
        obj.frame_results = {}
        obj._output_frame = None
        obj._active_frame = None
        return obj

    def _frame(self) -> pd.DataFrame:
        if self._active_frame is not None:
            return self._active_frame
        if self.frame is None:
            from app.services.datasets import DatasetService
            self.frame = DatasetService(None, self.writer_bind).load_frame(self.dataset, self.columns)
        return self.frame

    def frame_for(self, name, reference='dataset'):
        """Serial-only owned loader; monetary chains never use normalized copies."""
        exact=name in {'kpi_analysis','period_comparison','contribution_analysis','join_data','select_columns','filter_rows','sort_rows','sample_rows','select_data','filter_data','sort_data'}
        if name=='forecast' and hasattr(self,'semantic_mappings'):
            # Known monetary forecast must aggregate exact buckets before its
            # explicitly approximate numerical model is fitted.
            exact=True
        if reference!='dataset':
            frame=self.frame_results[reference]
            if exact: return frame
            from app.analysis.precision import generic_frame
            return generic_frame(frame)
        if exact and getattr(self,'exact_frame_loader',None):
            if not hasattr(self,'_exact_frame'):
                frame=self.exact_frame_loader()
                self.check_frame_budget(frame)
                self._exact_frame=frame
            return self._exact_frame
        frame=self._frame()
        if exact: return frame
        from app.analysis.precision import generic_frame
        return generic_frame(frame)

    def check_frame_budget(self,extra=None,reserved_bytes=0):
        from app.config import get_settings
        adapters=getattr(self,'budget_adapters',[self])
        frames=[*(extra if isinstance(extra,list) else [extra]),*self.frame_results.values()]
        frames.extend(getattr(self,'pending_frames',[]))
        for adapter in adapters:
            frames.extend([adapter.frame,getattr(adapter,'_exact_frame',None)])
            frames.extend(context.frame for context in getattr(adapter,'_contexts',{}).values())
        seen=set();memory=reserved_bytes
        for frame in frames:
            if frame is not None and id(frame) not in seen:
                seen.add(id(frame));memory+=int(frame.memory_usage(deep=True).sum())
        if memory>get_settings().dataframe_max_bytes: raise ValueError('WORKSPACE_MEMORY_BUDGET')

    def context_for_tool(self,name,reference='dataset'):
        from app.analysis.context import DatasetContext
        from app.config import get_settings
        frame=self.frame_for(name,reference);settings=get_settings()
        self.check_frame_budget(frame)
        budgets=dict(source_ref=reference,max_rows=settings.tool_max_rows,max_columns=settings.tool_max_columns,
            max_cells=settings.tool_max_cells,preview_rows=settings.tool_preview_rows,max_bytes=settings.dataframe_max_bytes,
            correlation_columns=settings.tool_correlation_columns)
        if reference=='dataset' and getattr(self,'version_schema',None):
            return DatasetContext(self.dataset.id,self.dataset_version_id,frame,self.version_schema,self.version_profile,**budgets)
        return DatasetContext.from_frame(frame,self.dataset.id,getattr(self,'dataset_version_id',None),**budgets)


    def run(self,name,args):
        return self.execute(name,args.model_dump(),source_ref=getattr(args,'source_ref','dataset')).data

    def execute(self, name, arguments, source_ref='dataset', call_id=''):
        from dataclasses import replace
        from app.analysis.catalog import build_registry
        from app.analysis.context import DatasetContext
        from app.analysis.engine import AnalysisEngine, ExecutionContext
        from app.analysis.models import ToolExecutionRequest
        from app.config import get_settings
        reference = arguments.get('source_ref', source_ref)
        if reference != source_ref:
            raise ValueError('argument source_ref conflicts with plan')
        if name == 'sql_query' and reference != 'dataset':
            raise ValueError('SQL may query only the authorized dataset projection')
        if reference != 'dataset' and reference not in self.frame_results:
            raise ValueError('source_ref must reference a completed full result')
        registry = getattr(self, '_registry', None)
        if registry is None:
            self._registry = registry = build_registry(include_legacy=True)
        parsed = registry.validate_input(name, arguments)
        if name == 'generate_chart' and not parsed.source_tool_call_id:
            parsed.source_tool_call_id = reference
        metadata_only = name == 'get_dataset_info'
        frame = pd.DataFrame(columns=list(self.schema)) if metadata_only and self.frame is None else self.frame_for(name,reference)
        settings = get_settings()
        from app.analysis.inputs import DataInput
        if isinstance(parsed,DataInput) and 'limit' not in arguments:parsed.limit=settings.tool_preview_rows
        cache = getattr(self, '_contexts', {})
        cache_key = (reference, metadata_only)
        if cache_key not in cache or cache[cache_key].frame is not frame:
            budgets=dict(source_ref=reference,
                max_rows=settings.tool_max_rows, max_columns=settings.tool_max_columns, max_cells=settings.tool_max_cells,
                preview_rows=settings.tool_preview_rows, max_bytes=settings.dataframe_max_bytes, correlation_columns=settings.tool_correlation_columns)
            if reference=='dataset' and not metadata_only and getattr(self,'version_schema',None):
                cache[cache_key]=DatasetContext(self.dataset.id,self.dataset_version_id,frame,self.version_schema,self.version_profile,**budgets)
            else:
                cache[cache_key]=DatasetContext.from_frame(frame,self.dataset.id,getattr(self,'dataset_version_id',None),**budgets)
        self._contexts = cache
        self.check_frame_budget()
        context = replace(cache[cache_key], legacy_calculator=self)
        if name=='join_data':
            related={alias:adapter.context_for_tool('join_data') for alias,adapter in getattr(self,'related_adapters',{}).items()}
            combined=int(frame.memory_usage(deep=True).sum())+sum(int(ctx.frame.memory_usage(deep=True).sum()) for ctx in related.values())
            if combined*3>settings.dataframe_max_bytes: raise ValueError('WORKSPACE_MEMORY_BUDGET')
            context=replace(context,related_inputs=related)
        if hasattr(self,'semantic_mappings'):
            from app.semantic.business_validation import validate_business_arguments,metadata_evidence
            mappings=getattr(self,'frame_semantics',{}).get(reference,self.semantic_mappings)
            validated=validate_business_arguments(name,arguments,mappings,getattr(self,'dataset_version_id',None),metadata_evidence(frame))
            if name in {'kpi_analysis','period_comparison','contribution_analysis'}:
                parsed=registry.validate_input(name,arguments)
            if name=='forecast' and validated:
                context=replace(context,monetary_metadata=validated)
        original_schema = self.schema
        self._active_frame = frame
        self._execution_context = context
        self._output_frame = None
        if reference != 'dataset':
            self.schema = {column:type('ColumnRef',(),{'original_name':column,'data_type':'decimal' if pd.api.types.is_numeric_dtype(frame[column]) else 'datetime' if pd.api.types.is_datetime64_any_dtype(frame[column]) else 'string'})() for column in frame}
        captured = []
        try:
            def stage(budget):
                if getattr(self, 'on_event', None): self.on_event('stage', {'stage':'tool', 'timeout_seconds':budget})
            if getattr(self,'on_event',None):self.on_event('tool_parameters',{'parameters':parsed.model_dump(mode='json'),'tool_name':name})
            outcome = AnalysisEngine(registry).execute(ToolExecutionRequest(tool_name=name, dataset_id=self.dataset.id,
                dataset_version=context.dataset_version, parameters=parsed.model_dump(), request_id=call_id or name),
                ExecutionContext(getattr(self.dataset,'user_id',0),context,permissions=self.permissions,deadline=getattr(self,'deadline',None),lease_check=getattr(self,'check_lease',None),capture_frame=captured.append,stage=stage))
            if outcome.data.kind in {'legacy','legacy_chart'}:
                data=outcome.data.payload.model_dump(exclude_unset=True)
            else:
                data=outcome.data.model_dump(mode='json')
                if data.get('columns') and isinstance(data['columns'][0],dict): data['columns']=[column['name'] for column in data['columns']]
            output_frame=captured[0] if captured else None
            if output_frame is not None and call_id:
                memory=sum(int(f.memory_usage(deep=True).sum()) for f in self.frame_results.values())+int(output_frame.memory_usage(deep=True).sum())
                if self.frame is not None: memory+=int(self.frame.memory_usage(deep=True).sum())
                if memory>settings.dataframe_max_bytes: raise ValueError('task frames exceed memory budget')
                self.frame_results[call_id]=output_frame.copy()
                self.check_frame_budget()
                if hasattr(self,'semantic_mappings'):
                    if name=='join_data':
                        from app.semantic.business_validation import joined_mappings
                        right=self.related_adapters[parsed.right_alias]
                        self.frame_semantics[call_id]=joined_mappings(mappings,getattr(right,'semantic_mappings',[]),frame.columns,right._frame().columns,arguments,self.dataset_version_id)
                    else: self.frame_semantics[call_id]=mappings
            if call_id: self.call_results[call_id]=data
            return ToolResult(data=data,warnings=outcome.warnings,summary=f'{name} completed',metadata={'source_ref':reference,'row_count':len(output_frame) if output_frame is not None else data.get('row_count'),'result_kind':outcome.data.kind,'exposes_rows':registry.get(name).metadata.exposes_rows},execution_time_ms=outcome.execution_time_ms)
        finally:
            self.schema=original_schema
            self._active_frame=None
            self._execution_context=None

    @property
    def permissions(self):
        from app.analysis.models import Permission
        return frozenset({Permission.READ_DATA,Permission.READ_DATABASE}) if self.readonly_bind is not None else frozenset({Permission.READ_DATA})


def model_tool_schemas(permissions=None) -> list[dict[str, Any]]:
    from app.tools.registry import tool_registry
    from app.analysis.models import Permission
    if permissions is None:permissions=frozenset({Permission.READ_DATA})
    return [{'type':'function','function':{'name':name,'description':spec.description,'parameters':spec.schema.model_json_schema()}} for name,spec in tool_registry(permissions).items()]
