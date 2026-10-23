from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings


settings = get_settings()
DATABASE_URL = settings.sqlalchemy_url

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    # Doc: "Connection timeout handling" / "Query timeout enforcement"
    # (Module 10: Error Recovery & Resilience) — bounds how long a new
    # connection attempt can hang (connect_timeout, a libpq/psycopg param)
    # and how long any single statement on that connection can run
    # (statement_timeout, set server-side per-session via `options`) so a
    # hung TCP connect or a runaway query can't block a worker forever.
    # sqlite (used by some ad hoc/offline tooling) doesn't understand either
    # kwarg, so they're only passed for the real postgresql+psycopg driver.
    connect_args=(
        {
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": f"-c statement_timeout={settings.db_statement_timeout_ms}",
        }
        if DATABASE_URL.startswith("postgresql")
        else {}
    ),
)

Base = declarative_base()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Belt-and-suspenders: make sure a failed request never leaves a
        # transaction half-applied. Session.close() alone would discard the
        # connection anyway, but rolling back explicitly here documents the
        # intent and guarantees it even if that default ever changes.
        db.rollback()
        raise
    finally:
        db.close()
