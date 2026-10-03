"""Disposable database, real HTTP process and trusted worker entry smoke checks."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
from datetime import UTC,datetime
from sqlalchemy import create_engine,select,text
from sqlalchemy.orm import Session


def test_isolated_http_readiness_and_tool_worker(tmp_path):
    from app.models import User,Dataset,BackgroundJob,ToolExecutionRecord
    from app.services.datasets import parse_file,write_projection,profile_frame
    from app.datasets.versions import create_initial_version
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest
    url=f'sqlite:///{(tmp_path/"runtime.db").as_posix()}'
    env=dict(os.environ,DATABASE_URL=url,PROJECTION_DATABASE_URL=url,MIGRATION_DATABASE_URL=url,SQL_READONLY_DATABASE_URL='',DEEPSEEK_API_KEY='',APP_ENV='test',TASK_EXECUTOR_ENABLED='false',UPLOAD_DIR=str(tmp_path/'uploads'),ARTIFACT_DIR=str(tmp_path/'artifacts'))
    upgraded=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],env=env,capture_output=True,text=True,timeout=30)
    assert upgraded.returncode==0,upgraded.stderr[-2000:]
    engine=create_engine(url)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    log=tmp_path/'server.log'
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        try:
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                try:
                    with urlopen(f'http://127.0.0.1:{port}/health/ready',timeout=1) as response:ready=json.load(response)
                    break
                except OSError:
                    assert process.poll() is None,log.read_text(encoding='utf-8')[-2000:]
                    time.sleep(.1)
            else:raise AssertionError('HTTP startup timed out')
            assert ready=={'status':'ready','model_configured':False}
            with urlopen(f'http://127.0.0.1:{port}/health/live') as response:assert json.load(response)['status']=='ok'
        finally:
            process.terminate();process.wait(timeout=10)
    now=datetime.now(UTC)
    source=tmp_path/'accepted.csv';source.write_text('x\n10\n20\n',encoding='utf-8');frame=parse_file(source,'csv')
    with Session(engine) as db:
        user=User(username='worker-test',password_hash='unused',created_at=now,updated_at=now);db.add(user);db.flush()
        dataset=Dataset(user_id=user.id,original_name='accepted.csv',stored_name='accepted.csv',file_type='csv',file_size=10,row_count=2,column_count=1,status='ready',created_at=now,updated_at=now)
        db.add(dataset);db.commit();dataset.projection_table=write_projection(frame,dataset.id,engine)
        dataset.projection_schema=engine.url.database
        db.add_all(profile_frame(frame,dataset.id));create_initial_version(db,dataset,frame,tmp_path);db.commit()
        service=ToolExecutionService(db,engine,engine)
        record,_=service.submit(user.id,ToolExecutionRequest(tool_name='aggregate',dataset_id=dataset.id,parameters={'metrics':[{'column':'x','aggregation':'sum'}]},request_id='trusted-process'))
        identifier=record.id
        job=db.scalar(select(BackgroundJob).where(BackgroundJob.kind=='tool',BackgroundJob.resource_id==identifier))
        job.status='running';job.lease_token='runtime-token';job.started_at=now;job.heartbeat_at=now;db.commit();job_id=job.id
    child=subprocess.run([sys.executable,'-m','app.task_runner','--job-id',str(job_id),'--lease','runtime-token','--parent-pid',str(os.getpid())],env=env,capture_output=True,text=True,timeout=25)
    assert child.returncode in (0,70),child.stderr[-2000:]
    with Session(engine) as db:
        record=db.get(ToolExecutionRecord,identifier)
        assert record.status=='succeeded',record.error_json
        assert record.result_json['data']['rows']==[{'x_sum':30}]
        assert record.result_json['artifact_ref']
        assert db.get(BackgroundJob,job_id).completed_at is not None
        from alembic.script import ScriptDirectory
        from alembic.config import Config
        assert db.scalar(text('SELECT version_num FROM alembic_version'))==ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
    engine.dispose()
