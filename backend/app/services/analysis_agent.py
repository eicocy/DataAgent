"""Backward compatible facade over constrained planning and execution."""
from dataclasses import dataclass
from langchain_openai import ChatOpenAI
from app.config import get_settings
from app.agent.model_adapter import ModelAdapter
from app.agent.planner import Planner
from app.agent.executor import WorkflowExecutor, clip_context


class AnalysisFailure(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.public_message, self.retryable = code, message, retryable


class ModelUnavailable(AnalysisFailure):
    def __init__(self):
        super().__init__("MODEL_UNAVAILABLE", "DeepSeek 暂时不可用，请稍后重试", True)


class ToolExecutionFailure(AnalysisFailure):
    def __init__(self, message="分析工具执行失败，请调整问题后重试"):
        super().__init__("TOOL_EXECUTION_FAILED", message)


@dataclass
class AgentOutcome:
    tool_calls: list
    tool_result: dict
    answer: str | None
    chart: dict | None
    status: str
    summary_error: str | None = None
    report: dict | None = None
    usage: dict | None = None
    plan: dict | None = None


class DeepSeekAgent:
    def __init__(self, settings=None, provider_factory=None):
        self.settings = settings or get_settings()
        self.provider_factory = provider_factory

    def prepare(self, question, context, candidates, requested_id=None, emit=None):
        from app.agent.providers import build_provider
        from app.agent.intent import IntentRouter
        from app.agent.context import DatasetResolver
        try:
            provider = self.provider_factory(emit) if self.provider_factory else build_provider(self.settings, emit)
        except ValueError as exc:
            if str(exc) == 'MODEL_UNAVAILABLE':
                raise ModelUnavailable() from exc
            raise
        decision = IntentRouter(provider).route(question, context)
        resolution = DatasetResolver().resolve(decision, context, candidates, requested_id)
        if emit:
            emit('intent', {'intent': decision.intent, 'confidence': decision.confidence,
                            'needs_clarification': resolution.needs_clarification,
                            'candidates': resolution.candidates})
        return provider, decision, resolution

    def respond_without_analysis(self, question, prepared):
        provider, decision, resolution = prepared
        if decision.intent == 'UNKNOWN':
            answer = '我还不能确定你的分析需求，请说明想分析的指标、范围或问题。'
            status = 'waiting'
        elif resolution.needs_clarification:
            answer = '请指定要使用的数据集，再继续分析。'
            status = 'waiting'
        elif decision.intent == 'GENERAL_CHAT':
            answer = provider.generate_text('general_chat', {'question': question[:2000]})
            status = 'succeeded'
        elif decision.intent == 'DATA_CLEANING':
            answer = '可以先分析数据质量并给出清洗建议；当前聊天入口不能执行清洗或发布新版本。'
            status = 'succeeded'
        else:
            answer = '请先选择要分析的数据集。'
            status = 'waiting'
        return AgentOutcome([], {}, answer, None, status,
                            report={'version': '1.0', 'status': status, 'answer': answer,
                                    'tables': [], 'charts': [], 'warnings': [], 'evidence_refs': [],
                                    'incomplete_steps': []})

    def _model(self):
        if not self.settings.deepseek_api_key.strip():
            raise ModelUnavailable()
        return ChatOpenAI(api_key=self.settings.deepseek_api_key, base_url=self.settings.deepseek_base_url,
                          model=self.settings.deepseek_model, temperature=0, timeout=self.settings.llm_timeout_seconds, max_retries=1)

    def analyze(self, question, tools):
        emit = getattr(tools, "on_event", None)
        prepared = getattr(tools, 'prepared', None)
        adapter = prepared[0] if prepared else ModelAdapter(self._model(), self.settings, emit)
        from app.services.datasets import DatasetService
        metadata = getattr(tools, 'model_metadata', None) or DatasetService.metadata(tools.dataset, tools.columns)
        try:
            if prepared:
                plan = Planner(adapter).plan_v2(question, metadata, tools.conversation_state,
                    task_id=str(tools.record_id), intent=prepared[1].intent,
                    permissions=tools.permissions, max_steps=self.settings.max_plan_steps)
            else:
                plan = Planner(adapter).plan(question, metadata, getattr(tools, "conversation_context", []),permissions=tools.permissions)
        except ValueError as exc:
            raise AnalysisFailure("PLAN_INVALID", "模型未能生成有效分析计划，请调整问题重试", True) from exc
        except Exception as exc:
            raise ModelUnavailable() from exc
        if prepared and emit:
            emit('plan', plan.model_dump())
            emit('plan_validated', {'plan_id': plan.plan_id, 'steps': len(plan.steps)})
        executor = WorkflowExecutor(tools, self.settings, adapter, emit)
        report = executor.execute(plan, question)
        plan = executor.final_plan
        primary = [step for step in plan.steps if step.step_id in executor.results and step.tool_name not in {"generate_chart", "get_dataset_info", "preview_data"}]
        if report.status == "failed":
            raise AnalysisFailure("TOOL_VALIDATION_FAILED", "计划没有完成有效计算，请调整问题重试")
        return AgentOutcome(executor.calls, executor.results[primary[-1].step_id] if primary else {}, report.answer,
                            report.charts[-1] if report.charts else None, report.status,
                            "SUMMARY_UNAVAILABLE" if not report.answer else None,
                            report.model_dump(), adapter.usage, plan.model_dump())


_clip_result = clip_context
