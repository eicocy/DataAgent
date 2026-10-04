from datetime import UTC, datetime
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import User, BackgroundJob
from app.services.jobs import terminate_job
from test_analysis_api import analysis_context


def test_terminating_worker_revokes_container_owner(monkeypatch):
    bind=create_engine('sqlite://'); Base.metadata.create_all(bind)
    factory=sessionmaker(bind=bind,expire_on_commit=False); now=datetime.now(UTC)
    with factory() as db:
        user=User(username='sandbox-owner',password_hash='test',created_at=now,updated_at=now)
        db.add(user); db.flush()
        job=BackgroundJob(kind='test',resource_id=1,user_id=user.id,status='running',lease_token='owned-lease',created_at=now)
        db.add(job); db.commit(); jid=job.id
    revoked=[]
    monkeypatch.setattr('app.sandbox.client.cancel_job_sandbox',lambda *args:revoked.append(args))
    terminate_job(factory,jid,'TASK_CANCELLED')
    with factory() as db:
        assert db.get(BackgroundJob,jid).status=='cancelled'
    assert revoked==[(jid,'owned-lease')]
    bind.dispose()


def test_sandbox_token_is_omitted_from_logs():
    import logging
    from app.observability import SafeFormatter
    record=logging.LogRecord('broker',logging.ERROR,__file__,1,'Bearer ttt-private-token',(),None)
    assert 'ttt-private-token' not in SafeFormatter().format(record)


def test_validated_sandbox_image_uses_owned_artifact_download(analysis_context):
    import importlib.util,io
    from PIL import Image
    from test_upgrade_phase4_artifacts import source
    from app.models import AnalysisRecord
    assert importlib.util.find_spec('app.sandbox.artifacts'), 'Sandbox artifact publisher is missing'
    from app.sandbox.artifacts import persist_images
    client,sessions,_=analysis_context; rid,sid=source(client,sessions)
    stream=io.BytesIO(); Image.new('RGB',(20,10),'white').save(stream,format='PNG')
    with sessions() as db:
        record=db.get(AnalysisRecord,rid)
        rows=persist_images(db,record,'sandbox',[stream.getvalue()],record.dataset_id,record.dataset_version_id)
        aid=rows[0].id
    result=client.get(f'/api/v1/artifacts/{aid}/download')
    assert result.status_code==200 and result.content.startswith(b'\x89PNG')
    preview=client.get(f'/api/v1/artifacts/{aid}/preview').json()['data']
    assert preview['artifact']['type']=='image' and preview['preview']['kind']=='document'
