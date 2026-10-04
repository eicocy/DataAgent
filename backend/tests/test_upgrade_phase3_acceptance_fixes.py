"""Real acceptance regressions; MySQL writes only exact named isolated schemas."""
from datetime import UTC,datetime
from pathlib import Path
from io import BytesIO
import json
import os
import sys
import uuid
import pytest
from sqlalchemy import create_engine,select,text,delete
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from app.models import User,Dataset,DatasetVersion,BackgroundJob,AnalysisSession,AnalysisRecord
from test_analysis_api import analysis_context


def test_upload_first_session_semantics_and_run_submission(analysis_context):
    from docx import Document
    client,sessions,_=analysis_context
    created=client.post('/api/v1/analysis/sessions',json={'title':'upload first'})
    assert created.status_code==201,created.text
    sid=created.json()['data']['id']
    doc=Document();table=doc.add_table(rows=2,cols=2)
    for cell,value in zip([c for row in table.rows for c in row.cells],['region','sales','North','12']):cell.text=value
    output=BytesIO();doc.save(output)
    uploaded=client.post('/api/v1/files/upload',data={'session_id':sid},files={'file':('evidence.docx',output.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
    assert uploaded.status_code==202,uploaded.text
    fid=uploaded.json()['data']['file']['id']
    confirmed=client.post(f'/api/v1/files/{fid}/extractions/1/datasets',json={'confirmed':True,'request_id':'confirm-context','session_id':sid})
    assert confirmed.status_code==202,confirmed.text
    did=confirmed.json()['data']['dataset']['id']
    with sessions() as db:vid=db.get(Dataset,did).current_version_id
    edited=client.patch(f'/api/v1/analysis/sessions/{sid}/semantic-mappings',json={'mappings':[{'column':'sales','concept':'quantity','role':'metric','dataset_version_id':vid}]})
    assert edited.status_code==200,edited.text
    submitted=client.post('/api/v1/analysis/runs',json={'session_id':sid,'dataset_id':did,'question':'分析销量','request_id':'upload-first-run','depth':'STANDARD'})
    assert submitted.status_code==202,submitted.text
    with sessions() as db:
        context=db.get(AnalysisSession,sid).context_json
        assert context['conversation_id']==sid and context['user_id']==db.get(AnalysisSession,sid).user_id
        assert context['uploaded_file_ids']==[fid] and context['attached_dataset_ids']==[did]
        assert context['semantic_mappings'][0]['concept']=='quantity'
        record=db.get(AnalysisRecord,submitted.json()['data']['record_id'])
        assert record.request_config_json['semantic_snapshot'][0]['concept']=='quantity'
    client.post('/api/v1/auth/logout')
    client.post('/api/v1/auth/register',json={'username':'other-owner','password':'safe-password-123'})
    assert client.patch(f'/api/v1/analysis/sessions/{sid}/semantic-mappings',json={'mappings':[{'column':'sales','concept':'quantity','role':'metric','dataset_version_id':vid}]}).status_code==403
    assert client.post('/api/v1/analysis/runs',json={'session_id':sid,'dataset_id':did,'question':'分析销量','request_id':'forbidden'}).status_code==404


@pytest.mark.parametrize('operation',['read_semantics','edit_semantics','submit_run'])
def test_old_partial_context_recovery_preserves_state_and_uses_owner_identity(analysis_context,operation):
    client,sessions,_=analysis_context
    did=client.post('/api/v1/datasets/upload',files={'file':('old.csv',b'sales,cost\n12,5\n','text/csv')}).json()['data']['id']
    sid=client.post('/api/v1/analysis/sessions',json={'dataset_id':did}).json()['data']['id']
    with sessions() as db:
        session=db.get(AnalysisSession,sid);vid=db.get(Dataset,did).current_version_id
        partial={'attached_dataset_ids':[did],'uploaded_file_ids':[501], 'messages_summary':'keep summary',
            'active_filters':[{'column':'sales','value':12}],'semantic_version':7,
            'semantic_mappings':[{'column':'cost','concept':'cost','role':'metric','dataset_version_id':vid,'source':'user','confidence':1.0}],
            'user_preferences':{'theme':'keep'},'legacy_extension':{'keep':True}}
        # Untrusted legacy identity must never be allowed to choose a different
        # user/session, whether missing or wrong in saved JSON.
        if operation=='submit_run':partial.update(conversation_id=999,user_id=999)
        session.context_json=partial;db.commit();uid=session.user_id
    if operation=='read_semantics':
        result=client.get(f'/api/v1/analysis/sessions/{sid}/semantic-mappings')
        assert result.status_code==200,result.text
        assert any(m['column']=='cost' and m['concept']=='cost' for m in result.json()['data']['mappings'])
    elif operation=='edit_semantics':
        result=client.patch(f'/api/v1/analysis/sessions/{sid}/semantic-mappings',json={'mappings':[{'column':'sales','concept':'quantity','role':'metric','dataset_version_id':vid}]})
        assert result.status_code==200,result.text
    else:
        result=client.post('/api/v1/analysis/runs',json={'session_id':sid,'dataset_id':did,'question':'检查数据','request_id':'old-partial','depth':'STANDARD'})
        assert result.status_code==202,result.text
    if operation!='read_semantics':
        with sessions() as db:
            context=db.get(AnalysisSession,sid).context_json
            assert context['conversation_id']==sid and context['user_id']==uid
            assert context['uploaded_file_ids']==[501] and context['messages_summary']=='keep summary'
            assert context['active_filters']==partial['active_filters']
            assert context['user_preferences']==partial['user_preferences']
            assert context['legacy_extension']=={'keep':True}
            assert any(m['column']=='cost' for m in context['semantic_mappings'])


@pytest.mark.parametrize('outcome',['ready','failed','stale_lease'])
def test_fixed_worker_mysql_rr_observes_committed_parse_state(tmp_path,monkeypatch,outcome):
    if os.environ.get('RUN_PHASE3_ISOLATED_MYSQL')!='1':pytest.skip('Explicit isolated MySQL regression switch not enabled')
    from app.config import get_settings
    from app import task_runner
    from app.services.datasets import process_dataset,drop_projection
    settings=get_settings()
    schemas=json.loads((Path(__file__).resolve().parents[2]/'.superpowers/sdd/phase3-v203/mysql-schemas.json').read_text(encoding='utf-8-sig'))
    assert schemas['core']=='datalens_test_phase3_core_20261004_d327abfd'
    assert schemas['projection']=='datalens_test_phase3_projection_20261004_6d29304f'
    core=create_engine(make_url(settings.database_url).set(database=schemas['core']),isolation_level='REPEATABLE READ',hide_parameters=True)
    projection=create_engine(make_url(settings.projection_database_url or settings.database_url).set(database=schemas['projection']),hide_parameters=True)
    factory=sessionmaker(bind=core,expire_on_commit=False)
    identifier=uuid.uuid4().hex;stored=identifier+'.csv';path=tmp_path/stored
    path.write_bytes(b'sales,sales\n12,5\n' if outcome=='failed' else b'sales\n12\n')
    now=datetime.now(UTC)
    with factory() as db:
        assert db.scalar(text('SELECT @@transaction_isolation'))=='REPEATABLE-READ'
        user=User(username='accept-fix-'+identifier[:12],password_hash='unused',status='active',created_at=now,updated_at=now)
        db.add(user);db.flush();uid=user.id
        dataset=Dataset(user_id=uid,original_name='acceptance.csv',stored_name=stored,file_type='csv',file_size=path.stat().st_size,status='parsing',created_at=now,updated_at=now)
        db.add(dataset);db.flush();did=dataset.id
        job=BackgroundJob(kind='parse',resource_id=did,dataset_id=did,user_id=uid,status='running',lease_token='original',created_at=now,
            heartbeat_at=now,started_at=now)
        db.add(job);db.commit();jid=job.id
    opened=[];observed={}
    def tracked_factory():
        db=factory();opened.append(db);return db
    def real_separate_session_parse(*args,**kwargs):
        process_dataset(*args,**kwargs)
        outer=opened[0]
        assert outer.in_transaction()
        observed['old_snapshot']=outer.get(Dataset,did).status
        with factory() as committed:
            observed['committed']=committed.get(Dataset,did).status
            if outcome=='stale_lease':
                current=committed.get(BackgroundJob,jid);current.lease_token='replacement';committed.commit()
    class QuietThread:
        def __init__(self,*args,**kwargs):pass
        def start(self):pass
    monkeypatch.setattr(task_runner,'SessionLocal',tracked_factory)
    monkeypatch.setattr(task_runner,'projection_engine',projection)
    monkeypatch.setattr(task_runner,'process_dataset',real_separate_session_parse)
    monkeypatch.setattr(task_runner.threading,'Thread',QuietThread)
    monkeypatch.setattr(settings,'upload_dir',str(tmp_path))
    monkeypatch.setattr(sys,'argv',['fixed-worker','--job-id',str(jid),'--lease','original','--parent-pid',str(os.getpid())])
    try:
        task_runner.main()
        assert observed['old_snapshot']=='parsing'
        assert observed['committed']==('failed' if outcome=='failed' else 'ready')
        with factory() as db:
            finished=db.get(BackgroundJob,jid)
            if outcome=='stale_lease':
                assert finished.status=='running' and finished.lease_token=='replacement' and finished.completed_at is None
            elif outcome=='failed':
                assert finished.status=='failed' and finished.error_code=='DATASET_DUPLICATE_COLUMNS'
            else:
                assert finished.status=='succeeded' and finished.error_code is None
                assert db.get(Dataset,did).current_version_id is not None
    finally:
        with factory() as db:
            db.execute(delete(BackgroundJob).where(BackgroundJob.id==jid));dataset=db.get(Dataset,did)
            if dataset:dataset.current_version_id=None;db.flush()
            db.execute(delete(DatasetVersion).where(DatasetVersion.dataset_id==did));db.delete(dataset);db.flush();db.execute(delete(User).where(User.id==uid));db.commit()
        drop_projection(did,projection);core.dispose();projection.dispose()
