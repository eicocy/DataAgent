import pytest
from pydantic import ValidationError

from app.config import Settings


def test_development_secret_is_random_and_long_enough(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    first = Settings(_env_file=None)
    second = Settings(_env_file=None)

    assert first.secret_key != second.secret_key
    assert len(first.secret_key) >= 32


def test_production_requires_an_explicit_secret():
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key=None, _env_file=None)


def test_rejects_short_explicit_secret():
    with pytest.raises(ValidationError):
        Settings(secret_key="short", _env_file=None)
