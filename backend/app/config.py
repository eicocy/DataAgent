from functools import lru_cache
import secrets
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: Literal["development", "test", "production"] = "development"
    secret_key: str | None = None
    database_url: str = (
        "mysql+pymysql://datalens_app:change-me@127.0.0.1:3306/"
        "datalens_agent?charset=utf8mb4"
    )
    sql_readonly_database_url: str = ""
    projection_database_url: str = ""
    migration_database_url: str = ""
    artifact_dir: str = "./artifacts"
    task_executor_enabled: bool = True
    max_plan_steps: int = 12
    max_tool_attempts: int = 20
    max_model_calls: int = 10
    max_retries_per_step: int = 2
    max_replans: int = 2
    max_plan_retries: int = 1
    llm_timeout_seconds: int = 30
    sql_timeout_seconds: int = 5
    pandas_timeout_seconds: int = 10
    analysis_timeout_seconds: int = 180
    parse_timeout_seconds: int = 120
    report_timeout_seconds: int = 300
    dataframe_max_bytes: int = 256 * 1024 * 1024
    artifact_max_bytes: int = 64 * 1024 * 1024
    artifact_task_max_bytes: int = 128 * 1024 * 1024
    artifact_retention_days: int = 7
    max_pending_jobs: int = 20
    max_user_active_runs: int = 2
    max_dataset_rows: int = 100000
    max_dataset_columns: int = 200
    tool_preview_rows: int = 100
    tool_max_rows: int = 100000
    tool_max_columns: int = 200
    tool_max_cells: int = 40000
    tool_correlation_columns: int = 50
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 20 * 1024 * 1024
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_provider: Literal['deepseek', 'openai'] = 'deepseek'
    openai_api_key: str = ''
    openai_model: str = 'gpt-4o-mini'
    frontend_origin: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_secret_key(self):
        if self.secret_key is None:
            if self.app_env == "production":
                raise ValueError("SECRET_KEY must be configured in production")
            self.secret_key = secrets.token_urlsafe(48)
        if len(self.secret_key) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 characters")
        if self.app_env == "production" and self.secret_key.startswith("replace-"):
            raise ValueError("Production SECRET_KEY cannot be a template value")
        if self.app_env == "production" and any(value in self.database_url for value in ("change-me", "example-password")):
            raise ValueError("Production database credentials must be configured")
        for name in ("max_plan_steps", "max_tool_attempts", "max_model_calls", "max_retries_per_step", "max_replans", "max_plan_retries", "analysis_timeout_seconds", "parse_timeout_seconds", "report_timeout_seconds", "dataframe_max_bytes", "artifact_max_bytes", "artifact_task_max_bytes", "max_pending_jobs", "max_dataset_rows", "max_dataset_columns", "max_upload_bytes"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ('tool_preview_rows','tool_max_rows','tool_max_columns','tool_max_cells','tool_correlation_columns'):
            if getattr(self,name)<=0:
                raise ValueError(f'{name} must be positive')
        if self.tool_preview_rows>500:
            raise ValueError('tool_preview_rows must not exceed 500')
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
