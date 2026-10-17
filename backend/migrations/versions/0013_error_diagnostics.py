"""Persist safe task diagnostics without rewriting historical records."""
from alembic import op
import sqlalchemy as sa

revision = '0013_error_diagnostics'
down_revision = '0012_artifact_workspace'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('analysis_records', sa.Column('error_info_json', sa.JSON(), nullable=True))
    op.add_column('background_jobs', sa.Column('error_info_json', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('background_jobs', 'error_info_json')
    op.drop_column('analysis_records', 'error_info_json')
