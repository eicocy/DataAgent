from sqlalchemy import select

from test_analysis_api import analysis_context, make_session
from app.models import AnalysisArtifact, AnalysisRecord
from app.services.artifacts import ArtifactStore
from app.routers import analysis
from app.services.analysis_agent import AgentOutcome


class ChartSourceAgent:
    def analyze(self, *_):
        return AgentOutcome(
            tool_calls=[{"tool_call_id": "chart-source-tool", "tool_name": "group_by_analysis",
                         "schema_version": "1.0", "parameters": {"group_columns": ["region"],
                         "value_column": "sales", "aggregation": "sum"}, "status": "succeeded",
                         "duration_ms": 2, "result_summary": "已汇总地区销售额"}],
            tool_result={"columns": ["region", "sales_sum"], "rows": [{"region": "East", "sales_sum": 12}],
                         "row_count": 1, "truncated": False},
            answer="East 销售额为 12。",
            chart={"type": "bar", "title": "地区销售额", "dimension": {"label": "地区"},
                   "metrics": [{"name": "销售额", "data": [{"name": "华东", "value": 12}]}]},
            status="succeeded")


def test_chart_render_creates_owned_high_resolution_artifacts(analysis_context, monkeypatch, tmp_path):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={
        "file": ("sales.csv", b"region,sales\nEast,12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    monkeypatch.setattr(analysis, "agent", ChartSourceAgent())
    run = client.post("/api/v1/analysis/chat", json={"session_id": session_id,
        "dataset_id": dataset_id, "question": "按地区汇总销售额", "request_id": "chart-source-1"})
    assert run.status_code == 200, run.text
    record_id = run.json()["data"]["record_id"]
    monkeypatch.setattr("app.config.get_settings", lambda: type("Settings", (), {
        "artifact_dir": str(tmp_path / "artifacts"), "artifact_retention_days": 7,
        "artifact_max_bytes": 2_000_000, "artifact_task_max_bytes": 10_000_000})())
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        chart_spec = {"chart_type": "bar", "title": "地区销售额", "x": "地区", "y": ["销售额"],
                      "series": [{"name": "销售额", "data": [{"x": "华东", "y": 12}]}]}
        source = ArtifactStore(db).write(record, "chart_source", chart_spec, kind="chart")
        source_id = source["artifact_id"]
        db.commit()

    rendered = client.post(f"/api/v1/charts/{source_id}/render", json={})
    assert rendered.status_code == 201, rendered.text
    files = rendered.json()["data"]
    assert {item["file_name"].rsplit("_", 1)[-1] for item in files} == {"svg.svg", "png.png", "thumbnail.png"}
    png = next(item for item in files if item["file_name"].endswith("_png.png"))
    downloaded = client.get(png["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "image/png"
    assert downloaded.content.startswith(b"\x89PNG\r\n\x1a\n")
    with sessions() as db:
        row = db.get(AnalysisArtifact, png["artifact_id"])
        assert row.metadata_json["width"] == 3000
        assert row.metadata_json["height"] == 1800
        assert row.metadata_json["dpi"] == 300
