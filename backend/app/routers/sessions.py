from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import current_user
from app.models import AnalysisMessage, AnalysisRecord, AnalysisSession, Dataset, DatasetColumn, User, AnalysisArtifact, AnalysisReport, AnalysisReportVersion, CleanupTask
from app.agent.context import ConversationContext
from app.routers.datasets import _owned_dataset


router = APIRouter(prefix="/analysis/sessions", tags=["analysis sessions"])


from app.semantic.mappings import SemanticMapping, merge_mappings


class SemanticPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mappings: list[SemanticMapping] = Field(min_length=1, max_length=200)


@router.patch('/{session_id}/semantic-mappings')
def update_semantics(session_id: int, request: SemanticPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.models import DatasetVersion
    _session_or_error(db, session_id, user.id)
    session = db.scalar(select(AnalysisSession).where(AnalysisSession.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if session is None or session.user_id != user.id:
        raise HTTPException(404, detail={'code': 'ANALYSIS_SESSION_NOT_FOUND', 'message': '分析会话不存在'})
    context = ConversationContext.from_session(session)
    allowed_ids = set(context.attached_dataset_ids) | {session.dataset_id}
    entries = []
    for item in request.mappings:
        version = db.get(DatasetVersion, item.dataset_version_id)
        dataset = db.get(Dataset, version.dataset_id) if version else None
        if not dataset or dataset.user_id != user.id or dataset.id not in allowed_ids:
            raise HTTPException(403, detail={'code': 'SEMANTIC_VERSION_FORBIDDEN', 'message': '只能修正会话中已授权的数据版本'})
        if item.column not in {c['name'] for c in version.schema_json['columns']}:
            raise HTTPException(422, detail={'code': 'COLUMN_NOT_FOUND', 'message': '语义字段不在该版本中'})
        entries.append(item.model_copy(update={'source': 'user', 'confidence': 1.0, 'reason': '用户明确修正'}).model_dump())
    changed = {(m['dataset_version_id'], m['column']) for m in entries}
    context.semantic_mappings = [m for m in context.semantic_mappings if (m['dataset_version_id'], m['column']) not in changed] + entries
    if len(context.semantic_mappings) > 2000:
        raise HTTPException(422, detail={'code': 'SEMANTIC_LIMIT', 'message': '语义映射达到会话上限'})
    context.semantic_version += 1
    session.context_json = {**(session.context_json or {}), **context.model_dump(mode='json')}
    db.commit()
    return {'code': 200, 'message': 'success', 'data': {'version': context.semantic_version, 'mappings': entries}}


@router.get('/{session_id}/semantic-mappings')
def get_semantics(session_id: int, dataset_id: int | None = Query(default=None, gt=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    from app.services.datasets import DatasetService
    from app.semantic.detectors import detect_semantics
    session = _session_or_error(db, session_id, user.id)
    context = ConversationContext.from_session(session)
    did = dataset_id or session.dataset_id
    if did is None:
        return {'code': 200, 'message': 'success', 'data': {'version': context.semantic_version, 'mappings': []}}
    if did not in set(context.attached_dataset_ids) | {session.dataset_id}:
        raise HTTPException(403, detail={'code': 'DATASET_FORBIDDEN', 'message': '数据集未绑定此会话'})
    dataset = _owned_dataset(db, did, user.id)
    from app.database import projection_engine
    from app.services.analysis import select_projection_bind
    service = DatasetService(db, select_projection_bind(dataset, db.get_bind(), projection_engine))
    version = service.get_version(dataset)
    columns = db.scalars(select(DatasetColumn).where(DatasetColumn.dataset_id == did)).all()
    frame = service.load_frame(dataset, columns, version.id)
    candidates = detect_semantics(frame, version.id, {c['name']: c.get('original_name', c['name']) for c in version.schema_json['columns']})
    mappings = merge_mappings(candidates, context.semantic_mappings, version.id)
    return {'code': 200, 'message': 'success', 'data': {'version': context.semantic_version, 'dataset_version_id': version.id, 'mappings': [m.model_dump() for m in mappings]}}


class SessionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None
    attached_dataset_ids: list[int] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def require_update(self):
        if self.title is None and self.is_pinned is None and self.attached_dataset_ids is None:
            raise ValueError("At least one session field is required")
        if self.title is not None and not self.title.strip():
            raise ValueError("Session title cannot be blank")
        if self.attached_dataset_ids is not None and any(value <= 0 for value in self.attached_dataset_ids):
            raise ValueError('Dataset IDs must be positive')
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
        "request_options": (record.request_config_json or {}).get('public'),
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


def _visible_attachments(db: Session, session: AnalysisSession, user_id: int) -> list[int]:
    ids = (session.context_json or {}).get('attached_dataset_ids', [])[:10]
    # 文件可能已被删除或权限改变；读接口也不泄露失效附件。
    owned = set(db.scalars(select(Dataset.id).where(Dataset.id.in_(ids), Dataset.user_id == user_id, Dataset.status == 'ready')).all())
    return [value for value in ids if value in owned]


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
        "session": {"id": session.id, "dataset_id": session.dataset_id, "attached_dataset_ids": _visible_attachments(db, session, user.id), "title": session.title, "status": session.status, "is_pinned": session.is_pinned, "created_at": session.created_at.isoformat(), "updated_at": session.updated_at.isoformat()},
        "dataset": {"id": dataset.id, "original_name": dataset.original_name, "row_count": dataset.row_count, "column_count": dataset.column_count, "file_type": dataset.file_type} if dataset else None,
        "messages": output_messages,
        "message_count": total_messages,
        "next_cursor": messages[0].id if has_more and messages else None,
    }}


@router.patch("/{session_id}")
def update_analysis_session(session_id: int, payload: SessionPatch,
                            user: User = Depends(current_user), db: Session = Depends(get_db)):
    session = _session_or_error(db, session_id, user.id)
    if payload.attached_dataset_ids is not None:
        # 与提交分析共用 Session 行锁；禁止运行期间覆盖正在持久化的上下文。
        session = db.scalar(select(AnalysisSession).where(AnalysisSession.id == session_id).with_for_update().execution_options(populate_existing=True))
        active = db.scalar(select(AnalysisRecord.id).where(AnalysisRecord.session_id == session_id, AnalysisRecord.status.in_(('pending', 'running'))).limit(1))
        if active is not None:
            raise HTTPException(409, detail={'code': 'SESSION_BUSY', 'message': '请等待当前分析结束后再调整附件'})
        ids = list(dict.fromkeys(payload.attached_dataset_ids))
        for dataset_id in ids:
            dataset = _owned_dataset(db, dataset_id, user.id)
            if dataset.status != 'ready':
                raise HTTPException(409, detail={'code': 'DATASET_NOT_READY', 'message': '附件尚未完成解析'})
        context = session.context_json or ConversationContext(conversation_id=session.id, user_id=user.id).model_dump()
        session.context_json = {**context, 'attached_dataset_ids': ids}
    if payload.title is not None:
        session.title = payload.title.strip()
    if payload.is_pinned is not None:
        session.is_pinned = payload.is_pinned
    session.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return {"code": 200, "message": "success", "data": {
        "id": session.id, "dataset_id": session.dataset_id, "attached_dataset_ids": _visible_attachments(db, session, user.id), "title": session.title,
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
