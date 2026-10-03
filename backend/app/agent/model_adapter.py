import time
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.prompts import SYSTEM


class ModelAdapter:
    def __init__(self, model, settings, emit=None):
        self.model, self.settings, self.emit = model, settings, emit or (lambda *args: None)
        self.calls = 0
        self.usage = None
        self.deadline = time.monotonic() + settings.analysis_timeout_seconds

    def invoke(self, prompt, payload, schema=None, name=None):
        if len(payload) > 30000:
            import json
            from app.agent.executor import clip_context
            content = json.loads(payload)
            if 'tools' in content and 'dataset' in content:
                # 工具参数与授权字段不能被静默裁剪；只缩短可选会话背景。
                for key in ('summary', 'previous_analysis', 'previous_plan'):
                    if len(json.dumps(content, ensure_ascii=False, default=str)) <= 60000:
                        break
                    content[key] = None
                if len(json.dumps(content, ensure_ascii=False, default=str)) > 60000:
                    raise ValueError('MODEL_CONTEXT_BUDGET_EXCEEDED')
            else:
                content = clip_context(content)
            payload = json.dumps(content, ensure_ascii=False, default=str)
        if self.calls >= self.settings.max_model_calls or time.monotonic() >= self.deadline:
            raise ValueError("MODEL_BUDGET_EXCEEDED")
        self.calls += 1
        self.emit("stage", {"stage": "llm"})
        target = self.model
        if schema:
            target = target.bind_tools([{"name": name, "description": "Return validated structured output", "parameters": schema.model_json_schema()}])
        try:
            response = target.invoke([SystemMessage(content=SYSTEM + "\n" + prompt), HumanMessage(content=payload)])
        finally:
            self.emit("stage", {"stage": "idle"})
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self.usage = {key: (self.usage or {}).get(key, 0) + value for key, value in usage.items() if isinstance(value, (int, float))}
        self.emit("usage", self.usage)
        return response
