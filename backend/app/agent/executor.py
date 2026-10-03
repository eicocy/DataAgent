import json
import time
from decimal import Decimal
import sqlglot
from sqlglot import exp
from datetime import datetime, UTC
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.agent.schemas import ExecutionPlan, AnalysisPlan, FinalReport, ToolCall
from app.agent.prompts import REPORT
from app.agent.planner import Planner, validate_plan_arguments
from app.execution.validators import ResultValidationError, validate_result
from app.execution.evidence import ReportContent, render_report
from app.analysis.errors import ToolError,ToolInputError


def clip_context(value: dict, max_rows=200, max_chars=30000) -> dict:
    """Only model context is clipped. Never mutate full computations or artifacts."""
    def bound(item):
        if isinstance(item, str):
            return item[:1000]
        if isinstance(item, list):
            return [bound(x) for x in item[:max_rows]]
        if isinstance(item, dict):
            return {str(k)[:1000]: bound(v) for k, v in list(item.items())[:200]}
        return item
    output = bound(value)
    output["truncated"] = output != value
    while len(json.dumps(output, ensure_ascii=False, default=str)) > max_chars:
        containers = [(parent, key, obj) for parent, key, obj in _containers(output) if isinstance(obj, (list, dict)) and obj]
        if not containers:
            return {"truncated": True, "summary": "Result exceeds model context budget"}
        parent, key, obj = max(containers, key=lambda x: len(json.dumps(x[2], ensure_ascii=False, default=str)))
        parent[key] = obj[:len(obj) // 2] if isinstance(obj, list) else dict(list(obj.items())[:len(obj) // 2])
        output["truncated"] = True
    return output


def _containers(item):
    if isinstance(item, dict):
        for key, value in list(item.items()):
            yield item, key, value
            yield from _containers(value)
    elif isinstance(item, list):
        for key, value in enumerate(item):
            yield item, key, value
            yield from _containers(value)


class StepCorrection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    arguments: dict[str, Any]


STEP_TRANSITIONS = {
    'PENDING': {'READY', 'COMPLETED', 'SKIPPED', 'CANCELLED'},
    'READY': {'RUNNING', 'SKIPPED', 'CANCELLED'},
    'RUNNING': {'COMPLETED', 'FAILED', 'WAITING', 'CANCELLED'},
    'FAILED': {'RUNNING', 'WAITING', 'CANCELLED'},
    'WAITING': {'READY', 'CANCELLED'},
    'COMPLETED': set(), 'SKIPPED': set(), 'CANCELLED': set(),
}


def transition_step(step, target):
    if target not in STEP_TRANSITIONS[step.status]:
        raise ValueError('STEP_TRANSITION_INVALID')
    step.status = target


class WorkflowExecutor:
    def __init__(self, tools, settings, adapter=None, emit=None):
        self.tools, self.settings, self.adapter = tools, settings, adapter
        self.emit = emit or (lambda *args: None)
        self.calls, self.results, self.charts, self.tables = [], {}, [], []
        self.attempts = 0
        self.step_attempts = {}
        self.correction_counts = {}
        self.replanned = False
        self.final_plan = None
        self.unrecoverable_steps = set()
        self.result_warnings = []
        self.deadline = time.monotonic() + settings.analysis_timeout_seconds
        self.tools.deadline=self.deadline

    @staticmethod
    def completion_status(has_result, has_answer, incomplete):
        return "failed" if not has_result else "partial" if incomplete or not has_answer else "succeeded"

    def _resolve(self, value, step):
        if isinstance(value, dict) and "$ref" in value:
            if set(value) != {"$ref", "field"} or value["$ref"] not in step.depends_on or value["$ref"] not in self.results:
                raise ValueError("Invalid result reference")
            if not isinstance(value['field'], str) or value['field'] not in self.results[value['$ref']]:
                raise ValueError('Referenced result field is missing')
            return self.results[value["$ref"]][value["field"]]
        if isinstance(value, dict):
            return {k: self._resolve(v, step) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve(v, step) for v in value]
        return value

    def _budget_available(self):
        return time.monotonic() < self.deadline and self.attempts < self.settings.max_tool_attempts

    def _reuse_completed(self, plan):
        """Hydrate unchanged completed steps from same-version, owned artifacts."""
        import pandas as pd
        available = getattr(self.tools, 'reuse_steps', {})
        remaining = {step.step_id for step in plan.steps}
        while remaining:
            changed = False
            for step in plan.steps:
                if step.step_id not in remaining or step.tool_name == 'generate_chart':
                    continue
                cached = available.get(step.step_id)
                if not cached or any(dep not in self.results for dep in step.depends_on):
                    continue
                old = cached['step']
                signature = ('tool_name', 'depends_on', 'source_ref', 'required')
                if any(old.get(key) != getattr(step, key) for key in signature):
                    continue
                def normalized_arguments(arguments, source_ref):
                    arguments = dict(arguments)
                    if arguments.get('source_ref') == source_ref:
                        arguments.pop('source_ref')
                    return arguments
                if normalized_arguments(old['arguments'], old['source_ref']) != normalized_arguments(step.arguments, step.source_ref):
                    continue
                payload = cached['payload']
                result = dict(payload.get('data') or {})
                if payload.get('rows') and 'rows' not in result:
                    result['rows'] = payload['rows']
                self.results[step.step_id] = result
                self.tools.frame_results[step.step_id] = pd.DataFrame(payload.get('rows') or [])
                self.tools.call_results[step.step_id] = result
                transition_step(step, 'COMPLETED')
                step.result_ref = f"artifact:{cached['artifact_id']}"
                call = ToolCall(call_id=f'{step.step_id}-reused', step_id=step.step_id,
                    attempt=1, tool_name=step.tool_name, parameters=step.arguments,
                    source_ref=step.source_ref, status='succeeded',
                    result_summary='复用同版本未过期分析工件', artifact_id=cached['artifact_id']).model_dump()
                call['reused'] = True
                self.calls.append(call)
                self.emit('call', call.copy())
                remaining.remove(step.step_id)
                changed = True
            if not changed:
                break

    def _model_results(self):
        """Keep raw previews out of model context while retaining complete artifacts."""
        tools = {call['step_id']: call['tool_name'] for call in self.calls if call['status'] == 'succeeded'}
        output = {}
        from app.tools.registry import tool_registry
        registry=tool_registry()
        for key, value in self.results.items():
            if tools.get(key) == 'sql_query' and self._aggregate_sql(key):
                frame = self.tools.frame_results.get(key)
                output[key] = dict(value)
                if frame is not None:
                    output[key]['rows'] = [dict(row, **{column: raw for column, raw in frame.iloc[index].items() if isinstance(raw, Decimal)}) for index, row in enumerate(value.get('rows', []))]
            elif tools.get(key) in registry and registry[tools[key]].metadata.exposes_rows:
                output[key] = {field: item for field, item in value.items() if field not in {'rows', 'sorted_rows', 'preview_rows'}}
            elif tools.get(key) == 'get_dataset_info':
                output[key] = dict(value, columns=[{field: item for field, item in column.items() if field != 'sample_values'} for column in value.get('columns', [])])
            else:
                output[key] = value
        return output

    def _aggregate_sql(self, key):
        """Expose derived SQL metrics, never arbitrary projected source rows."""
        call = next(call for call in reversed(self.calls) if call['step_id'] == key and call['status'] == 'succeeded')
        try:
            query = sqlglot.parse_one(call['parameters']['query'], read='mysql')
            if not isinstance(query, exp.Select) or not any(expression.find(exp.AggFunc) is not None for expression in query.expressions):
                return False
            grouping = query.args.get('group')
            groups = grouping.expressions if grouping else []
            for expression in query.expressions:
                expression = expression.this if isinstance(expression, exp.Alias) else expression
                if expression in groups:
                    continue
                if expression.find(exp.AggFunc) is None or expression.find(exp.Window) is not None:
                    return False
                if any(column.find_ancestor(exp.AggFunc) is None for column in expression.find_all(exp.Column)):
                    return False
            return True
        except Exception:
            return False

    def _run_step(self, step, question):
        parameters = step.arguments
        while self._budget_available() and self.step_attempts.get(step.step_id, 0) <= getattr(self.settings, 'max_retries_per_step', 2):
            transition_step(step, 'RUNNING')
            self.emit('plan', self.final_plan.model_dump())
            self.attempts += 1
            attempt = self.step_attempts.get(step.step_id, 0) + 1
            self.step_attempts[step.step_id] = attempt
            started = time.monotonic()
            call = ToolCall(call_id=step.step_id if attempt == 1 else f'{step.step_id}-attempt-{attempt}', step_id=step.step_id, attempt=attempt, tool_name=step.tool_name, parameters=parameters, source_ref=step.source_ref, status='running').model_dump()
            self.calls.append(call)
            call['started_at'] = datetime.now(UTC).isoformat()
            self.emit('call', call.copy())
            self.emit('stage', {'stage': 'sql' if step.tool_name == 'sql_query' else 'pandas'})
            error = None
            computed = False
            try:
                args = self._resolve(parameters, step)
                if 'source_ref' in args and args['source_ref'] != step.source_ref:
                    raise ValueError('Argument source conflicts with plan')
                if step.tool_name == 'generate_chart' and args.get('source_tool_call_id') not in (None, '', step.source_ref):
                    raise ValueError('Chart source conflicts with plan')
                result = self.tools.execute(step.tool_name, args, source_ref=step.source_ref, call_id=step.step_id)
                if result.status != 'succeeded':
                    raise ValueError('Tool failed')
                validation_notes = validate_result(result.data, self.tools.frame_results.get(step.step_id),
                    result_type=step.tool_name, parameters=args)
                self.result_warnings.extend(note.message for note in validation_notes)
                self.emit('result_validated', {'step_id': step.step_id,
                    'warnings': [note.code for note in validation_notes]})
                self.result_warnings.extend(w.message for w in result.warnings)
                computed = True
                # Do not mark success until persistence succeeds. Storage errors must not trigger paid recomputation.
                persisted = self.emit('result', {'step_id': step.step_id, 'tool_name': step.tool_name, 'data': result.data, 'frame': self.tools.frame_results.get(step.step_id)})
                self.results[step.step_id] = result.data
                call.update(status='succeeded', result_summary=result.summary, duration_ms=result.execution_time_ms)
                if isinstance(persisted, dict):
                    call['artifact_id'] = persisted.get('artifact_id')
                    step.result_ref = f"artifact:{persisted.get('artifact_id')}" if persisted.get('artifact_id') else None
                transition_step(step, 'COMPLETED')
                step.error = None
                if result.metadata.get('result_kind')=='legacy_chart':
                    chart = dict(result.data)
                    chart['source_ref'] = step.source_ref
                    if isinstance(persisted, dict):
                        chart['artifact_id'] = persisted.get('artifact_id')
                    self.charts.append(chart)
                elif step.tool_name not in {'get_dataset_info', 'preview_data'}:
                    table = dict(persisted or clip_context(result.data, max_rows=100))
                    table['source_ref'] = step.step_id
                    self.tables.append(table)
            except Exception as exc:
                error = exc
                if computed or (isinstance(exc, ResultValidationError) and not exc.recoverable) or isinstance(exc,ToolError) and not isinstance(exc,ToolInputError) or not isinstance(exc, (ValueError, KeyError, TypeError)):
                    self.unrecoverable_steps.add(step.step_id)
                call.update(status='failed', error_code=getattr(exc, 'code', 'TOOL_EXECUTION_FAILED'), result_summary='工具参数、数据或执行结果未通过校验', duration_ms=int((time.monotonic() - started) * 1000))
                transition_step(step, 'FAILED')
                step.error = call['error_code']
            call['completed_at'] = datetime.now(UTC).isoformat()
            self.emit('call', call.copy())
            step.retry_count = attempt - 1
            self.emit('plan', self.final_plan.model_dump())
            self.emit('stage', {'stage': 'idle'})
            if error is None:
                step.arguments = parameters
                return
            repair_limit = getattr(self.settings, 'max_retries_per_step', 2) if isinstance(self.final_plan, AnalysisPlan) else 1
            if (step.step_id in self.unrecoverable_steps or not self.adapter or
                self.correction_counts.get(step.step_id, 0) >= repair_limit or not self._budget_available()):
                return
            self.correction_counts[step.step_id] = self.correction_counts.get(step.step_id, 0) + 1
            try:
                from app.tools.registry import tool_registry
                correction_payload = clip_context({'question': question, 'step': step.model_dump(), 'metadata': self.tools.get_dataset_info(type('InfoArgs', (), {'include_samples': False})()), 'tool_schema': tool_registry()[step.tool_name].schema.model_json_schema(), 'error': '参数、字段、数据类型或来源校验失败', 'results': self._model_results()})
                if isinstance(self.final_plan, AnalysisPlan) and hasattr(self.adapter, 'generate_structured'):
                    corrected = StepCorrection.model_validate(self.adapter.generate_structured(
                        'step_correction', correction_payload, StepCorrection))
                else:
                    response = self.adapter.invoke('仅修正当前步骤参数。保持工具、source_ref和依赖不变。', json.dumps(correction_payload, ensure_ascii=False, default=str), StepCorrection, 'submit_step_correction')
                    calls = response.tool_calls or []
                    if len(calls) != 1 or calls[0]['name'] != 'submit_step_correction':
                        return
                    corrected = StepCorrection.model_validate(calls[0]['args'])
                candidate = step.model_copy(update={'arguments': corrected.arguments})
                validate_plan_arguments(ExecutionPlan.model_construct(steps=[candidate]))
                parameters = corrected.arguments
                self.emit('retry', {'step_id': step.step_id, 'attempt': attempt + 1})
            except Exception:
                return

    def execute(self, plan: ExecutionPlan, question: str):
        if isinstance(plan, AnalysisPlan):
            self._reuse_completed(plan)
        required = {step.step_id for step in plan.steps if step.required} | set(
            plan.expected_outputs if isinstance(plan, AnalysisPlan) else plan.completion_requirements)
        required_tools = {step.step_id: step.tool_name for step in plan.steps if step.step_id in required}
        successful_steps = {step.step_id: step.model_dump(include={'step_id', 'tool_name', 'arguments', 'depends_on', 'source_ref', 'required'})
                            for step in plan.steps if step.step_id in self.results}
        active_plan = plan
        max_rounds = min(3, getattr(self.settings, 'max_replans', 2) + 1) if isinstance(plan, AnalysisPlan) else 2
        for round_number in range(max_rounds):
            self.final_plan = active_plan
            if isinstance(active_plan, AnalysisPlan):
                active_plan.status = 'RUNNING'
            self.emit('plan', active_plan.model_dump())
            pending = {step.step_id for step in active_plan.steps if step.step_id not in self.results}
            while pending and self._budget_available():
                ready = next((step for step in active_plan.steps if step.step_id in pending and
                              all(dep in self.results for dep in step.depends_on)), None)
                if ready is None:
                    break
                pending.remove(ready.step_id)
                transition_step(ready, 'READY')
                self.emit('step_ready', {'step_id': ready.step_id})
                self.emit('plan', active_plan.model_dump())
                self._run_step(ready, question)
                if ready.step_id in self.results:
                    successful_steps[ready.step_id] = ready.model_dump(include={'step_id', 'tool_name', 'arguments', 'depends_on', 'source_ref', 'required'})
            for step in active_plan.steps:
                if step.step_id not in pending:
                    continue
                transition_step(step, 'SKIPPED')
                call = ToolCall(call_id=f'{step.step_id}-skipped-{round_number}', step_id=step.step_id, attempt=1, tool_name=step.tool_name, parameters=step.arguments, source_ref=step.source_ref, status='skipped', error_code='DEPENDENCY_OR_BUDGET', result_summary='依赖未完成或执行预算耗尽').model_dump()
                self.calls.append(call)
                self.emit('call', call.copy())
            self.emit('plan', active_plan.model_dump())
            incomplete = required - self.results.keys()
            if not incomplete or round_number >= max_rounds - 1 or not self.adapter or self.unrecoverable_steps or not self._budget_available():
                break
            self.replanned = True
            self.emit('replan', {'round': round_number + 1, 'failed_steps': sorted(incomplete)})
            try:
                from app.services.datasets import DatasetService
                metadata = getattr(self.tools, 'model_metadata', None) or DatasetService.metadata(self.tools.dataset, self.tools.columns)
                correction = clip_context({'plan': active_plan.model_dump(), 'completed_results': self._model_results(),
                    'failed_steps': sorted(incomplete),
                    'instruction': '保留所有已成功步骤的原定义和证据，不得删除原必需步骤；只修复未完成路径'})
                if isinstance(active_plan, AnalysisPlan):
                    replacement = Planner(self.adapter).plan_v2(question, metadata, self.tools.conversation_state,
                        task_id=active_plan.task_id, intent=active_plan.intent, permissions=self.tools.permissions,
                        max_steps=self.settings.max_plan_steps, correction=correction, prompt_name='replanner')
                else:
                    replacement = Planner(self.adapter).plan(question, metadata,
                        correction=correction, permissions=self.tools.permissions)
                replacements = {step.step_id: step.model_dump(include={'step_id', 'tool_name', 'arguments', 'depends_on', 'source_ref', 'required'}) for step in replacement.steps}
                if ((not isinstance(active_plan, AnalysisPlan) and not required <= replacements.keys()) or
                    any(replacements.get(key) != value for key, value in successful_steps.items())):
                    raise ValueError('Replan changed successful or required steps')
                if not isinstance(active_plan, AnalysisPlan) and any(replacements[key]['tool_name'] != value for key, value in required_tools.items()):
                    raise ValueError('Replan changed required tool capability')
                completed = {step.step_id: step for step in active_plan.steps if step.step_id in self.results}
                for step in replacement.steps:
                    if step.step_id in completed:
                        transition_step(step, 'COMPLETED')
                        step.result_ref = completed[step.step_id].result_ref
                next_required = {step.step_id for step in replacement.steps if step.required} | set(
                    replacement.expected_outputs if isinstance(replacement, AnalysisPlan) else replacement.completion_requirements)
                required = next_required if isinstance(replacement, AnalysisPlan) else required | next_required
                required_tools = {step.step_id: step.tool_name for step in replacement.steps if step.step_id in required}
                active_plan = replacement
            except Exception:
                break
        return self._finish(required, question)

    def _finish(self, required, question):
        incomplete = sorted(required - self.results.keys())
        valid_compute = any(step.step_id in self.results and step.tool_name not in {"get_dataset_info", "preview_data", "generate_chart"} for step in self.final_plan.steps)
        answer = None
        findings = []
        if valid_compute and self.adapter:
            try:
                self.emit('interpretation_started', {'completed_steps': len(self.results)})
                payload = clip_context({"question": question, "results": self._model_results(), "incomplete_steps": incomplete})
                if isinstance(self.final_plan, AnalysisPlan) and hasattr(self.adapter, 'generate_structured'):
                    from app.agent.interpreter import ResultInterpreter
                    answer, findings = ResultInterpreter(self.adapter, self.emit).interpret(
                        question=question, goal=self.final_plan.goal, results=self._model_results(),
                        incomplete_steps=incomplete)
                    content = None
                else:
                    response = self.adapter.invoke(REPORT, json.dumps(payload, ensure_ascii=False, default=str), ReportContent, "submit_final_report")
                    calls = response.tool_calls or []
                    content = ReportContent.model_validate(calls[0]["args"]) if len(calls) == 1 and calls[0]["name"] == "submit_final_report" else None
                if content:
                    answer = render_report(content, payload['results'])
                    findings = [{'kind': 'bound_fact', 'reference': fact.model_dump()} for fact in content.facts]
            except Exception:
                answer = None
        status = self.completion_status(valid_compute, bool(answer), incomplete)
        if isinstance(self.final_plan, AnalysisPlan):
            self.final_plan.status = {'succeeded': 'COMPLETED', 'partial': 'PARTIAL_SUCCESS', 'failed': 'FAILED'}[status]
            self.emit('plan', self.final_plan.model_dump())
            self.emit('plan_completed', {'status': self.final_plan.status})
        warnings = list(getattr(self.tools.dataset, "quality_warnings_json", None) or []) + self.result_warnings
        warnings = [w.get("message", w.get("code", "数据质量说明")) if isinstance(w, dict) else str(w) for w in warnings]
        for value in self.results.values():
            if value.get("excluded_count"):
                warnings.append(f"{value['excluded_count']} 个分组因首月非正或首末月缺失未参与增长率排名")
            if value.get("invalid_date_count"):
                warnings.append(f"{value['invalid_date_count']} 条日期无法解析，未参与时间统计")
        if not answer and valid_compute:
            warnings.append("模型总结不可用，以下保留真实计算结果")
        if incomplete:
            warnings.append("部分必需步骤未完成")
        return FinalReport(status=status, answer=answer, tables=self.tables, charts=self.charts, warnings=warnings, evidence_refs=list(self.results), findings=findings, incomplete_steps=incomplete)
