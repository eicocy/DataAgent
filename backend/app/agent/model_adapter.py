import time
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.prompts import SYSTEM
from app.agent.budget import task_deadline_context, FINALIZE_SECONDS
from app.diagnostics import classify_model_error, error_info


class ModelCallFailure(Exception):
    def __init__(self, reason, info):
        self.code = 'TASK_TIMEOUT' if reason in {'LLM_CALL_TIMEOUT', 'ANALYSIS_TOTAL_TIMEOUT'} else 'MODEL_UNAVAILABLE'
        self.public_message = info['reason']
        self.info = info
        super().__init__(reason)


class ModelAdapter:
    def __init__(self, model, settings, emit=None):
        self.model, self.settings, self.emit = model, settings, emit or (lambda *args: None)
        self.calls = 0
        self.usage = None
        self.deadline = time.monotonic() + settings.analysis_timeout_seconds
        if task_deadline_context.get() is not None:
            self.deadline = task_deadline_context.get()
        self.operation = None

    def invoke(self, prompt, payload, schema=None, name=None):
        if len(payload) > 30000:
            import json
            from app.agent.executor import clip_context
            content = json.loads(payload)
            if 'tools' in content and ('dataset' in content or 'datasets' in content):
                # 工具参数与授权字段不能被静默裁剪；只缩短可选会话背景。
                for key in ('summary', 'previous_analysis', 'previous_plan'):
                    if len(json.dumps(content, ensure_ascii=False, default=str)) <= 60000:
                        break
                    content[key] = None
                if len(json.dumps(content, ensure_ascii=False, default=str)) > 60000:
                    error = ValueError('MODEL_CONTEXT_BUDGET_EXCEEDED')
                    error.details = {'actual_length': len(json.dumps(content, ensure_ascii=False, default=str)), 'max_length': 60000}
                    raise error
            else:
                content = clip_context(content)
            payload = json.dumps(content, ensure_ascii=False, default=str)
        if self.calls >= self.settings.max_model_calls:
            raise ValueError("MODEL_BUDGET_EXCEEDED")
        remaining = self.deadline-time.monotonic()-FINALIZE_SECONDS
        if remaining <= 0:
            info = error_info('TASK_TIMEOUT', reason_code='ANALYSIS_TOTAL_TIMEOUT', stage='llm', operation=self.operation,
                              timeout_scope='task', limit_seconds=self.settings.analysis_timeout_seconds)
            raise ModelCallFailure('ANALYSIS_TOTAL_TIMEOUT', info)
        configured_timeout = getattr(self.settings, 'llm_timeout_seconds', 90)
        timeout = min(configured_timeout, remaining)
        self.calls += 1
        self.emit("stage", {"stage": "llm", 'operation': self.operation, 'timeout_seconds': timeout})
        target = self.model
        if schema:
            from app.agent.planner import compact_tool_schema
            target = target.bind_tools([{"name": name, "description": "Return validated structured output", "parameters": compact_tool_schema(schema.model_json_schema())}])
        if hasattr(target, 'bind'):
            target = target.bind(timeout=timeout)
        started = time.monotonic()
        try:
            response = target.invoke([SystemMessage(content=SYSTEM + "\n" + prompt), HumanMessage(content=payload)])
        except Exception as exc:
            reason = classify_model_error(exc)
            if reason:
                scope = 'task' if reason=='LLM_CALL_TIMEOUT' and remaining<=configured_timeout else 'stage'
                if scope=='task':
                    reason = 'ANALYSIS_TOTAL_TIMEOUT'
                info = error_info('TASK_TIMEOUT' if 'TIMEOUT' in reason else 'MODEL_UNAVAILABLE', reason_code=reason,
                                  stage='llm', operation=self.operation, limit_seconds=round(timeout,3), timeout_scope=scope, exception=exc)
                info['stage_elapsed_seconds'] = round(time.monotonic()-started,3)
                raise ModelCallFailure(reason, info) from exc
            raise
        finally:
            self.emit("stage", {"stage": "idle"})
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.usage = {key: (self.usage or {}).get(key, 0) + value for key, value in usage.items() if isinstance(value, (int, float))}
        self.emit("usage", self.usage)
        return response
