"""Versioned parsing and server-controlled projection location."""
from alembic import op
import sqlalchemy as sa

revision = "0005_projection_metadata"
down_revision = "0004_jobs_artifacts"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("dataset_columns") as batch:
        batch.alter_column("original_name", existing_type=sa.String(255), type_=sa.Text(), existing_nullable=False)
    for name, column_type in (("projection_schema", sa.String(64)), ("projection_table", sa.String(64)), ("parse_version", sa.String(20)), ("quality_warnings_json", sa.JSON())):
        op.add_column("datasets", sa.Column(name, column_type, nullable=True))


def downgrade():
    with op.batch_alter_table("dataset_columns") as batch:
        batch.alter_column("original_name", existing_type=sa.Text(), type_=sa.String(255), existing_nullable=False)
    for name in ("projection_schema", "projection_table", "parse_version", "quality_warnings_json"):
        op.drop_column("datasets", name)
