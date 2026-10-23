"""Schema verification against Alembic history (Foundation Core Module 9 —
database initialization architecture).

The app must never create or modify its own production schema outside of
Alembic. Previously main.py called `Base.metadata.create_all(bind=engine)`
on every startup, which is a second, uncontrolled schema-creation path that
runs alongside Alembic migrations. That's exactly the anti-pattern the
architecture forbids: two independent things can create tables, and neither
knows about the other.

The fix: startup only ever *verifies* that the database's `alembic_version`
matches this codebase's migration head. It never creates or alters
anything. If the database hasn't been migrated yet (fresh checkout, empty
DB, or someone skipped `alembic upgrade head`), startup fails loudly with a
clear instruction instead of silently improvising a schema.
"""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"


class SchemaNotReadyError(RuntimeError):
    """Raised when the connected database is not at the expected Alembic head."""


def _expected_head() -> str | None:
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_PROJECT_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def _current_db_revision(engine: Engine) -> str | None:
    try:
        with engine.connect() as connection:
            row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
            return row[0] if row else None
    except Exception:
        # No alembic_version table at all (never migrated) or DB unreachable —
        # either way, "not at head" is the correct verdict, not a crash here.
        return None


def verify_schema_ready(engine: Engine) -> None:
    """Raise SchemaNotReadyError unless the DB is exactly at our migration head.

    Deliberately does not attempt to fix anything itself (no create_all, no
    auto-upgrade) — running migrations is an explicit, reviewed operational
    step (`alembic upgrade head`), not something application startup decides
    to do on its own.
    """
    expected = _expected_head()
    actual = _current_db_revision(engine)
    if actual != expected:
        raise SchemaNotReadyError(
            "Database schema is not at the expected Alembic revision "
            f"(expected {expected!r}, found {actual!r}). "
            "Run `alembic upgrade head` before starting the application."
        )
