"""Session ownership, durable results and multi-input report snapshots."""
from alembic import op
import sqlalchemy as sa

revision = '0012_artifact_workspace'
down_revision = '0011_workspace_files'
branch_labels = depends_on = None


def upgrade():
    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.add_column(sa.Column('session_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('retention_class', sa.String(20), nullable=False, server_default='intermediate'))
        batch.alter_column('expires_at', existing_type=sa.DateTime(), nullable=True)
        batch.create_foreign_key('fk_artifact_session', 'analysis_sessions', ['session_id'], ['id'], ondelete='CASCADE')
        batch.create_index('ix_analysis_artifacts_session_id', ['session_id'])
    with op.batch_alter_table('analysis_report_versions') as batch:
        batch.add_column(sa.Column('dataset_versions_json', sa.JSON(), nullable=True))
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind, only=['analysis_artifacts', 'analysis_records', 'analysis_reports', 'analysis_report_versions', 'tool_execution_records'])
    artifacts, records, reports, versions, tools = [meta.tables[name] for name in [
        'analysis_artifacts', 'analysis_records', 'analysis_reports', 'analysis_report_versions', 'tool_execution_records']]
    record_map = {r['id']: r for r in bind.execute(sa.select(records)).mappings()}
    report_map = {r['id']: r for r in bind.execute(sa.select(reports)).mappings()}
    version_map = {r['id']: report_map.get(r['report_id']) for r in bind.execute(sa.select(versions)).mappings()}
    tool_map = {r['id']: record_map.get(r['analysis_record_id']) for r in bind.execute(sa.select(tools)).mappings()}
    for row in bind.execute(sa.select(artifacts)).mappings():
        owner = record_map.get(row['record_id']) or version_map.get(row['report_version_id']) or tool_map.get(row['tool_execution_id'])
        values = {'session_id': owner['session_id'] if owner else None}
        if owner and row['purged_at'] is None:
            values.update(retention_class='final' if row['record_id'] or row['report_version_id'] else 'evidence', expires_at=None)
        bind.execute(artifacts.update().where(artifacts.c.id == row['id']).values(**values))
    for row in bind.execute(sa.select(versions)).mappings():
        inputs = []
        for rid in row['source_records_json'] or []:
            record = record_map.get(rid)
            if record:
                for item in (record['request_config_json'] or {}).get('inputs') or [{
                    'alias': 'primary', 'dataset_id': record['dataset_id'], 'dataset_version_id': record['dataset_version_id']}]:
                    if item not in inputs: inputs.append(item)
        bind.execute(versions.update().where(versions.c.id == row['id']).values(dataset_versions_json=inputs))


def downgrade():
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT COUNT(*) FROM analysis_artifacts WHERE expires_at IS NULL OR retention_class <> 'intermediate'")):
        raise RuntimeError('Restore the pre-0012 backup; durable results must not silently regain expiry.')
    with op.batch_alter_table('analysis_report_versions') as batch:
        batch.drop_column('dataset_versions_json')
    with op.batch_alter_table('analysis_artifacts') as batch:
        batch.drop_index('ix_analysis_artifacts_session_id')
        batch.drop_constraint('fk_artifact_session',type_='foreignkey')
        batch.drop_column('session_id'); batch.drop_column('retention_class')
        batch.alter_column('expires_at',existing_type=sa.DateTime(),nullable=False)
