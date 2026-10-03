from datetime import datetime, UTC, timedelta
import pandas as pd
from sqlalchemy import select
from test_analysis_api import analysis_context, make_session
from app.models import AnalysisRecord, BackgroundJob, AnalysisArtifact
from app.services.artifacts import ArtifactStore
from app.services.analysis import execute_record
from app.routers import analysis
from app.services.analysis_agent import AgentOutcome


def prepare(client, sessions):
    response = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"region,sales\nEast,10\nWest,100\n", "text/csv")})
    dataset_id = response.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    return {"session_id": session_id, "dataset_id": dataset_id, "question": "统计", "request_id": "run-001"}


def test_async_submission_idempotency_mutex_and_authorization(analysis_context):
    client, sessions, _ = analysis_context
    request = prepare(client, sessions)
    first = client.post("/api/v1/analysis/runs", json=request)
    second = client.post("/api/v1/analysis/runs", json=request)
    assert first.status_code == 202 and second.status_code == 200
    record_id = first.json()["data"]["record_id"]
    assert second.json()["data"]["record_id"] == record_id
    assert client.post("/api/v1/analysis/runs", json=dict(request, question="不同问题")).status_code == 409
    assert client.post("/api/v1/analysis/runs", json=dict(request, request_id="run-002")).json()["code"] == "ANALYSIS_SESSION_BUSY"
    assert client.delete(f"/api/v1/datasets/{request['dataset_id']}").status_code == 409
    assert client.get(f"/api/v1/analysis/runs/{record_id}/trace").json()["data"]["steps"] == []
    with sessions() as db:
        assert db.query(BackgroundJob).count() == 1
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"username": "other", "password": "safe-password-123"})
    assert client.get(f"/api/v1/analysis/runs/{record_id}").status_code == 404


def test_artifact_retains_full_rows_and_expiry_is_explicit(analysis_context, monkeypatch, tmp_path):
    client, sessions, _ = analysis_context
    request = prepare(client, sessions)
    record_id = client.post("/api/v1/analysis/runs", json=request).json()["data"]["record_id"]
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path / "artifacts"))
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        frame = pd.DataFrame({"amount": range(250)})
        result = ArtifactStore(db).write(record, "full", {"columns": ["amount"], "rows": [{"amount": 0}]}, frame)
        db.commit()
        artifact_id = result["artifact_id"]
        assert len(result["rows"]) == 100
    url = f"/api/v1/analysis/runs/{record_id}/results/{artifact_id}"
    page = client.get(url + "?offset=200&limit=100").json()["data"]
    assert page["total"] == 250 and page["rows"][-1]["amount"] == 249
    assert client.get(url + "?limit=101").status_code == 422
    with sessions() as db:
        db.get(AnalysisArtifact, artifact_id).expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    assert client.get(url).status_code == 410


def test_trace_persisted_before_failure_keeps_computation(analysis_context, monkeypatch, tmp_path):
    client, sessions, _ = analysis_context
    request = prepare(client, sessions)
    record_id = client.post("/api/v1/analysis/runs", json=request).json()["data"]["record_id"]
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path / "artifacts"))
    class InterruptedAgent:
        def analyze(self, question, tools):
            tools.on_event("call", {"call_id": "sum", "step_id": "sum", "tool_name": "aggregate_analysis", "status": "running"})
            tools.on_event("result", {"step_id": "sum", "tool_name": "aggregate_analysis", "data": {"metric_values": {"sales_sum": 110}}, "frame": None})
            raise RuntimeError("private error")
    with sessions() as db:
        execute_record(db, record_id, InterruptedAgent(), db.bind, db.bind)
    data = client.get(f"/api/v1/analysis/runs/{record_id}").json()["data"]
    assert data["status"] == "partial"
    assert data["tool_result"]["metric_values"]["sales_sum"] == 110
    assert "private error" not in data["error_message"]


def test_expired_artifact_cleanup_advances_beyond_first_hundred(analysis_context, monkeypatch, tmp_path):
    client, sessions, _ = analysis_context
    request = prepare(client, sessions)
    record_id = client.post("/api/v1/analysis/runs", json=request).json()["data"]["record_id"]
    from app.config import get_settings
    from app.services.jobs import run_maintenance
    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path / "artifacts"))
    with sessions() as db:
        record = db.get(AnalysisRecord, record_id)
        for i in range(101):
            result = ArtifactStore(db).write(record, f"step{i}", {"rows": [{"amount": i}], "columns": ["amount"]})
            artifact = db.get(AnalysisArtifact, result["artifact_id"])
            artifact.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    run_maintenance(sessions)
    run_maintenance(sessions)
    assert list((tmp_path / "artifacts").glob("*.json")) == []
    with sessions() as db:
        assert db.query(AnalysisArtifact).filter(AnalysisArtifact.purged_at.is_(None)).count() == 0
