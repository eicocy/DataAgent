"""Opt-in real MySQL contracts. Never target an application database.

TEST_MYSQL_URL must point to a disposable, precreated datalens_test_* schema.
TEST_MYSQL_PROJECTION_URL points to a separate dedicated projection schema;
TEST_MYSQL_READONLY_URL is SELECT-only on that projection schema and must have
no business permissions. These tests never create users or schemas.
"""
import os
import re
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError


@pytest.fixture(scope="module")
def mysql_engine():
    raw = os.environ.get("TEST_MYSQL_URL")
    if not raw:
        pytest.skip("TEST_MYSQL_URL not configured; real MySQL not verified")
    url = make_url(raw)
    if url.get_backend_name() != "mysql" or not re.fullmatch(r'datalens_test_[A-Za-z0-9_]+', url.database or ''):
        pytest.fail("Integration tests require a dedicated datalens_test_* MySQL schema")
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True)
    with engine.connect() as connection:
        assert str(connection.scalar(text("SELECT VERSION()"))).startswith("8.")
    yield engine
    engine.dispose()


def test_upgrade_head_and_model_tables(mysql_engine):
    env = dict(os.environ)
    env.update(DATABASE_URL=os.environ["TEST_MYSQL_URL"], MIGRATION_DATABASE_URL=os.environ["TEST_MYSQL_URL"], TASK_EXECUTOR_ENABLED="false")
    def upgrade(revision):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=Path(__file__).parents[2], env=env, capture_output=True, text=True)
        assert result.returncode == 0, f"MySQL upgrade to {revision} failed: {result.stderr[-6000:]}"
    fresh = not inspect(mysql_engine).has_table('alembic_version')
    if fresh:
        upgrade('0001_initial')
    else:
        upgrade('head')
    # Seed before old batch migrations so CI verifies FK recreation and data
    # retention rather than only an empty-schema migration.
    suffix = uuid.uuid4().hex
    with mysql_engine.begin() as connection:
        user_id = connection.execute(text("INSERT INTO users (username,password_hash,created_at,updated_at) VALUES (:name,'testhash',NOW(),NOW())"), {'name': 'migration_' + suffix}).lastrowid
        dataset_id = connection.execute(text("INSERT INTO datasets (user_id,original_name,stored_name,file_type,file_size,created_at,updated_at) VALUES (:user,'contract.csv',:name,'csv',1,NOW(),NOW())"), {'user': user_id, 'name': suffix + '.csv'}).lastrowid
        session_id = connection.execute(text("INSERT INTO analysis_sessions (user_id,dataset_id,created_at,updated_at) VALUES (:user,:dataset,NOW(),NOW())"), {'user': user_id, 'dataset': dataset_id}).lastrowid
        record_id = connection.execute(text("INSERT INTO analysis_records (user_id,dataset_id,session_id,request_id,question,created_at) VALUES (:user,:dataset,:session,:request,'migration evidence',NOW())"), {'user': user_id, 'dataset': dataset_id, 'session': session_id, 'request': suffix}).lastrowid
    try:
        if fresh:
            upgrade('0003_user_message_link')
            upgrade('0007_analysis_engine')
        # On a fresh disposable schema, exercise 0008 with a pinned legacy
        # version and records already present at 0007, not just empty tables.
        with mysql_engine.begin() as connection:
            version_id = connection.execute(text("""INSERT INTO dataset_versions
                (dataset_id,version_number,status,source_kind,projection_table,
                 schema_json,profile_json,transformations_json,original_available,created_at)
                VALUES (:dataset,1,'ready','upload',:table,'{}','{}','[]',1,NOW())"""),
                {'dataset': dataset_id, 'table': 'migration_' + suffix}).lastrowid
            connection.execute(text('UPDATE datasets SET current_version_id=:version WHERE id=:dataset'),
                               {'version': version_id, 'dataset': dataset_id})
            connection.execute(text("UPDATE analysis_records SET dataset_version_id=:version, version_binding='snapshot' WHERE id=:record"),
                               {'version': version_id, 'record': record_id})
        upgrade('head')
        with mysql_engine.connect() as connection:
            assert connection.execute(text('SELECT question,dataset_id,dataset_version_id FROM analysis_records WHERE id=:id'),
                                      {'id': record_id}).one() == ('migration evidence', dataset_id, version_id)
            assert connection.scalar(text('SELECT dataset_id FROM analysis_sessions WHERE id=:id'), {'id': session_id}) == dataset_id
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
        with mysql_engine.begin() as connection:
            free_session = connection.execute(text("""INSERT INTO analysis_sessions
                (user_id,dataset_id,context_json,created_at,updated_at)
                VALUES (:user,NULL,:context,NOW(),NOW())"""),
                {'user': user_id, 'context': '{"preferences":{"language":"zh"}}'}).lastrowid
            free_record = connection.execute(text("""INSERT INTO analysis_records
                (user_id,dataset_id,session_id,request_id,question,created_at)
                VALUES (:user,NULL,:session,:request,'hello',NOW())"""),
                {'user': user_id, 'session': free_session, 'request': 'free_' + suffix}).lastrowid
            connection.execute(text("""INSERT INTO analysis_events
                (record_id,user_id,event_type,payload_json,created_at)
                VALUES (:record,:user,'run_completed','{}',NOW())"""),
                {'record': free_record, 'user': user_id})
            connection.execute(text("""INSERT INTO llm_call_records
                (request_id,record_id,conversation_id,user_id,provider,model,
                 prompt_version,latency_ms,status,created_at)
                VALUES (:request,:record,:session,:user,'deepseek','test',
                        'general_chat.v1',1,'succeeded',NOW())"""),
                {'request': 'free_' + suffix, 'record': free_record,
                 'session': free_session, 'user': user_id})
            assert connection.scalar(text('SELECT dataset_id FROM analysis_sessions WHERE id=:id'), {'id': free_session}) is None
            assert connection.scalar(text('SELECT COUNT(*) FROM analysis_events WHERE record_id=:record'), {'record': free_record}) == 1
            assert connection.scalar(text('SELECT conversation_id FROM llm_call_records WHERE record_id=:record'), {'record': free_record}) == free_session
    finally:
        with mysql_engine.begin() as connection:
            connection.execute(text('DELETE FROM users WHERE id=:id'), {'id': user_id})
    from app.database import Base
    from app import models  # noqa: F401
    actual = set(inspect(mysql_engine).get_table_names())
    assert set(Base.metadata.tables).issubset(actual)
    assert "alembic_version" in actual
    inspector = inspect(mysql_engine)
    assert next(c for c in inspector.get_columns('analysis_sessions') if c['name'] == 'dataset_id')['nullable']
    assert next(c for c in inspector.get_columns('analysis_records') if c['name'] == 'dataset_id')['nullable']
    assert next(c for c in inspector.get_columns('background_jobs') if c['name'] == 'cancel_requested')['default'] is not None


def test_mysql_date_decimal_json_and_identifier_contract(mysql_engine):
    from app.services.datasets import safe_column_names
    column = safe_column_names(["x" * 120])[0]
    assert len(column) <= 64
    table = "contract_" + uuid.uuid4().hex
    try:
        with mysql_engine.begin() as connection:
            connection.execute(text(f"CREATE TABLE `{table}` (`{column}` DATE, amount DECIMAL(12,2), payload JSON)"))
            connection.execute(text(f"INSERT INTO `{table}` VALUES (:day, :amount, :payload)"), {"day": "2026-06-01", "amount": "12.34", "payload": '{"value": null}'})
            row = connection.execute(text(f"SELECT * FROM `{table}`")).one()
            assert row[0].isoformat() == "2026-06-01"
            assert str(row[1]) == "12.34"
    finally:
        with mysql_engine.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))


def test_optional_readonly_account_cannot_write(mysql_engine):
    raw = os.environ.get("TEST_MYSQL_READONLY_URL")
    writer_raw = os.environ.get('TEST_MYSQL_PROJECTION_URL')
    if not raw or not writer_raw:
        pytest.skip("Projection writer/read-only URLs absent; account privileges not verified")
    url = make_url(raw)
    writer_url = make_url(writer_raw)
    admin_url = mysql_engine.url
    if any(candidate.get_backend_name() != 'mysql' or not re.fullmatch(r'datalens_test_[A-Za-z0-9_]+', candidate.database or '') for candidate in (url, writer_url)):
        pytest.fail('Projection URLs must target dedicated datalens_test_* MySQL schemas')
    if (url.host, url.port, url.database) != (writer_url.host, writer_url.port, writer_url.database) or url.database == admin_url.database or (url.host, url.port) != (admin_url.host, admin_url.port):
        pytest.fail("Reader and writer must share a separate projection schema on the same test server")
    assert inspect(mysql_engine).has_table('users'), 'Business users table must exist before permission verification'
    table = "permissions_" + uuid.uuid4().hex
    readonly = create_engine(url, hide_parameters=True)
    writer = create_engine(writer_url, hide_parameters=True)
    try:
        with writer.begin() as connection:
            connection.execute(text(f"CREATE TABLE `{table}` (value INTEGER)"))
            connection.execute(text(f"INSERT INTO `{table}` VALUES (7)"))
        with readonly.connect() as connection:
            assert connection.scalar(text(f"SELECT value FROM `{table}`")) == 7
            with pytest.raises(DBAPIError) as write_denied:
                connection.execute(text(f"INSERT INTO `{table}` VALUES (8)"))
            assert write_denied.value.orig.args[0] in {1044, 1142, 1143}
            # Prove the second security boundary independently of SQL AST.
            with pytest.raises(DBAPIError) as business_denied:
                connection.execute(text(f"SELECT password_hash FROM `{admin_url.database}`.users LIMIT 1"))
            assert business_denied.value.orig.args[0] in {1044, 1142, 1143}
    finally:
        readonly.dispose()
        with writer.begin() as connection:
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        writer.dispose()


def test_mysql_concurrent_transform_publication(mysql_engine,tmp_path,monkeypatch):
    """Two real connections race on one source version; only one may publish."""
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC,datetime
    from sqlalchemy.orm import Session
    from sqlalchemy import select,Table,MetaData
    import pandas as pd
    from app.models import User,Dataset,DatasetVersion,ToolExecutionRecord,CleanupTask
    from app.config import get_settings
    from app.services.datasets import write_projection,profile_frame
    from app.datasets.versions import create_initial_version
    from app.services.tool_execution import ToolExecutionService
    from app.analysis.models import ToolExecutionRequest,Permission
    from app.services.jobs import perform_cleanup
    monkeypatch.setattr(get_settings(),'artifact_dir',str(tmp_path/'artifacts'))
    now=datetime.now(UTC);suffix=uuid.uuid4().hex
    frame=pd.DataFrame({'measure':pd.array([1,None,3],dtype='Int64')})
    user_id=dataset_id=None
    try:
        with Session(mysql_engine) as db:
            user=User(username='race_'+suffix,password_hash='testhash',created_at=now,updated_at=now);db.add(user);db.flush();user_id=user.id
            dataset=Dataset(user_id=user.id,original_name='race.csv',stored_name=suffix+'.csv',file_type='csv',file_size=10,row_count=3,column_count=1,status='ready',created_at=now,updated_at=now)
            db.add(dataset);db.commit();dataset_id=dataset.id
            dataset.projection_table=write_projection(frame,dataset.id,mysql_engine);dataset.projection_schema=mysql_engine.url.database
            db.add_all(profile_frame(frame,dataset.id));create_initial_version(db,dataset,frame,tmp_path);db.commit()
            service=ToolExecutionService(db,mysql_engine,mysql_engine)
            grants=frozenset({Permission.READ_DATA,Permission.TRANSFORM_DATA})
            ids=[]
            for index in range(2):
                record,_=service.submit(user.id,ToolExecutionRequest(tool_name='fill_missing_values',dataset_id=dataset.id,parameters={'columns':['measure'],'value':index},request_id='race-'+str(index)),grants)
                ids.append(record.id)
        def execute(identifier):
            with Session(mysql_engine) as db:
                ToolExecutionService(db,mysql_engine,mysql_engine).execute(identifier)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(execute,ids))
        with Session(mysql_engine) as db:
            records=[db.get(ToolExecutionRecord,identifier) for identifier in ids]
            assert sorted(record.status for record in records)==['failed','succeeded']
            assert next(record for record in records if record.status=='failed').error_json['code']=='DATASET_VERSION_CONFLICT'
            assert len(list(db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id==dataset_id))))==2
            for task in db.scalars(select(CleanupTask).where(CleanupTask.status=='pending')):
                if task.payload_json.get('tool_execution_id') in ids:perform_cleanup(db,task,mysql_engine,mysql_engine)
    finally:
        if dataset_id:
            with Session(mysql_engine) as db:
                projections=list(db.scalars(select(DatasetVersion.projection_table).where(DatasetVersion.dataset_id==dataset_id)))
                projections+=list(db.scalars(select(ToolExecutionRecord.staging_projection).where(ToolExecutionRecord.dataset_id==dataset_id,ToolExecutionRecord.staging_projection.is_not(None))))
            for name in set(projections):
                if inspect(mysql_engine).has_table(name):Table(name,MetaData(),autoload_with=mysql_engine).drop(mysql_engine)
        if user_id:
            with mysql_engine.begin() as connection:connection.execute(text('DELETE FROM users WHERE id=:id'),{'id':user_id})
