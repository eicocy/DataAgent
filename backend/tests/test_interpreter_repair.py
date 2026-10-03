import pytest

from app.agent.interpreter import ResultInterpreter
from app.agent.providers import FakeLLMProvider


VALID = {'template': '销售额为 {sales}。', 'facts': [{'key': 'sales',
    'step_id': 'total', 'path': ['sales'], 'format': 'number'}], 'evidence_refs': ['total']}


def test_interpreter_repairs_invalid_binding_once_against_the_same_verified_results():
    class Capture(FakeLLMProvider):
        def __init__(self, responses):
            super().__init__(responses)
            self.payloads = []
        def generate_structured(self, name, payload, schema):
            self.payloads.append(dict(payload))
            return super().generate_structured(name, payload, schema)
    provider = Capture([dict(VALID, template='销售额为 999。'), VALID])
    answer, facts = ResultInterpreter(provider).interpret(question='总销售额', goal='汇总',
        results={'total': {'sales': 40}}, incomplete_steps=[])
    assert answer == '销售额为 40。'
    assert facts[0]['reference']['path'] == ['sales']
    assert provider.calls == 2
    assert provider.payloads[0]['results'] == provider.payloads[1]['results'] == {'total': {'sales': 40}}
    assert provider.payloads[1]['correction']['code'] == 'REPORT_FACT_BINDING_INVALID'
    assert '999' not in str(provider.payloads[1])


def test_interpreter_never_accepts_an_invented_fact_after_repair_budget():
    invalid = dict(VALID, facts=[dict(VALID['facts'][0], path=['invented'])])
    provider = FakeLLMProvider([invalid, invalid, VALID])
    with pytest.raises(ValueError, match='Invalid fact path'):
        ResultInterpreter(provider).interpret(question='销售额', goal='汇总',
            results={'total': {'sales': 40}}, incomplete_steps=[])
    assert provider.calls == 2


def test_interpreter_repair_respects_the_shared_model_call_budget():
    provider = FakeLLMProvider([dict(VALID, template='金额为 999。'), VALID], max_model_calls=1)
    with pytest.raises(ValueError, match='MODEL_BUDGET_EXCEEDED'):
        ResultInterpreter(provider).interpret(question='销售额', goal='汇总',
            results={'total': {'sales': 40}}, incomplete_steps=[])
    assert provider.calls == 1
