"""Versioned analysis strategies and immutable submission configuration."""
from alembic import op
import sqlalchemy as sa

revision = '0010_analysis_profiles'
down_revision = '0009_workspace_reports'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('analysis_records', sa.Column('request_config_json', sa.JSON(), nullable=True))
    op.create_table('analysis_profiles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('profile_id', sa.String(100), nullable=False),
        sa.Column('version', sa.String(30), nullable=False),
        sa.Column('definition_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('profile_id', 'version', name='uq_profile_version'))
    op.create_index('ix_analysis_profiles_profile_id', 'analysis_profiles', ['profile_id'])


def downgrade():
    op.drop_table('analysis_profiles')
    op.drop_column('analysis_records', 'request_config_json')
