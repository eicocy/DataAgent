"""Per-run server limits, shared by all model and exploration calls."""
import json
import time
import math
from dataclasses import dataclass
from contextvars import ContextVar
from datetime import UTC, datetime

task_deadline_context = ContextVar('task_deadline', default=None)
FINALIZE_SECONDS = 2


def execution_seconds(job, settings, record=None):
    if job.kind in {'parse', 'file_parse'}:
        return settings.parse_timeout_seconds
    if job.kind == 'report':
        return settings.report_timeout_seconds
    config = getattr(record, 'request_config_json', None) or {}
    return LIMITS[config['depth']][3] if config.get('inputs') and config.get('depth') in LIMITS else settings.analysis_timeout_seconds


def bind_task_deadline(job, seconds):
    """Translate the persisted execution start into a process-local monotonic deadline."""
    age = max(0, (datetime.now(UTC).replace(tzinfo=None)-job.started_at.replace(tzinfo=None)).total_seconds()) if job.started_at else 0
    return task_deadline_context.set(time.monotonic()+max(0, seconds-age))

LIMITS = {'FAST': (6, 0, 6, 60, 20000), 'STANDARD': (16, 0, 10, 180, 60000), 'DEEP': (32, 3, 16, 600, 120000)}


class BudgetExceeded(ValueError):
    pass


class TaskTimeExceeded(Exception):
    code = 'TASK_TIMEOUT'
    public_message = '任务执行超过总时间预算，已保留完成的成果。'


def ensure_execution_time(stage):
    deadline = task_deadline_context.get()
    if deadline is not None and time.monotonic() >= deadline-FINALIZE_SECONDS:
        from app.diagnostics import error_info
        error = TaskTimeExceeded()
        error.info = error_info(error.code,reason_code='ANALYSIS_TOTAL_TIMEOUT',stage=stage,timeout_scope='task')
        raise error


@dataclass
class RuntimeBudget:
    depth: str
    max_tasks: int
    max_depth: int
    max_calls: int
    seconds: int
    max_tokens: int
    calls: int = 0
    tokens: int = 0
    started: float = 0

    @classmethod
    def for_depth(cls, depth):
        budget = cls(depth, *LIMITS[depth], started=time.monotonic())
        if task_deadline_context.get() is not None:
            budget.started = min(budget.started, task_deadline_context.get()-budget.seconds)
        return budget

    @property
    def deadline(self):
        return self.started + self.seconds

    @property
    def output_tokens(self):
        return {'FAST': 2048, 'STANDARD': 4096, 'DEEP': 8192}[self.depth]

    def reserve(self, payload):
        # Conservative estimate for absent usage, plus capped model output.
        reservation = math.ceil(len(json.dumps(payload, ensure_ascii=False, default=str, separators=(',', ':')).encode('utf-8')) / 2) + self.output_tokens
        if self.calls >= self.max_calls or self.tokens + reservation > self.max_tokens or time.monotonic() >= self.deadline-FINALIZE_SECONDS:
            raise BudgetExceeded('MODEL_BUDGET_EXCEEDED')
        self.calls += 1
        self.tokens += reservation
        return reservation

    def snapshot(self):
        return {'depth': self.depth, 'max_tasks': self.max_tasks, 'max_depth': self.max_depth, 'max_model_calls': self.max_calls,
            'max_execution_time': self.seconds, 'max_token_usage': self.max_tokens, 'model_calls': self.calls, 'tokens_reserved': self.tokens}


class BudgetProvider:
    def __init__(self, provider, budget):
        self.provider, self.budget = provider, budget
        if hasattr(provider, 'adapter'):
            provider.adapter.deadline = budget.deadline

    @property
    def usage(self):
        return dict(getattr(self.provider, 'usage', {}) or {}, runtime_budget=self.budget.snapshot())

    @property
    def emit(self):
        return getattr(self.provider, 'emit', lambda *args: None)

    def generate_structured(self, prompt_name, payload, schema):
        from app.agent.planner import compact_tool_schema
        return self._call(prompt_name, dict(payload=payload, schema=compact_tool_schema(schema.model_json_schema())), lambda: self.provider.generate_structured(prompt_name, payload, schema))

    def generate_text(self, prompt_name, payload):
        return self._call(prompt_name, payload, lambda: self.provider.generate_text(prompt_name, payload))

    def _call(self, prompt_name, payload, call):
        from app.agent.providers import load_prompt
        from app.agent.prompts import SYSTEM
        body = load_prompt(prompt_name)[2]
        reservation = self.budget.reserve({'payload': payload, 'system': SYSTEM, 'prompt': body})
        before = dict(getattr(self.provider, 'usage', {}) or {})
        try:
            return call()
        finally:
            after = getattr(self.provider, 'usage', {}) or {}
            if all(isinstance(after.get(k), (int, float)) for k in ('input_tokens', 'output_tokens')):
                actual = sum(max(0, after[k] - before.get(k, 0)) for k in ('input_tokens', 'output_tokens'))
                if actual:
                    self.budget.tokens += int(actual) - reservation

    def invoke(self, *args, **kwargs):
        self.budget.reserve({'args': args, 'kwargs': kwargs})
        return self.provider.invoke(*args, **kwargs)
