from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Float, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def id_column() -> Mapped[int]:
    # Integer keeps SQLite test schemas autoincrement-compatible and MySQL 8 supports it.
    return mapped_column(Integer, primary_key=True, autoincrement=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = id_column()
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Dataset(Base):
    __tablename__ = "datasets"
    __table_args__ = (Index("ix_datasets_owner_created", "user_id", "created_at"),)

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    file_type: Mapped[str] = mapped_column(String(10))
    file_size: Mapped[int] = mapped_column(BigInteger)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="uploading")
    parse_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parse_error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    projection_schema: Mapped[str | None] = mapped_column(String(64), nullable=True)
    projection_table: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL", name="fk_dataset_current_version", use_alter=True), nullable=True)
    parse_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality_warnings_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    __table_args__ = (
        UniqueConstraint("dataset_id", "name"),
        UniqueConstraint("dataset_id", "ordinal_position"),
    )

    id: Mapped[int] = id_column()
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    ordinal_position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    original_name: Mapped[str] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(30))
    nullable: Mapped[bool] = mapped_column(default=False)
    missing_count: Mapped[int] = mapped_column(BigInteger, default=0)
    unique_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sample_values_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    __table_args__ = (Index("ix_sessions_owner_updated", "user_id", "updated_at"),)

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="新分析")
    status: Mapped[str] = mapped_column(String(20), default="active")
    context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisMessage(Base):
    __tablename__ = "analysis_messages"

    id: Mapped[int] = id_column()
    session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"
    __table_args__ = (UniqueConstraint("user_id", "request_id", name="uq_analysis_request"),)

    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("analysis_sessions.id", ondelete="CASCADE"))
    user_message_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_messages.id", ondelete="SET NULL"), nullable=True)
    assistant_message_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_messages.id", ondelete="SET NULL"), nullable=True)
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    version_binding: Mapped[str | None] = mapped_column(String(30), nullable=True)
    request_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    intent_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_calls_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chart_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    usage_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    __table_args__ = (UniqueConstraint("kind", "resource_id", name="uq_job_resource"), Index("ix_jobs_status_created", "status", "created_at"))
    id: Mapped[int] = id_column()
    kind: Mapped[str] = mapped_column(String(20))
    stage_timeout_seconds: Mapped[float | None] = mapped_column(Float,nullable=True)
    resource_id: Mapped[int] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    lease_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stage_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class AnalysisArtifact(Base):
    __tablename__ = "analysis_artifacts"
    __table_args__ = (CheckConstraint('(record_id IS NOT NULL AND tool_execution_id IS NULL) OR (record_id IS NULL AND tool_execution_id IS NOT NULL)',name='ck_artifact_owner'),)
    id: Mapped[int] = id_column()
    record_id: Mapped[int | None] = mapped_column(ForeignKey("analysis_records.id", ondelete="CASCADE"), index=True, nullable=True)
    tool_execution_id: Mapped[int | None] = mapped_column(ForeignKey("tool_execution_records.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    step_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(20))
    stored_name: Mapped[str] = mapped_column(String(64), unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    row_count: Mapped[int] = mapped_column(BigInteger, default=0)
    schema_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CleanupTask(Base):
    __tablename__ = "cleanup_tasks"
    id: Mapped[int] = id_column()
    payload_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"), Index("ix_dataset_versions_status", "status"))
    id: Mapped[int] = id_column()
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"))
    version_number: Mapped[int] = mapped_column(Integer)
    parent_version_id: Mapped[int | None] = mapped_column(ForeignKey("dataset_versions.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    source_kind: Mapped[str] = mapped_column(String(30))
    projection_schema: Mapped[str | None] = mapped_column(String(64), nullable=True)
    projection_table: Mapped[str] = mapped_column(String(64))
    schema_json: Mapped[dict] = mapped_column(JSON)
    profile_json: Mapped[dict] = mapped_column(JSON)
    transformations_json: Mapped[list] = mapped_column(JSON)
    original_available: Mapped[bool] = mapped_column(default=False)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ToolExecutionRecord(Base):
    __tablename__ = 'tool_execution_records'
    __table_args__ = (UniqueConstraint('user_id','request_id',name='uq_tool_execution_request'),)
    id: Mapped[int] = id_column()
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id',ondelete='CASCADE'))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id',ondelete='CASCADE'))
    dataset_version_id: Mapped[int | None] = mapped_column(ForeignKey('dataset_versions.id',ondelete='SET NULL'),nullable=True)
    analysis_record_id: Mapped[int | None] = mapped_column(ForeignKey('analysis_records.id',ondelete='CASCADE'),nullable=True,index=True)
    tool_name: Mapped[str] = mapped_column(String(64))
    tool_version: Mapped[str] = mapped_column(String(20))
    request_id: Mapped[str] = mapped_column(String(64))
    parameters_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20),default='pending')
    permissions_json: Mapped[list] = mapped_column(JSON)
    result_json: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    error_json: Mapped[dict | None] = mapped_column(JSON,nullable=True)
    staging_projection: Mapped[str | None] = mapped_column(String(64),nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer,default=0)


class AnalysisEvent(Base):
    __tablename__ = 'analysis_events'
    __table_args__ = (Index('ix_analysis_events_record_id_id', 'record_id', 'id'),)
    id: Mapped[int] = id_column()
    record_id: Mapped[int] = mapped_column(ForeignKey('analysis_records.id', ondelete='CASCADE'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    event_type: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LLMCallRecord(Base):
    __tablename__ = 'llm_call_records'
    __table_args__ = (Index('ix_llm_calls_record_id', 'record_id'),)
    id: Mapped[int] = id_column()
    request_id: Mapped[str] = mapped_column(String(64))
    record_id: Mapped[int] = mapped_column(ForeignKey('analysis_records.id', ondelete='CASCADE'))
    conversation_id: Mapped[int] = mapped_column(ForeignKey('analysis_sessions.id', ondelete='CASCADE'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
