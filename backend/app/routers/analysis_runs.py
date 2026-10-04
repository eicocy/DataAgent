from typing import Any, Literal
import asyncio
import json
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, Query, Response, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import current_user
from app.models import User, AnalysisRecord, AnalysisArtifact, AnalysisEvent, AnalysisMessage, BackgroundJob
from app.routers.analysis import AnalysisChatRequest, _response
from app.services.analysis import submit_analysis, domain_error, append_event
from app.services.artifacts import ArtifactStore
from app.artifacts.manager import expired
from app.agent.schemas import AgentResponse, Insight

router = APIRouter(prefix="/analysis/runs", tags=["analysis-runs"])


class RunSubmission(BaseModel):
    record_id: int
    session_id: int
    status: str
    status_url: str
    trace_url: str


class RunData(BaseModel):
    request_options: dict | None = None
    record_id: int
    session_id: int
    message_id: int
    status: Literal["pending", "running", "succeeded", "partial", "failed", "waiting", "cancelled"]
    dataset_id: int | None = None
    dataset_version_id: int | None = None
    current_step: str | None = None
    progress: dict[str, int] | None = None
    agent_response: AgentResponse | None = None
    artifacts: list[dict] = []
    evidence: list[dict] = []
    answer: str | None = None
    tool_name: str | None = None
    tool_parameters: dict | None = None
    tool_result: dict | None = None
    tool_calls: list[dict]
    chart: dict | None = None
    execution_time: float
    summary_error: str | None = None
    report: dict | None = None
    error_code: str | None = None
    error_message: str | None = None
    usage: dict | None = None


class TraceData(BaseModel):
    plan: dict | None = None
    steps: list[dict]


class ResultPage(BaseModel):
    artifact_id: int
    offset: int
    limit: int
    total: int
    columns: list[str]
    rows: list[dict[str, Any]]
    expired: bool = False


class SubmissionResponse(BaseModel):
    code: int
    message: str
    data: RunSubmission


class RunResponse(BaseModel):
    code: int
    message: str
    data: RunData


class TraceResponse(BaseModel):
    code: int
    message: str
    data: TraceData


class PageResponse(BaseModel):
    code: int
    message: str
    data: ResultPage


def owned_record(db, record_id, user_id):
    record = db.get(AnalysisRecord, record_id)
    if not record or record.user_id != user_id:
        raise domain_error(404, "ANALYSIS_NOT_FOUND", "分析记录不存在")
    return record


def owned_artifact(db, artifact_id, user_id, record_id=None):
    artifact = db.get(AnalysisArtifact, artifact_id)
    if not artifact or artifact.user_id != user_id or (record_id is not None and artifact.record_id != record_id):
        raise domain_error(404, "ARTIFACT_NOT_FOUND", "结果不存在")
    owned_record(db, artifact.record_id, user_id)
    return artifact


def referenced_artifact(db, record, artifact_id, user_id):
    artifact = owned_artifact(db, artifact_id, user_id)
    if artifact.record_id == record.id:
        return artifact
    refs = {step.get('result_ref') for step in (record.plan_json or {}).get('steps', [])}
    source = db.get(AnalysisRecord, artifact.record_id) if artifact.record_id else None
    if (f'artifact:{artifact_id}' not in refs or source is None or source.user_id != user_id or
        source.dataset_id != record.dataset_id or source.dataset_version_id != record.dataset_version_id):
        raise domain_error(404, 'ARTIFACT_NOT_FOUND', '结果不存在')
    return artifact


@router.post("", response_model=SubmissionResponse, status_code=202)
def submit(request: AnalysisChatRequest, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record, created = submit_analysis(db, user.id, request, allow_switch=True)
    response.status_code = 202 if created else 200
    url = f"/api/v1/analysis/runs/{record.id}"
    return {"code": response.status_code, "message": "accepted" if created else "replayed", "data": {"record_id": record.id, "session_id": record.session_id, "status": record.status, "status_url": url, "trace_url": url + "/trace"}}


@router.get("/{record_id}", response_model=RunResponse)
def status(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_record(db, record_id, user.id)
    data = _response(record)["data"]
    data['request_options'] = (record.request_config_json or {}).get('public')
    data.update(report=record.report_json, error_code=record.error_code, error_message=record.error_message, usage=record.usage_json)
    plan = record.plan_json or {}
    steps = plan.get('steps', [])
    reused_ids = {int(ref.split(':', 1)[1]) for item in steps
                  if (ref := item.get('result_ref', '') or '').startswith('artifact:')
                  and ref.split(':', 1)[1].isdigit()}
    artifact_rows = db.scalars(select(AnalysisArtifact).where(
        AnalysisArtifact.user_id == user.id,
        or_(AnalysisArtifact.record_id == record.id, AnalysisArtifact.id.in_(reused_ids))
    ).order_by(AnalysisArtifact.id)).all()
    artifact_rows = [item for item in artifact_rows if item.record_id == record.id or
                     (item.id in reused_ids and referenced_artifact(db, record, item.id, user.id))]
    now = datetime.now(UTC).replace(tzinfo=None)
    artifacts = [{'artifact_id': item.id, 'step_id': item.step_id, 'kind': item.kind,
                  'row_count': item.row_count, 'expired': expired(item)}
                 for item in artifact_rows]
    artifact_by_step = {item['step_id']: item['artifact_id'] for item in artifacts}
    tool_by_step = {item.get('step_id'): item.get('tool_name') for item in steps}
    evidence = []
    for finding in (record.report_json or {}).get('findings', []):
        if finding.get('kind') != 'bound_fact':
            continue
        fact = finding.get('reference') or {}
        step_id = fact.get('step_id')
        if step_id not in artifact_by_step:
            continue
        alias = next((s.get('input_alias') for s in steps if s['step_id'] == step_id), None)
        binding = next((i for i in (record.request_config_json or {}).get('inputs', []) if i['alias'] == alias), {})
        evidence.append({'evidence_id': f'{record.id}:{step_id}:{fact.get("key")}',
                         'source_type': 'tool_artifact',
                         'dataset_id': binding.get('dataset_id', record.dataset_id), 'dataset_version_id': binding.get('dataset_version_id', record.dataset_version_id),
                         'step_id': step_id, 'tool_name': tool_by_step.get(step_id),
                         'artifact_id': artifact_by_step[step_id],
                         'result_ref': f'artifact:{artifact_by_step[step_id]}',
                         'fact_path': fact.get('path'),
                         'key': fact.get('key')})
    completed = sum(item.get('status') == 'COMPLETED' for item in steps)
    active = next((item.get('step_id') for item in steps if item.get('status') == 'RUNNING'), None)
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.kind.in_(['analysis', 'report']), BackgroundJob.resource_id == record.id))
    intent_event = db.scalar(select(AnalysisEvent).where(AnalysisEvent.record_id == record.id,
        AnalysisEvent.event_type == 'intent_resolved').order_by(AnalysisEvent.id.desc()).limit(1))
    clarification = None
    if record.status == 'waiting':
        candidate_ids = (intent_event.payload_json or {}).get('candidates', []) if intent_event else []
        clarification = {'message': record.final_answer, 'candidate_dataset_ids': candidate_ids}
    report = record.report_json or {}
    response = AgentResponse(task_id=str(record.id), conversation_id=str(record.session_id),
        status=record.status, intent=record.intent_summary, answer=record.final_answer or '',
        summary=record.final_answer, insights=[Insight(title='已验证结论', description=record.final_answer,
            evidence_ids=[item['evidence_id'] for item in evidence])] if evidence and record.final_answer else [],
        tables=report.get('tables') or [], charts=report.get('charts') or [], evidence=evidence,
        artifacts=artifacts, warnings=report.get('warnings') or [],
        plan_summary={'goal': plan.get('goal'), 'status': plan.get('status'), 'steps': len(steps)} if plan else None,
        clarification=clarification)
    data.update(dataset_id=record.dataset_id, dataset_version_id=record.dataset_version_id,
                current_step=active or (job.active_stage if job else None),
                progress={'completed': completed, 'total': len(steps)}, agent_response=response,
                artifacts=artifacts, evidence=evidence)
    return {"code": 200, "message": "success", "data": data}


@router.get("/{record_id}/trace", response_model=TraceResponse)
def trace(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_record(db, record_id, user.id)
    return {"code": 200, "message": "success", "data": {"plan": record.plan_json, "steps": record.tool_calls_json or []}}


@router.get("/{record_id}/events")
async def events(record_id: int, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    owned_record(db, record_id, user.id)
    try:
        cursor = max(0, int(request.headers.get('Last-Event-ID', '0')))
    except ValueError:
        raise domain_error(400, 'EVENT_CURSOR_INVALID', '事件游标无效') from None

    async def stream():
        nonlocal cursor
        while not await request.is_disconnected():
            db.rollback()
            rows = db.scalars(select(AnalysisEvent).where(AnalysisEvent.record_id == record_id,
                AnalysisEvent.user_id == user.id, AnalysisEvent.id > cursor).order_by(AnalysisEvent.id).limit(100)).all()
            for item in rows:
                cursor = item.id
                yield f'id: {item.id}\nevent: {item.event_type}\ndata: {json.dumps(item.payload_json, ensure_ascii=False)}\n\n'
            db.expire_all()
            record = owned_record(db, record_id, user.id)
            if record.status in {'succeeded', 'partial', 'failed', 'cancelled', 'waiting'} and not rows:
                break
            if not rows:
                yield ': keep-alive\n\n'
                await asyncio.sleep(1)
    return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@router.post("/{record_id}/cancel")
def cancel(record_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_record(db, record_id, user.id)
    if record.status in {'succeeded', 'partial', 'failed', 'cancelled', 'waiting'}:
        return {'code': 200, 'message': 'success', 'data': {'record_id': record.id, 'status': record.status}}
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.kind.in_(['analysis', 'report']), BackgroundJob.resource_id == record.id).with_for_update())
    if not job:
        raise domain_error(409, 'TASK_NOT_FOUND', '任务状态不可用')
    if job.status == 'pending':
        now = datetime.now(UTC)
        job.status = record.status = 'cancelled'
        job.completed_at = record.completed_at = now
        record.error_code = job.error_code = 'TASK_CANCELLED'
        record.error_message = '任务已取消'
        message = db.get(AnalysisMessage, record.assistant_message_id) if record.assistant_message_id else None
        if message:
            message.status, message.content = 'cancelled', '任务已取消'
        else:
            message = AnalysisMessage(session_id=record.session_id, role='assistant', content='任务已取消', status='cancelled', created_at=now)
            db.add(message)
            db.flush()
            record.assistant_message_id = message.id
        append_event(db, record, 'analysis_cancelled', {'status': 'cancelled'})
    else:
        job.cancel_requested = True
        append_event(db, record, 'cancel_requested', {'status': 'running'})
    db.commit()
    return {'code': 200, 'message': 'success', 'data': {'record_id': record.id, 'status': record.status}}


@router.get("/{record_id}/results/{artifact_id}", response_model=PageResponse)
def results(record_id: int, artifact_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), user: User = Depends(current_user), db: Session = Depends(get_db)):
    record = owned_record(db, record_id, user.id)
    artifact = referenced_artifact(db, record, artifact_id, user.id)
    try:
        payload = ArtifactStore(db).read(artifact)
    except LookupError:
        raise domain_error(410, "ARTIFACT_EXPIRED", "完整中间结果已过期，历史预览仍可查看") from None
    return {"code": 200, "message": "success", "data": {"artifact_id": artifact.id, "offset": offset, "limit": limit, "total": artifact.row_count, "columns": payload["schema"]["columns"], "rows": payload["rows"][offset:offset + limit], "expired": False}}
