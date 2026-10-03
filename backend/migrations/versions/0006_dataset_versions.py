"""Immutable initial dataset versions and analysis provenance."""
from alembic import op
import sqlalchemy as sa
revision = '0006_dataset_versions'
down_revision = '0005_projection_metadata'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('dataset_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('dataset_id', sa.Integer(), sa.ForeignKey('datasets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('parent_version_id', sa.Integer(), sa.ForeignKey('dataset_versions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('source_kind', sa.String(30), nullable=False),
        sa.Column('projection_schema', sa.String(64), nullable=True),
        sa.Column('projection_table', sa.String(64), nullable=False),
        sa.Column('schema_json', sa.JSON(), nullable=False),
        sa.Column('profile_json', sa.JSON(), nullable=False),
        sa.Column('transformations_json', sa.JSON(), nullable=False),
        sa.Column('original_available', sa.Boolean(), nullable=False),
        sa.Column('source_checksum', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('dataset_id', 'version_number', name='uq_dataset_version_number'))
    op.create_index('ix_dataset_versions_status', 'dataset_versions', ['status'])
    with op.batch_alter_table('datasets') as batch:
        batch.add_column(sa.Column('current_version_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_dataset_current_version', 'dataset_versions', ['current_version_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('analysis_records') as batch:
        batch.add_column(sa.Column('dataset_version_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('schema_version', sa.String(20), nullable=True))
        batch.add_column(sa.Column('version_binding', sa.String(30), nullable=True))
        batch.create_foreign_key('fk_analysis_dataset_version', 'dataset_versions', ['dataset_version_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('analysis_records') as batch:
        batch.drop_constraint('fk_analysis_dataset_version', type_='foreignkey')
        for name in ('dataset_version_id', 'schema_version', 'version_binding'):
            batch.drop_column(name)
    with op.batch_alter_table('datasets') as batch:
        batch.drop_constraint('fk_dataset_current_version', type_='foreignkey')
        batch.drop_column('current_version_id')
    op.drop_table('dataset_versions')
