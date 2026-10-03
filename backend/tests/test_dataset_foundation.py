import pandas as pd

def test_profile_is_structured_finite_and_model_summary_has_no_values():
    from app.datasets.profiler import build_profile, model_summary
    frame = pd.DataFrame({'编号': ['001', '002'], 'measure': [1.0, float('inf')], 'blank': [None, None]})
    schema, profile = build_profile(frame)
    assert schema.columns[0].semantic_type == 'Identifier'
    assert profile.columns[1].non_finite_count == 1
    assert profile.columns[1].numeric.valid_count == 1
    assert profile.columns[2].numeric is None
    assert '001' not in str(model_summary(schema, profile))
    profile.model_dump_json()

def test_profile_integer_identifier_and_renamed_measure():
    from app.datasets.profiler import build_profile
    frame = pd.DataFrame({'entity_id': [101, 102], 'arbitrary': [10.0, 20.0]})
    schema, profile = build_profile(frame)
    assert schema.columns[0].role == 'Identifier'
    assert schema.columns[1].role == 'Metric'
    assert profile.columns[1].numeric.mean == 15

def test_0005_upgrade_and_repeat_backfill_preserve_projection(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session
    from datetime import UTC, datetime
    from app.models import Dataset, User, DatasetColumn, DatasetVersion, AnalysisRecord, AnalysisSession
    from app.datasets.versions import backfill_dataset
    target = tmp_path / 'upgrade.db'
    config = Config('alembic.ini')
    config.set_main_option('sqlalchemy.url', f'sqlite:///{target.as_posix()}')
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), 'migration_database_url', f'sqlite:///{target.as_posix()}')
    command.upgrade(config, '0005_projection_metadata')
    command.upgrade(config, 'head')
    engine = create_engine(f'sqlite:///{target.as_posix()}')
    assert 'dataset_versions' in inspect(engine).get_table_names()
    now = datetime.now(UTC)
    with Session(engine) as db:
        user = User(username='legacy', password_hash='unused', created_at=now, updated_at=now)
        db.add(user); db.flush()
        dataset = Dataset(user_id=user.id, original_name='old.csv', stored_name='missing.csv', file_type='csv', file_size=12, row_count=2, column_count=1, status='ready', created_at=now, updated_at=now)
        db.add(dataset); db.flush()
        db.add(DatasetColumn(dataset_id=dataset.id, ordinal_position=0, name='value', original_name='Value', data_type='integer', nullable=False, missing_count=0, unique_count=2, sample_values_json=[], created_at=now)); db.commit()
        pd.DataFrame({'value': [10, 20]}).to_sql(f'dataset_{dataset.id}', engine, index=False)
        assert backfill_dataset(db, dataset, engine, tmp_path)['status'] == 'would_backfill'
        assert db.query(DatasetVersion).count() == 0
        session = AnalysisSession(user_id=user.id, dataset_id=dataset.id, title='legacy', created_at=now, updated_at=now)
        db.add(session); db.flush()
        record = AnalysisRecord(user_id=user.id, dataset_id=dataset.id, session_id=session.id, request_id='legacy', question='old question', status='success', created_at=now)
        db.add(record); db.commit()
        assert backfill_dataset(db, dataset, engine, tmp_path, apply=True)['status'] == 'backfilled'
        assert record.dataset_version_id == dataset.current_version_id
        assert record.version_binding == 'legacy_association'
        assert backfill_dataset(db, dataset, engine, tmp_path, apply=True)['status'] == 'already_versioned'
        assert db.query(DatasetVersion).count() == 1
        version = db.get(DatasetVersion, dataset.current_version_id)
        assert not version.original_available
        assert version.schema_json['columns'][0]['original_name'] == 'Value'
        assert pd.read_sql_table(f'dataset_{dataset.id}', engine)['value'].tolist() == [10, 20]

def test_parser_respects_configured_row_and_column_limits(tmp_path, monkeypatch):
    import pytest
    from app.config import get_settings
    from app.services.datasets import DatasetParseError, parse_file
    path = tmp_path / 'bounded.csv'
    path.write_text('a,b\n1,2\n3,4\n', encoding='utf-8')
    monkeypatch.setattr(get_settings(), 'max_dataset_rows', 1)
    with pytest.raises(DatasetParseError) as raised:
        parse_file(path, 'csv')
    assert raised.value.code == 'DATASET_TOO_MANY_ROWS'
    monkeypatch.setattr(get_settings(), 'max_dataset_rows', 10)
    monkeypatch.setattr(get_settings(), 'max_dataset_columns', 1)
    with pytest.raises(DatasetParseError) as raised:
        parse_file(path, 'csv')
    assert raised.value.code == 'DATASET_TOO_MANY_COLUMNS'

def test_migration_preserves_existing_0005_rows_and_can_downgrade(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text, inspect
    from app.config import get_settings
    target = tmp_path / 'existing.db'
    url = f'sqlite:///{target.as_posix()}'
    monkeypatch.setattr(get_settings(), 'migration_database_url', url)
    config = Config('alembic.ini')
    command.upgrade(config, '0005_projection_metadata')
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO users (id,username,password_hash,status,created_at,updated_at) VALUES (1,'old','hash','active','2026-01-01','2026-01-01')"))
        connection.execute(text("INSERT INTO datasets (id,user_id,original_name,stored_name,file_type,file_size,status,created_at,updated_at) VALUES (1,1,'old.csv','server.csv','csv',9,'ready','2026-01-01','2026-01-01')"))
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT original_name FROM datasets WHERE id=1')) == 'old.csv'
        assert connection.scalar(text('SELECT current_version_id FROM datasets WHERE id=1')) is None
    command.downgrade(config, '0005_projection_metadata')
    assert 'dataset_versions' not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM datasets')) == 1
    command.upgrade(config, 'head')


def test_profile_constant_blank_datetime_and_overflow_statistics():
    from app.datasets.profiler import build_profile
    frame = pd.DataFrame({'constant': [1.0, 1.0], 'huge': [1e308, 1e308], 'day': pd.to_datetime(['2026-01-01', '2026-01-02']), 'empty': [None, None]})
    schema, profile = build_profile(frame)
    assert profile.columns[0].numeric.std == 0
    assert profile.columns[1].numeric.status == 'overflow'
    assert schema.columns[2].role == 'TimeDimension'
    assert schema.columns[3].semantic_type == 'Unknown'
    profile.model_dump_json()
