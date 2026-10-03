from logging.config import fileConfig

from alembic import context, op
from contextlib import contextmanager
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
settings = get_settings()
config.set_main_option("sqlalchemy.url", (settings.migration_database_url or settings.database_url).replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            original_batch = op.batch_alter_table
            @contextmanager
            def dialect_batch(*args, **kwargs):
                # Historical SQLite batch migrations force table recreation. MySQL
                # supports native ALTER and has schema-global FK names, so copying
                # the existing named FKs would collide with the original table.
                if connection.dialect.name == "mysql" and kwargs.get("recreate") == "always":
                    kwargs["recreate"] = "auto"
                with original_batch(*args, **kwargs) as batch:
                    yield batch
            op.batch_alter_table = dialect_batch
            try:
                context.run_migrations()
            finally:
                op.batch_alter_table = original_batch


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
