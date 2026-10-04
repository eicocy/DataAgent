from contextlib import asynccontextmanager
from pathlib import Path
from alembic.script import ScriptDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import validation_error_handler
from app.routers.api import api_router
from app.database import engine, SessionLocal
from app.observability import configure_logging, RequestBodyLimitMiddleware
from app.services.jobs import TaskSupervisor
from sqlalchemy import text


settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    configure_logging()
    supervisor = TaskSupervisor(SessionLocal, settings) if settings.task_executor_enabled else None
    application.state.task_supervisor = supervisor
    if supervisor:
        supervisor.start()
    try:
        yield
    finally:
        if supervisor:
            supervisor.stop()
        application.state.task_supervisor = None


app = FastAPI(title="DataLens Agent API", version="2.0.4", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def enforce_origin_for_mutations(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin != settings.frontend_origin:
            return JSONResponse(
                status_code=403,
                content={"code": "ORIGIN_NOT_ALLOWED", "message": "请求来源不受允许", "data": None},
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def handle_validation(request: Request, exc: RequestValidationError):
    return await validation_error_handler(request, exc)


@app.exception_handler(HTTPException)
async def handle_http_error(_: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": detail.get("code", "HTTP_ERROR"), "message": detail.get("message", "请求失败"), "data": detail.get("data")},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, __: Exception):
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务暂时不可用", "data": None},
    )


@app.get("/health")
@app.get("/health/live")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            revisions = set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            heads = set(ScriptDirectory(str(Path(__file__).resolve().parents[1] / 'migrations')).get_heads())
            if revisions != heads:
                raise ValueError("Migration required")
        api_key = (settings.openai_api_key if settings.llm_provider == "openai"
                   else settings.deepseek_api_key)
        return {"status": "ready", "model_configured": bool(api_key.strip())}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "code": "DATABASE_NOT_READY"})


app.include_router(api_router)
