"""Independent tool executions and artifact ownership."""
from alembic import op
import sqlalchemy as sa
revision='0007_analysis_engine'
down_revision='0006_dataset_versions'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('tool_execution_records',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('dataset_id',sa.Integer(),sa.ForeignKey('datasets.id',ondelete='CASCADE'),nullable=False),
        sa.Column('dataset_version_id',sa.Integer(),sa.ForeignKey('dataset_versions.id',ondelete='SET NULL')),
        sa.Column('analysis_record_id',sa.Integer(),sa.ForeignKey('analysis_records.id',ondelete='CASCADE')),
        sa.Column('tool_name',sa.String(64),nullable=False),sa.Column('tool_version',sa.String(20),nullable=False),
        sa.Column('request_id',sa.String(64),nullable=False),sa.Column('parameters_json',sa.JSON(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('permissions_json',sa.JSON(),nullable=False),
        sa.Column('result_json',sa.JSON()),sa.Column('error_json',sa.JSON()),sa.Column('staging_projection',sa.String(64)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('started_at',sa.DateTime(timezone=True)),
        sa.Column('finished_at',sa.DateTime(timezone=True)),sa.Column('duration_ms',sa.Integer(),nullable=False,server_default='0'),
        sa.UniqueConstraint('user_id','request_id',name='uq_tool_execution_request'))
    op.create_index('ix_tool_execution_records_analysis_record_id','tool_execution_records',['analysis_record_id'])
    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.alter_column('record_id',existing_type=sa.Integer(),nullable=True)
        batch.add_column(sa.Column('tool_execution_id',sa.Integer(),nullable=True))
        batch.create_foreign_key('fk_artifact_tool_execution','tool_execution_records',['tool_execution_id'],['id'],ondelete='CASCADE')
        batch.create_index('ix_analysis_artifacts_tool_execution_id',['tool_execution_id'])
        batch.create_check_constraint('ck_artifact_owner','(record_id IS NOT NULL AND tool_execution_id IS NULL) OR (record_id IS NULL AND tool_execution_id IS NOT NULL)')
    with op.batch_alter_table('background_jobs') as batch:
        batch.add_column(sa.Column('stage_timeout_seconds',sa.Float(),nullable=True))


def downgrade():
    # Independent evidence cannot be relabeled as chat evidence during downgrade.
    connection=op.get_bind()
    if connection.execute(sa.text('SELECT count(*) FROM analysis_artifacts WHERE record_id IS NULL')).scalar():
        raise RuntimeError('Independent artifacts must be archived before downgrade')
    with op.batch_alter_table('background_jobs') as batch:
        batch.drop_column('stage_timeout_seconds')
    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.drop_constraint('ck_artifact_owner',type_='check')
        batch.drop_index('ix_analysis_artifacts_tool_execution_id')
        batch.drop_constraint('fk_artifact_tool_execution',type_='foreignkey')
        batch.drop_column('tool_execution_id')
        batch.alter_column('record_id',existing_type=sa.Integer(),nullable=False)
    op.drop_table('tool_execution_records')
