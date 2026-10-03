"""Initial immutable versions; legacy binding does not assert historical snapshots."""
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from sqlalchemy import select
from app.models import DatasetVersion, AnalysisRecord
from app.datasets.profiler import build_profile


def create_initial_version(db, dataset, frame, upload_dir, source_kind='parsed_upload'):
    existing = db.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset.id, DatasetVersion.version_number == 1))
    if existing:
        dataset.current_version_id = existing.id
        return existing
    schema, profile = build_profile(frame)
    path = Path(upload_dir) / dataset.stored_name
    checksum = None
    if path.is_file():
        with path.open('rb') as source:
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
    version = DatasetVersion(dataset_id=dataset.id, version_number=1, status='ready', source_kind=source_kind, projection_schema=dataset.projection_schema, projection_table=dataset.projection_table or f'dataset_{dataset.id}', schema_json=schema.model_dump(mode='json'), profile_json=profile.model_dump(mode='json'), transformations_json=frame.attrs.get('transformations', []) if source_kind == 'parsed_upload' else [{'operation': 'legacy_projection_binding', 'historical_snapshot': False}], original_available=path.is_file(), source_checksum=checksum, created_at=datetime.now(UTC))
    db.add(version)
    db.flush()
    dataset.current_version_id = version.id
    return version


def backfill_dataset(db, dataset, bind, upload_dir, apply=False):
    from app.services.datasets import DatasetService
    service = DatasetService(db, bind)
    _, columns = service.get(dataset.id, dataset.user_id)
    if dataset.current_version_id is not None:
        service.get_version(dataset, dataset.current_version_id)
        return {'dataset_id': dataset.id, 'status': 'already_versioned'}
    frame = service.load_frame(dataset, columns)
    frame.attrs['original_columns'] = [column.original_name for column in columns]
    if not apply:
        return {'dataset_id': dataset.id, 'status': 'would_backfill', 'row_count': len(frame)}
    version = create_initial_version(db, dataset, frame, upload_dir, 'legacy_projection')
    for record in db.scalars(select(AnalysisRecord).where(AnalysisRecord.dataset_id == dataset.id, AnalysisRecord.dataset_version_id.is_(None))):
        record.dataset_version_id = version.id
        record.version_binding = 'legacy_association'
    db.commit()
    return {'dataset_id': dataset.id, 'status': 'backfilled', 'version_id': version.id}
