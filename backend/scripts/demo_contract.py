"""Deterministic sales acceptance evidence; explicitly does not call a model."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from app.agent.schemas import ExecutionPlan
from app.agent.executor import WorkflowExecutor
from app.config import Settings
from app.services.analysis_tools import DatasetTools


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    frame = pd.read_csv(root / "sample-data/sales_growth_demo.csv")
    tools = DatasetTools.from_frame(1, frame.to_dict(orient="records"))
    plan = ExecutionPlan(intent="Six-month product growth", steps=[
        {"step_id": "monthly", "tool_name": "time_group_analysis", "arguments": {"date_column": "order_date", "group_column": "product", "value_column": "sales", "months": 6}},
        {"step_id": "growth", "tool_name": "growth_analysis", "arguments": {"date_column": "order_date", "group_column": "product", "value_column": "sales_sum", "top_n": 3}, "source_ref": "monthly", "depends_on": ["monthly"]},
        {"step_id": "chart", "tool_name": "generate_chart", "arguments": {"type": "line", "dimension": "order_date", "group_column": "product", "metrics": [{"field": "sales_sum"}], "title": "Six-month sales trend", "selected_groups": {"$ref": "growth", "field": "selected_groups"}}, "source_ref": "monthly", "depends_on": ["monthly", "growth"]},
    ], completion_requirements=["monthly", "growth", "chart"])
    executor = WorkflowExecutor(tools, Settings(_env_file=None))
    report = executor.execute(plan, "Six-month product growth")
    rows = executor.results["growth"]["rows"]
    assert [row["product"] for row in rows] == ["A", "B", "C"]
    assert [round(row["growth_rate"], 6) for row in rows] == [1.0, 0.5, 0.2]
    assert executor.results["growth"]["excluded_count"] == 2
    assert [series["name"] for series in report.charts[0]["series"]] == ["A", "B", "C"]
    evidence = {"validation": "deterministic tools only; no MySQL or model call", "source": "sample-data/sales_growth_demo.csv", "plan": plan.model_dump(), "trace": executor.calls, "results": executor.results, "report": report.model_dump()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("A=100%, B=50%, C=20%; excluded=2; chart series=3; summary unavailable => partial")


if __name__ == "__main__":
    main()
