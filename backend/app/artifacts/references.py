"""Structured mentions resolve to complete, immutable authorized sources."""
from app.artifacts.manager import ArtifactManager
from app.models import AnalysisRecord, AnalysisReportVersion, Dataset, DatasetVersion


def resolve_references(db, user_id, session_id, ids):
    manager = ArtifactManager(db)
    resolved = []
    for identifier in dict.fromkeys(ids):
        item = manager.owned(identifier, user_id, session_id, require_ready=True)
        if item.kind not in {'table', 'chart', 'dataset', 'report'}:
            raise LookupError('ARTIFACT_REFERENCE_TYPE_UNSUPPORTED')
        if item.mime_type in {'text/x-python','application/sql','application/zip','image/png','image/svg+xml'} and item.kind != 'chart':
            raise LookupError('ARTIFACT_REFERENCE_TYPE_UNSUPPORTED')
        base = item
        visited = set()
        while base.storage_key and base.kind == 'chart':
            sources = (base.metadata_json or {}).get('source_artifact_ids') or [(base.metadata_json or {}).get('source_artifact_id')]
            if not sources[0] or base.id in visited: raise LookupError('ARTIFACT_SOURCE_UNAVAILABLE')
            visited.add(base.id)
            base = manager.owned(sources[0], user_id, session_id, require_ready=True)
        record = db.get(AnalysisRecord, base.record_id) if base.record_id else None
        report_version = db.get(AnalysisReportVersion, base.report_version_id) if base.report_version_id else None
        versions = ((base.metadata_json or {}).get('dataset_versions') or
            ((record.request_config_json or {}).get('inputs') if record else None) or
            (report_version.dataset_versions_json if report_version else None) or
            ([{'alias':'primary', 'dataset_id':record.dataset_id, 'dataset_version_id':record.dataset_version_id}] if record else []))
        if not versions: raise LookupError('ARTIFACT_VERSION_UNAVAILABLE')
        for binding in versions:
            dataset = db.get(Dataset, binding.get('dataset_id'))
            version = db.get(DatasetVersion, binding.get('dataset_version_id'))
            if not dataset or dataset.user_id != user_id or not version or version.dataset_id != dataset.id or version.status != 'ready':
                raise LookupError('ARTIFACT_VERSION_UNAVAILABLE')
        manager.protect(base)
        resolved.append({'artifact_id': identifier, 'source_artifact_id': base.id, 'type': base.kind,
            'record_id': record.id if record else None, 'report_version_id': base.report_version_id,
            'dataset_versions': versions})
    return resolved
