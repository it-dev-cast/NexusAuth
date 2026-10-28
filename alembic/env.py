import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool, text
from alembic import context

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
load_dotenv()

from app.core.config import get_settings
from app.database.database import Base
import app.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)

# Interpret the config file for Python logging
if config.config_file_name:
    fileConfig(config.config_file_name)

# 3. Set target_metadata for autogenerate support
target_metadata = Base.metadata

# Arbitrary fixed key for pg_advisory_xact_lock, shared by every migration run.
MIGRATION_LOCK_KEY = 7364821990


def _lock_timeout() -> str:
    """MIGRATION_LOCK_TIMEOUT, e.g. "10s" or "2min" (default 10s)."""
    value = os.environ.get("MIGRATION_LOCK_TIMEOUT", "10s").strip()
    if not value or not all(c.isalnum() for c in value):
        raise ValueError("MIGRATION_LOCK_TIMEOUT must look like 10s, 500ms or 2min.")
    return value


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit SQL statements to script output.
    """
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
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, 
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            # One migration run at a time: a second `alembic upgrade` (e.g. two
            # deploys starting together) waits here, then finds the database
            # already at head. The lock is released when this transaction ends.
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
            # Don't queue behind long-running queries holding table locks for
            # ever (and block everything queued behind us meanwhile).
            connection.execute(text(f"SET LOCAL lock_timeout = '{_lock_timeout()}'"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()