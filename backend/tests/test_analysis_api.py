from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AnalysisRecord, AnalysisSession, Dataset, User
from app.routers import analysis
from app.routers import datasets as datasets_router
from app.services.analysis_agent import AgentOutcome, ModelUnavailable


@pytest.fixture
def analysis_context(tmp_path, monkeypatch):
    test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)
    old_override = app.dependency_overrides.get(get_db)

    def db_override():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(datasets_router, "SessionLocal", sessions)
    monkeypatch.setattr(datasets_router, "engine", test_engine)
    monkeypatch.setattr(datasets_router.settings, "upload_dir", str(upload_dir))
    monkeypatch.setattr(analysis, "engine", test_engine)
    monkeypatch.setattr(analysis, "readonly_engine", None)
    client = TestClient(app, headers={"Origin": "http://localhost:5173"})
    client.post("/api/v1/auth/register", json={"username": "alice", "password": "safe-password-123"})
    yield client, sessions, Path(upload_dir)
    if old_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = old_override
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


def make_session(sessions, dataset_id):
    with sessions() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        now = datetime.now(UTC)
        session = AnalysisSession(user_id=user.id, dataset_id=dataset_id, title="新分析", status="active", created_at=now, updated_at=now)
        db.add(session)
        db.commit()
        return session.id


class SuccessfulAgent:
    calls = 0

    def analyze(self, question, _tools):
        self.calls += 1
        return AgentOutcome(
            tool_calls=[{"tool_call_id": "tc_01", "tool_name": "group_by_analysis", "schema_version": "1.0", "parameters": {"group_columns": ["region"], "value_column": "sales", "aggregation": "sum"}, "status": "succeeded", "duration_ms": 4, "result_summary": "按分组字段得到 2 组"}],
            tool_result={"columns": ["region", "sales_sum"], "rows": [{"region": "East", "sales_sum": 12}], "row_count": 1, "truncated": False},
            answer="East 销售额为 12。",
            chart=None,
            status="succeeded",
        )


def test_chat_persists_evidence_and_is_idempotent(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"region,sales\nEast,12\nWest,5\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    fake_agent = SuccessfulAgent()
    monkeypatch.setattr(analysis, "agent", fake_agent)
    request = {"session_id": session_id, "dataset_id": dataset_id, "question": "按地区统计销售额", "request_id": "api-test-001"}

    first = client.post("/api/v1/analysis/chat", json=request)
    second = client.post("/api/v1/analysis/chat", json=request)

    assert first.status_code == 200
    assert first.json()["data"]["status"] == "succeeded"
    assert first.json()["data"]["tool_result"]["rows"][0]["sales_sum"] == 12
    assert first.json()["data"]["message_id"] > 0
    assert second.json()["data"]["record_id"] == first.json()["data"]["record_id"]
    assert fake_agent.calls == 1
    with sessions() as db:
        assert db.scalar(select(AnalysisRecord).where(AnalysisRecord.request_id == "api-test-001")).status == "succeeded"
        assert db.scalar(select(AnalysisRecord).where(AnalysisRecord.request_id == "api-test-001")).assistant_message_id == first.json()["data"]["message_id"]


def test_chat_keeps_partial_result_when_summary_is_unavailable(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"region,sales\nEast,12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)

    class PartialAgent:
        def analyze(self, *_):
            return AgentOutcome(
                tool_calls=[{"tool_call_id": "tc_01", "tool_name": "aggregate_data", "status": "succeeded", "duration_ms": 3}],
                tool_result={"metric_values": {"sales_sum": 12}}, answer=None, chart=None,
                status="partial", summary_error="SUMMARY_UNAVAILABLE",
            )

    monkeypatch.setattr(analysis, "agent", PartialAgent())
    response = client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": dataset_id, "question": "总销售额", "request_id": "api-test-002"})

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "partial"
    assert response.json()["data"]["answer"] is None
    assert response.json()["data"]["tool_result"]["metric_values"]["sales_sum"] == 12


def test_chat_model_failure_is_explicit_and_saved(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)

    class UnavailableAgent:
        calls = 0

        def analyze(self, *_):
            self.calls += 1
            raise ModelUnavailable()

    fake_agent = UnavailableAgent()
    monkeypatch.setattr(analysis, "agent", fake_agent)
    request = {"session_id": session_id, "dataset_id": dataset_id, "question": "总销售额", "request_id": "api-test-003"}
    response = client.post("/api/v1/analysis/chat", json=request)
    replay = client.post("/api/v1/analysis/chat", json=request)

    assert response.status_code == 503
    assert response.json()["code"] == "MODEL_UNAVAILABLE"
    assert replay.status_code == 503
    assert replay.json()["code"] == "MODEL_UNAVAILABLE"
    assert fake_agent.calls == 1
    session_detail = client.get(f"/api/v1/analysis/sessions/{session_id}").json()["data"]
    assert session_detail["messages"][-1]["status"] == "failed"
    assert session_detail["messages"][-1]["content"] == "DeepSeek 暂时不可用，请稍后重试"
    with sessions() as db:
        record = db.scalar(select(AnalysisRecord).where(AnalysisRecord.request_id == "api-test-003"))
        assert record.status == "failed"
        assert record.error_code == "MODEL_UNAVAILABLE"


def test_chat_unexpected_failure_is_saved_with_safe_message(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)

    class BrokenAgent:
        def analyze(self, *_):
            raise RuntimeError("internal model response leaked")

    monkeypatch.setattr(analysis, "agent", BrokenAgent())
    response = client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": dataset_id, "question": "总销售额", "request_id": "api-test-unexpected"})

    assert response.status_code == 500
    assert response.json()["code"] == "ANALYSIS_FAILED"
    assert response.json()["message"] == "分析失败，请稍后重试"
    with sessions() as db:
        record = db.scalar(select(AnalysisRecord).where(AnalysisRecord.request_id == "api-test-unexpected"))
        assert record.status == "failed"
        assert record.error_code == "ANALYSIS_FAILED"
        assert record.error_message == "分析失败，请稍后重试"
        assert record.assistant_message_id is not None


def test_chat_rejects_dataset_session_mismatch(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    first = client.post("/api/v1/datasets/upload", files={"file": ("one.csv", b"x\n1\n", "text/csv")})
    second = client.post("/api/v1/datasets/upload", files={"file": ("two.csv", b"x\n2\n", "text/csv")})
    session_id = make_session(sessions, first.json()["data"]["id"])
    fake_agent = SuccessfulAgent()
    monkeypatch.setattr(analysis, "agent", fake_agent)

    response = client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": second.json()["data"]["id"], "question": "分析", "request_id": "api-test-004"})

    assert response.status_code == 409
    assert response.json()["code"] == "ANALYSIS_SESSION_DATASET_MISMATCH"
    assert fake_agent.calls == 0


def test_session_creation_requires_owned_ready_dataset(analysis_context):
    client, _, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n12\n", "text/csv")})

    created = client.post("/api/v1/analysis/sessions", json={"dataset_id": uploaded.json()["data"]["id"], "title": "销售复盘"})

    assert created.status_code == 201
    assert created.json()["data"]["title"] == "销售复盘"


def test_session_and_history_return_messages_and_saved_evidence(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"region,sales\nEast,12\nWest,5\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    monkeypatch.setattr(analysis, "agent", SuccessfulAgent())
    chat = client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": dataset_id, "question": "按地区统计销售额", "request_id": "api-test-history"})

    sessions_page = client.get("/api/v1/analysis/sessions?q=销售额").json()["data"]
    first_page = client.get(f"/api/v1/analysis/sessions/{session_id}?message_limit=1").json()["data"]
    second_page = client.get(f"/api/v1/analysis/sessions/{session_id}?message_cursor={first_page['next_cursor']}&message_limit=1").json()["data"]
    history_page = client.get("/api/v1/history?tool_name=group_by_analysis&status=succeeded").json()["data"]
    history_detail = client.get(f"/api/v1/history/{chat.json()['data']['record_id']}").json()["data"]
    dashboard = client.get("/api/v1/dashboard/summary").json()["data"]

    assert sessions_page["total"] == 1
    assert sessions_page["items"][0]["last_question"] == "按地区统计销售额"
    assert first_page["messages"][0]["role"] == "assistant"
    assert first_page["messages"][0]["analysis_record"]["tool_result"]["rows"][0]["sales_sum"] == 12
    assert second_page["messages"][0]["role"] == "user"
    assert history_page["total"] == 1
    assert history_detail["tool_calls"][0]["tool_name"] == "group_by_analysis"
    assert history_detail["user_message"]["content"] == "按地区统计销售额"
    assert dashboard["session_count"] == 1
    assert dashboard["recent_analyses"][0]["id"] == chat.json()["data"]["record_id"]


def test_deleting_a_session_removes_messages_and_records_but_keeps_dataset(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"sales\n12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    monkeypatch.setattr(analysis, "agent", SuccessfulAgent())
    client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": dataset_id, "question": "统计销售额", "request_id": "api-test-delete"})

    removed = client.delete(f"/api/v1/analysis/sessions/{session_id}")

    assert removed.status_code == 200
    assert client.get(f"/api/v1/analysis/sessions/{session_id}").status_code == 404
    assert client.get(f"/api/v1/datasets/{dataset_id}").status_code == 200
    with sessions() as db:
        assert db.query(AnalysisRecord).filter_by(session_id=session_id).count() == 0


def test_sessions_and_history_are_scoped_to_the_authenticated_owner(analysis_context, monkeypatch):
    client, sessions, _ = analysis_context
    uploaded = client.post("/api/v1/datasets/upload", files={"file": ("sales.csv", b"region,sales\nEast,12\n", "text/csv")})
    dataset_id = uploaded.json()["data"]["id"]
    session_id = make_session(sessions, dataset_id)
    monkeypatch.setattr(analysis, "agent", SuccessfulAgent())
    chat = client.post("/api/v1/analysis/chat", json={"session_id": session_id, "dataset_id": dataset_id, "question": "汇总销售额", "request_id": "api-test-owner"})
    record_id = chat.json()["data"]["record_id"]
    client.post("/api/v1/auth/logout")
    client.post("/api/v1/auth/register", json={"username": "bobby", "password": "safe-password-123"})

    assert client.get(f"/api/v1/analysis/sessions/{session_id}").status_code == 403
    assert client.delete(f"/api/v1/analysis/sessions/{session_id}").status_code == 403
    assert client.get(f"/api/v1/history/{record_id}").status_code == 403
