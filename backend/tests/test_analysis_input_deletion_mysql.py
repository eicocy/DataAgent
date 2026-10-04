"""Opt-in DB admission race proof; only the exact worker-free migration manifest."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, delete, event, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.models import AnalysisRecord, AnalysisSession, BackgroundJob, CleanupTask, Dataset, DatasetVersion, ToolExecutionRecord, User
from app.routers.analysis import AnalysisChatRequest


@pytest.mark.parametrize('first_operation',['submit','delete','worker','right_publisher'])
def test_mysql_rr_admission_delete_orders_ignore_old_snapshot(monkeypatch,first_operation):
    if os.environ.get('RUN_PHASE3_ISOLATED_MYSQL')!='1':
        pytest.skip('Explicit isolated MySQL switch not enabled')
    from app.config import get_settings
    from app.services import analysis, jobs
    from app.routers.datasets import delete_dataset
    names=json.loads((Path(__file__).resolve().parents[2]/'.superpowers/sdd/phase3-v203/mysql-schemas.json').read_text(encoding='utf-8-sig'))
    target='datalens_test_phase3_migration_20261004_0d1db4d8'
    assert names['migration']==target
    settings=get_settings()
    url=make_url(settings.database_url)
    assert url.get_backend_name()=='mysql' and url.database==target
    assert not settings.deepseek_api_key and not settings.openai_api_key
    assert not settings.task_executor_enabled
    engine=create_engine(url,hide_parameters=True,isolation_level='REPEATABLE READ',pool_pre_ping=True)
    sessions=sessionmaker(bind=engine,expire_on_commit=False)
    # Emulate independent server processes: DB mutex, not Python RLock, must win.
    monkeypatch.setattr(analysis,'resource_lock',nullcontext())
    monkeypatch.setattr(jobs,'perform_cleanup',lambda *args:None)
    now=datetime.now(UTC);suffix=uuid.uuid4().hex
    with sessions() as db:
        assert db.scalar(text('SELECT @@transaction_isolation'))=='REPEATABLE-READ'
        user=User(username='delete-race-'+suffix[:16],password_hash='unused',status='active',created_at=now,updated_at=now)
        db.add(user);db.flush();uid=user.id
        ids=[];versions=[]
        for label in ['left','right']:
            dataset=Dataset(user_id=uid,original_name=label+'.csv',stored_name=suffix+label+'.csv',file_type='csv',file_size=1,status='ready',created_at=now,updated_at=now)
            db.add(dataset);db.flush();ids.append(dataset.id)
            version=DatasetVersion(dataset_id=dataset.id,version_number=1,status='ready',source_kind='upload',projection_table=f'dataset_{dataset.id}',schema_json={'columns':[{'name':'id','storage_type':'integer'}]},profile_json={'row_count':1},transformations_json=[],original_available=True,created_at=now)
            db.add(version);db.flush();versions.append(version.id);dataset.current_version_id=version.id
        session=AnalysisSession(user_id=uid,dataset_id=ids[0],title='simulated lock test',status='active',created_at=now,updated_at=now)
        db.add(session);db.commit();sid=session.id
        if first_operation in {'worker','right_publisher'}:
            resource_id=0
            if first_operation=='right_publisher':
                execution=ToolExecutionRecord(user_id=uid,dataset_id=ids[0],dataset_version_id=versions[0],tool_name='publish_join',tool_version='3.0',request_id=suffix,parameters_json={'right_dataset_id':ids[1],'right_version_id':versions[1]},status='running',permissions_json=[],created_at=now)
                db.add(execution);db.flush();resource_id=execution.id;tid=execution.id
            job=BackgroundJob(kind='tool',resource_id=resource_id,dataset_id=ids[0] if first_operation=='right_publisher' else ids[1],user_id=uid,status='running',lease_token='simulated',created_at=now)
            db.add(job);db.commit();jid=job.id
    request=AnalysisChatRequest(session_id=sid,dataset_id=ids[0],question='simulated join',request_id=suffix,depth='STANDARD',inputs=[{'alias':alias,'dataset_id':did,'dataset_version_id':vid} for alias,did,vid in zip(['primary','right'],ids,versions)])
    old_snapshot=threading.Event();locked=threading.Event();attempted=threading.Event();release=threading.Event()
    thread_role=threading.local();delete_locks=[]
    def before_cursor(connection,cursor,statement,parameters,context,many):
        if getattr(thread_role,'role',None)=='second' and 'FOR UPDATE' in statement:
            delete_locks.append(statement)
        mutex_table='FROM background_jobs' if first_operation in {'worker','right_publisher'} else 'FROM users'
        if mutex_table in statement and 'FOR UPDATE' in statement and getattr(thread_role,'role',None)=='second':
            attempted.set()
    def after_cursor(connection,cursor,statement,parameters,context,many):
        mutex_table='FROM datasets' if first_operation=='right_publisher' else ('FROM background_jobs' if first_operation=='worker' else 'FROM users')
        if mutex_table in statement and 'FOR UPDATE' in statement and getattr(thread_role,'role',None)=='first':
            locked.set()
            assert release.wait(10),'test failed to release first DB mutex'
    event.listen(engine,'before_cursor_execute',before_cursor)
    event.listen(engine,'after_cursor_execute',after_cursor)
    def operate(which,role):
        thread_role.role=role
        with sessions() as db:
            user=db.get(User,uid)
            if role=='second':
                # Authentication/cache plus a genuine RR consistent snapshot
                # predates the winning operation's eventual commit.
                assert db.get(Dataset,ids[1]) is not None
                assert not list(db.scalars(select(AnalysisRecord).where(AnalysisRecord.user_id==uid)))
                old_snapshot.set();assert locked.wait(10)
            else:
                assert old_snapshot.wait(10)
            try:
                if which in {'worker','right_publisher'}:
                    # Production ToolExecutionService.execute.check()/publish()
                    # retain lease Job lock while subsequently locking Dataset.
                    db.scalar(select(BackgroundJob).where(BackgroundJob.id==jid).with_for_update())
                    db.scalar(select(Dataset).where(Dataset.id==ids[1]).with_for_update())
                    if which=='right_publisher':
                        # Final worker result update occurs while Dataset locks
                        # remain held; deletion must reject before Dataset lock.
                        execution=db.scalar(select(ToolExecutionRecord).where(ToolExecutionRecord.id==tid).with_for_update())
                        assert execution.status=='running'
                    db.commit()
                    return ('worker_published',None)
                if which=='submit':
                    record,created=analysis.submit_analysis(db,uid,request)
                    assert created
                    return ('submitted',record.id)
                delete_dataset(ids[1],user,db)
                return ('deleted',None)
            except HTTPException as exc:
                assert not db.in_transaction(),'failed operation must release its mutex'
                return (exc.status_code,exc.detail['code'])
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            second=pool.submit(operate,'delete' if first_operation in {'submit','worker','right_publisher'} else 'submit','second')
            first=pool.submit(operate,first_operation,'first')
            try:
                assert locked.wait(10) and attempted.wait(10)
                assert not second.done(),'second operation bypassed database owner lock'
            finally:
                release.set()
            first_result=first.result(timeout=15);second_result=second.result(timeout=15)
        with sessions() as db:
            records=list(db.scalars(select(AnalysisRecord).where(AnalysisRecord.user_id==uid)))
            if first_operation in {'worker','right_publisher'}:
                assert first_result[0]=='worker_published'
                assert second_result==(409,'DATASET_BUSY')
                assert db.get(Dataset,ids[1]) is not None and not records
                if first_operation=='right_publisher':
                    assert any('FROM tool_execution_records' in query for query in delete_locks)
                    assert not any('FROM datasets' in query for query in delete_locks)
            elif first_operation=='submit':
                assert first_result[0]=='submitted'
                assert second_result==(409,'DATASET_BUSY')
                assert db.get(Dataset,ids[1]) is not None and db.get(DatasetVersion,versions[1]) is not None
                assert len(records)==1 and records[0].status=='pending'
            else:
                assert first_result[0]=='deleted'
                assert second_result==(403,'DATASET_FORBIDDEN')
                assert db.get(Dataset,ids[1]) is None and not records
    finally:
        release.set()
        event.remove(engine,'before_cursor_execute',before_cursor)
        event.remove(engine,'after_cursor_execute',after_cursor)
        with sessions() as db:
            # Exact synthetic owner only. Never truncate/reset global evidence.
            db.execute(delete(BackgroundJob).where(BackgroundJob.user_id==uid))
            db.execute(delete(ToolExecutionRecord).where(ToolExecutionRecord.user_id==uid))
            db.execute(delete(CleanupTask).where(CleanupTask.payload_json['dataset_id'].as_integer().in_(ids)))
            db.execute(delete(AnalysisRecord).where(AnalysisRecord.user_id==uid))
            db.execute(delete(AnalysisSession).where(AnalysisSession.user_id==uid))
            for dataset in db.scalars(select(Dataset).where(Dataset.user_id==uid)):
                dataset.current_version_id=None
            db.flush()
            db.execute(delete(DatasetVersion).where(DatasetVersion.dataset_id.in_(ids)))
            db.execute(delete(Dataset).where(Dataset.user_id==uid))
            db.execute(delete(User).where(User.id==uid));db.commit()
        engine.dispose()
