from langchain_core.messages import AIMessage

from app.config import Settings
from app.services import analysis_agent
from app.services.analysis_agent import DeepSeekAgent, ModelUnavailable
from app.services.analysis_tools import DatasetTools


def test_agent_requires_real_deepseek_credentials():
    agent = DeepSeekAgent(Settings(secret_key="s" * 40, deepseek_api_key=""))

    try:
        agent.analyze("按地区汇总销售额", DatasetTools.from_frame(1, [{"region": "East", "sales": 3}]))
    except ModelUnavailable as error:
        assert error.code == "MODEL_UNAVAILABLE"
    else:
        raise AssertionError("missing DeepSeek key must fail explicitly")


def test_tool_result_survives_deepseek_summary_failure(monkeypatch):
    class FakeModel:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, _):
            return self

        def invoke(self, _):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(content="", tool_calls=[{
                    "name": "submit_execution_plan",
                    "args": {"intent": "按地区统计销售额", "steps": [{"step_id": "group", "tool_name": "group_by_analysis", "arguments": {"group_columns": ["region"], "value_column": "sales", "aggregation": "sum"}}]},
                    "id": "tc_group",
                    "type": "tool_call",
                }])
            raise RuntimeError("simulated provider outage")

    model = FakeModel()
    monkeypatch.setattr(analysis_agent, "ChatOpenAI", lambda **_: model)
    agent = DeepSeekAgent(Settings(secret_key="s" * 40, deepseek_api_key="configured-key"))

    outcome = agent.analyze(
        "按地区汇总销售额",
        DatasetTools.from_frame(1, [{"region": "East", "sales": 3}, {"region": "West", "sales": 2}]),
    )

    assert outcome.status == "partial"
    assert outcome.answer is None
    assert outcome.summary_error == "SUMMARY_UNAVAILABLE"
    assert outcome.tool_result["rows"] == [{"region": "East", "sales_sum": 3}, {"region": "West", "sales_sum": 2}]
    assert outcome.tool_calls[0]["status"] == "succeeded"
