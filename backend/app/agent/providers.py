"""Provider-neutral structured and text generation over the existing model adapter."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Protocol, TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar('T', bound=BaseModel)


class LLMProvider(Protocol):
    def generate_structured(self, prompt_name: str, payload: dict, schema: type[T]) -> dict: ...
    def generate_text(self, prompt_name: str, payload: dict) -> str: ...


def load_prompt(name: str) -> tuple[str, str, str]:
    allowed = {'intent_router', 'analysis_planner', 'replanner', 'result_interpreter',
               'conversation_summarizer', 'general_chat', 'step_correction', 'workspace_planner', 'exploration_planner'}
    if name not in allowed:
        raise ValueError('PROMPT_NOT_FOUND')
    version = {'intent_router': 'v2', 'analysis_planner': 'v3', 'result_interpreter': 'v3'}.get(name, 'v1')
    return name, version, (Path(__file__).parent / 'prompt_templates' / f'{name}.{version}.txt').read_text(encoding='utf-8')


class FakeLLMProvider:
    """Deterministic offline provider; each generation consumes one response."""
    def __init__(self, responses, emit=None, max_model_calls=10):
        self.responses = iter(responses)
        self.usage = {}
        self.emit = emit or (lambda *args: None)
        self.calls = 0
        self.max_model_calls = max_model_calls

    def _next(self, prompt_name, validate):
        _, version, _ = load_prompt(prompt_name)
        if self.calls >= self.max_model_calls:
            raise ValueError('MODEL_BUDGET_EXCEEDED')
        self.calls += 1
        started = time.monotonic()
        status, error_code = 'succeeded', None
        try:
            return validate(next(self.responses))
        except Exception as exc:
            status = 'failed'
            error_code = 'MODEL_OUTPUT_INVALID' if isinstance(exc, (ValidationError, ValueError)) else 'MODEL_CALL_FAILED'
            raise
        finally:
            self.emit('llm_call', {'provider': 'fake', 'model': 'scripted',
                'prompt_version': f'{prompt_name}.{version}', 'input_tokens': 0, 'output_tokens': 0,
                'latency_ms': int((time.monotonic() - started) * 1000),
                'status': status, 'error_code': error_code})

    def generate_structured(self, prompt_name: str, payload: dict, schema: type[T]) -> dict:
        try:
            return self._next(prompt_name, lambda value: schema.model_validate(value).model_dump())
        except ValidationError as exc:
            raise ValueError('MODEL_OUTPUT_INVALID') from exc

    def generate_text(self, prompt_name: str, payload: dict) -> str:
        def parse(value):
            if not isinstance(value, str):
                raise ValueError('MODEL_OUTPUT_INVALID')
            return value
        return self._next(prompt_name, parse)


class LangChainProvider:
    def __init__(self, model, settings, provider_name: str, model_name: str, emit=None):
        from app.agent.model_adapter import ModelAdapter
        self.adapter = ModelAdapter(model, settings, emit)
        self.settings = settings
        self.provider_name, self.model_name = provider_name, model_name
        self.emit = emit or (lambda *args: None)

    @property
    def usage(self):
        return self.adapter.usage

    def _call(self, prompt, payload, schema=None, function_name=None, validate=None):
        started = time.monotonic()
        before = dict(self.adapter.usage or {})
        _, version, body = load_prompt(prompt)
        status, error_code = 'succeeded', None
        try:
            result = self.adapter.invoke(body, json.dumps(payload, ensure_ascii=False, default=str), schema, function_name)
            return validate(result) if validate else result
        except Exception as exc:
            status, error_code = 'failed', ('MODEL_BUDGET_EXCEEDED' if str(exc) == 'MODEL_BUDGET_EXCEEDED'
                else 'MODEL_OUTPUT_INVALID' if isinstance(exc, ValueError) else 'MODEL_CALL_FAILED')
            raise
        finally:
            after = self.adapter.usage or {}
            self.emit('llm_call', {'provider': self.provider_name, 'model': self.model_name,
                'prompt_version': f'{prompt}.{version}',
                'input_tokens': after.get('input_tokens', 0) - before.get('input_tokens', 0),
                'output_tokens': after.get('output_tokens', 0) - before.get('output_tokens', 0),
                'latency_ms': int((time.monotonic() - started) * 1000),
                'status': status, 'error_code': error_code})

    def generate_structured(self, prompt_name: str, payload: dict, schema: type[T]) -> dict:
        name = f'submit_{prompt_name}'
        def parse(response):
            calls = response.tool_calls or []
            if getattr(response, 'invalid_tool_calls', None) or len(calls) != 1 or calls[0]['name'] != name:
                raise ValueError('MODEL_OUTPUT_INVALID')
            try:
                return schema.model_validate(calls[0]['args']).model_dump()
            except ValidationError as exc:
                raise ValueError('MODEL_OUTPUT_INVALID') from exc
        return self._call(prompt_name, payload, schema, name, parse)

    def generate_text(self, prompt_name: str, payload: dict) -> str:
        def parse(response):
            if not isinstance(response.content, str):
                raise ValueError('MODEL_OUTPUT_INVALID')
            return response.content
        return self._call(prompt_name, payload, validate=parse)

    def invoke(self, prompt, payload, schema=None, name=None):
        # Existing correction and fact-binding paths share the same call budget.
        started = time.monotonic()
        status, error_code = 'succeeded', None
        try:
            return self.adapter.invoke(prompt, payload, schema, name)
        except Exception:
            status, error_code = 'failed', 'MODEL_CALL_FAILED'
            raise
        finally:
            self.emit('llm_call', {'provider': self.provider_name, 'model': self.model_name,
                'prompt_version': 'legacy.v1', 'input_tokens': None, 'output_tokens': None,
                'latency_ms': int((time.monotonic() - started) * 1000),
                'status': status, 'error_code': error_code})


def build_provider(settings, emit=None):
    from langchain_openai import ChatOpenAI
    name = settings.llm_provider
    if name == 'deepseek':
        if not settings.deepseek_api_key.strip():
            raise ValueError('MODEL_UNAVAILABLE')
        model_name = settings.deepseek_model
        model = ChatOpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url,
                          model=model_name, temperature=0, timeout=settings.llm_timeout_seconds, max_retries=1)
    elif name == 'openai':
        if not settings.openai_api_key.strip():
            raise ValueError('MODEL_UNAVAILABLE')
        model_name = settings.openai_model
        model = ChatOpenAI(api_key=settings.openai_api_key, model=model_name,
                          temperature=0, timeout=settings.llm_timeout_seconds, max_retries=1)
    else:
        raise ValueError('MODEL_PROVIDER_INVALID')
    return LangChainProvider(model, settings, name, model_name, emit)
