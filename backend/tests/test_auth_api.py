from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_get_db():
    with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(engine)
client = TestClient(app, headers={"Origin": "http://localhost:5173"})


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_register_login_me_and_logout():
    registered = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "strong-pass-123"},
    )
    assert registered.status_code == 201
    assert registered.json()["data"]["username"] == "alice"
    assert "password_hash" not in registered.text

    logged_in = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "strong-pass-123"},
    )
    assert logged_in.status_code == 200
    assert "datalens_session" in logged_in.cookies

    client.cookies.update(logged_in.cookies)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "alice"

    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_uses_generic_error_for_unknown_user_and_wrong_password():
    unknown = client.post(
        "/api/v1/auth/login",
        json={"username": "missing", "password": "strong-pass-123"},
    )
    assert unknown.status_code == 401

    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "strong-pass-123"},
    )
    wrong = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "wrong-pass-123"},
    )
    assert wrong.status_code == 401
    assert unknown.json()["code"] == wrong.json()["code"] == "AUTH_INVALID_CREDENTIALS"


def test_register_normalizes_username_and_rejects_duplicates():
    first = client.post(
        "/api/v1/auth/register",
        json={"username": "Alice", "password": "strong-pass-123"},
    )
    duplicate = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "strong-pass-123"},
    )

    assert first.status_code == 201
    assert first.json()["data"]["username"] == "alice"
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "AUTH_USERNAME_EXISTS"


def test_mutating_requests_reject_a_foreign_origin():
    response = client.post(
        "/api/v1/auth/logout",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"


def test_mutating_requests_require_an_origin_header():
    response = TestClient(app).post("/api/v1/auth/logout")

    assert response.status_code == 403
    assert response.json()["code"] == "ORIGIN_NOT_ALLOWED"
