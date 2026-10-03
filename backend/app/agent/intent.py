"""Structured intent classification; rules are not the primary classifier."""
from typing import Literal
from pydantic import BaseModel, Field, ValidationError


IntentName = Literal[
    "DATA_ANALYSIS", "DATA_PREVIEW", "DATASET_INFO", "DATA_CLEANING", "DATA_FILTER",
    "DATA_AGGREGATION", "STATISTICAL_ANALYSIS", "TREND_ANALYSIS", "COMPARISON_ANALYSIS",
    "ANOMALY_ANALYSIS", "CORRELATION_ANALYSIS", "CHART_GENERATION", "REPORT_GENERATION",
    "FOLLOW_UP_ANALYSIS", "GENERAL_CHAT", "UNKNOWN",
]


class DatasetReference(BaseModel):
    id: int | None = None
    name: str | None = None
    ordinal: int | None = None


class IntentDecision(BaseModel):
    intent: IntentName
    confidence: float = Field(ge=0, le=1)
    requires_dataset: bool = False
    requires_analysis: bool = False
    dataset_reference: DatasetReference | None = None
    follow_up: bool = False


class IntentRouter:
    def __init__(self, provider):
        self.provider = provider

    def route(self, question, context):
        payload = {"question": question[:2000], "summary": context.messages_summary[:2000],
                   "active_dataset_id": context.active_dataset_id,
                   "current_intent": context.current_intent}
        for attempt in range(2):
            try:
                raw = self.provider.generate_structured("intent_router", payload, IntentDecision)
                decision = IntentDecision.model_validate(raw)
                if decision.confidence < 0.6:
                    return IntentDecision(intent="UNKNOWN", confidence=decision.confidence)
                # 意图类别决定执行前提；模型的冗余布尔字段不能绕过正式路由。
                requires_analysis = decision.intent not in {'GENERAL_CHAT', 'UNKNOWN'}
                return decision.model_copy(update={'requires_dataset': requires_analysis,
                                                   'requires_analysis': requires_analysis})
            except (ValidationError, ValueError, TypeError) as exc:
                if attempt == 0 and (isinstance(exc, ValidationError) or str(exc) == 'MODEL_OUTPUT_INVALID'):
                    payload['correction'] = {'code': 'INTENT_SCHEMA_INVALID',
                        'instruction': '重新调用结构化输出；只能选择已列出的意图，confidence 为 0 到 1。'}
                    continue
                return IntentDecision(intent="UNKNOWN", confidence=0)
        return IntentDecision(intent="UNKNOWN", confidence=0)
