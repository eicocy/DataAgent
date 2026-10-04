from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from test_analysis_api import analysis_context, make_session
from app.models import AnalysisArtifact, AnalysisRecord, User
from app.services.artifacts import ArtifactStore


def source(client, sessions):
    dataset_id = client.post('/api/v1/datasets/upload', files={'file': ('data.csv', b'x\n1\n2\n', 'text/csv')}).json()['data']['id']
    session_id = make_session(sessions, dataset_id)
    with sessions() as db:
        user = db.scalar(select(User))
        record = AnalysisRecord(user_id=user.id, dataset_id=dataset_id, session_id=session_id,
            request_id='phase4-source', question='test', status='succeeded', created_at=datetime.now(UTC))
        db.add(record); db.commit()
        return record.id, session_id


def test_final_artifact_has_session_and_no_expiry(analysis_context, tmp_path):
    client, sessions, _ = analysis_context
    rid, sid = source(client, sessions)
    with sessions() as db:
        record = db.get(AnalysisRecord, rid)
        store = ArtifactStore(db)
        result = store.write(record, 'result', {'columns': ['x'], 'rows': [{'x': 1}]})
        from app.artifacts.manager import ArtifactManager
        ArtifactManager(db).finalize_record(record)
        row = db.get(AnalysisArtifact, result['artifact_id'])
        assert row.session_id == sid
        assert row.expires_at is None
        assert row.retention_class == 'final'
        assert store.read(row)['rows'] == [{'x': 1}]
        view = ArtifactManager(db).view(row)
        assert view['session_id'] == sid and view['expires_at'] is None
        assert 'storage_key' not in view and 'stored_name' not in view


def test_quota_rejects_write_without_removing_final(analysis_context, tmp_path):
    client, sessions, _ = analysis_context
    rid, _ = source(client, sessions)
    with sessions() as db:
        from app.artifacts.manager import ArtifactManager
        settings = SimpleNamespace(artifact_dir=str(tmp_path/'artifacts'), artifact_user_max_bytes=32,
            artifact_max_bytes=1024, artifact_task_max_bytes=2048, artifact_retention_days=7)
        store = ArtifactStore(db, settings)
        with pytest.raises(ValueError, match='ARTIFACT_USER_QUOTA_EXCEEDED'):
            store.write(db.get(AnalysisRecord, rid), 'too_big', {'rows': [{'x': 'a'*50}]})
        assert list((tmp_path/'artifacts').glob('*')) == []


def test_finalize_does_not_revive_purged_artifact(analysis_context):
    client, sessions, _ = analysis_context
    rid, _ = source(client, sessions)
    with sessions() as db:
        from app.artifacts.manager import ArtifactManager
        record = db.get(AnalysisRecord, rid)
        value = ArtifactStore(db).write(record, 'old', {'rows': []})
        item = db.get(AnalysisArtifact, value['artifact_id'])
        item.purged_at = datetime.now(UTC).replace(tzinfo=None)
        item.expires_at = item.purged_at - timedelta(days=1)
        ArtifactManager(db).finalize_record(record)
        assert ArtifactManager(db).view(item)['status'] == 'EXPIRED'
        with pytest.raises(LookupError): ArtifactStore(db).read(item)
