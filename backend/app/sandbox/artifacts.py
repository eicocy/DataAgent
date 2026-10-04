"""Publish already re-encoded images through the existing owner-scoped store."""
from datetime import UTC, datetime
import uuid
from app.models import AnalysisArtifact
from app.artifacts.manager import ArtifactManager
from app.artifacts.storage import LocalArtifactStorage
from app.config import get_settings


def persist_images(db,record,step_id,images,dataset_id,dataset_version_id,check_lease=None):
    settings=get_settings(); storage=LocalArtifactStorage(settings.artifact_dir)
    if not images: return []
    if len(images)>4 or sum(len(image) for image in images)>settings.artifact_task_max_bytes:
        raise ValueError('SANDBOX_IMAGE_BUDGET')
    if check_lease: check_lease()
    ArtifactManager(db).check_quota(record.user_id,sum(len(image) for image in images))
    keys=[]; rows=[]
    try:
        for index,content in enumerate(images):
            artifact=AnalysisArtifact(user_id=record.user_id,record_id=record.id,session_id=record.session_id,
                dataset_id=dataset_id,step_id=f'{step_id}_image_{index}',kind='image',retention_class='evidence',
                stored_name=uuid.uuid4().hex+'.json',status='CREATING',size_bytes=len(content),row_count=0,
                schema_json={'columns':[],'types':{},'version':'1.0'},created_at=datetime.now(UTC).replace(tzinfo=None),
                expires_at=None,file_name=f'自定义分析图-{index+1}.png',mime_type='image/png',
                metadata_json={'source_step_id':step_id,'dataset_versions':[{'dataset_id':dataset_id,'dataset_version_id':dataset_version_id}]})
            db.add(artifact); db.flush()
            saved=storage.save(user_id=record.user_id,conversation_id=record.session_id,task_id=record.id,
                artifact_id=artifact.id,file_name=artifact.file_name,content=content)
            keys.append(saved.storage_key); artifact.storage_key=saved.storage_key; artifact.status='READY'
            rows.append(artifact)
        if check_lease: check_lease()
        db.commit()
    except Exception:
        db.rollback()
        for key in keys: storage.delete(key)
        raise
    return rows
