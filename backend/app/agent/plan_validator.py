"""Validate a model-authored plan against a trusted task and live tool catalog."""
from app.agent.schemas import AnalysisPlan
from app.agent.planner import validate_plan_arguments
from app.analysis.models import Permission
from app.tools.registry import tool_registry
from app.agent.tool_policy import CLEANING_TOOLS


class PlanValidator:
    def __init__(self, max_steps: int = 12):
        self.max_steps = max_steps

    def validate(self, plan: AnalysisPlan, *, dataset_id: int, dataset_version_id: int,
                 columns: dict[str, str], permissions: frozenset[Permission]) -> AnalysisPlan:
        if plan.dataset_id != dataset_id or plan.dataset_version_id != dataset_version_id:
            raise ValueError("PLAN_DATASET_MISMATCH")
        if not 1 <= len(plan.steps) <= self.max_steps:
            raise ValueError("PLAN_STEP_LIMIT")
        registry = tool_registry(permissions)
        steps = {step.step_id: step for step in plan.steps}
        if len(steps) != len(plan.steps):
            raise ValueError("DUPLICATE_STEP")
        for step in plan.steps:
            if step.tool_name not in registry:
                raise ValueError("TOOL_NOT_ALLOWED")
            if plan.intent == 'DATA_CLEANING' and step.tool_name not in CLEANING_TOOLS:
                raise ValueError('CLEANING_ANALYSIS_ONLY')
            if step.status != 'PENDING' or step.result_ref or step.error or step.retry_count:
                raise ValueError('PLAN_STEP_STATE_INVALID')
            if any(dep not in steps or dep == step.step_id for dep in step.depends_on):
                raise ValueError("DEPENDENCY_INVALID")
            if step.source_ref != "dataset" and step.source_ref not in step.depends_on:
                raise ValueError("SOURCE_DEPENDENCY_MISSING")
            try:
                validate_plan_arguments(AnalysisPlan.model_construct(steps=[step]))
            except ValueError as exc:
                raise ValueError("TOOL_ARGUMENTS_INVALID") from exc
            if step.source_ref == "dataset" and step.tool_name != "sql_query":
                for field in self._referenced_fields(step.arguments):
                    if field not in columns:
                        raise ValueError("COLUMN_NOT_FOUND")
                if step.tool_name in {"time_group_analysis", "growth_analysis"}:
                    if columns.get(step.arguments.get("date_column")) not in {"datetime", "date", "timestamp", "string"}:
                        raise ValueError("COLUMN_TYPE_MISMATCH")
                    if columns.get(step.arguments.get("value_column")) not in {"integer", "decimal", "float", "numeric", "number"}:
                        raise ValueError("COLUMN_TYPE_MISMATCH")
                numeric = {'integer', 'decimal', 'float', 'numeric', 'number'}
                for metric in step.arguments.get('metrics', []):
                    if not isinstance(metric, dict):
                        continue
                    operation = metric.get('aggregation') or metric.get('operation')
                    if operation in {'sum', 'avg', 'mean', 'median', 'std', 'var'} and columns.get(metric.get('column')) not in numeric:
                        raise ValueError('COLUMN_TYPE_MISMATCH')
        visited, active = set(), set()
        def walk(key):
            if key in active:
                raise ValueError("DEPENDENCY_CYCLE")
            if key in visited:
                return
            active.add(key)
            for dep in steps[key].depends_on:
                walk(dep)
            active.remove(key)
            visited.add(key)
        for key in steps:
            walk(key)
        if any(output not in steps for output in plan.expected_outputs):
            raise ValueError("EXPECTED_OUTPUT_MISSING")
        return plan.model_copy(update={"status": "READY"}, deep=True)

    @staticmethod
    def _referenced_fields(arguments):
        single = {"column", "date_column", "group_column", "value_column", "weight_column", "x", "group_by"}
        multiple = {"columns", "group_columns", "dimensions", "index", "y"}
        def scan(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in single and isinstance(item, str):
                        yield item
                    elif key in multiple and isinstance(item, list):
                        yield from (part for part in item if isinstance(part, str))
                    else:
                        yield from scan(item)
            elif isinstance(value, list):
                for item in value:
                    yield from scan(item)
        return set(scan(arguments))
