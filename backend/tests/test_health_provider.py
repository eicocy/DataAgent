"""Readiness checks configuration for the selected provider, without network calls."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


@pytest.mark.parametrize(
    "provider,deepseek_key,openai_key,expected",
    [
        ("deepseek", "deepseek-test", "", True),
        ("deepseek", "", "openai-test", False),
        ("openai", "", "openai-test", True),
        ("openai", "deepseek-test", "", False),
        ("openai", "", "", False),
    ],
)
def test_readiness_reports_selected_provider_configuration(
    tmp_path, monkeypatch, provider, deepseek_key, openai_key, expected
):
    import app.main as main

    engine = create_engine(f"sqlite:///{tmp_path / 'ready.db'}")
    head = ScriptDirectory(str(Path(__file__).parents[1] / "migrations")).get_current_head()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
        connection.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": head})
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        llm_provider=provider, deepseek_api_key=deepseek_key, openai_api_key=openai_key
    ))
    try:
        response = TestClient(main.app).get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready", "model_configured": expected}
    finally:
        engine.dispose()
