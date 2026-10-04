import json
from pydantic import ValidationError
from app.agent.schemas import ExecutionPlan, AnalysisPlan, AnalysisStep
from app.agent.prompts import PLAN
from app.services.analysis_tools import model_tool_schemas
from app.tools.registry import tool_registry


def compact_tool_schema(schema):
    """Strip annotations on schema nodes, never keys of property/default maps."""
    if not isinstance(schema,dict):return schema
    result={}
    maps={'properties','$defs','definitions','patternProperties','dependentSchemas'}
    nodes={'items','contains','not','if','then','else','additionalProperties','propertyNames','unevaluatedProperties'}
    arrays={'allOf','anyOf','oneOf','prefixItems'}
    for key,value in schema.items():
        if key in {'title','examples'}:continue
        if key in maps and isinstance(value,dict):result[key]={name:compact_tool_schema(item) for name,item in value.items()}
        elif key in nodes:result[key]=compact_tool_schema(value)
        elif key in arrays and isinstance(value,list):result[key]=[compact_tool_schema(item) for item in value]
        else:result[key]=value
    return result


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
    def plan_v3(self, question, metadata_by_input, context, *, task_id, intent, config, permissions, correction=None, prior_plan=None):
        from app.agent.schemas import AnalysisPlanV3
        from app.agent.budget import RuntimeBudget, BudgetExceeded
        from app.agent.task_graph import validate_graph, deduplicate_steps
        from app.analysis.catalog import build_registry
        registry = build_registry(include_legacy=True)
        wanted = {'dataset_overview', 'column_summary', 'missing_value_analysis', 'duplicate_analysis', 'descriptive_statistics', 'generate_chart', 'aggregate', 'groupby_aggregate', 'filter_rows', 'chart_recommendations'}
        for profile in config['profiles']:
            wanted.update(profile['preferred_tools'])
        import re
        if re.search(r'预测|未来|forecast',question,re.I):wanted.add('forecast')
        if len(config['inputs'])>1:wanted.add('join_data')
        if intent == 'DATA_CLEANING':
            from app.agent.tool_policy import CLEANING_TOOLS
            wanted.intersection_update(CLEANING_TOOLS)
        manifests = [t for t in registry.get_llm_tool_manifest(permissions) if t['name'] in wanted]
        # Share identical parameter schemas instead of repeating full definitions.
        import json
        schemas, names, tools = {}, {}, []
        for tool in manifests:
            parameters=compact_tool_schema(tool['parameters'])
            signature = json.dumps(parameters, sort_keys=True)
            if signature not in names:
                names[signature] = f'params_{len(names)}'
                schemas[names[signature]] = parameters
            tools.append(dict(tool, parameters={'$ref': f"#/tool_parameter_schemas/{names[signature]}"}))
        budget = getattr(self.adapter, 'budget', None) or RuntimeBudget.for_depth(config['depth'])
        delivery_tasks = 1+len(config['delivery']['formats']) if config.get('delivery') else 0
        analysis_task_limit = max(0,budget.max_tasks-delivery_tasks)
        payload = {'question': question[:2000], 'task_id': task_id, 'intent': intent, 'inputs': config['inputs'],
            'datasets': metadata_by_input, 'dataset': metadata_by_input.get(config['inputs'][0]['alias'], {}),
            'profiles': [{k:p[k] for k in ('id','version','name','category','description','expected_metrics','expected_dimensions','preferred_tools','analysis_steps','constraints','prompt_context') if k in p} for p in config['profiles']], 'semantics': config['semantic_snapshot'], 'semantic_version': config['semantic_version'],
            'depth': config['depth'], 'budget': budget.snapshot(), 'tools': tools, 'tool_parameter_schemas': schemas}
        if delivery_tasks:
            payload['budget'].update(max_analysis_tasks=analysis_task_limit, reserved_delivery_tasks=delivery_tasks)
        if config.get('artifact_references'):
            payload['artifact_references'] = config['artifact_references']
            payload['referenced_plans'] = config.get('reference_plans',[])
        from datetime import datetime
        from zoneinfo import ZoneInfo
        payload['current_date']=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
        payload['timezone']='Asia/Shanghai'
        payload.update(filters=context.active_filters[:20], metrics=context.active_metrics[:20], dimensions=context.active_dimensions[:20],
            time_range=context.active_time_range, previous_plan=context.previous_plan, summary=context.messages_summary[:2000])
        columns = {alias: {c['name']: c['data_type'] for c in meta.get('columns', [])} for alias, meta in metadata_by_input.items()}
        if correction:
            payload['correction'] = correction
        for attempt in range(2):
            try:
                raw = self.adapter.generate_structured('workspace_planner', payload, AnalysisPlanV3)
                plan = AnalysisPlanV3.model_validate(raw)
                if plan.task_id != task_id or plan.intent != intent or [i.model_dump() for i in plan.inputs] != config['inputs']:
                    raise ValueError('PLAN_TASK_INPUT_MISMATCH')
                if len(plan.steps) > analysis_task_limit:
                    raise ValueError('PLAN_STEP_LIMIT')
                trusted_steps = {s.step_id: s for s in prior_plan.steps} if prior_plan else {}
                for step in plan.steps:
                    if step.exploration_parent or step.exploration_depth:
                        previous = trusted_steps.get(step.step_id)
                        if (previous is None or
                            (step.exploration_parent, step.exploration_depth) != (previous.exploration_parent, previous.exploration_depth)):
                            raise ValueError('INITIAL_EXPLORATION_INVALID')
                plan.profiles = config['profiles']
                plan.semantic_snapshot = config['semantic_snapshot']
                plan.semantic_version = config['semantic_version']
                plan.depth, plan.budget = config['depth'], budget.snapshot()
                validate_graph(plan, columns, permissions, budget.max_tasks,metadata_by_input)
                plan.steps, aliases = deduplicate_steps(plan.steps, {i.alias: i.dataset_version_id for i in plan.inputs}, plan.semantic_version)
                plan.expected_outputs = list(dict.fromkeys(aliases.get(k, k) for k in plan.expected_outputs))
                return validate_graph(plan, columns, permissions, budget.max_tasks,metadata_by_input)
            except BudgetExceeded:
                raise
            except ValueError as exc:
                payload['correction'] = {'code': str(exc)[:100], 'instruction': '只修正计划结构、工具参数和授权输入，不输出分析事实'}
                if attempt:
                    raise ValueError('PLAN_INVALID') from exc

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
