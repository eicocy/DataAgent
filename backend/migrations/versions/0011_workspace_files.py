"""Register original files without moving historical data."""
from alembic import op
import sqlalchemy as sa

revision='0011_workspace_files'
down_revision='0010_analysis_profiles'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('uploaded_files',
        sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('original_name',sa.String(255),nullable=False),
        sa.Column('stored_name',sa.String(255),nullable=False,unique=True),
        sa.Column('file_type',sa.String(10),nullable=False),sa.Column('file_size',sa.BigInteger(),nullable=False),
        sa.Column('mime_type',sa.String(128),nullable=True),sa.Column('checksum',sa.String(64),nullable=True),
        sa.Column('status',sa.String(20),nullable=False),sa.Column('error_code',sa.String(64),nullable=True),
        sa.Column('error_message',sa.String(500),nullable=True),sa.Column('parsed_json',sa.JSON(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_uploaded_files_user_id','uploaded_files',['user_id'])
    with op.batch_alter_table('datasets') as batch:
        batch.add_column(sa.Column('uploaded_file_id',sa.Integer(),nullable=True))
        batch.add_column(sa.Column('origin_metadata_json',sa.JSON(),nullable=True))
        batch.create_foreign_key('fk_dataset_uploaded_file','uploaded_files',['uploaded_file_id'],['id'],ondelete='SET NULL')
    bind=op.get_bind()
    metadata=sa.MetaData()
    datasets=sa.Table('datasets',metadata,autoload_with=bind)
    files=sa.Table('uploaded_files',metadata,autoload_with=bind)
    for row in bind.execute(sa.select(datasets)).mappings():
        file_id=bind.execute(sa.insert(files).values(user_id=row['user_id'],original_name=row['original_name'],stored_name=row['stored_name'],
            file_type=row['file_type'],file_size=row['file_size'],status='ready',created_at=row['created_at'],updated_at=row['updated_at'])).inserted_primary_key[0]
        bind.execute(sa.update(datasets).where(datasets.c.id==row['id']).values(uploaded_file_id=file_id,
            origin_metadata_json={'source_kind':'legacy_table_file','file_id':file_id,'checksum':None}))


def downgrade():
    with op.batch_alter_table('datasets') as batch:
        batch.drop_constraint('fk_dataset_uploaded_file',type_='foreignkey')
        batch.drop_column('origin_metadata_json');batch.drop_column('uploaded_file_id')
    op.drop_table('uploaded_files')
