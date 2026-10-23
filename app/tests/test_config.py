"""Only HS256 is actually implemented (see app/core/jwt_service.py — a
single shared secret, no RSA keypair loading anywhere). JWT_ALGORITHM must
fail fast at startup for anything else, not silently accept a value that
would only break later on a user's first login."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides):
    defaults = {
        "jwt_secret_key": "a" * 32,
        "db_user": "nexus_auth_test_user",
        "db_password": "nexus_auth_test_password",
        "db_name": "nexus_auth_test",
    }
    defaults.update(overrides)
    # _env_file=None: construct from explicit kwargs only, ignoring the
    # real .env, so these tests aren't at the mercy of the dev environment's
    # actual configuration.
    return Settings(_env_file=None, **defaults)


def test_hs256_is_accepted():
    settings = _settings(jwt_algorithm="HS256")
    assert settings.jwt_algorithm == "HS256"


def test_rs256_is_rejected_at_startup():
    with pytest.raises(ValidationError, match="JWT_ALGORITHM"):
        _settings(jwt_algorithm="RS256")


def test_other_unsupported_algorithms_are_rejected():
    with pytest.raises(ValidationError):
        _settings(jwt_algorithm="ES256")


def test_weak_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        _settings(jwt_secret_key="too-short")


def test_database_url_alone_is_sufficient():
    settings = _settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        db_user=None,
        db_password=None,
        db_name=None,
    )
    assert settings.sqlalchemy_url == "postgresql+psycopg://u:p@localhost:5432/db"


def test_incomplete_db_config_is_rejected_at_startup():
    # Doc: "Required configuration enforcement" (Module 10: Configuration)
    # — without DATABASE_URL, all of DB_USER/DB_PASSWORD/DB_NAME must be
    # set, or startup should fail loudly instead of building a malformed
    # connection string like "postgresql+psycopg://None:None@host/None"
    # that only breaks on the first real query.
    with pytest.raises(ValidationError, match="Database is not configured"):
        _settings(database_url=None, db_password=None)
