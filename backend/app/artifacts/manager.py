"""Unified authorized facade; JSON evidence and binary exports keep their stores."""
from datetime import UTC, datetime
import os
from sqlalchemy import func, select
from app.config import get_settings
from app.models import (AnalysisArtifact, AnalysisRecord, AnalysisReport,
                        AnalysisReportVersion, ToolExecutionRecord, User)


def expired(item):
    return bool(item.purged_at or (item.expires_at is not None and
        item.expires_at <= datetime.now(UTC).replace(tzinfo=None)))


class ArtifactManager:
    def __init__(self, db, settings=None):
        self.db, self.settings = db, settings or get_settings()

    def check_quota(self, user_id, size):
        # Serialize owner writes; the lock is held until publication commits.
        self.db.scalar(select(User.id).where(User.id == user_id).with_for_update())
        self.db.flush()
        used = self.db.scalar(select(func.coalesce(func.sum(AnalysisArtifact.size_bytes), 0)).where(
            AnalysisArtifact.user_id == user_id, AnalysisArtifact.purged_at.is_(None))) or 0
        maximum = getattr(self.settings, 'artifact_user_max_bytes',
            int(os.environ.get('ARTIFACT_USER_MAX_BYTES', 2 * 1024**3)))
        if size < 0 or used + size > maximum:
            raise ValueError('ARTIFACT_USER_QUOTA_EXCEEDED')

    def owned(self, artifact_id, user_id, session_id=None, require_ready=False):
        item = self.db.get(AnalysisArtifact, artifact_id)
        if not item or item.user_id != user_id:
            raise LookupError('ARTIFACT_NOT_FOUND')
        if session_id is not None and self.session_id(item) != session_id:
            raise LookupError('ARTIFACT_SESSION_MISMATCH')
        if require_ready:
            if expired(item) or not self.available(item):
                raise LookupError('ARTIFACT_EXPIRED')
            if item.status != 'READY': raise LookupError('ARTIFACT_NOT_READY')
        return item

    def session_id(self, item):
        if item.session_id is not None: return item.session_id
        if item.record_id:
            record = self.db.get(AnalysisRecord, item.record_id)
            return record.session_id if record else None
        if item.tool_execution_id:
            execution = self.db.get(ToolExecutionRecord, item.tool_execution_id)
            record = self.db.get(AnalysisRecord, execution.analysis_record_id) if execution and execution.analysis_record_id else None
            return record.session_id if record else None
        version = self.db.get(AnalysisReportVersion, item.report_version_id) if item.report_version_id else None
        report = self.db.get(AnalysisReport, version.report_id) if version else None
        return report.session_id if report else None

    def available(self, item):
        from app.artifacts.storage import LocalArtifactStorage
        from app.services.artifacts import ArtifactStore
        try:
            path = LocalArtifactStorage(self.settings.artifact_dir)._path(item.storage_key) if item.storage_key else ArtifactStore(self.db, self.settings)._path(item.stored_name)
            return path.is_file()
        except (ValueError, OSError): return False

    def view(self, item):
        metadata = item.metadata_json or {}
        mime = item.mime_type or 'application/json'
        kind = {'application/pdf': 'pdf', 'text/x-python': 'python', 'application/sql': 'sql',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'excel',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'word'}.get(mime, item.kind)
        return {'id': item.id, 'artifact_id': item.id, 'session_id': self.session_id(item),
            'conversation_id': self.session_id(item), 'task_id': item.record_id or item.tool_execution_id or item.report_version_id,
            'step_id': item.step_id, 'type': kind, 'artifact_type': kind.upper(),
            'name': item.file_name or item.step_id, 'title': item.file_name or item.step_id,
            'description': metadata.get('description'), 'mime_type': mime,
            'file_name': item.file_name, 'size_bytes': item.size_bytes, 'row_count': item.row_count,
            'status': 'EXPIRED' if expired(item) or (item.status == 'READY' and not self.available(item)) else item.status,
            'preview_url': f'/api/v1/artifacts/{item.id}/preview',
            'download_url': f'/api/v1/artifacts/{item.id}/download', 'metadata': metadata,
            'dataset_versions': metadata.get('dataset_versions', []),
            'source_artifact_ids': metadata.get('source_artifact_ids', []),
            'retention_class': item.retention_class, 'created_at': item.created_at.isoformat(),
            'expires_at': item.expires_at.isoformat() if item.expires_at else None}

    def protect(self, item, category='evidence'):
        if item.purged_at or not self.available(item): return
        item.retention_class, item.expires_at = category, None
        item.session_id = self.session_id(item)
        for identifier in (item.metadata_json or {}).get('source_artifact_ids', []):
            source = self.db.get(AnalysisArtifact, identifier)
            if source and source.user_id == item.user_id and source.id != item.id:
                # Follow one level; record finalization protects the complete graph.
                if not source.purged_at and self.available(source):
                    source.retention_class, source.expires_at = 'evidence', None

    def finalize_record(self, record):
        rows = self.db.scalars(select(AnalysisArtifact).where(
            AnalysisArtifact.user_id == record.user_id, AnalysisArtifact.record_id == record.id)).all()
        versions = (record.request_config_json or {}).get('inputs') or ([{
            'alias': 'primary', 'dataset_id': record.dataset_id, 'dataset_version_id': record.dataset_version_id}] if record.dataset_version_id else [])
        for item in rows:
            item.session_id = record.session_id
            item.metadata_json = {**(item.metadata_json or {}), 'dataset_versions': versions}
            self.protect(item, 'final')
        for step in (record.plan_json or {}).get('steps', []):
            ref = step.get('result_ref') or ''
            if ref.startswith('artifact:') and ref.split(':', 1)[1].isdigit():
                item = self.db.get(AnalysisArtifact, int(ref.split(':', 1)[1]))
                if item and item.user_id == record.user_id: self.protect(item)

    def regenerate(self, source):
        """Publish a new immutable copy from the complete saved result; never recompute."""
        import uuid
        from app.services.artifacts import ArtifactStore
        from app.artifacts.storage import LocalArtifactStorage
        self.owned(source.id, source.user_id, require_ready=True)
        storage = LocalArtifactStorage(self.settings.artifact_dir)
        content = storage.read(source.storage_key) if source.storage_key else ArtifactStore(self.db,self.settings)._path(source.stored_name).read_bytes()
        self.check_quota(source.user_id,len(content))
        row = AnalysisArtifact(record_id=source.record_id, tool_execution_id=source.tool_execution_id,
            report_version_id=source.report_version_id, user_id=source.user_id, dataset_id=source.dataset_id,
            session_id=self.session_id(source), step_id=source.step_id, kind=source.kind,
            stored_name=uuid.uuid4().hex+'.json', size_bytes=len(content), row_count=source.row_count,
            schema_json=source.schema_json, status='READY', created_at=datetime.now(UTC).replace(tzinfo=None),
            expires_at=None, retention_class='final', mime_type=source.mime_type, file_name=source.file_name,
            metadata_json={**(source.metadata_json or {}), 'source_artifact_ids':[source.id], 'regenerated_from':source.id})
        self.db.add(row); self.db.flush()
        path = None
        try:
            if source.storage_key:
                sid = row.session_id
                if not sid: raise LookupError('ARTIFACT_SESSION_UNAVAILABLE')
                saved = storage.save(user_id=row.user_id,conversation_id=sid,
                    task_id=row.record_id or row.tool_execution_id or row.report_version_id,
                    artifact_id=row.id,file_name=row.file_name,content=content)
                row.storage_key = saved.storage_key
            else:
                path = ArtifactStore(self.db,self.settings)._path(row.stored_name)
                path.write_bytes(content)
            self.protect(source)
            self.db.commit()
        except Exception:
            self.db.rollback()
            if path: path.unlink(missing_ok=True)
            if row.storage_key: storage.delete(row.storage_key)
            raise
        return row
