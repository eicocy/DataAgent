import pytest
from pydantic import BaseModel
from app.agent.providers import FakeLLMProvider, load_prompt


class Example(BaseModel):
    value: int


def test_fake_provider_validates_structured_responses_without_network():
    provider = FakeLLMProvider([{"value": 7}, "hello"])
    assert provider.generate_structured('intent_router', {}, Example) == {"value": 7}
    assert provider.generate_text('general_chat', {}) == 'hello'


def test_fake_provider_rejects_bad_model_payload():
    provider = FakeLLMProvider([{"value": "wrong"}])
    with pytest.raises(ValueError):
        provider.generate_structured('intent_router', {}, Example)


def test_prompt_loader_has_versioned_distinct_templates():
    name, version, body = load_prompt('analysis_planner')
    assert name == 'analysis_planner' and version == 'v3'
    assert 'AnalysisPlan' in body
    assert load_prompt('intent_router')[2] != body


def test_fake_provider_records_the_active_prompt_version():
    calls = []
    provider = FakeLLMProvider([{'value': 7}], emit=lambda kind, data: calls.append(data))
    provider.generate_structured('analysis_planner', {}, Example)
    assert calls[0]['prompt_version'] == 'analysis_planner.v3'
