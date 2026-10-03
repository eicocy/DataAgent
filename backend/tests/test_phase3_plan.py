import pytest

from app.agent.schemas import AnalysisPlan, AnalysisStep
from app.agent.plan_validator import PlanValidator
from app.analysis.models import Permission
from app.agent.executor import WorkflowExecutor
from app.services.analysis_tools import DatasetTools
from types import SimpleNamespace


def make_plan(steps, dataset_id=2, version=3):
    return AnalysisPlan(task_id="run-7", goal="地区销售趋势", intent="TREND_ANALYSIS",
                        dataset_id=dataset_id, dataset_version_id=version, steps=steps,
                        expected_outputs=["trend"])


def test_plan_validator_accepts_dependency_graph_and_registered_tool():
    plan = make_plan([
        AnalysisStep(step_id="chart", tool_name="generate_chart", source_ref="trend",
            depends_on=["trend"], arguments={"type": "line", "dimension": "day", "metrics": [{"field": "sales_sum"}], "title": "Sales"}),
        AnalysisStep(step_id="trend", tool_name="time_group_analysis",
            arguments={"date_column": "day", "group_column": "region", "value_column": "sales"}),
    ])
    checked = PlanValidator().validate(plan, dataset_id=2, dataset_version_id=3,
        columns={"day": "datetime", "region": "string", "sales": "decimal"},
        permissions=frozenset({Permission.READ_DATA}))
    assert checked.status == "READY"
    assert [step.step_id for step in checked.steps] == ["chart", "trend"]


@pytest.mark.parametrize("bad_step", [
    AnalysisStep(step_id="trend", tool_name="time_group_analysis",
        arguments={"date_column": "day", "group_column": "region", "value_column": "missing"}),
    AnalysisStep(step_id="trend", tool_name="execute_python", arguments={}),
])
def test_plan_validator_rejects_unknown_field_or_tool(bad_step):
    with pytest.raises(ValueError):
        PlanValidator().validate(make_plan([bad_step]), dataset_id=2, dataset_version_id=3,
            columns={"day": "datetime", "region": "string", "sales": "decimal"},
            permissions=frozenset({Permission.READ_DATA}))


def test_plan_validator_rejects_cycle_and_oversized_plan():
    a = AnalysisStep(step_id="a", tool_name="preview_data", depends_on=["b"])
    b = AnalysisStep(step_id="b", tool_name="preview_data", depends_on=["a"])
    validator = PlanValidator()
    with pytest.raises(ValueError, match="DEPENDENCY_CYCLE"):
        validator.validate(make_plan([a, b]), dataset_id=2, dataset_version_id=3,
            columns={}, permissions=frozenset({Permission.READ_DATA}))
    with pytest.raises(ValueError, match="PLAN_STEP_LIMIT"):
        validator.validate(make_plan([AnalysisStep(step_id=f"s{i}", tool_name="preview_data") for i in range(100)]),
            dataset_id=2, dataset_version_id=3, columns={}, permissions=frozenset({Permission.READ_DATA}))


def test_cleaning_intent_allows_quality_read_only_tools_only():
    plan = make_plan([AnalysisStep(step_id='quality', tool_name='missing_value_analysis', arguments={})])
    plan.intent = 'DATA_CLEANING'
    plan.expected_outputs = ['quality']
    assert PlanValidator().validate(plan, dataset_id=2, dataset_version_id=3,
        columns={}, permissions=frozenset({Permission.READ_DATA})).status == 'READY'
    plan.steps[0] = AnalysisStep(step_id='quality', tool_name='aggregate_data',
        arguments={'metrics': [{'column': 'sales', 'aggregation': 'sum'}]})
    with pytest.raises(ValueError, match='CLEANING_ANALYSIS_ONLY'):
        PlanValidator().validate(plan, dataset_id=2, dataset_version_id=3,
            columns={'sales': 'integer'}, permissions=frozenset({Permission.READ_DATA}))


def test_orchestrator_executes_ready_steps_in_dependency_order():
    tools = DatasetTools.from_frame(2, [{"sales": 10}, {"sales": 20}])
    plan = make_plan([
        AnalysisStep(step_id="total", tool_name="aggregate_data", depends_on=["filtered"],
            source_ref="filtered", arguments={"metrics": [{"column": "sales", "aggregation": "sum"}]}),
        AnalysisStep(step_id="filtered", tool_name="filter_data",
            arguments={"conditions": [{"column": "sales", "operator": "gt", "value": 0}]}),
    ])
    plan.expected_outputs = ["total"]
    settings = SimpleNamespace(analysis_timeout_seconds=20, max_tool_attempts=5)
    runner = WorkflowExecutor(tools, settings)
    report = runner.execute(plan, "总销售额")
    assert [call["step_id"] for call in runner.calls] == ["filtered", "total"]
    assert runner.results["total"]["metric_values"]["sales_sum"] == 30
    assert all(step.status == "COMPLETED" for step in runner.final_plan.steps)
    assert report.status == "partial"  # No interpreter provider in this focused test.
