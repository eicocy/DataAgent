from datetime import UTC, datetime
import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, MetaData, select
from app.config import get_settings


@pytest.mark.parametrize('database', ['sqlite','mysql'])
def test_0011_to_0012_preserves_sources_and_backfills_retention(tmp_path, monkeypatch, database):
    url = 'sqlite:///' + (tmp_path/'migration.db').as_posix()
    if database=='mysql':
        from sqlalchemy.engine import make_url
        url=os.environ.get('TEST_PHASE4_MIGRATION_URL')
        if not url: pytest.skip('Dedicated Phase 4 MySQL schema not configured')
        assert (make_url(url).database or '').startswith('datalens_test_phase4_')
    monkeypatch.setattr(get_settings(), 'migration_database_url', url)
    cfg = Config('alembic.ini')
    command.upgrade(cfg, '0011_workspace_files')
    engine = create_engine(url); meta = MetaData(); meta.reflect(engine)
    now = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    with engine.begin() as conn:
        def add(name, **values): return conn.execute(meta.tables[name].insert().values(**values)).inserted_primary_key[0]
        uid = add('users', username='legacy', password_hash='test', status='active', created_at=now, updated_at=now)
        did = add('datasets', user_id=uid, original_name='x.csv', stored_name='x.csv', file_type='csv', file_size=2, status='ready', created_at=now, updated_at=now)
        sid = add('analysis_sessions', user_id=uid, dataset_id=did, title='keep', status='active', is_pinned=False, created_at=now, updated_at=now)
        rid = add('analysis_records', user_id=uid, dataset_id=did, session_id=sid, request_id='legacy', question='keep', status='succeeded', plan_json={'version':'3.0'}, created_at=now)
        aid = add('analysis_artifacts', record_id=rid, user_id=uid, dataset_id=did, step_id='result', kind='table', stored_name='a'*32+'.json', size_bytes=10, row_count=1, schema_json={}, status='READY', created_at=now, expires_at=now)
        purged = add('analysis_artifacts', record_id=rid, user_id=uid, dataset_id=did, step_id='purged', kind='table', stored_name='b'*32+'.json', size_bytes=10, row_count=1, schema_json={}, status='READY', created_at=now, expires_at=now, purged_at=now)
    command.upgrade(cfg, 'head'); command.upgrade(cfg, 'head')
    meta.clear(); meta.reflect(engine)
    with engine.connect() as conn:
        items = {r['id']:r for r in conn.execute(select(meta.tables['analysis_artifacts'])).mappings()}
        assert items[aid]['session_id'] == sid and items[aid]['expires_at'] is None
        assert items[aid]['retention_class'] == 'final'
        assert items[purged]['purged_at'] == now and items[purged]['expires_at'] == now
        assert conn.execute(select(meta.tables['analysis_records'].c.plan_json)).scalar_one() == {'version':'3.0'}
    assert next(c for c in inspect(engine).get_columns('analysis_artifacts') if c['name']=='expires_at')['nullable']
    engine.dispose()
