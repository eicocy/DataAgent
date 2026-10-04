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
                 columns: dict[str, str], permissions: frozenset[Permission], columns_by_input=None,
                 semantic_snapshot=None, metadata_by_input=None, versions_by_input=None) -> AnalysisPlan:
        if plan.dataset_id != dataset_id or plan.dataset_version_id != dataset_version_id:
            raise ValueError("PLAN_DATASET_MISMATCH")
        if not 1 <= len(plan.steps) <= self.max_steps:
            raise ValueError("PLAN_STEP_LIMIT")
        registry = tool_registry(permissions)
        steps = {step.step_id: step for step in plan.steps}
        if len(steps) != len(plan.steps):
            raise ValueError("DUPLICATE_STEP")
        def source_schema(step,active=None):
            active=set() if active is None else active
            root=(columns_by_input or {}).get(step.input_alias,columns)
            mappings=[m for m in semantic_snapshot or [] if m.get('dataset_version_id')==(versions_by_input or {}).get(step.input_alias,dataset_version_id)]
            if step.source_ref=='dataset' or step.source_ref not in steps or step.step_id in active: return root,mappings,False
            active.add(step.step_id);source=steps[step.source_ref]
            left,left_mappings,known=source_schema(source,active)
            if source.tool_name!='join_data': return left,left_mappings,known
            right_alias=source.arguments.get('right_alias')
            right=(columns_by_input or {}).get(right_alias,{})
            shared={l for l,r in zip(source.arguments.get('left_on',[]),source.arguments.get('right_on',[])) if l==r}
            overlap=(set(left)&set(right))-shared
            output={column+'_left' if column in overlap else column:dtype for column,dtype in left.items()}
            output.update({column+'_right' if column in overlap else column:dtype for column,dtype in right.items() if column not in shared})
            from app.semantic.business_validation import joined_mappings
            right_mappings=[m for m in semantic_snapshot or [] if m.get('dataset_version_id')==(versions_by_input or {}).get(right_alias)]
            merged=joined_mappings(left_mappings,right_mappings,left,right,source.arguments,(versions_by_input or {}).get(step.input_alias,dataset_version_id))
            return output,merged,True
        for step in plan.steps:
            step_columns = columns_by_input[step.input_alias] if columns_by_input is not None else columns
            step_columns,mappings,known_source=source_schema(step)
            from app.semantic.business_validation import validate_business_arguments
            version=(versions_by_input or {}).get(step.input_alias,dataset_version_id)
            metadata=(metadata_by_input or {}).get(step.input_alias,{})
            validate_business_arguments(step.tool_name,step.arguments,mappings,version,metadata.get('business_metadata',{}) if step.source_ref=='dataset' else {})
            if step.tool_name=='join_data':
                right=step.arguments.get('right_alias')
                if columns_by_input is None or right not in columns_by_input or right==step.input_alias:
                    raise ValueError('JOIN_INPUT_UNAVAILABLE')
                if any(c not in columns_by_input[right] for c in step.arguments.get('right_on',[])):
                    raise ValueError('COLUMN_NOT_FOUND')
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
            if (step.source_ref == "dataset" or known_source) and step.tool_name != "sql_query":
                for field in self._referenced_fields(step.arguments):
                    if field not in step_columns:
                        raise ValueError("COLUMN_NOT_FOUND")
                if step.tool_name in {"time_group_analysis", "growth_analysis"}:
                    if step_columns.get(step.arguments.get("date_column")) not in {"datetime", "date", "timestamp", "string"}:
                        raise ValueError("COLUMN_TYPE_MISMATCH")
                    if step_columns.get(step.arguments.get("value_column")) not in {"integer", "decimal", "float", "numeric", "number"}:
                        raise ValueError("COLUMN_TYPE_MISMATCH")
                numeric = {'integer', 'decimal', 'float', 'numeric', 'number'}
                if step.tool_name in {'period_comparison','contribution_analysis'}:
                    from app.analysis.inputs import PeriodComparisonInput
                    from app.analysis.business_tools import ranges
                    ranges(PeriodComparisonInput.model_validate({k:v for k,v in step.arguments.items() if k!='dimension'}))
                for metric in step.arguments.get('metrics', []):
                    if not isinstance(metric, dict):
                        continue
                    operation = metric.get('aggregation') or metric.get('operation')
                    if operation in {'sum', 'avg', 'mean', 'median', 'std', 'var'} and step_columns.get(metric.get('column')) not in numeric:
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
        single = {"column", "date_column", "time_column", "target_column", "dimension", "currency_column", "unit_column", "order_id_column", "customer_id_column", "product_id_column", "group_column", "value_column", "weight_column", "x", "group_by"}
        multiple = {"columns", "group_columns", "dimensions", "index", "y", "left_on"}
        def scan(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in single and isinstance(item, str):
                        yield item
                    elif key in multiple and isinstance(item, list):
                        yield from (part for part in item if isinstance(part, str))
                    elif key=='metrics' and isinstance(item,dict):
                        yield from (column for column in item.values() if isinstance(column,str))
                    else:
                        yield from scan(item)
            elif isinstance(value, list):
                for item in value:
                    yield from scan(item)
        return set(scan(arguments))
