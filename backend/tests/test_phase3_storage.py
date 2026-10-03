from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from app.config import get_settings


def test_0008_migration_supports_dataset_free_sessions_and_durable_events(tmp_path, monkeypatch):
    url = f'sqlite:///{(tmp_path / "phase3.db").as_posix()}'
    monkeypatch.setattr(get_settings(), 'migration_database_url', url)
    command.upgrade(Config('alembic.ini'), 'head')
    engine = create_engine(url)
    inspector = inspect(engine)
    session_columns = {column['name']: column for column in inspector.get_columns('analysis_sessions')}
    record_columns = {column['name']: column for column in inspector.get_columns('analysis_records')}
    assert session_columns['dataset_id']['nullable']
    assert record_columns['dataset_id']['nullable']
    assert 'context_json' in session_columns
    assert 'analysis_events' in inspector.get_table_names()
    assert 'llm_call_records' in inspector.get_table_names()
    assert 'conversation_id' in {column['name'] for column in inspector.get_columns('llm_call_records')}
    assert 'cancel_requested' in {column['name'] for column in inspector.get_columns('background_jobs')}
    engine.dispose()


def test_0007_to_0008_preserves_existing_session_and_run(tmp_path, monkeypatch):
    url = f'sqlite:///{(tmp_path / "upgrade.db").as_posix()}'
    monkeypatch.setattr(get_settings(), 'migration_database_url', url)
    config = Config('alembic.ini')
    command.upgrade(config, '0007_analysis_engine')
    engine = create_engine(url)
    now = '2026-10-03 00:00:00'
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id, username, password_hash, status, created_at, updated_at) VALUES (1, 'owner', 'hash', 'active', :now, :now)"), {'now': now})
        connection.execute(text("INSERT INTO datasets (id, user_id, original_name, stored_name, file_type, file_size, status, created_at, updated_at) VALUES (1, 1, 'old.csv', 'stored.csv', 'csv', 10, 'ready', :now, :now)"), {'now': now})
        connection.execute(text("INSERT INTO analysis_sessions (id, user_id, dataset_id, title, status, created_at, updated_at) VALUES (1, 1, 1, '旧会话', 'active', :now, :now)"), {'now': now})
        connection.execute(text("INSERT INTO analysis_records (id, user_id, dataset_id, session_id, request_id, question, status, created_at) VALUES (1, 1, 1, 1, 'legacy', '旧分析', 'succeeded', :now)"), {'now': now})
    command.upgrade(config, 'head')
    with engine.begin() as connection:
        assert connection.execute(text('SELECT dataset_id, title FROM analysis_sessions WHERE id = 1')).one() == (1, '旧会话')
        assert connection.execute(text('SELECT dataset_id, question FROM analysis_records WHERE id = 1')).one() == (1, '旧分析')
        connection.execute(text("INSERT INTO analysis_sessions (id, user_id, dataset_id, title, status, created_at, updated_at) VALUES (2, 1, NULL, '无数据集', 'active', :now, :now)"), {'now': now})
        assert connection.execute(text('SELECT dataset_id FROM analysis_sessions WHERE id = 2')).scalar_one() is None
    engine.dispose()
