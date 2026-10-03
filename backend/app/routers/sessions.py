from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models import AnalysisMessage, AnalysisRecord, AnalysisSession, Dataset, User, AnalysisArtifact, AnalysisReport, AnalysisReportVersion, CleanupTask


router = APIRouter(prefix="/analysis/sessions", tags=["analysis sessions"])


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None

    @model_validator(mode="after")
    def require_update(self):
        if self.title is None and self.is_pinned is None:
            raise ValueError("At least one session field is required")
        if self.title is not None and not self.title.strip():
            raise ValueError("Session title cannot be blank")
        return self


def _session_or_error(db: Session, session_id: int, user_id: int) -> AnalysisSession:
    session = db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "ANALYSIS_SESSION_NOT_FOUND", "message": "分析会话不存在", "data": None})
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail={"code": "ANALYSIS_SESSION_FORBIDDEN", "message": "你没有权限访问这个分析会话", "data": None})
    return session


def _record_evidence(record: AnalysisRecord | None) -> dict | None:
    if record is None:
        return None
    return {
        "id": record.id,
        "request_id": record.request_id,
        "question": record.question,
        "session_id": record.session_id,
        "dataset_id": record.dataset_id,
        "dataset_version_id": record.dataset_version_id,
        "status": record.status,
        "tool_calls": record.tool_calls_json or [],
        "tool_result": record.tool_result_json,
        "plan": record.plan_json,
        "report": record.report_json,
        "usage": record.usage_json,
        "chart": record.chart_json,
        "final_answer": record.final_answer,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "execution_time_ms": record.execution_time_ms,
    }


@router.get("")
def list_analysis_sessions(
    q: str | None = None,
    dataset_id: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    last_question = (
        select(AnalysisMessage.content)
        .where(AnalysisMessage.session_id == AnalysisSession.id, AnalysisMessage.role == "user")
        .order_by(AnalysisMessage.created_at.desc(), AnalysisMessage.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    message_count = select(func.count(AnalysisMessage.id)).where(AnalysisMessage.session_id == AnalysisSession.id).scalar_subquery()
    query = select(AnalysisSession, Dataset.original_name, message_count.label("message_count"), last_question.label("last_question")).outerjoin(Dataset, Dataset.id == AnalysisSession.dataset_id).where(AnalysisSession.user_id == user.id)
    count_query = select(func.count()).select_from(AnalysisSession).where(AnalysisSession.user_id == user.id)
    if dataset_id:
        query = query.where(AnalysisSession.dataset_id == dataset_id)
        count_query = count_query.where(AnalysisSession.dataset_id == dataset_id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        condition = or_(AnalysisSession.title.ilike(pattern), last_question.ilike(pattern), Dataset.original_name.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.outerjoin(Dataset, Dataset.id == AnalysisSession.dataset_id).where(condition)
    total = db.scalar(count_query) or 0
    rows = db.execute(query.order_by(AnalysisSession.is_pinned.desc(), AnalysisSession.updated_at.desc(), AnalysisSession.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"code": 200, "message": "success", "data": {"items": [
        {"id": session.id, "dataset_id": session.dataset_id, "dataset_name": dataset_name, "title": session.title, "status": session.status, "is_pinned": session.is_pinned, "message_count": count, "last_question": question, "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat()}
        for session, dataset_name, count, question in rows
    ], "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}}


@router.get("/{session_id}")
def get_analysis_session(
    session_id: int,
    message_cursor: int | None = Query(default=None, ge=0),
    message_limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    session = _session_or_error(db, session_id, user.id)
    dataset = db.get(Dataset, session.dataset_id) if session.dataset_id else None
    total_messages = db.scalar(select(func.count()).select_from(AnalysisMessage).where(AnalysisMessage.session_id == session.id)) or 0
    message_query = select(AnalysisMessage).where(AnalysisMessage.session_id == session.id)
    if message_cursor is not None:
        message_query = message_query.where(AnalysisMessage.id < message_cursor)
    fetched = db.scalars(message_query.order_by(AnalysisMessage.id.desc()).limit(message_limit + 1)).all()
    has_more = len(fetched) > message_limit
    messages = list(reversed(fetched[:message_limit]))
    message_ids = [message.id for message in messages]
    records = db.scalars(
        select(AnalysisRecord).where(
            AnalysisRecord.session_id == session.id,
            or_(AnalysisRecord.user_message_id.in_(message_ids), AnalysisRecord.assistant_message_id.in_(message_ids)),
        )
    ).all() if message_ids else []
    by_message: dict[int, AnalysisRecord] = {}
    for record in records:
        if record.user_message_id:
            by_message[record.user_message_id] = record
        if record.assistant_message_id:
            by_message[record.assistant_message_id] = record
    output_messages = [{
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
        "analysis_record": _record_evidence(by_message.get(message.id)),
    } for message in messages]
    return {"code": 200, "message": "success", "data": {
        "session": {"id": session.id, "dataset_id": session.dataset_id, "title": session.title, "status": session.status, "is_pinned": session.is_pinned, "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat()},
        "dataset": {"id": dataset.id, "original_name": dataset.original_name, "row_count": dataset.row_count, "column_count": dataset.column_count, "file_type": dataset.file_type} if dataset else None,
        "messages": output_messages,
        "message_count": total_messages,
        "next_cursor": messages[0].id if has_more and messages else None,
    }}


@router.patch("/{session_id}")
def update_analysis_session(session_id: int, payload: SessionPatch,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session_or_error(db, session_id, user.id)
    if payload.title is not None:
        session.title = payload.title.strip()
    if payload.is_pinned is not None:
        session.is_pinned = payload.is_pinned
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return {"code": 200, "message": "success", "data": {
        "id": session.id, "dataset_id": session.dataset_id, "title": session.title,
        "status": session.status, "is_pinned": session.is_pinned,
        "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat()}}


@router.delete("/{session_id}")
def delete_analysis_session(session_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session_or_error(db, session_id, user.id)
    db.scalar(select(AnalysisSession).where(AnalysisSession.id == session_id).with_for_update())
    pending = db.scalar(select(func.count()).select_from(AnalysisRecord).where(AnalysisRecord.session_id == session.id, AnalysisRecord.status.in_(("pending", "running")))) or 0
    if pending:
        raise HTTPException(status_code=409, detail={"code": "SESSION_BUSY", "message": "分析仍在处理中，请稍后删除", "data": None})
    session_report_ids = select(AnalysisReportVersion.id).join(AnalysisReport, AnalysisReport.id == AnalysisReportVersion.report_id).where(AnalysisReport.session_id == session.id)
    stored_artifacts = db.scalars(select(AnalysisArtifact.stored_name).where(
        AnalysisArtifact.record_id.in_(select(AnalysisRecord.id).where(AnalysisRecord.session_id == session.id)))).all()
    stored_artifacts += db.scalars(select(AnalysisArtifact.stored_name).where(
        AnalysisArtifact.report_version_id.in_(session_report_ids))).all()
    file_keys = db.scalars(select(AnalysisArtifact.storage_key).where(
        or_(AnalysisArtifact.report_version_id.in_(session_report_ids),
            AnalysisArtifact.record_id.in_(select(AnalysisRecord.id).where(AnalysisRecord.session_id == session.id))),
        AnalysisArtifact.storage_key.is_not(None))).all()
    if stored_artifacts or file_keys:
        db.add(CleanupTask(payload_json={"artifacts": stored_artifacts,
            "artifact_storage_keys": file_keys}, status="pending", created_at=datetime.now(UTC)))
    db.query(AnalysisRecord).filter(AnalysisRecord.session_id == session.id).delete(synchronize_session=False)
    db.query(AnalysisMessage).filter(AnalysisMessage.session_id == session.id).delete(synchronize_session=False)
    deleted_id = session.id
    db.delete(session)
    db.commit()
    return {"code": 200, "message": "success", "data": {"deleted_id": deleted_id, "deleted_at": datetime.now(UTC).isoformat()}}
