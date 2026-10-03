"""Durable jobs, evidence artifacts and execution reports."""
from alembic import op
import sqlalchemy as sa

revision = "0004_jobs_artifacts"
down_revision = "0003_user_message_link"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("plan_json", "report_json", "usage_json"):
        op.add_column("analysis_records", sa.Column(name, sa.JSON(), nullable=True))
    op.create_table("background_jobs",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("lease_token", sa.String(64)),
        sa.Column("heartbeat_at", sa.DateTime()), sa.Column("started_at", sa.DateTime()), sa.Column("completed_at", sa.DateTime()),
        sa.Column("active_stage", sa.String(30)), sa.Column("stage_started_at", sa.DateTime()), sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.UniqueConstraint("kind", "resource_id", name="uq_job_resource"))
    op.create_index("ix_jobs_status_created", "background_jobs", ["status", "created_at"])
    op.create_table("analysis_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("record_id", sa.Integer(), sa.ForeignKey("analysis_records.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.String(64), nullable=False), sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("stored_name", sa.String(64), nullable=False, unique=True), sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=False), sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("expires_at", sa.DateTime(), nullable=False), sa.Column("purged_at", sa.DateTime()))
    op.create_index("ix_analysis_artifacts_record_id", "analysis_artifacts", ["record_id"])
    op.create_table("cleanup_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("error_code", sa.String(64)), sa.Column("next_attempt_at", sa.DateTime()))


def downgrade():
    op.drop_table("cleanup_tasks")
    op.drop_table("analysis_artifacts")
    op.drop_table("background_jobs")
    for name in ("plan_json", "report_json", "usage_json"):
        op.drop_column("analysis_records", name)
