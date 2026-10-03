import json
from pydantic import ValidationError
from app.agent.schemas import ExecutionPlan, AnalysisPlan, AnalysisStep
from app.agent.prompts import PLAN
from app.services.analysis_tools import model_tool_schemas
from app.tools.registry import tool_registry


def validate_plan_arguments(plan):
    registry = tool_registry()
    for step in plan.steps:
        deferred = []

        def references(value, path=()):
            if isinstance(value, dict) and '$ref' in value:
                if set(value) != {'$ref', 'field'} or value['$ref'] not in step.depends_on or not isinstance(value['field'], str):
                    raise ValueError('Invalid dynamic result reference')
                deferred.append(path)
            elif isinstance(value, dict):
                for key, item in value.items():
                    references(item, (*path, key))
            elif isinstance(value, list):
                for index, item in enumerate(value):
                    references(item, (*path, index))

        references(step.arguments)
        if 'source_ref' in step.arguments and step.arguments['source_ref'] != step.source_ref:
            raise ValueError('Argument source conflicts with plan')
        if step.tool_name == 'generate_chart' and step.arguments.get('source_tool_call_id') not in (None, '', step.source_ref):
            raise ValueError('Chart source conflicts with plan')
        try:
            registry[step.tool_name].schema.model_validate(step.arguments)
        except ValidationError as exc:
            # Only explicitly declared result values may defer type validation until execution.
            if any(not any(tuple(error['loc'])[:len(path)] == path for path in deferred) for error in exc.errors()):
                raise ValueError('Invalid tool arguments') from exc
    return plan


class Planner:
    def __init__(self, adapter):
        self.adapter = adapter

    def plan(self, question, metadata, context=None, correction=None, permissions=None):
        payload = {"question": question, "metadata": metadata, "tools": model_tool_schemas(permissions), "context": context or [], "correction": correction}
        for attempt in range(2):
            response = self.adapter.invoke(PLAN, json.dumps(payload, ensure_ascii=False, default=str), ExecutionPlan, "submit_execution_plan")
            try:
                calls = response.tool_calls or []
                if getattr(response, 'invalid_tool_calls', None):
                    raise ValueError('PLAN_ARGUMENTS_INVALID_JSON')
                if len(calls) != 1 or calls[0]["name"] != "submit_execution_plan":
                    raise ValueError("Plan tool required")
                plan = ExecutionPlan.model_validate(calls[0]["args"])
                validate_plan_arguments(plan)
                allowed={item['function']['name'] for item in payload['tools']}
                if any(step.tool_name not in allowed for step in plan.steps):raise ValueError('Tool permission denied')
                if any(word in question.lower() for word in ("图表", "趋势图", "柱状图", "折线图", "饼图", "散点图", "直方图", "绘图", "画图", "chart", "plot")) and not any(step.tool_name == "generate_chart" and step.required for step in plan.steps):
                    raise ValueError("Required chart missing from plan")
                if len(plan.steps) > self.adapter.settings.max_plan_steps:
                    raise ValueError("Plan budget exceeded")
                return plan
            except (ValueError, KeyError, TypeError) as error:
                payload['correction'] = plan_correction(error)
        raise ValueError("PLAN_INVALID")

    def plan_v2(self, question, metadata, context, *, task_id, intent, permissions, max_steps=12,
                correction=None, prompt_name='analysis_planner'):
        from app.agent.context import ContextBuilder
        from app.agent.plan_validator import PlanValidator
        tools = model_tool_schemas(permissions)
        payload = ContextBuilder().build(question, context, metadata,
            [item['function'] for item in tools])
        payload.update(task_id=task_id, intent=intent, correction=correction)
        columns = {item['name']: item['data_type'] for item in metadata['columns']}
        for _ in range(2):
            try:
                raw = self.adapter.generate_structured(prompt_name, payload, AnalysisPlan)
                plan = AnalysisPlan.model_validate(raw)
                if plan.task_id != task_id or plan.intent != intent:
                    raise ValueError('PLAN_TASK_MISMATCH')
                return PlanValidator(max_steps).validate(plan,
                    dataset_id=metadata['dataset_id'],
                    dataset_version_id=metadata['dataset_version_id'],
                    columns=columns, permissions=permissions)
            except (ValueError, ValidationError) as exc:
                payload['correction'] = {'code': str(exc)[:80],
                                         'instruction': '保持任务与固定数据集版本，修复字段、工具、参数和依赖'}
        raise ValueError('PLAN_INVALID')


def plan_correction(error):
    """Return bounded schema locations, never exception inputs or provider content."""
    validation = error if isinstance(error, ValidationError) else error.__cause__
    errors = []
    if isinstance(validation, ValidationError):
        errors = [{'path': '.'.join(str(part)[:64] for part in item['loc']), 'type': item['type']}
                  for item in validation.errors(include_input=False, include_context=False, include_url=False)[:10]]
    code = 'PLAN_ARGUMENTS_INVALID_JSON' if str(error) == 'PLAN_ARGUMENTS_INVALID_JSON' else 'PLAN_SCHEMA_INVALID'
    return {'code': code, 'errors': errors, 'allowed_step_fields': list(AnalysisStep.model_fields),
            'instruction': '重新调用submit_execution_plan，修正上述字段；禁止增加未声明字段。图表title只能在generate_chart的arguments内。参数必须是合法JSON。'}
