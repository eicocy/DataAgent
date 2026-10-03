"""V3 scheduling over existing tools, validators, evidence and interpretation."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, UTC
from dataclasses import replace
import time
from pydantic import BaseModel, ConfigDict, Field
from app.agent.executor import WorkflowExecutor, transition_step, clip_context
from app.agent.schemas import AnalysisStep, ToolCall
from app.agent.task_graph import validate_graph
from app.analysis.catalog import build_registry
from app.analysis.context import DatasetContext
from app.execution.validators import ResultValidationError, validate_result
from app.analysis.errors import ToolError, ToolInputError
from app.tools.schemas import ToolResult


class InputWorkspace:
    """One private compatibility adapter per input, all callbacks on the owner thread."""
    def __init__(self, inputs):
        self.inputs = inputs
        self.active = next(iter(inputs.values()))
        self.frame_results, self.call_results, self.reuse_steps = {}, {}, {}
        self.registry = getattr(self.active, '_registry', None) or build_registry(include_legacy=True)
        self.conversation_state = getattr(self.active, 'conversation_state', None)
        self.model_metadata = getattr(self.active, 'model_metadata', {})

    def __getattr__(self, name):
        return getattr(self.active, name)

    def select(self, alias):
        self.active = self.inputs[alias]
        self.active.frame_results, self.active.call_results = self.frame_results, self.call_results
        self.active.deadline = self.deadline

    def execute(self, *args, **kwargs):
        return self.active.execute(*args, **kwargs)


class ExplorationProposal(BaseModel):
    model_config = ConfigDict(extra='forbid')
    trigger_step_id: str | None = None
    reason: str = Field(default='', max_length=500)
    steps: list[AnalysisStep] = Field(default_factory=list, max_length=8)


def validate_replacement(old, replacement, completed):
    if old.task_id != replacement.task_id or old.inputs != replacement.inputs:
        raise ValueError('REPLAN_INPUT_CHANGED')
    next_steps = {s.step_id: s for s in replacement.steps}
    required = {s.step_id for s in old.steps if s.required} | set(old.expected_outputs)
    if not required <= next_steps.keys() or not required <= ({s.step_id for s in replacement.steps if s.required} | set(replacement.expected_outputs)):
        raise ValueError('REQUIRED_STEP_REMOVED')
    fields = {'step_id', 'tool_name', 'arguments', 'depends_on', 'source_ref', 'required', 'input_alias', 'exploration_parent', 'exploration_depth'}
    for step in old.steps:
        newer = next_steps.get(step.step_id)
        if step.step_id in completed and (newer is None or step.model_dump(include=fields) != newer.model_dump(include=fields)):
            raise ValueError('COMPLETED_STEP_CHANGED')
        if step.step_id in required and (newer.tool_name != step.tool_name or newer.input_alias != step.input_alias):
            raise ValueError('REQUIRED_TOOL_CHANGED')


class GraphExecutor(WorkflowExecutor):
    def __init__(self, tools, settings, adapter=None, emit=None, budget=None):
        super().__init__(tools, settings, adapter, emit)
        self.budget = budget
        self.deadline = budget.deadline
        tools.deadline = self.deadline

    def _safe_parallel(self, step):
        metadata = self.tools.registry.get(step.tool_name).metadata
        if not (metadata.parallel_safe and not metadata.modifies_dataset and metadata.chat_enabled and metadata.permissions <= self.tools.permissions):
            return False
        try:
            self.tools.registry.validate_input(step.tool_name, self._resolve(step.arguments, step))
            return step.source_ref == 'dataset' or step.source_ref in self.tools.frame_results
        except ValueError:
            return False

    def _source_context(self, step):
        tools = self.tools.inputs[step.input_alias]
        source = tools.frame if step.source_ref == 'dataset' else self.tools.frame_results[step.source_ref]
        frame = source.copy(deep=True)
        settings = __import__('app.config', fromlist=['get_settings']).get_settings()
        return DatasetContext.from_frame(frame, dataset_id=tools.dataset.id, dataset_version=getattr(tools, 'dataset_version_id', None),
            source_ref=step.source_ref, max_bytes=settings.dataframe_max_bytes, registry=self.tools.registry)

    def _run_parallel(self, steps):
        registry = self.tools.registry
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='analysis-readonly')
        pending = []
        try:
            for step in steps:
                self.tools.select(step.input_alias)
                if getattr(self.tools, 'check_lease', None):
                    self.tools.check_lease()
                transition_step(step, 'RUNNING')
                step.started_at = datetime.now(UTC).isoformat()
                self.attempts += 1
                self.step_attempts[step.step_id] = 1
                args = self._resolve(step.arguments, step)
                tool = registry.get(step.tool_name)
                parsed = registry.validate_input(step.tool_name, args)
                context = self._source_context(step)
                call = ToolCall(call_id=step.step_id, step_id=step.step_id, attempt=1, tool_name=step.tool_name, parameters=args, source_ref=step.source_ref, status='running').model_dump()
                call.update(input_alias=step.input_alias, started_at=step.started_at)
                self.calls.append(call)
                self.emit('call', call.copy())
                self.emit('tool_parameters', {'parameters': parsed.model_dump(mode='json'), 'tool_name': step.tool_name})
                pending.append((step, call, context, tool, time.monotonic(), pool.submit(tool.execute, context, parsed)))
            self.emit('plan', self.final_plan.model_dump())
            self.emit('stage', {'stage': 'tool', 'timeout_seconds': min(registry.get(s.tool_name).metadata.timeout_seconds for s in steps)})
            for step, call, context, tool, started, future in pending:
                self.tools.select(step.input_alias)
                computed = False
                try:
                    while True:
                        if getattr(self.tools, 'check_lease', None):
                            self.tools.check_lease()
                        if not self._budget_available() and time.monotonic() >= self.deadline:
                            raise ValueError('TOOL_TIMEOUT')
                        try:
                            output = future.result(timeout=.1)
                            break
                        except TimeoutError:
                            if time.monotonic() - started >= tool.metadata.timeout_seconds:
                                raise ValueError('TOOL_TIMEOUT')
                    output = registry.validate_output(tool, context, output)
                    data = output.data.model_dump(mode='json')
                    if data.get('columns') and isinstance(data['columns'][0], dict):
                        data['columns'] = [c['name'] for c in data['columns']]
                    notes = validate_result(data, output.frame, result_type=step.tool_name, parameters=call['parameters'])
                    self.result_warnings.extend(n.message for n in notes)
                    self.result_warnings.extend(w.message for w in output.warnings)
                    if output.frame is not None:
                        memory = sum(int(f.memory_usage(deep=True).sum()) for f in self.tools.frame_results.values()) + int(output.frame.memory_usage(deep=True).sum())
                        if memory > context.max_bytes:
                            raise ValueError('RESULT_BUDGET_EXCEEDED')
                        self.tools.frame_results[step.step_id] = output.frame.copy(deep=True)
                    computed = True
                    # Refresh execution pointer on the main thread before persistence.
                    self.emit('call', call.copy())
                    self.emit('result_validated', {'step_id': step.step_id, 'warnings': [n.code for n in notes]})
                    persisted = self.emit('result', {'step_id': step.step_id, 'tool_name': step.tool_name, 'data': data, 'frame': output.frame, 'input_alias': step.input_alias})
                    self.results[step.step_id] = data
                    self.tools.call_results[step.step_id] = data
                    if isinstance(persisted, dict) and persisted.get('artifact_id'):
                        step.result_ref = f"artifact:{persisted['artifact_id']}"
                        call['artifact_id'] = persisted['artifact_id']
                    call.update(status='succeeded', result_summary=f'{step.tool_name} completed')
                    transition_step(step, 'COMPLETED')
                    if isinstance(data.get('rows'), list):
                        self.tables.append(dict(data, source_ref=step.step_id))
                except Exception as exc:
                    if exc.__class__.__name__ == 'WorkerLeaseLost':
                        raise
                    code = getattr(exc, 'code', None) or ('TOOL_TIMEOUT' if str(exc) == 'TOOL_TIMEOUT' else 'TOOL_EXECUTION_FAILED')
                    call.update(status='failed', error_code=code, result_summary='计算或持久化未通过校验')
                    step.error = code
                    transition_step(step, 'FAILED')
                    if (computed or code in {'TOOL_TIMEOUT', 'RESULT_BUDGET_EXCEEDED'}
                        or isinstance(exc, ResultValidationError) and not exc.recoverable
                        or isinstance(exc, ToolError) and not isinstance(exc, ToolInputError)
                        or not isinstance(exc, (ValueError, KeyError, TypeError))):
                        self.unrecoverable_steps.add(step.step_id)
                step.finished_at = datetime.now(UTC).isoformat()
                call.update(duration_ms=int((time.monotonic() - started) * 1000), completed_at=step.finished_at)
                self.emit('call', call.copy())
                self.emit('plan', self.final_plan.model_dump())
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            self.emit('stage', {'stage': 'idle'})

    def _explore(self, plan):
        if not self.adapter or plan.depth != 'DEEP' or not self.results or not self._budget_available():
            return False
        remaining = self.budget.max_tasks - len(plan.steps)
        if remaining <= 0:
            return False
        try:
            proposal = ExplorationProposal.model_validate(self.adapter.generate_structured('exploration_planner', {
                'question': self.question, 'completed_results': clip_context(self._model_results()), 'remaining_tasks': remaining,
                'budget': self.budget.snapshot(), 'tools': self.tools.registry.get_llm_tool_manifest(self.tools.permissions),
                'plan': plan.model_dump()}, ExplorationProposal))
            if not proposal.steps:
                return False
            parents = {s.step_id: s for s in plan.steps}
            parent = parents.get(proposal.trigger_step_id)
            if not parent or parent.step_id not in self.results or not proposal.reason.strip():
                raise ValueError('EXPLORATION_REQUIRES_EVIDENCE')
            depth = parent.exploration_depth + 1
            if depth > self.budget.max_depth or len(proposal.steps) > remaining:
                raise ValueError('EXPLORATION_BUDGET')
            for step in proposal.steps:
                if step.step_id in parents or step.input_alias != parent.input_alias:
                    raise ValueError('EXPLORATION_INPUT_CHANGED')
                step.exploration_parent, step.exploration_depth = parent.step_id, depth
            candidate = plan.model_copy(deep=True)
            candidate.steps.extend(proposal.steps)
            validation = candidate.model_copy(deep=True)
            for step in validation.steps[:len(plan.steps)]:
                step.status, step.result_ref, step.error, step.retry_count = 'PENDING', None, None, 0
                step.started_at = step.finished_at = None
            validate_graph(validation, self.columns, self.tools.permissions, self.budget.max_tasks)
            plan.steps.extend(proposal.steps)
            self.emit('exploration_created', {'trigger_step_id': parent.step_id, 'step_ids': [s.step_id for s in proposal.steps], 'depth': depth, 'reason': proposal.reason})
            return True
        except Exception as exc:
            if exc.__class__.__name__ == 'WorkerLeaseLost':
                raise
            self.result_warnings.append('主动探索未生成可验证的新任务或已达到预算，保留已完成分析。')
            return False

    def execute(self, plan, question):
        self.final_plan, self.question = plan, question
        self.columns = {alias: {c.name: c.data_type for c in tools.columns} for alias, tools in self.tools.inputs.items()}
        required = {s.step_id for s in plan.steps if s.required} | set(plan.expected_outputs)
        plan.status = 'RUNNING'
        self.emit('plan', plan.model_dump())
        explored = 0
        replans = 0
        while True:
            pending = {s.step_id for s in plan.steps if s.status == 'PENDING'}
            while pending and self._budget_available():
                ready = sorted([s for s in plan.steps if s.step_id in pending and all(d in self.results for d in s.depends_on)], key=lambda s: -s.priority)
                if not ready:
                    break
                parallel = [s for s in ready if self._safe_parallel(s)][:min(2, self.settings.max_tool_attempts - self.attempts)]
                batch = parallel if len(parallel) == 2 else ready[:1]
                for step in batch:
                    pending.remove(step.step_id)
                    transition_step(step, 'READY')
                    self.emit('step_ready', {'step_id': step.step_id})
                if len(batch) == 2:
                    self._run_parallel(batch)
                else:
                    step = batch[0]
                    self.tools.select(step.input_alias)
                    step.started_at = datetime.now(UTC).isoformat()
                    self._run_step(step, question)
                    step.finished_at = datetime.now(UTC).isoformat()
            for step in plan.steps:
                if step.step_id in pending:
                    transition_step(step, 'SKIPPED')
                    step.error = 'DEPENDENCY_OR_BUDGET'
                    self.emit('call', dict(ToolCall(call_id=step.step_id, step_id=step.step_id, attempt=1, tool_name=step.tool_name,
                        parameters=step.arguments, source_ref=step.source_ref, status='skipped', error_code=step.error).model_dump(), input_alias=step.input_alias))
            if required - self.results.keys() and replans < getattr(self.settings, 'max_replans', 2) and self.adapter and not self.unrecoverable_steps and self._budget_available() and getattr(self.tools, 'configuration', None):
                replans += 1
                try:
                    from app.agent.planner import Planner
                    replacement = Planner(self.adapter).plan_v3(question, self.tools.metadata_by_input, self.tools.conversation_state,
                        task_id=plan.task_id, intent=plan.intent, config=self.tools.configuration, permissions=self.tools.permissions,
                        prior_plan=plan,
                        correction=clip_context({'plan': plan.model_dump(), 'completed_results': self._model_results(),
                            'failed_steps': sorted(required - self.results.keys()), 'instruction': '保留已完成节点原定义及全部必需节点和工具，仅修复失败路径'}))
                    validate_replacement(plan, replacement, set(self.results))
                    completed = {s.step_id: s for s in plan.steps if s.step_id in self.results}
                    replacement.steps = [completed.get(s.step_id, s) for s in replacement.steps]
                    plan = self.final_plan = replacement
                    required.update(s.step_id for s in plan.steps if s.required)
                    required.update(plan.expected_outputs)
                    self.replanned = True
                    self.emit('replan', {'round': replans, 'failed_steps': sorted(required - self.results.keys())})
                    continue
                except Exception as exc:
                    if exc.__class__.__name__ == 'WorkerLeaseLost':
                        raise
            if explored >= self.budget.max_depth or not self._explore(plan):
                break
            explored += 1
            required.update(s.step_id for s in plan.steps if s.required)
        plan.budget = self.budget.snapshot()
        return self._finish(required, question)
