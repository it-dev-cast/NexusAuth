"""Secrets and configuration: JWT/PII key rotation, required token expiry,
environment rules, bootstrap admin password, HSTS / no-store headers."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from jose import jwt
from pydantic import ValidationError

from app.core import jwt_service, pii_crypto
from app.core.config import Settings
from app.tests.conftest import client, register_and_login

NEW_KEY = "rotation-test-new-key-0123456789-abcdefghij"
OLD_KEY = "rotation-test-old-key-9876543210-zyxwvutsrq"


def _settings(**overrides) -> Settings:
    values = {
        "jwt_secret_key": NEW_KEY,
        "db_user": "u",
        "db_password": "p",
        "db_name": "nexus_auth_test",
        # The suite switches the rate limit off through the environment (see
        # conftest.py); production settings must be built the way a real
        # deployment would have them.
        "rate_limit_enabled": True,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _token(key: str, **claims) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": "1", "jti": "j", "token_type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    payload.update(claims)
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, key, algorithm="HS256")


def test_token_signed_with_a_previous_key_still_verifies(monkeypatch):
    settings = _settings(jwt_previous_secret_keys=OLD_KEY)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    assert jwt_service.decode_token(_token(OLD_KEY))["sub"] == "1"
    assert jwt_service.decode_token(_token(NEW_KEY))["sub"] == "1"


def test_new_tokens_are_signed_with_the_current_key_only(monkeypatch):
    settings = _settings(jwt_previous_secret_keys=OLD_KEY)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    token, _ = jwt_service.create_access_token(1, "admin", 1)
    jwt.decode(token, NEW_KEY, algorithms=["HS256"])  # raises if not signed with NEW_KEY


def test_unknown_key_and_missing_expiry_are_rejected(monkeypatch):
    settings = _settings(jwt_previous_secret_keys=OLD_KEY)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(_token("some-other-key-0123456789-abcdefghijklmn"))
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(_token(NEW_KEY, exp=None))
    expired = _token(OLD_KEY, exp=datetime.now(timezone.utc) - timedelta(minutes=1))
    with pytest.raises(ValueError, match="expired"):
        jwt_service.decode_token(expired)


def test_previous_keys_get_the_same_strength_checks():
    with pytest.raises(ValidationError, match="JWT_PREVIOUS_SECRET_KEYS"):
        _settings(jwt_previous_secret_keys="short")
    with pytest.raises(ValidationError, match="JWT_PREVIOUS_SECRET_KEYS"):
        _settings(jwt_previous_secret_keys="b" * 40)


def test_pii_values_encrypted_with_a_previous_key_still_decrypt(monkeypatch):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    monkeypatch.setattr(pii_crypto, "get_settings", lambda: _settings(pii_encryption_key=old))
    stored = pii_crypto.encrypt_value("ABCDE1234F")
    monkeypatch.setattr(
        pii_crypto,
        "get_settings",
        lambda: _settings(pii_encryption_key=new, pii_previous_encryption_keys=old),
    )
    assert pii_crypto.decrypt_value(stored) == "ABCDE1234F"
    # New writes use the new key only.
    Fernet(new.encode()).decrypt(pii_crypto.encrypt_value("x").encode())


def test_environment_must_be_a_known_name():
    assert _settings(environment="Staging").environment == "staging"
    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        _settings(environment="prdouction")


def test_production_requires_pii_key_and_no_wildcard_cors():
    with pytest.raises(ValidationError, match="PII_ENCRYPTION_KEY"):
        _settings(environment="production", pii_encryption_key="")
    with pytest.raises(ValidationError, match="CORS"):
        _settings(environment="production", pii_encryption_key=Fernet.generate_key().decode(), cors_allowed_origins="*")
    assert _settings(environment="production", pii_encryption_key=Fernet.generate_key().decode())


def test_bootstrap_creates_no_admin_without_a_configured_password(monkeypatch):
    from app.services import auth_service

    created = []

    class _Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    db = SimpleNamespace(query=lambda *args: _Query())
    monkeypatch.setattr(auth_service, "count_users", lambda _db: 0)
    monkeypatch.setattr(auth_service, "create_user", lambda _db, user: created.append(user))
    monkeypatch.setattr(auth_service, "get_settings", lambda: SimpleNamespace(bootstrap_admin_password=None))
    auth_service.bootstrap_admin(db)
    assert created == []


def test_auth_responses_are_not_cacheable():
    _, tokens = register_and_login()
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/health").headers.get("cache-control") != "no-store"


def test_hsts_is_sent_only_when_configured(monkeypatch):
    from app.core import security_middleware

    assert "strict-transport-security" not in client.get("/health").headers
    monkeypatch.setattr(security_middleware.get_settings(), "hsts_max_age_seconds", 31536000)
    assert client.get("/health").headers["strict-transport-security"].startswith("max-age=31536000")
