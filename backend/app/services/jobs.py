"""Single-instance durable queue with supervised, terminable worker processes."""
import os
import subprocess
import sys
import threading
import uuid
import time
from datetime import datetime, timedelta, UTC
from pathlib import Path
from sqlalchemy import select, update, or_, exists
from app.config import get_settings
from app.models import BackgroundJob, AnalysisRecord, Dataset, AnalysisMessage, CleanupTask, AnalysisArtifact


def perform_cleanup(db, task, business_bind, projection_bind):
    from app.services.datasets import drop_projection
    from app.services.analysis import select_projection_bind
    from app.services.artifacts import ArtifactStore
    import re
    payload = task.payload_json
    try:
        if "dataset_id" in payload:
            location = type("Location", (), {"projection_schema": payload.get("projection_schema")})()
            drop_projection(int(payload["dataset_id"]), select_projection_bind(location, business_bind, projection_bind))
        for projection in payload.get('projections',[]):
            name=projection['table']
            if not re.fullmatch(r'dataset_\d+(?:_v_[a-f0-9]{32})?',name):
                raise ValueError('Invalid server projection name')
            from sqlalchemy import Table,MetaData,inspect
            location=type('Location',(),{'projection_schema':projection.get('schema')})()
            bind=select_projection_bind(location,business_bind,projection_bind)
            if inspect(bind).has_table(name): Table(name,MetaData(),autoload_with=bind).drop(bind)
        if payload.get("stored_name"):
            name = payload["stored_name"]
            if not re.fullmatch(r"[a-f0-9]{32}\.(csv|tsv|json|jsonl|parquet|xls|xlsx)", name):
                raise ValueError("Invalid server upload name")
            from app.models import UploadedFile
            if not db.scalar(select(UploadedFile.id).where(UploadedFile.stored_name == name)):
                (Path(get_settings().upload_dir).resolve() / name).unlink(missing_ok=True)
        store = ArtifactStore(db)
        if payload.get('file_stored_name'):
            from app.models import UploadedFile
            name=payload['file_stored_name']
            if not re.fullmatch(r'[a-f0-9]{32}\.(txt|pdf|docx|csv|tsv|json|jsonl|xls|xlsx|parquet)',name):
                raise ValueError('Invalid server file name')
            if not db.scalar(select(UploadedFile.id).where(UploadedFile.stored_name==name)):
                (Path(get_settings().upload_dir).resolve()/name).unlink(missing_ok=True)
        for name in payload.get("artifacts", []):
            store._path(name).unlink(missing_ok=True)
        from app.artifacts.storage import LocalArtifactStorage
        file_store = LocalArtifactStorage(get_settings().artifact_dir)
        for storage_key in payload.get("artifact_storage_keys", []):
            file_store.delete(storage_key)
        task.status, task.error_code = "succeeded", None
    except Exception:
        task.attempts += 1
        task.error_code = "CLEANUP_FAILED"
        task.next_attempt_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(seconds=min(3600, 2 ** task.attempts))
        if task.attempts >= 10:
            task.status = "failed"
    db.commit()


def run_maintenance(factory):
    from app.database import engine, projection_engine
    with factory() as db:
        tasks = db.scalars(select(CleanupTask).where(CleanupTask.status == "pending", or_(CleanupTask.next_attempt_at.is_(None), CleanupTask.next_attempt_at <= datetime.now(UTC).replace(tzinfo=None))).limit(10)).all()
        for task in tasks:
            perform_cleanup(db, task, engine, projection_engine)
        store_settings = get_settings()
        for artifact in db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.retention_class == 'intermediate', AnalysisArtifact.expires_at < datetime.now(UTC).replace(tzinfo=None), AnalysisArtifact.purged_at.is_(None)).limit(100)):
            from app.services.artifacts import ArtifactStore
            try:
                if artifact.storage_key:
                    from app.artifacts.storage import LocalArtifactStorage
                    LocalArtifactStorage(store_settings.artifact_dir).delete(artifact.storage_key)
                else:
                    ArtifactStore(db, store_settings)._path(artifact.stored_name).unlink(missing_ok=True)
                artifact.purged_at = datetime.now(UTC).replace(tzinfo=None)
            except OSError:
                pass
        db.commit()


def claim_job(factory):
    with factory() as db:
        # No second task may run while a valid lease exists.
        if db.scalar(select(BackgroundJob.id).where(BackgroundJob.status == "running").limit(1)):
            return None
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.status == "pending").order_by(BackgroundJob.id).with_for_update(skip_locked=True).limit(1))
        if not job:
            return None
        token, now = uuid.uuid4().hex, datetime.now(UTC).replace(tzinfo=None)
        changed = db.execute(update(BackgroundJob).where(BackgroundJob.id == job.id, BackgroundJob.status == "pending").values(status="running", lease_token=token, started_at=now, heartbeat_at=now)).rowcount
        db.commit()
        return (job.id, token) if changed else None


def terminate_job(factory, job_id, code="TASK_INTERRUPTED"):
    with factory() as db:
        job = db.get(BackgroundJob, job_id)
        if not job or job.status not in {"pending", "running"}:
            return
        now = datetime.now(UTC).replace(tzinfo=None)
        cancelled = code == 'TASK_CANCELLED'
        job.status, job.error_code, job.completed_at = ('cancelled' if cancelled else 'failed'), code, now
        if job.kind == "analysis":
            record = db.get(AnalysisRecord, job.resource_id)
            if record and record.status in {"pending", "running"}:
                record.status = 'cancelled' if cancelled else ('partial' if record.tool_result_json else 'failed')
                record.error_code, record.error_message, record.completed_at = code, ('任务已取消' if cancelled else '任务中断或超时，已保留完成的证据，请重新分析'), now
                if cancelled and record.plan_json:
                    plan = dict(record.plan_json)
                    plan['status'] = 'CANCELLED'
                    plan['steps'] = [dict(step, status='CANCELLED') if step.get('status') not in {'COMPLETED', 'FAILED'} else step for step in plan.get('steps', [])]
                    record.plan_json = plan
                calls = list(record.tool_calls_json or [])
                for call in calls:
                    if call.get("status") == "running":
                        call.update(status='cancelled' if cancelled else 'failed', error_code=code, result_summary='任务已取消' if cancelled else '执行中断')
                record.tool_calls_json = calls
                record.report_json = {"version": "1.0", "status": record.status, "answer": None, "tables": [record.tool_result_json] if record.tool_result_json else [], "charts": [record.chart_json] if record.chart_json else [], "warnings": [record.error_message], "evidence_refs": [], "incomplete_steps": [c.get("step_id", "") for c in calls if c.get("status") == "failed"]}
                message = AnalysisMessage(session_id=record.session_id, role="assistant", content=record.error_message, status=record.status, created_at=now)
                db.add(message)
                db.flush()
                record.assistant_message_id = message.id
                if cancelled:
                    from app.services.analysis import append_event
                    append_event(db, record, 'analysis_cancelled', {'status': 'cancelled'})
            from app.models import ToolExecutionRecord
            for execution in db.scalars(select(ToolExecutionRecord).where(ToolExecutionRecord.analysis_record_id==job.resource_id,ToolExecutionRecord.status=='running')):
                execution.status='failed';execution.finished_at=now
                execution.error_json={'code':code,'message':'工具任务中断或超时','details':{},'recoverable':False,'suggestion':'显式重试分析'}
            for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='reserved')):
                if task.payload_json.get('analysis_record_id')==job.resource_id:task.status='pending'
        elif job.kind == "report":
            record = db.get(AnalysisRecord, job.resource_id)
            if record and record.status in {"pending", "running"}:
                record.status = "cancelled" if cancelled else "failed"
                record.error_code = code
                record.error_message = "任务已取消" if cancelled else "报告任务中断或超时，请重新提交"
                record.final_answer, record.completed_at = record.error_message, now
                record.report_json = {"version": "2.0", "operation": (job.task_payload_json or {}).get("operation"), "status": record.status}
                message = db.get(AnalysisMessage, record.assistant_message_id) if record.assistant_message_id else None
                if message:
                    message.status, message.content = record.status, record.error_message
                from app.services.analysis import append_event
                append_event(db, record, "analysis_cancelled" if cancelled else "analysis_failed",
                             {"status": record.status, "error_code": code})
        elif job.kind == 'file_parse':
            from app.models import UploadedFile
            file = db.get(UploadedFile, job.resource_id)
            if file and file.status == 'parsing':
                file.status, file.error_code, file.error_message = 'failed', code, '文档解析中断或超时，请重新上传'
        elif job.kind == "parse":
            dataset = db.get(Dataset, job.resource_id)
            if dataset and dataset.status in {"uploading", "parsing"}:
                dataset.status, dataset.parse_error_code, dataset.parse_error_message = "failed", code, "文件解析中断或超时，请重新上传"
                db.add(CleanupTask(payload_json={"dataset_id": dataset.id, "projection_schema": dataset.projection_schema}, status="pending", created_at=now))
        elif job.kind=='tool':
            from app.models import ToolExecutionRecord
            record=db.get(ToolExecutionRecord,job.resource_id)
            if record and record.status in {'pending','running'}:
                record.status='failed';record.finished_at=now
                record.error_json={'code':code,'message':'工具任务中断或超时','details':{},'recoverable':False,'suggestion':'检查数据后显式重试'}
                for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='reserved')):
                    if task.payload_json.get('tool_execution_id')==record.id: task.status='pending'
        db.commit()


def recover_expired_jobs(factory):
    with factory() as db:
        ids = list(db.scalars(select(BackgroundJob.id).where(BackgroundJob.status == "running", or_(BackgroundJob.heartbeat_at.is_(None), BackgroundJob.heartbeat_at < datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=30)))))
    for job_id in ids:
        terminate_job(factory, job_id)
    return len(ids)


def recover_legacy_records(factory):
    """Terminate old synchronous in-flight rows which have no durable queue owner."""
    with factory() as db:
        now = datetime.now(UTC).replace(tzinfo=None)
        has_analysis_job = exists(select(BackgroundJob.id).where(BackgroundJob.kind.in_(("analysis", "report")), BackgroundJob.resource_id == AnalysisRecord.id))
        records = db.scalars(select(AnalysisRecord).where(AnalysisRecord.status.in_(("pending", "running")), ~has_analysis_job)).all()
        for record in records:
            record.status = "partial" if record.tool_result_json else "failed"
            record.error_code, record.error_message, record.completed_at = "TASK_INTERRUPTED", "旧版分析已中断，请重新分析", now
        has_parse_job = exists(select(BackgroundJob.id).where(BackgroundJob.kind == "parse", BackgroundJob.resource_id == Dataset.id))
        for dataset in db.scalars(select(Dataset).where(Dataset.status.in_(("uploading", "parsing")), ~has_parse_job)):
            dataset.status, dataset.parse_error_code, dataset.parse_error_message = "failed", "TASK_INTERRUPTED", "旧版解析已中断，请重新上传"
            db.add(CleanupTask(payload_json={"dataset_id": dataset.id, "projection_schema": dataset.projection_schema}, status="pending", created_at=now))
        db.commit()


class TaskSupervisor:
    def __init__(self, factory, settings=None):
        self.factory, self.settings = factory, settings or get_settings()
        self.stop_event = threading.Event()
        self.thread = None
        self.process = None

    def start(self):
        recover_legacy_records(self.factory)
        recover_expired_jobs(self.factory)
        self.thread = threading.Thread(target=self._loop, name="datalens-supervisor", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
        if self.thread:
            self.thread.join(timeout=8)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                recover_expired_jobs(self.factory)
                claimed = claim_job(self.factory)
                if claimed:
                    self.run_claimed(*claimed)
                else:
                    run_maintenance(self.factory)
                    self.stop_event.wait(0.5)
            except Exception:
                # Never log provider/database exception values.
                self.stop_event.wait(1)

    def run_claimed(self, job_id, token):
        env = os.environ.copy()
        for name, value in self.settings.model_dump().items():
            if value is not None:
                env[name.upper()] = str(value)
        env["DATABASE_URL"] = self.settings.database_url
        env["SECRET_KEY"] = self.settings.secret_key
        env["PROJECTION_DATABASE_URL"] = self.settings.projection_database_url
        env["SQL_READONLY_DATABASE_URL"] = self.settings.sql_readonly_database_url
        env["UPLOAD_DIR"], env["ARTIFACT_DIR"] = str(Path(self.settings.upload_dir).resolve()), str(Path(self.settings.artifact_dir).resolve())
        with self.factory() as db:
            job = db.get(BackgroundJob, job_id)
            budget = self.settings.parse_timeout_seconds if job.kind in {"parse", "file_parse"} else self.settings.report_timeout_seconds if job.kind == "report" else self.settings.analysis_timeout_seconds
            if job.kind == 'analysis':
                record = db.get(AnalysisRecord, job.resource_id)
                if record and record.request_config_json and record.request_config_json.get('inputs'):
                    from app.agent.budget import LIMITS
                    budget = LIMITS[record.request_config_json['depth']][3]
        deadline = time.monotonic() + budget
        self.process = subprocess.Popen([sys.executable, "-m", "app.task_runner", "--job-id", str(job_id), "--lease", token, "--parent-pid", str(os.getpid())], cwd=str(Path(__file__).resolve().parents[2]), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        timed_out = False
        cancelled = False
        process = self.process
        try:
            while process.poll() is None and not self.stop_event.is_set():
                with self.factory() as db:
                    job = db.get(BackgroundJob, job_id)
                    if not job or job.lease_token != token or job.status != "running":
                        break
                    if job.cancel_requested:
                        cancelled = True
                        break
                    now = datetime.now(UTC).replace(tzinfo=None)
                    stage_budget = job.stage_timeout_seconds if job.active_stage=='tool' else {"llm": self.settings.llm_timeout_seconds, "sql": self.settings.sql_timeout_seconds, "pandas": self.settings.pandas_timeout_seconds}.get(job.active_stage)
                    timed_out = time.monotonic() >= deadline or bool(stage_budget and job.stage_started_at and (now - job.stage_started_at).total_seconds() > stage_budget)
                    if not timed_out:
                        job.heartbeat_at = now
                        db.commit()
                if timed_out:
                    break
                self.stop_event.wait(0.25)
        finally:
            # Temporary DB faults must never leave a worker outside supervision.
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            self.process = None
            terminate_job(self.factory, job_id, 'TASK_CANCELLED' if cancelled else ("TASK_TIMEOUT" if timed_out else "TASK_INTERRUPTED"))
