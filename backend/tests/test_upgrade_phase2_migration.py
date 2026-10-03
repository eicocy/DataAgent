from datetime import datetime, UTC
import os
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, MetaData, insert, select, inspect
from app.config import get_settings


@pytest.mark.parametrize('database', ['sqlite', 'mysql'])
def test_upgrade_0009_preserves_historical_plan_and_session(tmp_path, monkeypatch, database):
    url = 'sqlite:///' + (tmp_path / 'migration.db').as_posix()
    if database == 'mysql':
        from sqlalchemy.engine import make_url
        url = os.environ.get('TEST_PHASE2_MIGRATION_URL')
        if not url:
            pytest.skip('Dedicated Phase 2 MySQL migration schema not configured')
        if not (make_url(url).database or '').startswith('datalens_test_phase2_'):
            pytest.fail('Refusing a non-test migration database')
    monkeypatch.setattr(get_settings(), 'migration_database_url', url)
    command.upgrade(Config('alembic.ini'), '0009_workspace_reports')
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(engine)
    now = datetime.now(UTC)
    old_plan = {'version': '2.0', 'steps': [{'step_id': 'legacy', 'status': 'COMPLETED'}]}
    with engine.begin() as connection:
        uid = connection.execute(insert(metadata.tables['users']).values(username='legacy', password_hash='unused', status='active', created_at=now, updated_at=now)).inserted_primary_key[0]
        sid = connection.execute(insert(metadata.tables['analysis_sessions']).values(user_id=uid, title='keep', status='active', context_json={'attached_dataset_ids': [], 'messages_summary': 'keep'}, created_at=now, updated_at=now)).inserted_primary_key[0]
        rid = connection.execute(insert(metadata.tables['analysis_records']).values(user_id=uid, session_id=sid, request_id='legacy', question='keep', status='succeeded', plan_json=old_plan, created_at=now)).inserted_primary_key[0]
    command.upgrade(Config('alembic.ini'), 'head')
    metadata.clear()
    metadata.reflect(engine)
    assert 'analysis_profiles' in inspect(engine).get_table_names()
    with engine.connect() as connection:
        record = connection.execute(select(metadata.tables['analysis_records']).where(metadata.tables['analysis_records'].c.id == rid)).mappings().one()
        assert record['plan_json'] == old_plan
        assert record['request_config_json'] is None
        assert connection.execute(select(metadata.tables['analysis_sessions'].c.title).where(metadata.tables['analysis_sessions'].c.id == sid)).scalar_one() == 'keep'
    from app.profiles.service import ProfileService
    from sqlalchemy.orm import Session
    with Session(engine) as db:
        service = ProfileService(db)
        service.seed()
        db.commit()
        service.seed()
        db.commit()
        assert len(service.catalog()['items']) == 105
    engine.dispose()
