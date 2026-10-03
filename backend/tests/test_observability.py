import logging
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.observability import SafeFormatter, RequestBodyLimitMiddleware


def test_exception_formatter_does_not_print_sql_values_or_passwords():
    try:
        raise RuntimeError("password=secret [SQL: SELECT 'customer-private'] [parameters: ('secret',)]")
    except RuntimeError:
        import sys
        record = logging.LogRecord("app", logging.ERROR, __file__, 1, "Analysis failed record_id=%s", (12,), sys.exc_info())
        value = SafeFormatter().format(record)
    assert "secret" not in value and "customer-private" not in value and "SQL:" not in value
    assert "RuntimeError" in value and "record_id=12" in value


def test_body_limit_rejects_before_endpoint_and_without_content_length():
    app = FastAPI()
    calls = []
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=10)
    @app.post("/")
    async def endpoint(request: Request):
        await request.body()
        calls.append(True)
        return {"ok": True}
    with TestClient(app) as client:
        assert client.post("/", content=b"x" * 11).status_code == 413
        assert client.post("/", content=iter([b"x" * 6, b"x" * 6])).status_code == 413
    assert not calls
