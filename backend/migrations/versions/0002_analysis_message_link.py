"""Link analysis records to their assistant message."""

from alembic import op
import sqlalchemy as sa


revision = "0002_analysis_message_link"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("analysis_records", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("assistant_message_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_analysis_records_assistant_message",
            "analysis_messages",
            ["assistant_message_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("analysis_records", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_analysis_records_assistant_message", type_="foreignkey")
        batch_op.drop_column("assistant_message_id")
