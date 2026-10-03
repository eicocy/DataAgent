from app.agent.context import ConversationContext, DatasetCandidate, DatasetResolver, ContextBuilder
from app.agent.intent import IntentDecision, IntentRouter
from app.agent.providers import load_prompt


def test_router_keeps_intent_confidence_separate_from_dataset_ambiguity():
    _, version, prompt = load_prompt('intent_router')
    assert version == 'v2'
    assert '数据集未指明' in prompt and 'confidence' in prompt


def test_router_repairs_one_invalid_structured_output_without_guessing_intent():
    class Provider:
        def __init__(self):
            self.payloads = []
        def generate_structured(self, _, payload, __):
            self.payloads.append(dict(payload))
            if len(self.payloads) == 1:
                raise ValueError('MODEL_OUTPUT_INVALID')
            return {'intent': 'DATA_AGGREGATION', 'confidence': 0.94}
    provider = Provider()
    decision = IntentRouter(provider).route('汇总销售额', ConversationContext(conversation_id=1, user_id=1))
    assert decision.intent == 'DATA_AGGREGATION' and decision.requires_dataset
    assert len(provider.payloads) == 2
    assert provider.payloads[1]['correction']['code'] == 'INTENT_SCHEMA_INVALID'


def test_low_confidence_intent_still_requires_user_clarification():
    provider = FixedProvider({'intent': 'DATA_AGGREGATION', 'confidence': 0.58})
    decision = IntentRouter(provider).route('不明确问题', ConversationContext(conversation_id=1, user_id=1))
    assert decision.intent == 'UNKNOWN' and not decision.requires_dataset


class FixedProvider:
    def __init__(self, answer):
        self.answer = answer

    def generate_structured(self, *args, **kwargs):
        return self.answer


def test_intent_router_accepts_structured_follow_up_and_rejects_unknown_intent():
    router = IntentRouter(FixedProvider({
        "intent": "FOLLOW_UP_ANALYSIS", "confidence": 0.91,
        "requires_dataset": True, "requires_analysis": True,
        "dataset_reference": None, "follow_up": True,
    }))
    decision = router.route("只看华南", ConversationContext(conversation_id=7, user_id=3))
    assert decision.follow_up and decision.intent == "FOLLOW_UP_ANALYSIS"
    assert IntentRouter(FixedProvider({"intent": "MADE_UP", "confidence": 1})).route(
        "something", ConversationContext(conversation_id=7, user_id=3)
    ).intent == "UNKNOWN"


def test_analysis_intent_cannot_disable_dataset_and_execution_requirements():
    decision = IntentRouter(FixedProvider({'intent': 'CHART_GENERATION', 'confidence': 0.99,
        'requires_dataset': False, 'requires_analysis': False, 'follow_up': True})).route(
        '换成折线图', ConversationContext(conversation_id=1, user_id=1, active_dataset_id=7))
    assert decision.requires_dataset and decision.requires_analysis
    chat = IntentRouter(FixedProvider({'intent': 'GENERAL_CHAT', 'confidence': 0.99,
        'requires_dataset': True, 'requires_analysis': True})).route(
        '你好', ConversationContext(conversation_id=1, user_id=1))
    assert not chat.requires_dataset and not chat.requires_analysis


def test_explicit_requested_dataset_precedes_current_conversation_dataset():
    context = ConversationContext(conversation_id=1, user_id=1, active_dataset_id=1, active_dataset_version_id=11)
    candidates = [DatasetCandidate(id=1, name='first.csv', version_id=11),
                  DatasetCandidate(id=2, name='second.csv', version_id=22)]
    decision = IntentDecision(intent='DATA_AGGREGATION', confidence=0.99, requires_dataset=True)
    result = DatasetResolver().resolve(decision, context, candidates, requested_id=2)
    assert (result.dataset_id, result.dataset_version_id) == (2, 22)


def test_dataset_resolver_prefers_explicit_reference_and_never_guesses_ambiguous_name():
    candidates = [DatasetCandidate(id=1, name="sales.csv", version_id=11), DatasetCandidate(id=2, name="sales.csv", version_id=22)]
    context = ConversationContext(conversation_id=7, user_id=3, active_dataset_id=1, active_dataset_version_id=11)
    resolver = DatasetResolver()
    chosen = resolver.resolve(IntentDecision(intent="DATA_ANALYSIS", confidence=1, requires_dataset=True,
        requires_analysis=True, dataset_reference={"id": 2}), context, candidates)
    assert (chosen.dataset_id, chosen.dataset_version_id) == (2, 22)
    unclear = resolver.resolve(IntentDecision(intent="DATA_ANALYSIS", confidence=1, requires_dataset=True,
        requires_analysis=True, dataset_reference={"name": "sales.csv"}), context, candidates)
    assert unclear.needs_clarification and unclear.dataset_id is None


def test_switching_dataset_discards_dataset_specific_follow_up_context():
    context = ConversationContext(conversation_id=7, user_id=3, active_dataset_id=1,
        active_dataset_version_id=11, active_filters=[{"column": "region", "value": "华南"}],
        active_metrics=["sales"], user_preferences={"language": "zh"}, messages_summary="旧数据集销售额下降")
    changed = context.with_dataset(2, 22)
    assert changed.active_filters == [] and changed.active_metrics == []
    assert changed.user_preferences == {"language": "zh"}
    assert changed.messages_summary == ""


def test_context_builder_excludes_raw_rows_and_long_history():
    context = ConversationContext(conversation_id=7, user_id=3, messages_summary="地区销售下降")
    payload = ContextBuilder().build("为什么下降", context,
        {"dataset_id": 1, "columns": [{"name": "sales", "data_type": "decimal", "sample_values": ["SECRET"]}],
         "rows": [{"sales": "SECRET"}], "row_count": 200},
        [{"name": "aggregate_data", "parameters": {"type": "object"}}])
    assert payload["dataset"]["columns"][0] == {"name": "sales", "data_type": "decimal"}
    assert "SECRET" not in str(payload)
    assert payload["summary"] == "地区销售下降"
