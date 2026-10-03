from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()


def configured_engine(url: str):
    options = {"pool_pre_ping": True, "hide_parameters": True}
    if url.startswith("mysql"):
        options.update(pool_size=3, max_overflow=2, connect_args={"connect_timeout": 5, "read_timeout": 6, "write_timeout": 6})
    return create_engine(url, **options)


engine = configured_engine(settings.database_url)
projection_engine = configured_engine(settings.projection_database_url) if settings.projection_database_url else engine
readonly_engine = (
    configured_engine(settings.sql_readonly_database_url)
    if settings.sql_readonly_database_url
    else None
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
