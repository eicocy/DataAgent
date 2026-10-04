from __future__ import annotations

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import engine, get_db, readonly_engine
from app.dependencies import current_user
from app.models import AnalysisMessage, AnalysisRecord, AnalysisSession, Dataset, User
from app.services.analysis_agent import DeepSeekAgent


router = APIRouter(prefix="/analysis", tags=["analysis"])
agent = DeepSeekAgent()


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    alias: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,31}$')
    dataset_id: int = Field(gt=0)
    dataset_version_id: int | None = Field(default=None, gt=0)


class AnalysisChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(gt=0)
    dataset_id: int | None = Field(default=None, gt=0)
    question: str = Field(max_length=2000)
    request_id: str = Field(min_length=1, max_length=64)
    inputs: list[RunInput] = Field(default_factory=list, max_length=10)
    profile_ids: list[str] = Field(default_factory=list, max_length=3)
    depth: str | None = Field(default=None, pattern=r'^(FAST|STANDARD|DEEP)$')
    category: str | None = Field(default=None, max_length=50)
    model_id: str | None = Field(default=None, max_length=100)
    artifact_refs: list[int] = Field(default_factory=list, max_length=10)
    report_template: str | None = Field(default=None, pattern=r'^(auto|quick|detailed|executive|technical|data_quality|forecast)$')
    output_formats: list[str] = Field(default_factory=list, max_length=9)

    @field_validator("question")
    @classmethod
    def trim_question(cls, value: str) -> str:
        return value.strip()


class AnalysisSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=200)


def _error(status_code: int, code: str, message: str, data: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "data": data})


def _response(record: AnalysisRecord, assistant_content: str | None = None) -> dict:
    calls = record.tool_calls_json or []
    primary = next((item for item in calls if item.get("status") == "succeeded" and item.get("tool_name") != "generate_chart"), None)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "session_id": record.session_id,
            "message_id": record.assistant_message_id or record.id,
            "record_id": record.id,
            "status": record.status,
            "answer": record.final_answer if record.final_answer is not None else assistant_content,
            "tool_name": record.primary_tool_name,
            "tool_parameters": primary.get("parameters") if primary else None,
            "tool_result": record.tool_result_json,
            "tool_calls": calls,
            "chart": record.chart_json,
            "execution_time": (record.execution_time_ms or 0) / 1000,
            "summary_error": "SUMMARY_UNAVAILABLE" if record.status == "partial" else None,
        },
    }


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_analysis_session(
    request: AnalysisSessionRequest,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, request.dataset_id) if request.dataset_id else None
    if request.dataset_id:
        if dataset is None:
            raise _error(404, "DATASET_NOT_FOUND", "数据集不存在")
        if dataset.user_id != user.id:
            raise _error(403, "DATASET_FORBIDDEN", "你没有权限使用这个数据集")
        if dataset.status != "ready":
            raise _error(409, "DATASET_NOT_READY", "数据集尚未完成解析")
    title = request.title.strip() if request.title else "新分析"
    now = datetime.now(UTC)
    session = AnalysisSession(user_id=user.id, dataset_id=dataset.id if dataset else None, title=title or "新分析", status="active", created_at=now, updated_at=now)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"code": 201, "message": "created", "data": {"id": session.id, "dataset_id": session.dataset_id, "title": session.title, "status": session.status, "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat()}}


@router.post("/chat")
def analysis_chat(request: AnalysisChatRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.analysis import submit_analysis, execute_record
    from app.models import BackgroundJob
    record, created = submit_analysis(db, user.id, request)
    if record.status in {"pending", "running"}:
        if not isinstance(agent, DeepSeekAgent):
            job = db.scalar(select(BackgroundJob).where(BackgroundJob.kind == "analysis", BackgroundJob.resource_id == record.id))
            execute_record(db, record.id, agent, engine, engine, readonly_engine, job.id)
        else:
            deadline = time.monotonic() + agent.settings.analysis_timeout_seconds + 30
            while record.status in {"pending", "running"} and time.monotonic() < deadline:
                db.rollback()
                time.sleep(0.25)
                db.refresh(record)
            if record.status in {"pending", "running"}:
                raise _error(409, "ANALYSIS_REQUEST_IN_PROGRESS", "任务仍在处理中，请通过任务接口查看", {"record_id": record.id, "retryable": True})
    if record.status == "failed":
        status_code = 503 if record.error_code == "MODEL_UNAVAILABLE" else 422 if record.error_code in {"TOOL_VALIDATION_FAILED", "PLAN_INVALID"} else 500
        raise _error(status_code, record.error_code or "ANALYSIS_FAILED", record.error_message or "分析失败", {"record_id": record.id, "retryable": status_code == 503})
    return _response(record)
