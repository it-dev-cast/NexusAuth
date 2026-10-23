import os
import uuid
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv

# Doc: "Test database setup" (Module 10: Testing & Validation Infrastructure)
# — point the whole suite at its own database, never at the real dev/demo
# one. Without this, every pytest run wrote directly into whatever
# DATABASE_URL happened to be active (see app/database/database.py, which
# builds its engine at import time from get_settings()), and repeated runs
# during ordinary development silently filled the real database with
# thousands of test-generated rows (companies/employees/users named things
# like "Acme intern_<hex>@casterly.com" — see unique_email() below) with no
# cleanup, since there's no per-test transaction rollback either. This must
# run BEFORE `from main import app`, since that import is what first reads
# DATABASE_URL via get_settings() and builds the SQLAlchemy engine.
#
# TEST_DATABASE_URL, if set, wins outright. Otherwise this derives one from
# the real DATABASE_URL by appending "_test" to the database name — e.g.
# ".../nexus_auth" -> ".../nexus_auth_test" — so a plain local checkout
# isolates itself with zero extra config, as long as that database exists
# and is migrated to head (see scripts/create_test_db.py).
load_dotenv()


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL")
    if not base:
        # No DATABASE_URL at all means the app is configured via the
        # individual DB_* vars instead (see app/core/config.py's
        # sqlalchemy_url) — nothing to safely derive a test URL from here,
        # so leave DATABASE_URL unset and let Settings fall back to
        # DB_NAME etc. as normal (whoever set those up is responsible for
        # pointing DB_NAME at a test database themselves).
        return None
    parts = urlsplit(base)
    db_name = parts.path.lstrip("/")
    if db_name.endswith("_test"):
        return base
    return urlunsplit(parts._replace(path=f"/{db_name}_test"))


_test_url = _test_database_url()
if _test_url:
    os.environ["DATABASE_URL"] = _test_url

# Same isolation reasoning as DATABASE_URL above, for app/core/uploads.py's
# saved files: without this, every test run that exercises the upload
# endpoint (test_employee_photo_upload.py) writes real files into the
# project's own uploads/ directory, which never gets cleaned up. A fresh
# OS temp directory per test session means nothing lands in the repo at
# all — not even somewhere requiring its own .gitignore entry — and it's
# reclaimed by the OS's normal temp-file lifecycle, not by this suite.
import tempfile  # noqa: E402

os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="nexusauth_test_uploads_")

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)
PASSWORD = "TestPassword123"


def unique_email() -> str:
    return f"intern_{uuid.uuid4().hex[:12]}@casterly.com"


def unique_word() -> str:
    # Same purpose as unique_email() — a per-call unique token so
    # parallel/repeated test runs don't collide on a duplicate name — but
    # letters-only. Backs COMPANY names specifically: CompanyCreateRequest/
    # CompanyUpdateRequest now reject digits/#/brackets in a company's
    # name, so the many tests that used to build one as
    # f"Acme {unique_email()}" (embedding unique_email()'s hex digits)
    # need a token that's still unique but never contains a digit. A fixed
    # digit->letter substitution over a uuid4 hex is still a bijection
    # over the same character space, so uniqueness is preserved exactly.
    return uuid.uuid4().hex[:12].translate(str.maketrans("0123456789", "pqrstuvwxy"))


def register_and_login(email: str | None = None):
    email = email or unique_email()
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Intern Demo"},
    )
    assert register.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login.status_code == 200
    return email, login.json()["data"]
