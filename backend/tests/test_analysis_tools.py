import pytest
import sqlglot
import pandas as pd
from sqlalchemy import create_engine
from pydantic import ValidationError

from app.services.analysis_tools import (
    AggregateArgs,
    ChartArgs,
    DatasetTools,
    FilterArgs,
    GroupByArgs,
    SqlQueryArgs,
    validate_readonly_query,
)


def test_group_by_and_filter_compute_from_real_dataframe():
    tools = DatasetTools.from_frame(
        17,
        [
            {"region": "East", "sales": 12},
            {"region": "West", "sales": 5},
            {"region": "East", "sales": 8},
        ],
    )

    grouped = tools.group_by_analysis(
        GroupByArgs(group_columns=["region"], value_column="sales", aggregation="sum", sort="desc", limit=10)
    )
    filtered = FilterArgs.model_validate(
        {"conditions": [{"column": "sales", "operator": "gte", "value": 8}], "limit": 10}
    )
    filtered_result = tools.run("filter_data", filtered)

    assert grouped["rows"] == [{"region": "East", "sales_sum": 20}, {"region": "West", "sales_sum": 5}]
    assert filtered_result["matched_count"] == 2
    assert [row["sales"] for row in filtered_result["preview_rows"]] == [12, 8]


def test_sql_validator_rejects_other_tables_and_non_select_statements():
    with pytest.raises(ValueError, match="only the current dataset"):
        validate_readonly_query("SELECT * FROM users", 17, {"region", "sales"}, 100)

    with pytest.raises(ValueError, match="single SELECT"):
        validate_readonly_query("SELECT sales FROM dataset_17; DELETE FROM dataset_17", 17, {"sales"}, 100)

    with pytest.raises(ValueError, match="field"):
        validate_readonly_query("SELECT password_hash FROM dataset_17", 17, {"sales"}, 100)

    with pytest.raises(ValueError, match="disallowed function"):
        validate_readonly_query("SELECT SLEEP(10) FROM dataset_17", 17, {"sales"}, 100)


def test_sql_validator_caps_limit_and_checks_tool_parameters():
    query = validate_readonly_query("SELECT region, SUM(sales) AS total FROM dataset_17 GROUP BY region", 17, {"region", "sales"}, 20)
    parsed = sqlglot.parse_one(query, read="mysql")
    assert parsed.args["limit"].expression.this == "20"

    capped = validate_readonly_query("SELECT sales FROM dataset_17 LIMIT 900", 17, {"sales"}, 20)
    assert sqlglot.parse_one(capped, read="mysql").args["limit"].expression.this == "20"

    with pytest.raises(ValidationError):
        SqlQueryArgs(query="SELECT 1", max_rows=501)


def test_aggregate_time_series_sort_and_chart_are_grounded_in_results():
    tools = DatasetTools.from_frame(
        17,
        [
            {"order_date": "2026-01-05", "region": "East", "sales": 10},
            {"order_date": "2026-01-12", "region": "East", "sales": 20},
            {"order_date": "2026-02-01", "region": "West", "sales": 5},
        ],
    )
    tools.frame["order_date"] = pd.to_datetime(tools.frame["order_date"])
    tools.schema["order_date"].data_type = "date"

    aggregate = tools.aggregate_data(AggregateArgs.model_validate({"metrics": [{"column": "sales", "aggregation": "sum"}], "date_column": "order_date", "frequency": "month"}))
    assert aggregate["rows"] == [
        {"order_date": "2026-01-01", "sales_sum": 30},
        {"order_date": "2026-02-01", "sales_sum": 5},
    ]

    tools.call_results["tc_source"] = {"columns": ["region", "sales_sum"], "rows": [{"region": "East", "sales_sum": 30}, {"region": "West", "sales_sum": 5}]}
    chart = tools.generate_chart(ChartArgs.model_validate({"source_tool_call_id": "tc_source", "type": "bar", "dimension": "region", "metrics": [{"field": "sales_sum", "label": "销售额"}], "title": "地区销售额"}))
    assert chart["source_tool_call_id"] == "tc_source"
    assert chart["series"][0]["data"][0] == {"name": "East", "value": 30}


def test_group_by_can_retain_missing_categories_when_requested():
    tools = DatasetTools.from_frame(17, [{"region": "East", "sales": 4}, {"region": None, "sales": 3}])

    result = tools.group_by_analysis(GroupByArgs(group_columns=["region"], value_column="sales", aggregation="sum", drop_missing=False))

    assert {row["region"] for row in result["rows"]} == {"East", None}


def test_sql_tool_executes_only_the_validated_dataset_projection():
    engine = create_engine("sqlite://")
    pd.DataFrame([{"region": "East", "sales": 12}, {"region": "West", "sales": 5}]).to_sql("dataset_17", engine, index=False)
    dataset = type("DatasetRef", (), {"id": 17, "original_name": "sales.csv", "row_count": 2, "column_count": 2, "file_type": "csv"})()
    columns = [type("ColumnRef", (), {"name": name, "original_name": name, "data_type": "string", "nullable": False, "missing_count": 0, "unique_count": 2, "sample_values_json": []})() for name in ("region", "sales")]
    tools = DatasetTools(dataset, columns, engine, engine)

    result = tools.sql_query(SqlQueryArgs.model_validate({"query": "SELECT region, SUM(sales) AS total FROM dataset_17 GROUP BY region ORDER BY total DESC", "max_rows": 10}))

    assert result["rows"][0] == {"region": "East", "total": 12}
    engine.dispose()
