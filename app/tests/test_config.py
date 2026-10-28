"""JWT_ALGORITHM is HS256 (shared secret) or RS256 (RSA key pair, see
app/core/jwt_service.py). Anything else, or RS256 without a usable key, must
fail fast at startup, not silently accept a value that would only break later
on a user's first login."""
import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides):
    defaults = {
        "jwt_secret_key": "test-only-secret-0123456789-abcdefghijk",
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


def test_rs256_without_a_key_is_rejected_at_startup():
    # RS256 is supported, but only with an RSA private key to sign with
    # (the full RS256 behaviour is in test_security_hardening.py).
    with pytest.raises(ValidationError, match="private key"):
        _settings(jwt_algorithm="RS256")


def test_other_unsupported_algorithms_are_rejected():
    with pytest.raises(ValidationError):
        _settings(jwt_algorithm="ES256")


def test_weak_jwt_secret_is_rejected():
    with pytest.raises(ValidationError):
        _settings(jwt_secret_key="too-short")


def test_repetitive_jwt_secret_is_rejected():
    with pytest.raises(ValidationError, match="too repetitive"):
        _settings(jwt_secret_key="a" * 40)


def test_env_example_placeholder_secret_is_rejected():
    from app.core.config import _example_env_secrets

    placeholders = _example_env_secrets()
    assert placeholders, ".env.example should define a JWT secret placeholder"
    for placeholder in placeholders:
        with pytest.raises(ValidationError, match="placeholder") as exc:
            _settings(jwt_secret_key=placeholder)
        # The error names the problem without echoing the secret.
        assert placeholder not in str(exc.value)


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
