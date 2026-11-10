from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (register models on Base.metadata)
from app.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    # Migrations need a direct (non-pooled) connection: PgBouncer's transaction mode
    # does not keep session state across statements.
    url = config.get_main_option("sqlalchemy.url") or get_settings().migration_database_url
    if not url:
        raise RuntimeError("DATABASE_URL_UNPOOLED / DATABASE_URL is not set (.env).")
    return url


def run_migrations_offline() -> None:
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
