from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, create_engine, inspect, insert, select, update
from datetime import UTC, datetime, timedelta

from app.config import get_settings


def test_0009_adds_report_versions_and_extends_existing_artifacts(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'reports.db').as_posix()}"
    monkeypatch.setattr(get_settings(), "migration_database_url", url)

    command.upgrade(Config("alembic.ini"), "head")

    inspector = inspect(create_engine(url))
    assert {"analysis_reports", "analysis_report_versions"} <= set(inspector.get_table_names())
    assert "is_pinned" in {column["name"] for column in inspector.get_columns("analysis_sessions")}
    assert "task_payload_json" in {column["name"] for column in inspector.get_columns("background_jobs")}
    artifact_columns = {column["name"]: column for column in inspector.get_columns("analysis_artifacts")}
    assert {"storage_key", "file_name", "mime_type", "status", "metadata_json", "report_version_id"} <= set(artifact_columns)
    assert "parse_options_json" in {column["name"] for column in inspector.get_columns("datasets")}
    checks = {item["name"] for item in inspector.get_check_constraints("analysis_artifacts")}
    assert "ck_artifact_owner" in checks


def test_0008_to_0009_preserves_existing_session_run_version_and_json_artifact(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'legacy-reports.db').as_posix()}"
    monkeypatch.setattr(get_settings(), "migration_database_url", url)
    command.upgrade(Config("alembic.ini"), "0008_agent_orchestration")
    engine = create_engine(url)
    metadata = MetaData()
    metadata.reflect(engine)
    now = datetime.now(UTC).replace(tzinfo=None)
    with engine.begin() as connection:
        user_id = connection.execute(insert(metadata.tables["users"]).values(
            username="legacy-user", password_hash="not-a-real-login", status="active",
            created_at=now, updated_at=now)).inserted_primary_key[0]
        dataset_id = connection.execute(insert(metadata.tables["datasets"]).values(
            user_id=user_id, original_name="legacy.csv", stored_name="a" * 32 + ".csv",
            file_type="csv", file_size=10, row_count=1, column_count=1, status="ready",
            created_at=now, updated_at=now)).inserted_primary_key[0]
        version_id = connection.execute(insert(metadata.tables["dataset_versions"]).values(
            dataset_id=dataset_id, version_number=1, status="ready", source_kind="upload",
            projection_table=f"dataset_{dataset_id}", schema_json={"columns": ["sales"]},
            profile_json={}, transformations_json=[], original_available=True, created_at=now)).inserted_primary_key[0]
        session_id = connection.execute(insert(metadata.tables["analysis_sessions"]).values(
            user_id=user_id, dataset_id=dataset_id, title="legacy session", status="active",
            created_at=now, updated_at=now)).inserted_primary_key[0]
        record_id = connection.execute(insert(metadata.tables["analysis_records"]).values(
            user_id=user_id, dataset_id=dataset_id, session_id=session_id,
            dataset_version_id=version_id, request_id="legacy-run", question="legacy question",
            status="succeeded", created_at=now)).inserted_primary_key[0]
        artifact_id = connection.execute(insert(metadata.tables["analysis_artifacts"]).values(
            record_id=record_id, user_id=user_id, dataset_id=dataset_id, step_id="step_1",
            kind="table", stored_name="b" * 32 + ".json", size_bytes=16, row_count=1,
            schema_json={"columns": ["sales"]}, created_at=now, expires_at=now + timedelta(days=7))).inserted_primary_key[0]
        connection.execute(update(metadata.tables["datasets"]).where(
            metadata.tables["datasets"].c.id == dataset_id).values(current_version_id=version_id))

    command.upgrade(Config("alembic.ini"), "0009_workspace_reports")
    metadata.clear()
    metadata.reflect(engine)
    with engine.connect() as connection:
        assert connection.execute(select(metadata.tables["analysis_sessions"].c.title).where(
            metadata.tables["analysis_sessions"].c.id == session_id)).scalar_one() == "legacy session"
        assert connection.execute(select(metadata.tables["analysis_records"].c.request_id).where(
            metadata.tables["analysis_records"].c.id == record_id)).scalar_one() == "legacy-run"
        assert connection.execute(select(metadata.tables["analysis_records"].c.dataset_version_id).where(
            metadata.tables["analysis_records"].c.id == record_id)).scalar_one() == version_id
        old_artifact = connection.execute(select(metadata.tables["analysis_artifacts"]).where(
            metadata.tables["analysis_artifacts"].c.id == artifact_id)).mappings().one()
        assert old_artifact["stored_name"] == "b" * 32 + ".json"
        assert old_artifact["storage_key"] is None and old_artifact["report_version_id"] is None
    engine.dispose()
