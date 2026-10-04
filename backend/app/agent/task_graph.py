"""V3 graph validation and canonical public-step deduplication."""
import json
from app.agent.schemas import AnalysisPlan
from app.agent.plan_validator import PlanValidator
from app.analysis.models import Permission
from app.analysis.catalog import build_registry


def deduplicate_steps(steps, versions, semantic_version):
    signatures, aliases, unique = {}, {}, []
    retained = {}
    def canonical(value):
        if isinstance(value, dict):
            return {k: aliases.get(v, v) if k == '$ref' and isinstance(v, str) else canonical(v) for k, v in value.items()}
        if isinstance(value, list):
            return [canonical(v) for v in value]
        return value
    for step in steps:
        # Only source computations with no dependency are common across profiles.
        signature = json.dumps([versions.get(step.input_alias), step.tool_name, step.arguments, semantic_version], sort_keys=True, default=str)
        eligible = step.source_ref == 'dataset' and not step.depends_on and not step.exploration_parent
        if eligible and signature in signatures:
            aliases[step.step_id] = signatures[signature]
            survivor = retained[signatures[signature]]
            survivor.required = survivor.required or step.required
            survivor.priority = max(survivor.priority, step.priority)
        else:
            if eligible:
                signatures[signature] = step.step_id
            survivor = step.model_copy(deep=True)
            retained[step.step_id] = survivor
            unique.append(survivor)
    for step in unique:
        step.depends_on = list(dict.fromkeys(aliases.get(k, k) for k in step.depends_on))
        step.source_ref = aliases.get(step.source_ref, step.source_ref)
        step.arguments = canonical(step.arguments)
    return unique, aliases


def validate_graph(plan, columns_by_input, permissions=frozenset({Permission.READ_DATA}), max_steps=32, metadata_by_input=None):
    bindings = {item.alias: item for item in plan.inputs}
    if len(bindings) != len(plan.inputs) or len(plan.steps) > max_steps:
        raise ValueError('PLAN_INPUT_OR_STEP_LIMIT')
    if (plan.dataset_id, plan.dataset_version_id) != (plan.inputs[0].dataset_id, plan.inputs[0].dataset_version_id):
        raise ValueError('PLAN_DATASET_MISMATCH')
    steps = {s.step_id: s for s in plan.steps}
    registry = build_registry(include_legacy=True)
    def references(value):
        if isinstance(value, dict):
            if '$ref' in value:
                yield value
            else:
                for item in value.values():
                    yield from references(item)
        elif isinstance(value, list):
            for item in value:
                yield from references(item)
    for step in plan.steps:
        if step.input_alias not in bindings:
            raise ValueError('PLAN_INPUT_UNKNOWN')
        if step.source_ref != 'dataset' and step.source_ref in steps and steps[step.source_ref].input_alias != step.input_alias:
            raise ValueError('CROSS_INPUT_SOURCE')
        if step.source_ref in steps and registry.exists(steps[step.source_ref].tool_name) and not registry.get(steps[step.source_ref].tool_name).metadata.provides_frame:
            raise ValueError('SOURCE_RESULT_TYPE')
        for ref in references(step.arguments):
            dep = ref.get('$ref')
            if dep not in steps or dep not in step.depends_on or set(ref) != {'$ref', 'field'}:
                raise ValueError('RESULT_REFERENCE_INVALID')
            if steps[dep].input_alias != step.input_alias:
                raise ValueError('CROSS_INPUT_RESULT_REFERENCE')
            if registry.exists(steps[dep].tool_name):
                schema = registry.get(steps[dep].tool_name).output_schema
                if schema.__name__ == 'LegacyResult':
                    from app.analysis.models import LegacyData
                    schema = LegacyData
                elif schema.__name__ == 'LegacyChartResult':
                    from app.tools.schemas import ChartSpec
                    schema = ChartSpec
                if ref['field'] not in schema.model_fields:
                    raise ValueError('RESULT_FIELD_UNKNOWN')
        if step.started_at or step.finished_at:
            raise ValueError('PLAN_STEP_STATE_INVALID')
    proxy = AnalysisPlan(task_id=plan.task_id, goal=plan.goal, intent=plan.intent, dataset_id=plan.dataset_id,
        dataset_version_id=plan.dataset_version_id, steps=plan.steps, expected_outputs=plan.expected_outputs)
    PlanValidator(max_steps).validate(proxy, dataset_id=plan.dataset_id, dataset_version_id=plan.dataset_version_id,
        columns={}, permissions=permissions, columns_by_input=columns_by_input,
        semantic_snapshot=plan.semantic_snapshot, metadata_by_input=metadata_by_input,
        versions_by_input={alias:binding.dataset_version_id for alias,binding in bindings.items()})
    return plan.model_copy(update={'status': 'READY'}, deep=True)
