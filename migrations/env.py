from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from finalboss.config import Settings, secret_value
from finalboss.storage.database import Base, _normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = secret_value(Settings().database_url)
if database_url is None:
    raise RuntimeError("FINALBOSS_DATABASE_URL is required")
config.set_main_option("sqlalchemy.url", _normalize_database_url(database_url))
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
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
