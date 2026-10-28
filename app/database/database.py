from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from starlette.requests import Request

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

class AppSession(Session):
    """Inside an API request, commit() only flushes: the request is one
    transaction, committed once by TransactionMiddleware after the route has
    finished (and so after its audit row is written). A failure anywhere
    rolls back the business change and its audit trail together, instead of
    leaving a committed change with no audit row.

    Outside a request (scripts, startup, tests using SessionLocal directly)
    commit() behaves normally."""

    def commit(self) -> None:
        if self.info.get("defer_commit"):
            self.flush()
            return
        super().commit()

    def commit_now(self) -> None:
        """Commit even inside a request. Only for writes that must survive
        the error the request is about to return: failed-login counters,
        access-denied audit rows, token-reuse revocations."""
        super().commit()


def commit_now(db: Session) -> None:
    """AppSession.commit_now() where available; a plain commit otherwise."""
    getattr(db, "commit_now", db.commit)()


SessionLocal = sessionmaker(
    class_=AppSession,
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db(request: Request):
    db = SessionLocal()
    db.info["defer_commit"] = True
    # TransactionMiddleware (app/core/transaction.py) commits or rolls back
    # this session before the response is sent; this generator's exit code
    # only runs after the response has gone out.
    request.state.db_session = db
    try:
        yield db
    except Exception:
        # Belt-and-suspenders: make sure a failed request never leaves a
        # transaction half-applied.
        db.rollback()
        raise
    finally:
        db.close()
