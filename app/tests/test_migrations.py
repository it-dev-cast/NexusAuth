"""Migration checks. The structural ones always run; the full
upgrade -> downgrade -> upgrade cycle runs only with RUN_MIGRATION_TESTS=1,
because it creates (and then drops) a throwaway database, which needs the
CREATEDB privilege. It never touches the configured or test database."""
import ast
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def _script() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_there_is_exactly_one_head():
    assert len(_script().get_heads()) == 1


def test_every_migration_has_a_real_downgrade():
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        downgrade = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "downgrade")
        body = [n for n in downgrade.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        assert body and not all(isinstance(n, ast.Pass) for n in body), f"{path.name} has an empty downgrade()"


@pytest.mark.skipif(os.environ.get("RUN_MIGRATION_TESTS") != "1", reason="set RUN_MIGRATION_TESTS=1 to run")
def test_full_upgrade_downgrade_cycle_on_a_throwaway_database():
    import psycopg

    base = os.environ["DATABASE_URL"]
    parts = urlsplit(base)
    name = f"nexus_auth_migtest_{uuid.uuid4().hex[:8]}"
    admin_url = urlunsplit(parts._replace(scheme="postgresql", path="/postgres"))
    throwaway = urlunsplit(parts._replace(path=f"/{name}"))

    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    try:
        env = {**os.environ, "DATABASE_URL": throwaway}

        def alembic(*args):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True
            )
            assert result.returncode == 0, result.stderr[-2000:]

        alembic("upgrade", "head")
        alembic("downgrade", "-1")
        alembic("upgrade", "head")
        alembic("check")
    finally:
        with psycopg.connect(admin_url, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
