"""Workspace report versions and file-backed artifact metadata."""
from alembic import op
import sqlalchemy as sa


revision = '0009_workspace_reports'
down_revision = '0008_agent_orchestration'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('datasets', sa.Column('parse_options_json', sa.JSON(), nullable=True))
    op.add_column('analysis_sessions', sa.Column(
        'is_pinned', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('background_jobs', sa.Column('task_payload_json', sa.JSON(), nullable=True))

    op.create_table('analysis_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('analysis_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE')),
        sa.Column('dataset_version_id', sa.Integer(), sa.ForeignKey('dataset_versions.id', ondelete='SET NULL')),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='READY'),
        sa.Column('latest_version_number', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_analysis_reports_owner_updated', 'analysis_reports', ['user_id', 'updated_at'])

    op.create_table('analysis_report_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('report_id', sa.Integer(), sa.ForeignKey('analysis_reports.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='READY'),
        sa.Column('spec_json', sa.JSON(), nullable=False),
        sa.Column('document_json', sa.JSON(), nullable=False),
        sa.Column('source_records_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('report_id', 'version_number', name='uq_report_version'))
    op.create_index('ix_analysis_report_versions_report_id', 'analysis_report_versions', ['report_id'])

    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.drop_constraint('ck_artifact_owner', type_='check')
        batch.add_column(sa.Column('storage_key', sa.String(512)))
        batch.create_unique_constraint('uq_artifact_storage_key', ['storage_key'])
        batch.add_column(sa.Column('file_name', sa.String(255)))
        batch.add_column(sa.Column('mime_type', sa.String(128)))
        batch.add_column(sa.Column('status', sa.String(20), nullable=False, server_default='READY'))
        batch.add_column(sa.Column('metadata_json', sa.JSON()))
        batch.add_column(sa.Column('report_version_id', sa.Integer()))
        batch.create_foreign_key('fk_artifact_report_version', 'analysis_report_versions',
                                 ['report_version_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_analysis_artifacts_report_version_id', ['report_version_id'])
        batch.create_check_constraint('ck_artifact_owner',
            '(record_id IS NOT NULL AND tool_execution_id IS NULL AND report_version_id IS NULL) OR '
            '(record_id IS NULL AND tool_execution_id IS NOT NULL AND report_version_id IS NULL) OR '
            '(record_id IS NULL AND tool_execution_id IS NULL AND report_version_id IS NOT NULL)')


def downgrade():
    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.drop_constraint('ck_artifact_owner', type_='check')
        batch.drop_constraint('uq_artifact_storage_key', type_='unique')
        batch.drop_index('ix_analysis_artifacts_report_version_id')
        batch.drop_constraint('fk_artifact_report_version', type_='foreignkey')
        batch.drop_column('report_version_id')
        batch.drop_column('metadata_json')
        batch.drop_column('status')
        batch.drop_column('mime_type')
        batch.drop_column('file_name')
        batch.drop_column('storage_key')
        batch.create_check_constraint('ck_artifact_owner',
            '(record_id IS NOT NULL AND tool_execution_id IS NULL) OR '
            '(record_id IS NULL AND tool_execution_id IS NOT NULL)')

    op.drop_index('ix_analysis_report_versions_report_id', table_name='analysis_report_versions')
    op.drop_table('analysis_report_versions')
    op.drop_index('ix_analysis_reports_owner_updated', table_name='analysis_reports')
    op.drop_table('analysis_reports')
    op.drop_column('background_jobs', 'task_payload_json')
    op.drop_column('analysis_sessions', 'is_pinned')
    op.drop_column('datasets', 'parse_options_json')
