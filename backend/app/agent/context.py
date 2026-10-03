"""Bounded, version-pinned conversation state and dataset resolution."""
from __future__ import annotations

from typing import Any
import json
from pydantic import BaseModel, Field
from app.agent.tool_policy import CLEANING_TOOLS


class ConversationContext(BaseModel):
    conversation_id: int
    user_id: int
    active_dataset_id: int | None = None
    active_dataset_version_id: int | None = None
    attached_dataset_ids: list[int] = Field(default_factory=list, max_length=10)
    current_goal: str | None = None
    current_intent: str | None = None
    previous_analysis: dict[str, Any] | None = None
    previous_plan: dict[str, Any] | None = None
    previous_result_ref: str | None = None
    active_filters: list[dict[str, Any]] = Field(default_factory=list)
    active_dimensions: list[str] = Field(default_factory=list)
    active_metrics: list[str] = Field(default_factory=list)
    active_time_range: dict[str, Any] | None = None
    last_chart_spec: dict[str, Any] | None = None
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    messages_summary: str = ""

    def with_dataset(self, dataset_id: int, version_id: int) -> ConversationContext:
        if (dataset_id, version_id) == (self.active_dataset_id, self.active_dataset_version_id):
            return self.model_copy(deep=True)
        return self.model_copy(update={
            "active_dataset_id": dataset_id, "active_dataset_version_id": version_id,
            "current_goal": None, "current_intent": None, "previous_analysis": None,
            "previous_plan": None, "previous_result_ref": None, "active_filters": [],
            "active_dimensions": [], "active_metrics": [], "active_time_range": None,
            "last_chart_spec": None, "messages_summary": "",
        }, deep=True)


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
