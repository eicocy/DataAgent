from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, or_
from sqlalchemy.orm import Session

from app.artifacts.storage import LocalArtifactStorage
from app.services.artifacts import ArtifactStore
from app.charts.renderer import ChartRenderer, chart_spec_from_legacy
from app.config import get_settings
from app.models import (AnalysisArtifact, AnalysisEvent, AnalysisMessage, AnalysisRecord,
                        AnalysisReport, AnalysisReportVersion, AnalysisSession, BackgroundJob,
                        Dataset, DatasetVersion, DatasetColumn, User, ToolExecutionRecord)
from app.reports.builder import ReportBuilder
from app.reports.exporters import MAX_EXPORT_ROWS, ExportOptions, exporter_registry
from app.reports.schemas import ReportSpec
from app.artifacts.manager import ArtifactManager, expired


class ReportError(ValueError):
    def __init__(self, code: str, status_code: int = 422):
        self.code, self.status_code = code, status_code
        super().__init__(code)


def _input_lineage(db, user_id, bindings):
    """Pin all immutable inputs, including both sides of saved joins."""
    result, seen = [], set()
    pending = list(bindings)
    while pending:
        binding = pending.pop(0)
        key = (binding['dataset_id'], binding['dataset_version_id'])
        if key in seen: continue
        seen.add(key)
        version = db.get(DatasetVersion, key[1]); dataset = db.get(Dataset, key[0])
        if not dataset or dataset.user_id != user_id or not version or version.dataset_id != dataset.id or version.status != 'ready':
            raise ReportError('REPORT_INPUT_VERSION_UNAVAILABLE',410)
        result.append(binding)
        # Walk ancestors to discover joins followed by later cleaning steps.
        ancestor, ancestors = version, set()
        while ancestor:
            if ancestor.id in ancestors: raise ReportError('REPORT_INPUT_LINEAGE_INVALID')
            ancestors.add(ancestor.id)
            for operation in ancestor.transformations_json or []:
                for source in operation.get('source_versions', []):
                    if source['dataset_id'] != dataset.id:
                        pending.append({'alias':f"lineage_{source['dataset_id']}_{source['version_id']}",
                            'dataset_id':source['dataset_id'],'dataset_version_id':source['version_id']})
            ancestor = db.get(DatasetVersion,ancestor.parent_version_id) if ancestor.parent_version_id else None
    return result


def _owned_dataset_version(db: Session, user_id: int, spec: ReportSpec):
    dataset = db.get(Dataset, spec.dataset_id)
    version = db.get(DatasetVersion, spec.dataset_version_id)
    if not dataset or dataset.user_id != user_id:
        raise ReportError("DATASET_NOT_FOUND", 404)
    if not version or version.dataset_id != dataset.id or version.status != "ready":
        raise ReportError("DATASET_VERSION_NOT_FOUND", 404)
    return dataset, version


def _source_rows(db: Session, user_id: int, session_id: int, spec: ReportSpec,
                 record_ids: list[int], inline_source: tuple[int,str] | None = None) -> list[dict]:
    if not record_ids or len(record_ids) > 50:
        raise ReportError("REPORT_SOURCE_REQUIRED")
    session = db.get(AnalysisSession, session_id)
    if not session or session.user_id != user_id:
        raise ReportError("SESSION_NOT_FOUND", 404)
    rows = db.scalars(select(AnalysisRecord).where(
        AnalysisRecord.id.in_(set(record_ids)), AnalysisRecord.user_id == user_id,
        AnalysisRecord.session_id == session_id,
        AnalysisRecord.dataset_id == spec.dataset_id,
        AnalysisRecord.dataset_version_id == spec.dataset_version_id,
        or_(AnalysisRecord.status.in_(["succeeded", "partial"]),
            AnalysisRecord.id == inline_source[0] if inline_source else False),
    )).all()
    if len(rows) != len(set(record_ids)):
        raise ReportError("REPORT_SOURCE_NOT_FOUND", 404)
    referenced_ids = {int(ref.split(':',1)[1]) for row in rows for step in (row.plan_json or {}).get('steps',[])
        if (ref:=step.get('result_ref') or '').startswith('artifact:') and ref.split(':',1)[1].isdigit()}
    artifacts = db.scalars(select(AnalysisArtifact).where(
        AnalysisArtifact.user_id == user_id,
        or_(AnalysisArtifact.record_id.in_([row.id for row in rows]), AnalysisArtifact.id.in_(referenced_ids)),
    )).all()
    artifacts = [item for item in artifacts if ArtifactManager(db).session_id(item)==session_id]
    artifacts_by_record: dict[int, list[dict]] = {}
    for artifact in artifacts:
        artifacts_by_record.setdefault(artifact.record_id, []).append({
            "artifact_id": artifact.id, "step_id": artifact.step_id,
            "kind": artifact.kind,
            "expired": expired(artifact) or not ArtifactManager(db).available(artifact),
        })
    for row in rows:
        existing_ids = {item['artifact_id'] for item in artifacts_by_record.get(row.id,[])}
        for step in (row.plan_json or {}).get('steps',[]):
            ref = step.get('result_ref') or ''
            if not ref.startswith('artifact:') or not ref.split(':',1)[1].isdigit(): continue
            identifier = int(ref.split(':',1)[1])
            if identifier in existing_ids: continue
            item = next((a for a in artifacts if a.id==identifier),None)
            if item:
                artifacts_by_record.setdefault(row.id,[]).append({'artifact_id':item.id,'step_id':step['step_id'],
                    'kind':item.kind,'expired':expired(item) or not ArtifactManager(db).available(item)})
    sources = []
    for row in rows:
        from app.reports.result_tables import result_tables
        calculations, tables = [], []
        for artifact in artifacts:
            if artifact.id not in {item['artifact_id'] for item in artifacts_by_record.get(row.id,[])} or artifact.storage_key: continue
            if not expired(artifact) and ArtifactManager(db).available(artifact):
                payload = ArtifactStore(db).read(artifact)
                result = payload.get('data') or {}
                if payload.get('rows'):
                    result = {**result, 'columns':payload.get('schema',{}).get('columns',[]),'rows':payload['rows']}
                if artifact.kind != 'chart':
                    calculations.append(result); tables.extend(result_tables(result))
                ArtifactManager(db).protect(artifact)
        facts = (row.report_json or {}).get("findings", [])
        evidence = []
        for fact in facts:
            ref = fact.get("reference") or {}
            step_id, key = ref.get("step_id"), ref.get("key")
            artifact = next((item for item in artifacts_by_record.get(row.id, [])
                             if item["step_id"] == step_id), None)
            if fact.get("kind") == "bound_fact" and not artifact:
                raise ReportError('REPORT_EVIDENCE_UNAVAILABLE',410)
            if fact.get("kind") == "bound_fact" and artifact:
                owner_artifact = db.get(AnalysisArtifact,artifact['artifact_id'])
                if artifact['expired']: raise ReportError('REPORT_EVIDENCE_EXPIRED',410)
                execution = next((e for e in db.scalars(select(ToolExecutionRecord).where(
                    ToolExecutionRecord.analysis_record_id.in_([row.id,owner_artifact.record_id])).order_by(ToolExecutionRecord.id.desc()))
                    if (e.result_json or {}).get('artifact_ref')==owner_artifact.id),None)
                value = ArtifactStore(db).read(owner_artifact).get('data') or {}
                try:
                    for part in ref.get('path',[]): value = value[part]
                except (KeyError,IndexError,TypeError): raise ReportError('REPORT_EVIDENCE_INVALID',422) from None
                evidence.append({
                    "evidence_id": f"{row.id}:{step_id}:{key}",
                    "dataset_id": owner_artifact.dataset_id, "dataset_version_id": execution.dataset_version_id if execution else row.dataset_version_id,
                    "step_id": step_id, "tool_name": next((step.get("tool_name") for step in
                        (row.plan_json or {}).get("steps", []) if step.get("step_id") == step_id), None),
                    "artifact_id": artifact["artifact_id"], "fact_path": ref.get("path"), "key": key, 'value':value,
                })
        sources.append({
            "record_id": row.id, "dataset_id": row.dataset_id,
            "dataset_version_id": row.dataset_version_id, "status": inline_source[1] if inline_source and row.id==inline_source[0] else row.status,
            "answer": row.final_answer, "report": {**(row.report_json or {}),'tables': tables or (row.report_json or {}).get('tables',[])},
            'results':calculations, 'plan':row.plan_json,
            'dataset_name':db.get(Dataset,row.dataset_id).original_name,
            'dataset_versions': _input_lineage(db,user_id,(row.request_config_json or {}).get('inputs') or [{'alias':'primary','dataset_id':row.dataset_id,'dataset_version_id':row.dataset_version_id}]),
            "evidence": evidence, "artifacts": artifacts_by_record.get(row.id, []),
        })
    return sources


def create_report(db: Session, user_id: int, session_id: int,
                  spec: ReportSpec, record_ids: list[int], *, report_id: int | None = None,
                  inline_source: tuple[int,str] | None = None) -> tuple[AnalysisReport, AnalysisReportVersion]:
    dataset, version = _owned_dataset_version(db, user_id, spec)
    sources = _source_rows(db, user_id, session_id, spec, record_ids,inline_source)
    report = (db.scalar(select(AnalysisReport).where(AnalysisReport.id == report_id).with_for_update().execution_options(populate_existing=True))
              if report_id else None)
    now = datetime.now(UTC)
    if report_id:
        if not report or report.user_id != user_id:
            raise ReportError("REPORT_NOT_FOUND", 404)
        if report.session_id != session_id or report.dataset_id != dataset.id or report.dataset_version_id != version.id:
            raise ReportError("REPORT_SOURCE_MISMATCH", 409)
        if spec.base_version != report.latest_version_number:
            raise ReportError("REPORT_VERSION_CONFLICT", 409)
    else:
        report = AnalysisReport(user_id=user_id, session_id=session_id,
            dataset_id=dataset.id, dataset_version_id=version.id, title=spec.title,
            status="READY", latest_version_number=0, created_at=now, updated_at=now)
        db.add(report)
        db.flush()

    number = report.latest_version_number + 1
    try:
        doc = ReportBuilder().build(spec, sources, report_id=report.id, report_version=number)
    except ValueError as error:
        raise ReportError(str(error)) from None
    row = AnalysisReportVersion(report_id=report.id, version_number=number, status="READY",
        spec_json=spec.model_dump(mode="json"), document_json=doc.model_dump(mode="json"),
        source_records_json=sorted(set(record_ids)), dataset_versions_json=doc.metadata.get('dataset_versions',[]), created_at=now)
    report.title, report.latest_version_number, report.updated_at = spec.title, number, now
    db.add(row)
    db.commit()
    db.refresh(report)
    db.refresh(row)
    return report, row


def export_report_version(db: Session, report: AnalysisReport, version: AnalysisReportVersion,
                          format: str) -> list[AnalysisArtifact]:
    from app.reports.schemas import ReportDocument

    storage = LocalArtifactStorage(get_settings().artifact_dir)
    cached = db.scalars(select(AnalysisArtifact).where(
        AnalysisArtifact.report_version_id == version.id,
        AnalysisArtifact.kind == "report", AnalysisArtifact.status == "READY")).all()
    cached = [item for item in cached if (item.metadata_json or {}).get("format") == format]
    if cached:
        try:
            for item in cached:
                if expired(item):
                    raise OSError("expired")
                storage.read(item.storage_key)
            return cached
        except (ValueError, OSError):
            pass
    document = ReportDocument.model_validate(version.document_json)
    chart_files: dict[int, bytes] = {}
    raw_data: list[dict] = []
    cleaned_data: list[dict] = []
    input_snapshots: list[dict] = []
    source_plan: dict = {}
    if document.artifacts and version.source_records_json:
        source_rows = db.scalars(select(AnalysisArtifact).where(
            AnalysisArtifact.user_id == report.user_id,
            AnalysisArtifact.id.in_(document.artifacts), AnalysisArtifact.kind.in_(["chart", "image"]))).all()
        source_rows = [item for item in source_rows if ArtifactManager(db).session_id(item)==report.session_id and ArtifactManager(db).available(item)]
        chart_ids = {artifact.id for artifact in source_rows}
        for source_artifact in source_rows:
            try:
                if source_artifact.kind == 'image':
                    import base64
                    from app.sandbox.results import safe_png
                    chart_files[source_artifact.id] = safe_png(base64.b64encode(storage.read(source_artifact.storage_key)).decode())
                    continue
                payload = ArtifactStore(db).read(source_artifact).get("data") or {}
                spec_payload = chart_spec_from_legacy(payload)
                chart_files[source_artifact.id] = ChartRenderer().render(spec_payload).png
            except (LookupError, ValueError, OSError):
                raise ValueError("REPORT_CHART_SOURCE_EXPIRED") from None
        expected_chart_ids = {
            item["artifact_id"]
            for section in document.sections
            for item in section.data.get("artifacts", [])
            if item.get("kind") in {"chart", "image"} and type(item.get("artifact_id")) is int
        }
        if expected_chart_ids - chart_ids:
            raise ValueError("REPORT_CHART_SOURCE_EXPIRED")
    if format in {"xlsx", "python", "sql"}:
        records = db.scalars(select(AnalysisRecord).where(
            AnalysisRecord.id.in_(version.source_records_json),
            AnalysisRecord.user_id == report.user_id,
            AnalysisRecord.session_id == report.session_id,
            AnalysisRecord.dataset_id == report.dataset_id,
            AnalysisRecord.dataset_version_id == report.dataset_version_id,
        )).all()
        if not records: raise ValueError('REPORT_SOURCE_NOT_FOUND')
        source_plan = {**(records[-1].plan_json or {}),
            'semantic_snapshot':(records[-1].request_config_json or {}).get('semantic_snapshot',[])}
        from app.services.datasets import DatasetService
        from app.services.analysis import select_projection_bind
        from app.database import projection_engine
        from app.analysis.serialization import records as frame_records
        seen = set()
        for binding in version.dataset_versions_json or document.metadata.get('dataset_versions',[]) or [{'alias':'primary','dataset_id':report.dataset_id,'dataset_version_id':report.dataset_version_id}]:
            key = (binding['dataset_id'],binding['dataset_version_id'])
            if key in seen: continue
            seen.add(key)
            dataset = db.get(Dataset,key[0]); fixed = db.get(DatasetVersion,key[1])
            if not dataset or dataset.user_id != report.user_id or not fixed or fixed.dataset_id != dataset.id or fixed.status != 'ready':
                raise ValueError('REPORT_INPUT_VERSION_UNAVAILABLE')
            service = DatasetService(db,select_projection_bind(fixed,db.get_bind(),projection_engine))
            columns = db.scalars(select(DatasetColumn).where(DatasetColumn.dataset_id==dataset.id)).all()
            if format == 'xlsx':
                current_frame = service.load_frame(dataset,columns,fixed.id,preserve_decimal=True)
                current_rows = frame_records(current_frame)
                original = fixed
                ancestors = set()
                while original.parent_version_id:
                    if original.id in ancestors: raise ValueError('REPORT_INPUT_LINEAGE_INVALID')
                    ancestors.add(original.id)
                    original = db.get(DatasetVersion,original.parent_version_id)
                    if not original or original.dataset_id != dataset.id or original.status != 'ready':
                        raise ValueError('REPORT_ORIGINAL_VERSION_UNAVAILABLE')
                raw_frame = current_frame if original.id == fixed.id else service.load_frame(dataset,columns,original.id,preserve_decimal=True)
                raw_rows = frame_records(raw_frame)
                def annotated(rows,vid):
                    return [{**row,'_input_alias':binding.get('alias','primary'),'_dataset_id':dataset.id,
                        '_dataset_version_id':vid,'source_record_id':records[-1].id} for row in rows]
                raw_data.extend(annotated(raw_rows,original.id))
                if original.id != fixed.id: cleaned_data.extend(annotated(current_rows,fixed.id))
            input_snapshots.append({**binding,'dataset_name':dataset.original_name,'schema':fixed.schema_json,
                'profile':fixed.profile_json,'transformations':fixed.transformations_json,'source_checksum':fixed.source_checksum})
    files = exporter_registry().export(format, document, ExportOptions(
        chart_files=chart_files, include_raw_data=format=='xlsx', raw_data=raw_data,
        cleaned_data=cleaned_data,input_snapshots=input_snapshots,source_plan=source_plan))
    rows: list[AnalysisArtifact] = []
    used = db.scalar(select(func.coalesce(func.sum(AnalysisArtifact.size_bytes), 0)).where(
        AnalysisArtifact.report_version_id == version.id, AnalysisArtifact.status == "READY")) or 0
    if used + sum(len(item.content) for item in files) > 128 * 1024 * 1024:
        raise ValueError("REPORT_TASK_ARTIFACT_BUDGET_EXCEEDED")
    ArtifactManager(db).check_quota(report.user_id,sum(len(item.content) for item in files))
    created_keys: list[str] = []
    try:
        for file in files:
            artifact = AnalysisArtifact(
                session_id=report.session_id, retention_class='final', record_id=None, tool_execution_id=None, report_version_id=version.id,
                user_id=report.user_id, dataset_id=report.dataset_id, step_id=f"export_{format}",
                kind="report", stored_name=f"{uuid.uuid4().hex}.json", size_bytes=len(file.content),
                row_count=0, schema_json={"columns": [], "types": {}, "version": "2.0"},
                created_at=datetime.now(UTC).replace(tzinfo=None),
                expires_at=None,
                status="CREATING", metadata_json={"report_id": report.id, "version": version.version_number,
                                                   "format": format, "file_name": file.file_name,
                                                   'dataset_versions':version.dataset_versions_json or [],
                                                   'source_artifact_ids':document.artifacts},
                file_name=file.file_name, mime_type=file.mime_type,
            )
            db.add(artifact)
            db.flush()
            saved = storage.save(user_id=report.user_id, conversation_id=report.session_id,
                task_id=report.id, artifact_id=artifact.id, file_name=file.file_name, content=file.content)
            created_keys.append(saved.storage_key)
            artifact.storage_key, artifact.file_name = saved.storage_key, saved.file_name
            artifact.mime_type, artifact.status = file.mime_type, "READY"
            rows.append(artifact)
        db.commit()
    except Exception:
        db.rollback()
        for storage_key in created_keys:
            storage.delete(storage_key)
        raise
    return rows








def enqueue_report_task(db: Session, user_id: int, session_id: int, dataset_id: int,
                        dataset_version_id: int, operation: str, payload: dict, *, request_id: str | None = None) -> AnalysisRecord:
    """Queue trusted, schema-validated report work on the existing supervised worker."""
    if operation not in {"create", "export"}:
        raise ReportError("REPORT_OPERATION_UNSUPPORTED")
    now = datetime.now(UTC).replace(tzinfo=None)
    db.scalar(select(User.id).where(User.id == user_id).with_for_update())
    request_config = {'operation':operation, 'session_id':session_id, 'dataset_id':dataset_id,
        'dataset_version_id':dataset_version_id, 'payload':payload}
    if request_id:
        existing = db.scalar(select(AnalysisRecord).where(AnalysisRecord.user_id == user_id,
            AnalysisRecord.request_id == request_id).with_for_update())
        if existing:
            if existing.request_config_json != request_config:
                raise ReportError('REPORT_REQUEST_ID_CONFLICT',409)
            existing._request_replayed = True
            return existing
    session = db.scalar(select(AnalysisSession).where(
        AnalysisSession.id == session_id, AnalysisSession.user_id == user_id).with_for_update())
    dataset = db.get(Dataset, dataset_id)
    if not session:
        raise ReportError("SESSION_NOT_FOUND", 404)
    if not dataset or dataset.user_id != user_id:
        raise ReportError("DATASET_NOT_FOUND", 404)
    version = db.get(DatasetVersion, dataset_version_id)
    if not version or version.dataset_id != dataset.id or version.status != "ready":
        raise ReportError("DATASET_VERSION_NOT_FOUND", 404)
    if operation == "create":
        spec = ReportSpec.model_validate(payload.get("spec") or {})
        _source_rows(db, user_id, session_id, spec, payload.get("source_record_ids") or [])
    settings = get_settings()
    queued = db.scalar(select(func.count()).select_from(BackgroundJob).where(
        BackgroundJob.status.in_(["pending", "running"]))) or 0
    if queued >= settings.max_pending_jobs:
        raise ReportError("TASK_QUEUE_FULL", 429)
    if db.scalar(select(AnalysisRecord.id).where(
        AnalysisRecord.session_id == session_id, AnalysisRecord.status.in_(["pending", "running"])).limit(1)):
        raise ReportError("ANALYSIS_SESSION_BUSY", 409)
    title = payload.get("spec", {}).get("title") or "报告导出"
    question = f"REPORT_{operation.upper()}: {title[:200]}"
    user_message = AnalysisMessage(session_id=session_id, role="user", content=question,
                                   status="complete", created_at=now)
    db.add(user_message)
    db.flush()
    assistant_message = AnalysisMessage(session_id=session_id, role="assistant", content="正在生成报告…",
                                        status="pending", created_at=now)
    db.add(assistant_message)
    db.flush()
    record = AnalysisRecord(user_id=user_id, dataset_id=dataset_id, session_id=session_id,
        user_message_id=user_message.id, assistant_message_id=assistant_message.id,
        dataset_version_id=dataset_version_id, schema_version="2.0", version_binding="snapshot",
        request_id=request_id or uuid.uuid4().hex, request_config_json=request_config, question=question, intent_summary="REPORT_GENERATION",
        status="pending", created_at=now, tool_calls_json=[], report_json={"version": "2.0", "operation": operation})
    db.add(record)
    db.flush()
    job = BackgroundJob(kind="report", resource_id=record.id, user_id=user_id, dataset_id=dataset_id,
                        status="pending", task_payload_json={"operation": operation, **payload}, created_at=now)
    db.add(job)
    db.add(AnalysisEvent(record_id=record.id, user_id=user_id, event_type="analysis_queued",
                         payload_json={"status": "pending", "operation": operation}, created_at=now))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(record)
    return record


def execute_report_task(db: Session, record_id: int, job_id: int, lease_token: str) -> None:
    """Execute report creation/export inside the supervised child process."""
    now = datetime.now(UTC).replace(tzinfo=None)
    record = db.get(AnalysisRecord, record_id)
    job = db.get(BackgroundJob, job_id)
    if not record or not job or job.kind != "report" or job.resource_id != record.id:
        return
    if job.status != "running" or job.lease_token != lease_token or job.cancel_requested:
        db.rollback()
        return
    payload = job.task_payload_json or {}
    record.status = "running"
    job.active_stage, job.stage_started_at = "report", now
    db.commit()
    try:
        if payload.get("operation") == "create":
            spec = ReportSpec.model_validate(payload["spec"])
            report, version = create_report(db, record.user_id, record.session_id, spec,
                                            payload["source_record_ids"], report_id=spec.report_id)
            result = {"operation": "create", "report": {
                "id": report.id, "session_id": report.session_id, "dataset_id": report.dataset_id,
                "dataset_version_id": report.dataset_version_id, "title": report.title,
                "status": report.status, "latest_version": report.latest_version_number,
                "version": version.version_number, "spec": version.spec_json,
                "document": version.document_json, "source_record_ids": version.source_records_json,
                "created_at": version.created_at.isoformat()}}
            message = "报告预览已生成。"
        elif payload.get("operation") == "export":
            report = db.get(AnalysisReport, int(payload["report_id"]))
            version = db.get(AnalysisReportVersion, int(payload["version_id"]))
            if not report or report.user_id != record.user_id or not version or version.report_id != report.id:
                raise ReportError("REPORT_NOT_FOUND", 404)
            artifacts = export_report_version(db, report, version, str(payload["format"]))
            result = {"operation": "export", "report_id": report.id,
                      "version": version.version_number, "artifacts": [{
                          "artifact_id": item.id, "file_name": item.file_name,
                          "mime_type": item.mime_type, "size_bytes": item.size_bytes,
                          "download_url": f"/api/v1/artifacts/{item.id}/download",
                          "preview_url": f"/api/v1/artifacts/{item.id}/preview"} for item in artifacts]}
            message = "报告文件已生成。"
        else:
            raise ReportError("REPORT_OPERATION_UNSUPPORTED")
        db.refresh(job)
        if job.status != "running" or job.lease_token != lease_token or job.cancel_requested:
            db.rollback()
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        record.status, record.final_answer = "succeeded", message
        record.report_json = {"version": "2.0", **result}
        record.completed_at = now
        assistant = db.get(AnalysisMessage, record.assistant_message_id) if record.assistant_message_id else None
        if assistant:
            assistant.status, assistant.content = "complete", message
        job.status, job.completed_at, job.active_stage = "succeeded", now, "complete"
        db.add(AnalysisEvent(record_id=record.id, user_id=record.user_id, event_type="response_ready",
            payload_json={"status": "succeeded", "operation": result["operation"]}, created_at=now))
        db.commit()
    except ReportError as error:
        _finish_report_failure(db, record, job, lease_token, error.code, error.status_code)
    except Exception as error:
        code = str(error) if str(error).startswith(("REPORT_", "DATASET_")) else "REPORT_TASK_FAILED"
        _finish_report_failure(db, record, job, lease_token, code, 500)


def _finish_report_failure(db: Session, record: AnalysisRecord, job: BackgroundJob,
                           lease_token: str, code: str, status_code: int) -> None:
    db.rollback()
    db.refresh(record)
    db.refresh(job)
    if job.status != "running" or job.lease_token != lease_token:
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    message = "报告任务无法完成，请检查来源记录和报告版本后重试。"
    record.status, record.error_code, record.error_message = "failed", code[:64], message
    record.final_answer, record.completed_at = message, now
    record.report_json = {"version": "2.0", "operation": (job.task_payload_json or {}).get("operation"),
                          "error_code": code[:64], "status_code": status_code}
    assistant = db.get(AnalysisMessage, record.assistant_message_id) if record.assistant_message_id else None
    if assistant:
        assistant.status, assistant.content = "failed", message
    job.status, job.error_code, job.completed_at, job.active_stage = "failed", code[:64], now, "failed"
    db.add(AnalysisEvent(record_id=record.id, user_id=record.user_id, event_type="analysis_failed",
        payload_json={"status": "failed", "error_code": code[:64]}, created_at=now))
    db.commit()
