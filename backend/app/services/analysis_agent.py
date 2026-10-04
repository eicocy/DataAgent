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

    def prepare(self, question, context, candidates, requested_id=None, emit=None, runtime_budget=None):
        from app.agent.providers import build_provider
        from app.agent.intent import IntentRouter
        from app.agent.context import DatasetResolver
        try:
            settings = self.settings.model_copy(update={'analysis_timeout_seconds': runtime_budget.seconds, 'max_model_calls': runtime_budget.max_calls}) if runtime_budget else self.settings
            provider = self.provider_factory(emit) if self.provider_factory else build_provider(settings, emit)
            if runtime_budget:
                from app.agent.budget import BudgetProvider
                if hasattr(provider, 'adapter'):
                    provider.adapter.model = provider.adapter.model.model_copy(update={'max_tokens': runtime_budget.output_tokens})
                provider = BudgetProvider(provider, runtime_budget)
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
        if getattr(tools, 'configuration', None):
            return self._analyze_workspace(question, tools)
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

    def _analyze_workspace(self, question, tools):
        from app.agent.template_router import AnalysisTemplateRouter
        from app.agent.graph_executor import GraphExecutor
        from app.agent.budget import BudgetExceeded
        config = tools.configuration
        provider, decision, _ = tools.prepared
        event = tools.on_event
        selected_ids = config['public']['profile_ids']
        if not selected_ids and (decision.follow_up or decision.intent == 'FOLLOW_UP_ANALYSIS') and tools.conversation_state.previous_analysis:
            selected_ids = [p['id'] for p in tools.conversation_state.selected_profiles if p.get('source') == 'system']
        route = AnalysisTemplateRouter(config['catalog']).route(question, selected_ids, config['semantic_snapshot'], config['public']['category'],tools.metadata_by_input)
        event('profile_selected', route.model_dump())
        if route.needs_clarification:
            answer = '请补充或确认分析需求：' + ('；'.join(route.missing_requirements) or '请选择分析模板或说明想分析的指标。')
            return AgentOutcome([], {}, answer, None, 'waiting', report={'version': '1.0', 'status': 'waiting', 'answer': answer,
                'warnings': route.missing_requirements, 'tables': [], 'charts': [], 'evidence_refs': [], 'incomplete_steps': []}, usage=provider.usage)
        config['profiles'] = [p for key in route.profile_ids for p in config['catalog'] if p['id'] == key]
        if route.profile_ids == ['custom-question']:
            from app.profiles.schemas import AnalysisProfile
            dynamic = dict(config['profiles'][0], id=f'custom-session-{tools.record_id}', source='session',
                name='当前问题的自定义分析', description=question[:500], prompt_context=question[:2000])
            config['profiles'] = [AnalysisProfile.model_validate(dynamic).model_dump()]
        try:
            plan = Planner(provider).plan_v3(question, tools.metadata_by_input, tools.conversation_state,
                task_id=str(tools.record_id), intent=decision.intent, config=config, permissions=tools.permissions)
        except BudgetExceeded:
            return AgentOutcome([], {}, '分析规划已达到本次预算，请缩小问题范围或选择更高分析深度。', None, 'waiting', usage=provider.usage)
        except ValueError as exc:
            from app.sandbox.agent import UnknownToolCapability, propose_plan
            if isinstance(exc, UnknownToolCapability):
                try:
                    plan, tools.sandbox_authorization = propose_plan(question, provider, config, tools.metadata_by_input,
                        str(tools.record_id), decision.intent, exc)
                except ValueError as sandbox_error:
                    code = getattr(sandbox_error, 'code', 'SANDBOX_PROPOSAL_INVALID')
                    raise AnalysisFailure(code, '当前注册工具无法完成该方法，受限沙箱未启用、不可用或代码未通过校验。请调整分析方法。', False) from sandbox_error
            else:
                cause=exc
                while cause.__cause__ is not None: cause=cause.__cause__
                if str(cause).startswith(('BUSINESS_METADATA','BUSINESS_METRIC','BUSINESS_PERIOD','BUSINESS_PREVIOUS')):
                    answer='请确认金额字段的币种和单位、指标含义以及完整且不重叠的比较区间；现有数据需覆盖这些区间。'
                    return AgentOutcome([],{},answer,None,'waiting',report={'version':'1.0','status':'waiting','answer':answer,'warnings':[str(cause)],'tables':[],'charts':[],'evidence_refs':[],'incomplete_steps':[]},usage=provider.usage)
                raise AnalysisFailure('PLAN_INVALID', '模型未能生成有效分析计划，请调整问题重试', True) from exc
        event('plan', plan.model_dump())
        event('plan_validated', {'plan_id': plan.plan_id, 'steps': len(plan.steps)})
        settings = self.settings.model_copy(update={'max_tool_attempts': provider.budget.max_tasks * (self.settings.max_retries_per_step + 1), 'analysis_timeout_seconds': provider.budget.seconds})
        runner = GraphExecutor(tools, settings, provider, event, provider.budget)
        report = runner.execute(plan, question)
        computed = [s for s in runner.final_plan.steps if s.step_id in runner.results and s.tool_name not in {'generate_chart', 'get_dataset_info', 'preview_data'}]
        return AgentOutcome(runner.calls, runner.results[computed[-1].step_id] if computed else {}, report.answer,
            report.charts[-1] if report.charts else None, report.status, report=report.model_dump(), usage=provider.usage, plan=runner.final_plan.model_dump())


_clip_result = clip_context
