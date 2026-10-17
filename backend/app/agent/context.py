"""Bounded, version-pinned conversation state and dataset resolution."""
from __future__ import annotations

from typing import Any
import json
from pydantic import BaseModel, Field, ConfigDict
from app.agent.tool_policy import CLEANING_TOOLS


class ConversationContext(BaseModel):
    conversation_id: int
    user_id: int
    active_dataset_id: int | None = None
    active_dataset_version_id: int | None = None
    attached_dataset_ids: list[int] = Field(default_factory=list, max_length=10)
    uploaded_file_ids: list[int] = Field(default_factory=list, max_length=10)
    current_goal: str | None = None
    current_intent: str | None = None
    previous_analysis: dict[str, Any] | None = None
    previous_plan: dict[str, Any] | None = None
    previous_result_ref: str | None = None
    active_filters: list[dict[str, Any]] = Field(default_factory=list)
    active_filter_groups: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    active_dimensions: list[str] = Field(default_factory=list)
    active_metrics: list[str] = Field(default_factory=list)
    active_time_range: dict[str, Any] | None = None
    last_chart_spec: dict[str, Any] | None = None
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    messages_summary: str = ""
    recent_messages: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    semantic_mappings: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    semantic_version: int = 0
    selected_profiles: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    workspace_selection: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_session(cls, session, **defaults) -> ConversationContext:
        """Recover old partial state using identity from an owned database row.

        Saved/client JSON never chooses the owner or conversation identity.
        Validation and existing state bounds still apply to all other fields.
        """
        state = dict(session.context_json or {})
        for name, value in defaults.items():
            state.setdefault(name, value)
        state.setdefault('active_dataset_id', session.dataset_id)
        state.update(conversation_id=session.id, user_id=session.user_id)
        return cls.model_validate(state)

    def with_dataset(self, dataset_id: int, version_id: int) -> ConversationContext:
        if (dataset_id, version_id) == (self.active_dataset_id, self.active_dataset_version_id):
            return self.model_copy(deep=True)
        return self.model_copy(update={
            "active_dataset_id": dataset_id, "active_dataset_version_id": version_id,
            "current_goal": None, "current_intent": None, "previous_analysis": None,
            "previous_plan": None, "previous_result_ref": None, "active_filters": [],
            "active_dimensions": [], "active_metrics": [], "active_time_range": None,
            "last_chart_spec": None, "messages_summary": "",
            'recent_messages': [],
            'active_filter_groups': [],
        }, deep=True)


class ContextPatch(BaseModel):
    """An explicit proposed change, validated against the pinned schema before use."""
    model_config = ConfigDict(extra='forbid')
    filters: list[dict] = Field(default_factory=list, max_length=20)
    clear_filter_columns: list[str] = Field(default_factory=list, max_length=20)
    clear_all_filters: bool = False
    dimensions: list[str] | None = Field(default=None, max_length=10)
    metrics: list[str] | None = Field(default=None, max_length=20)
    time_range: dict | None = None
    clear_time_range: bool = False


def conversation_payload(context, question=''):
    if context is None:
        return {'summary': '', 'recent_messages': []}
    messages = context.recent_messages[-6:]
    if messages and messages[-1].get('role')=='user' and messages[-1].get('content')==question:
        messages = messages[:-1]
    return {'summary': context.messages_summary[-4000:],
            'recent_messages': [{'role': m['role'], 'content': m['content'][-1200:]} for m in messages],
            'active_dataset_id': context.active_dataset_id, 'dataset_version_id': context.active_dataset_version_id,
            'filters': context.active_filters[:20], 'filter_groups': context.active_filter_groups[:20], 'dimensions': context.active_dimensions[:20],
            'metrics': context.active_metrics[:20], 'time_range': context.active_time_range,
            'units': [{k:m.get(k) for k in ('column','currency','unit')} for m in context.semantic_mappings if m.get('currency') or m.get('unit')][:20]}


def apply_context_patch(context, patch, columns, question=''):
    from app.analysis.inputs import FilterCondition
    from app.analysis.errors import ToolInputError
    import re
    patch = patch or ContextPatch()
    names = set(columns)
    proposed = [FilterCondition.model_validate(f).model_dump(mode='json') for f in patch.filters]
    mentioned = {f['column'] for f in proposed} | set(patch.clear_filter_columns) | set(patch.dimensions or []) | set(patch.metrics or [])
    if patch.time_range:
        mentioned.add(patch.time_range.get('column', ''))
    if not mentioned <= names:
        raise ToolInputError('CONTEXT_PATCH_INVALID', '追问中的字段不属于当前固定数据版本。',
                             details={'column': sorted(mentioned-names)[0]})
    if patch.time_range:
        if set(patch.time_range) != {'column','start','end'}:
            raise ToolInputError('CONTEXT_PATCH_INVALID', '时间范围需要字段、开始和结束。')
        from datetime import datetime
        try:
            if datetime.fromisoformat(patch.time_range['start']) > datetime.fromisoformat(patch.time_range['end']):
                raise ValueError()
        except (TypeError, ValueError):
            raise ToolInputError('CONTEXT_PATCH_INVALID', '时间范围格式或先后顺序无效。') from None
    reset = patch.clear_all_filters or (not patch.clear_filter_columns and bool(re.fullmatch(r'\s*(请)?(取消|清除|移除|去掉)(所有|全部)?(筛选|过滤)(条件)?[。！!\s]*|\s*不再筛选[。！!\s]*', question)))
    replaced = {f['column'] for f in proposed} | set(patch.clear_filter_columns)
    original_groups = context.active_filter_groups or ([{'input_alias':'primary','source_ref':'dataset','logic':'and','filters':context.active_filters}] if context.active_filters else [])
    groups, inserted = [], set()
    for group in ([] if reset else original_groups):
        if group.get('input_alias','primary')!='primary' or group.get('source_ref','dataset')!='dataset':
            groups.append(group)
            continue
        conditions, local = [], set()
        for condition in group['filters']:
            column = condition.get('column')
            if column not in replaced:
                conditions.append(condition)
            elif column not in local:
                conditions.extend(f for f in proposed if f['column']==column)
                local.add(column); inserted.add(column)
        if conditions:
            groups.append(dict(group,filters=conditions))
    remaining = [f for f in proposed if f['column'] not in inserted]
    if remaining:
        groups.append({'input_alias':'primary','source_ref':'dataset','logic':'and','filters':remaining})
    context.active_filter_groups = groups[:20]
    context.active_filters = [f for g in groups if g.get('input_alias','primary')=='primary' and g.get('source_ref','dataset')=='dataset' and g.get('logic','and')=='and' for f in g['filters']][:20]
    if patch.dimensions is not None:
        context.active_dimensions = patch.dimensions
    if patch.metrics is not None:
        context.active_metrics = patch.metrics
    if patch.clear_time_range:
        context.active_time_range = None
    elif patch.time_range:
        context.active_time_range = patch.time_range
    return context


def extract_plan_state(context, plan):
    """Merge explicit operations from legacy and current tool schemas."""
    filters, dimensions, metrics, groups = [], [], [], []
    prior_groups = context.active_filter_groups or ([{'input_alias':'primary','source_ref':'dataset','logic':'and','filters':list(context.active_filters)}] if context.active_filters else [])
    for step in (plan or {}).get('steps', []):
        args = step.get('arguments') or {}
        conditions = args.get('filters') or args.get('conditions') or []
        if conditions:
            group = {'input_alias':step.get('input_alias','primary'),'source_ref':step.get('source_ref','dataset'),
                     'logic':args.get('logic','and'),'filters':conditions}
            if group not in groups:
                groups.append(group)
            if group['input_alias']=='primary' and group['source_ref']=='dataset' and group['logic']=='and':
                filters.extend(conditions)
        dimensions.extend(args.get('dimensions') or args.get('group_columns') or [])
        dimensions.extend(args[k] for k in ('group_column','date_column','time_column') if isinstance(args.get(k),str))
        metrics.extend(m['column'] for m in args.get('metrics',[]) if isinstance(m,dict) and isinstance(m.get('column'),str))
        metrics.extend(args[k] for k in ('value_column','column') if isinstance(args.get(k),str) and step.get('tool_name') in {'aggregate','aggregate_data','descriptive_statistics','column_summary','group_by_analysis'})
    # Preserve inherited conditions absent from the new plan; replace only explicitly changed columns.
    replaced = {f.get('column') for f in filters if isinstance(f,dict)}
    context.active_filters = ([f for f in context.active_filters if f.get('column') not in replaced]+filters)[:20]
    if groups:
        retained, consumed = [], set()
        for prior in prior_groups:
            scope = (prior.get('input_alias','primary'),prior.get('source_ref','dataset'))
            prior_columns = {f.get('column') for f in prior['filters']}
            partial_or = [(i,g) for i,g in enumerate(groups) if prior.get('logic')=='or' and
                          (g['input_alias'],g['source_ref'])==scope and {f.get('column') for f in g['filters']} < prior_columns]
            if partial_or:
                changed = {f.get('column') for _,g in partial_or for f in g['filters']}
                retained.append(dict(prior,filters=[f for f in prior['filters'] if f.get('column') not in changed]+[f for _,g in partial_or for f in g['filters']]))
                consumed.update(i for i,_ in partial_or)
                continue
            changed = {f.get('column') for i,g in enumerate(groups) if i not in consumed and (g['input_alias'],g['source_ref'])==scope for f in g['filters']}
            remaining = [f for f in prior['filters'] if f.get('column') not in changed]
            if remaining:
                retained.append(dict(prior,filters=remaining))
        context.active_filter_groups = (retained+[g for i,g in enumerate(groups) if i not in consumed])[:20]
    # The compatibility list is derived from canonical AND groups only; OR groups retain their logic.
    context.active_filters = [f for g in context.active_filter_groups if g.get('input_alias','primary')=='primary' and g.get('source_ref','dataset')=='dataset' and g.get('logic','and')=='and' for f in g['filters']][:20] if context.active_filter_groups else context.active_filters
    if dimensions:
        context.active_dimensions = list(dict.fromkeys(dimensions))[:20]
    if metrics:
        context.active_metrics = list(dict.fromkeys(metrics))[:20]


class DatasetCandidate(BaseModel):
    id: int
    name: str
    version_id: int


class DatasetResolution(BaseModel):
    dataset_id: int | None = None
    dataset_version_id: int | None = None
    needs_clarification: bool = False
    candidates: list[int] = Field(default_factory=list)


class DatasetResolver:
    def resolve(self, decision: Any, context: ConversationContext,
                candidates: list[DatasetCandidate], requested_id: int | None = None) -> DatasetResolution:
        if not decision.requires_dataset:
            return DatasetResolution()
        owned = {item.id: item for item in candidates}
        ref = decision.dataset_reference
        matches: list[DatasetCandidate] = []
        if ref:
            if ref.id is not None:
                matches = [owned[ref.id]] if ref.id in owned else []
            elif ref.name:
                matches = [item for item in candidates if item.name.casefold() == ref.name.casefold()]
            elif ref.ordinal is not None and 0 < ref.ordinal <= len(candidates):
                matches = [candidates[ref.ordinal - 1]]
            if len(matches) != 1:
                return DatasetResolution(needs_clarification=True, candidates=[item.id for item in matches or candidates])
        else:
            chosen = requested_id or context.active_dataset_id
            if chosen in owned:
                matches = [owned[chosen]]
            elif context.previous_analysis and context.previous_analysis.get("dataset_id") in owned:
                matches = [owned[context.previous_analysis["dataset_id"]]]
            elif len(candidates) == 1:
                matches = candidates
            else:
                return DatasetResolution(needs_clarification=True, candidates=[item.id for item in candidates])
        item = matches[0]
        version_id = context.active_dataset_version_id if item.id == context.active_dataset_id and context.active_dataset_version_id else item.version_id
        return DatasetResolution(dataset_id=item.id, dataset_version_id=version_id)


class ContextBuilder:
    def build(self, question: str, context: ConversationContext, metadata: dict,
              manifests: list[dict]) -> dict:
        columns = [{key: column[key] for key in ("name", "label", "data_type", "semantic_type", "missing_count") if key in column}
                   for column in metadata.get("columns", [])[:200]]
        payload = {"question": question[:2000], "summary": context.messages_summary[:4000],
                "goal": context.current_goal, "intent": context.current_intent,
                "filters": context.active_filters[:20], "dimensions": context.active_dimensions[:20],
                "metrics": context.active_metrics[:20], "time_range": context.active_time_range,
                "previous_analysis": context.previous_analysis,
                "previous_plan": context.previous_plan,
                "dataset": {"dataset_id": metadata.get("dataset_id"),
                            "dataset_version_id": metadata.get("dataset_version_id"),
                            "row_count": metadata.get("row_count"), "columns": columns},
                "tools": self._needed_tools(context, manifests)}
        if context.current_intent == 'FOLLOW_UP_ANALYSIS':
            # 追问可引入新分析；相同的真实参数 Schema 只传一次，约束不裁剪。
            schemas, names, tools = {}, {}, []
            for tool in payload['tools']:
                key = json.dumps(tool['parameters'], sort_keys=True, ensure_ascii=False)
                if key not in names:
                    names[key] = f'params_{len(names)}'
                    schemas[names[key]] = tool['parameters']
                tools.append(dict(tool, parameters={'$ref': f'#/tool_parameter_schemas/{names[key]}'}))
            payload.update(tools=tools, tool_parameter_schemas=schemas)
        return payload

    @staticmethod
    def _needed_tools(context, manifests):
        if context.current_intent == 'DATA_CLEANING':
            return [tool for tool in manifests if tool.get('name') in CLEANING_TOOLS]
        if context.current_intent == 'FOLLOW_UP_ANALYSIS':
            return manifests
        # 按正式意图选取真实 Registry 定义，避免通用裁剪破坏参数 Schema。
        common = {'get_dataset_info', 'preview_data', 'filter_data', 'aggregate_data',
                  'group_by_analysis', 'sort_data', 'generate_chart', 'describe_data',
                  'time_group_analysis', 'growth_analysis', 'sql_query'}
        quality = {'missing_value_analysis', 'duplicate_analysis', 'constant_column_analysis',
                   'cardinality_analysis', 'invalid_numeric_analysis', 'invalid_datetime_analysis',
                   'infinite_value_analysis', 'outlier_analysis', 'column_summary'}
        groups = {
            'STATISTICAL_ANALYSIS': {'descriptive_statistics', 'percentile', 'quantile', 'variance',
                'standard_deviation', 'skewness', 'kurtosis', 'weighted_average'},
            'CORRELATION_ANALYSIS': {'correlation', 'covariance'},
            'ANOMALY_ANALYSIS': quality,
            'TREND_ANALYSIS': {'cumulative_sum', 'percentage_change', 'growth_rate', 'rolling_statistics'},
            'COMPARISON_ANALYSIS': {'pivot_table', 'crosstab', 'rank', 'top_n', 'bottom_n', 'percentage_share'},
            'DATA_FILTER': {'select_columns', 'filter_rows', 'sample_rows', 'unique_values', 'value_counts'},
            'DATASET_INFO': {'dataset_overview', 'column_summary', 'unique_values', 'value_counts'},
            'DATA_AGGREGATION': {'multi_aggregate', 'weighted_average', 'percentage_share'},
            'CHART_GENERATION': {'chart_recommendations'},
            'DATA_ANALYSIS': {'eda', 'weighted_average', 'percentage_share', 'rank', 'pivot_table'},
            'REPORT_GENERATION': {'eda', 'descriptive_statistics', 'missing_value_analysis'},
        }
        names = common | groups.get(context.current_intent, set())
        names |= {step.get('tool_name') for step in (context.previous_plan or {}).get('steps', [])}
        return [tool for tool in manifests if tool.get('name') in names]
