"""Alembic environment for the refactored MySQL schema."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from backend.core.config import get_settings
from backend.db.base import Base
from backend.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def ensure_version_table_capacity(connection) -> None:
    """Alembic's default version column is too short for this repo's revision ids."""
    dialect_name = connection.dialect.name
    if dialect_name not in {"mysql", "mariadb"}:
        return
    connection.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(191) NOT NULL PRIMARY KEY)"))
    connection.execute(text("ALTER TABLE alembic_version MODIFY version_num VARCHAR(191) NOT NULL"))


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        ensure_version_table_capacity(connection)
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()
        if connection.dialect.name in {"mysql", "mariadb"}:
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
