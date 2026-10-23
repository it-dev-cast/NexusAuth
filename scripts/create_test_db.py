"""One-time setup: create the isolated test database app/tests/conftest.py
points the test suite at (see its TEST_DATABASE_URL / "_test" derivation
logic), then bring it to the current Alembic head.

Usage:
    python scripts/create_test_db.py

Safe to re-run — does nothing if the database already exists (migrations
still get re-applied, which is a no-op if already at head).
"""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

from app.core.config import get_settings  # noqa: E402


def _test_database_url_and_name(base_url: str) -> tuple[str, str]:
    parts = urlsplit(base_url)
    db_name = parts.path.lstrip("/")
    if not db_name.endswith("_test"):
        db_name = f"{db_name}_test"
    test_url = urlunsplit(parts._replace(path=f"/{db_name}"))
    return test_url, db_name


def main() -> None:
    settings = get_settings()
    base_url = settings.sqlalchemy_url
    test_url, test_db_name = _test_database_url_and_name(base_url)

    # psycopg (not SQLAlchemy) for CREATE DATABASE: it can't run inside a
    # transaction block, and connecting via the app's own "postgresql+psycopg"
    # SQLAlchemy URL scheme needs stripping the "+psycopg" driver suffix for
    # a plain psycopg.connect() DSN.
    admin_url = urlunsplit(urlsplit(base_url.replace("+psycopg", ""))._replace(path="/postgres"))
    conn = psycopg.connect(admin_url, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (test_db_name,))
        if cur.fetchone():
            print(f"{test_db_name} already exists")
        else:
            cur.execute(f'CREATE DATABASE "{test_db_name}"')
            print(f"created {test_db_name}")
    finally:
        conn.close()

    print(f"Running migrations against {test_db_name}...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(Path(__file__).resolve().parent.parent),
        # Bug fix: os.environ's own DATABASE_URL (loaded from .env, pointing
        # at the real dev DB) must NOT win over test_url here — a dict
        # literal's later keys overwrite earlier ones, so test_url has to
        # come last. As written before, this silently re-migrated the dev
        # database every time instead of the test one; alembic upgrade head
        # against an already-current dev DB is a harmless no-op, which is
        # exactly why this went unnoticed (no error, just the wrong target).
        env={**os.environ, "DATABASE_URL": test_url},
    )
    if result.returncode != 0:
        sys.exit(result.returncode)
    print("Test database ready.")


if __name__ == "__main__":
    main()
