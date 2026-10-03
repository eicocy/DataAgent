from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models import AnalysisMessage, AnalysisRecord, Dataset, User


router = APIRouter(prefix="/history", tags=["history"])


def _history_or_error(db: Session, record_id: int, user_id: int) -> AnalysisRecord:
    record = db.get(AnalysisRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "HISTORY_NOT_FOUND", "message": "分析记录不存在", "data": None})
    if record.user_id != user_id:
        raise HTTPException(status_code=403, detail={"code": "HISTORY_FORBIDDEN", "message": "你没有权限查看这条分析记录", "data": None})
    return record


@router.get("")
def list_history(
    q: str | None = None,
    dataset_id: int | None = Query(default=None, gt=0),
    tool_name: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(succeeded|partial|failed|pending|running)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    query = select(AnalysisRecord, Dataset.original_name).join(Dataset, Dataset.id == AnalysisRecord.dataset_id).where(AnalysisRecord.user_id == user.id)
    count_query = select(func.count()).select_from(AnalysisRecord).join(Dataset, Dataset.id == AnalysisRecord.dataset_id).where(AnalysisRecord.user_id == user.id)
    if dataset_id:
        query = query.where(AnalysisRecord.dataset_id == dataset_id)
        count_query = count_query.where(AnalysisRecord.dataset_id == dataset_id)
    if tool_name:
        query = query.where(AnalysisRecord.primary_tool_name == tool_name)
        count_query = count_query.where(AnalysisRecord.primary_tool_name == tool_name)
    if status_filter:
        query = query.where(AnalysisRecord.status == status_filter)
        count_query = count_query.where(AnalysisRecord.status == status_filter)
    if date_from:
        start = datetime.combine(date_from, time.min, tzinfo=UTC)
        query = query.where(AnalysisRecord.created_at >= start)
        count_query = count_query.where(AnalysisRecord.created_at >= start)
    if date_to:
        end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        query = query.where(AnalysisRecord.created_at < end)
        count_query = count_query.where(AnalysisRecord.created_at < end)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        condition = or_(AnalysisRecord.question.ilike(pattern), Dataset.original_name.ilike(pattern))
        query = query.where(condition)
        count_query = count_query.where(condition)
    total = db.scalar(count_query) or 0
    rows = db.execute(query.order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"code": 200, "message": "success", "data": {"items": [
        {"id": record.id, "question": record.question, "dataset_id": record.dataset_id, "dataset_name": dataset_name,
         "session_id": record.session_id, "primary_tool_name": record.primary_tool_name, "status": record.status,
         "execution_time_ms": record.execution_time_ms, "created_at": record.created_at.isoformat()}
        for record, dataset_name in rows
    ], "page": page, "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size}}


@router.get("/{record_id}")
def get_history(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = _history_or_error(db, record_id, user.id)
    dataset = db.get(Dataset, record.dataset_id)
    user_message = db.get(AnalysisMessage, record.user_message_id) if record.user_message_id else None
    assistant_message = db.get(AnalysisMessage, record.assistant_message_id) if record.assistant_message_id else None
    return {"code": 200, "message": "success", "data": {
        "id": record.id,
        "request_id": record.request_id,
        "question": record.question,
        "intent_summary": record.intent_summary,
        "dataset": {"id": dataset.id, "original_name": dataset.original_name, "row_count": dataset.row_count, "column_count": dataset.column_count, "file_type": dataset.file_type},
        "session_id": record.session_id,
        "user_message": {"id": user_message.id, "content": user_message.content, "created_at": user_message.created_at.isoformat()} if user_message else None,
        "assistant_message": {"id": assistant_message.id, "content": assistant_message.content, "status": assistant_message.status, "created_at": assistant_message.created_at.isoformat()} if assistant_message else None,
        "primary_tool_name": record.primary_tool_name,
        "tool_calls": record.tool_calls_json or [],
        "tool_result": record.tool_result_json,
        "plan": record.plan_json,
        "report": record.report_json,
        "usage": record.usage_json,
        "chart": record.chart_json,
        "final_answer": record.final_answer,
        "status": record.status,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "execution_time_ms": record.execution_time_ms,
        "created_at": record.created_at.isoformat(),
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }}
