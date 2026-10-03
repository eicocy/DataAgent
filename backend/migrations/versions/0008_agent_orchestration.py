"""Conversation context, safe Agent trace, model usage, and cancellation."""
from alembic import op
import sqlalchemy as sa

revision = '0008_agent_orchestration'
down_revision = '0007_analysis_engine'
branch_labels = None
depends_on = None


def _session_dataset_fk():
    fks = sa.inspect(op.get_bind()).get_foreign_keys('analysis_sessions')
    return next((fk['name'] for fk in fks if fk['constrained_columns'] == ['dataset_id'] and fk['name']),
                'fk_analysis_sessions_dataset_id_datasets')


def upgrade():
    with op.batch_alter_table('analysis_sessions', recreate='always',
                              naming_convention={'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}) as batch:
        batch.drop_constraint(_session_dataset_fk(), type_='foreignkey')
        batch.alter_column('dataset_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('context_json', sa.JSON(), nullable=True))
        batch.create_foreign_key('fk_analysis_sessions_dataset_id', 'datasets', ['dataset_id'], ['id'], ondelete='SET NULL')
    with op.batch_alter_table('analysis_records') as batch:
        batch.alter_column('dataset_id', existing_type=sa.Integer(), nullable=True)
    with op.batch_alter_table('background_jobs') as batch:
        batch.add_column(sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table('analysis_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('record_id', sa.Integer(), sa.ForeignKey('analysis_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(40), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_analysis_events_record_id_id', 'analysis_events', ['record_id', 'id'])
    op.create_table('llm_call_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('request_id', sa.String(64), nullable=False),
        sa.Column('record_id', sa.Integer(), sa.ForeignKey('analysis_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('analysis_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(40), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('prompt_version', sa.String(80), nullable=False),
        sa.Column('input_tokens', sa.Integer()), sa.Column('output_tokens', sa.Integer()),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('error_code', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_llm_calls_record_id', 'llm_call_records', ['record_id'])


def downgrade():
    op.drop_index('ix_llm_calls_record_id', table_name='llm_call_records')
    op.drop_table('llm_call_records')
    op.drop_index('ix_analysis_events_record_id_id', table_name='analysis_events')
    op.drop_table('analysis_events')
    with op.batch_alter_table('background_jobs') as batch:
        batch.drop_column('cancel_requested')
    with op.batch_alter_table('analysis_records') as batch:
        batch.alter_column('dataset_id', existing_type=sa.Integer(), nullable=False)
    with op.batch_alter_table('analysis_sessions', recreate='always',
                              naming_convention={'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s'}) as batch:
        batch.drop_constraint('fk_analysis_sessions_dataset_id', type_='foreignkey')
        batch.drop_column('context_json')
        batch.alter_column('dataset_id', existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key('fk_analysis_sessions_dataset_id', 'datasets', ['dataset_id'], ['id'], ondelete='CASCADE')
