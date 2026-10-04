"""Select verified facts and render their real values without model arithmetic."""
from app.execution.evidence import ReportContent, render_report


class ResultInterpreter:
    def __init__(self, provider, emit=None):
        self.provider = provider
        self.emit = emit or getattr(provider, 'emit', lambda *args: None)

    def interpret(self, *, question: str, goal: str, results: dict, incomplete_steps: list[str], binding_results: dict | None = None):
        from app.agent.executor import clip_context
        payload = clip_context({'question': question[:2000], 'goal': goal[:500],
                                'results': results, 'incomplete_steps': incomplete_steps})
        original_error = None
        for attempt in range(2):
            try:
                raw = self.provider.generate_structured('result_interpreter', payload, ReportContent)
                content = ReportContent.model_validate(raw)
                answer = render_report(content, binding_results if binding_results is not None else payload['results'])
                findings = [{'kind': 'bound_fact', 'reference': fact.model_dump()} for fact in content.facts]
                return answer, findings
            except ValueError as exc:
                if str(exc) in {'MODEL_BUDGET_EXCEEDED', 'MODEL_CONTEXT_BUDGET_EXCEEDED'}:
                    raise
                self.emit('interpretation_rejected', {'attempt': attempt + 1, 'code': 'REPORT_FACT_BINDING_INVALID'})
                if attempt:
                    raise
                original_error = exc
                # 只返回安全错误码，禁止把模型编造的数值或原始输出放回上下文。
                payload['correction'] = {'code': 'REPORT_FACT_BINDING_INVALID',
                    'instruction': '仅使用 results 中实际存在的事实路径；所有数字与标签用单层占位符绑定；每个 fact 必须使用，禁止自行运算。'}
                self.emit('interpretation_retry', {'attempt': 2})
            except Exception:
                if original_error is not None:
                    raise original_error from None
                raise
