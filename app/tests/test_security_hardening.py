"""Security hardening: over-long passwords, the lockout response, the login /
register rate limiter (shared counters, real client address) and RS256 JWTs."""
import time
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from pydantic import ValidationError
from sqlalchemy import text

from app.core import jwt_service
from app.core.client_ip import rate_limit_identity, resolve_client_ip
from app.core.config import Settings, get_settings
from app.core.password_service import MAX_PASSWORD_BYTES, hash_password, verify_password
from app.core.rate_limit import DatabaseRateLimiter, MemoryRateLimiter
from app.database.database import SessionLocal, engine
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email

HS_SECRET = "hardening-test-secret-0123456789-abcdefghij"
OLD_HS_SECRET = "hardening-old-secret-9876543210-zyxwvutsrq"


# --------------------------------------------------------------------------
# 1. passwords longer than bcrypt's 72 bytes
# --------------------------------------------------------------------------
def test_verify_password_treats_an_overlong_password_as_wrong_not_an_error():
    hashed = hash_password(PASSWORD)
    assert verify_password("a1" * 40, hashed) is False  # 80 bytes
    assert verify_password("é" * 40, hashed) is False  # 40 characters, 80 bytes
    assert verify_password(PASSWORD, hashed) is True


def test_hash_password_refuses_to_store_a_truncated_password():
    assert hash_password("a1" * 36)  # exactly 72 bytes is fine
    with pytest.raises(ValueError):
        hash_password("a1" * 37)
    assert MAX_PASSWORD_BYTES == 72


@pytest.mark.parametrize("password", ["a1" * 40, "é" * 40, "x" * 1000])
def test_login_with_an_overlong_password_is_invalid_credentials_not_a_500(password):
    email, _ = register_and_login()
    for address in (email, unique_email()):  # a real account and an unknown one
        response = client.post("/api/v1/auth/login", json={"email": address, "password": password})
        assert response.status_code == 401
        assert response.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


def test_login_body_size_is_capped():
    response = client.post("/api/v1/auth/login", json={"email": unique_email(), "password": "x" * 1025})
    assert response.status_code == 422


def test_change_password_with_an_overlong_current_password_is_rejected_cleanly():
    _, tokens = register_and_login()
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "a1" * 40, "new_password": "BrandNewPassword456"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


# --------------------------------------------------------------------------
# 3. a locked account answers like any other failed login
# --------------------------------------------------------------------------
def test_locked_account_is_indistinguishable_from_a_wrong_password():
    email, _ = register_and_login()
    wrong = client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"})
    unknown = client.post("/api/v1/auth/login", json={"email": unique_email(), "password": "WrongPassword123"})
    for _ in range(get_settings().max_failed_login_attempts):
        client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"})

    with SessionLocal() as db:
        assert db.query(User).filter(User.email == email).one().locked_until is not None

    for password in ("WrongPassword123", PASSWORD):  # even the right password
        locked = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert locked.status_code == wrong.status_code == unknown.status_code == 401
        assert locked.json()["error_code"] == wrong.json()["error_code"] == unknown.json()["error_code"]
        assert locked.json()["message"] == wrong.json()["message"] == unknown.json()["message"]
        assert "retry-after" not in {h.lower() for h in locked.headers}


def test_the_lock_reason_is_still_recorded_for_administrators():
    email, _ = register_and_login()
    for _ in range(get_settings().max_failed_login_attempts + 1):
        client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"})
    with engine.connect() as connection:
        reasons = connection.execute(
            text(
                "SELECT new_value FROM audit_logs WHERE action = 'login_failure' "
                "AND new_value::text LIKE :needle"
            ),
            {"needle": "%account_locked%"},
        ).fetchall()
    assert reasons


# --------------------------------------------------------------------------
# 2. unauthenticated endpoints
# --------------------------------------------------------------------------
def test_db_test_needs_an_administrator():
    assert client.get("/db-test").status_code == 401
    _, tokens = register_and_login()  # a self-registered user is read-only
    assert client.get("/db-test", headers={"Authorization": f"Bearer {tokens['access_token']}"}).status_code == 403


def test_the_only_public_endpoints_are_the_login_shell_probes_and_public_keys():
    # /ui and /favicon.ico are static files the login screen itself needs;
    # they carry no data. The API behind them is what requires a token.
    assert client.get("/api/v1/employees").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/ui").status_code == 200


# --------------------------------------------------------------------------
# 4. client address + rate limiting
# --------------------------------------------------------------------------
PROXIES = Settings(
    _env_file=None, jwt_secret_key=HS_SECRET, db_user="u", db_password="p", db_name="nexus_auth_test",
    trusted_proxies="10.0.0.0/8, 192.168.1.5",
).trusted_proxy_networks


def test_forwarded_for_is_ignored_without_trusted_proxies():
    assert resolve_client_ip("203.0.113.9", "1.2.3.4", []) == "203.0.113.9"


def test_forwarded_for_is_ignored_from_an_untrusted_peer():
    assert resolve_client_ip("203.0.113.9", "1.2.3.4", PROXIES) == "203.0.113.9"


def test_the_client_behind_a_trusted_proxy_is_the_forwarded_address():
    assert resolve_client_ip("10.1.2.3", "198.51.100.7", PROXIES) == "198.51.100.7"
    assert resolve_client_ip("192.168.1.5", "198.51.100.7, 10.9.9.9", PROXIES) == "198.51.100.7"


def test_a_spoofed_leftmost_forwarded_entry_does_not_pick_the_address():
    # The caller sent "6.6.6.6"; our proxy appended the address it really saw.
    assert resolve_client_ip("10.1.2.3", "6.6.6.6, 198.51.100.7", PROXIES) == "198.51.100.7"


def test_a_malformed_forwarded_header_is_not_believed():
    assert resolve_client_ip("10.1.2.3", "not-an-ip", PROXIES) == "10.1.2.3"
    assert resolve_client_ip("10.1.2.3", None, PROXIES) == "10.1.2.3"
    assert resolve_client_ip(None, "1.2.3.4", PROXIES) == "unknown"


def test_ipv6_callers_are_counted_per_64():
    assert rate_limit_identity("2001:db8:1:2:aaaa::1") == rate_limit_identity("2001:db8:1:2:bbbb::9")
    assert rate_limit_identity("2001:db8:1:3::1") != rate_limit_identity("2001:db8:1:2::1")
    assert rate_limit_identity("203.0.113.9") == "203.0.113.9"


def test_trusted_proxies_must_be_addresses():
    with pytest.raises(ValidationError, match="TRUSTED_PROXIES"):
        Settings(_env_file=None, jwt_secret_key=HS_SECRET, db_user="u", db_password="p", db_name="d", trusted_proxies="nope")


@pytest.fixture
def limiter_on(monkeypatch):
    """Turn the (suite-wide disabled) limiter on for one test, with a clean slate."""
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_backend", "database")

    def wipe():
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM rate_limit_counters WHERE key LIKE '/api/v1/auth/%'"))

    wipe()
    yield settings
    wipe()


def _register(headers=None):
    return client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": PASSWORD, "full_name": "Rate Limit Test"},
        headers=headers or {},
    )


def test_register_is_rate_limited_per_caller(limiter_on):
    statuses = [_register().status_code for _ in range(limiter_on.rate_limit_register_per_minute + 2)]
    assert statuses[: limiter_on.rate_limit_register_per_minute] == [202] * limiter_on.rate_limit_register_per_minute
    assert statuses[-2:] == [429, 429]


def test_login_is_rate_limited_and_says_when_to_retry(limiter_on, monkeypatch):
    monkeypatch.setattr(limiter_on, "rate_limit_login_per_minute", 3)
    responses = [
        client.post("/api/v1/auth/login", json={"email": unique_email(), "password": "WrongPassword123"})
        for _ in range(5)
    ]
    assert [r.status_code for r in responses] == [401, 401, 401, 429, 429]
    assert responses[-1].json()["error_code"] == "RATE_LIMITED"
    assert 1 <= int(responses[-1].headers["Retry-After"]) <= 60


def test_a_forged_forwarded_for_header_does_not_dodge_the_limit(limiter_on):
    statuses = [
        _register({"X-Forwarded-For": f"198.51.100.{n}"}).status_code
        for n in range(limiter_on.rate_limit_register_per_minute + 2)
    ]
    assert statuses[-1] == 429


def test_other_endpoints_are_not_rate_limited(limiter_on):
    assert all(client.get("/health").status_code == 200 for _ in range(30))


def test_the_limiter_is_off_when_disabled(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    assert all(_register().status_code == 202 for _ in range(8))


def test_database_counters_are_shared_between_workers(limiter_on):
    # Two limiter objects with separate in-process state stand in for two
    # worker processes: they must see one count.
    worker_a = DatabaseRateLimiter(engine, MemoryRateLimiter())
    worker_b = DatabaseRateLimiter(engine, MemoryRateLimiter())
    key = "/api/v1/auth/login|shared-test"
    assert worker_a.hit(key, 60)[0] == 1
    assert worker_b.hit(key, 60)[0] == 2
    assert worker_a.hit(key, 60)[0] == 3


def test_a_database_counter_starts_over_when_its_window_ends(limiter_on):
    limiter = DatabaseRateLimiter(engine, MemoryRateLimiter())
    key = "/api/v1/auth/login|window-test"
    assert limiter.hit(key, 1)[0] == 1
    assert limiter.hit(key, 1)[0] == 2
    time.sleep(1.2)
    assert limiter.hit(key, 1)[0] == 1


def test_if_the_database_is_unreachable_the_limiter_falls_back_to_this_process():
    class Broken:
        def begin(self):
            raise RuntimeError("database down")

    limiter = DatabaseRateLimiter(Broken(), MemoryRateLimiter())
    assert [limiter.hit("k", 60)[0] for _ in range(3)] == [1, 2, 3]


def test_memory_limiter_counts_and_resets_per_window():
    limiter = MemoryRateLimiter()
    assert [limiter.hit("k", 1)[0] for _ in range(3)] == [1, 2, 3]
    assert limiter.hit("other", 1)[0] == 1
    time.sleep(1.1)
    assert limiter.hit("k", 1)[0] == 1


def test_rate_limiting_cannot_be_turned_off_in_production():
    with pytest.raises(ValidationError, match="RATE_LIMIT_ENABLED"):
        Settings(
            _env_file=None, jwt_secret_key=HS_SECRET, db_user="u", db_password="p", db_name="d",
            environment="production", pii_encryption_key=None, rate_limit_enabled=False,
        )


# --------------------------------------------------------------------------
# 5. RS256
# --------------------------------------------------------------------------
def _pem_pair(bits=2048):
    key = rsa.generate_private_key(public_exponent=65537, key_size=bits)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return private, public


@pytest.fixture(scope="module")
def pair():
    return _pem_pair()


@pytest.fixture(scope="module")
def other_pair():
    return _pem_pair()


def _rs_settings(tmp_path, private, **overrides):
    path = tmp_path / "jwt_private.pem"
    path.write_text(private)
    values = {
        "jwt_algorithm": "RS256",
        "jwt_secret_key": HS_SECRET,
        "jwt_private_key_path": str(path),
        "db_user": "u",
        "db_password": "p",
        "db_name": "nexus_auth_test",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _forge_hs256(claims: dict, secret: str) -> str:
    """An HS256 token signed with `secret`, built by hand: jose itself refuses
    to HMAC with a PEM key, but an attacker isn't using jose."""
    import base64
    import hashlib
    import hmac
    import json

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    signing_input = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()) + "." + b64(
        json.dumps({k: int(v.timestamp()) if isinstance(v, datetime) else v for k, v in claims.items()}).encode()
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + b64(signature)


def _claims(**extra):
    now = datetime.now(timezone.utc)
    claims = {"sub": "1", "jti": "j", "token_type": "access", "iat": now, "exp": now + timedelta(minutes=5)}
    claims.update(extra)
    return claims


def test_rs256_tokens_are_signed_with_the_private_key_and_name_their_key(tmp_path, pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0])
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    token, _ = jwt_service.create_access_token(7, "admin", 1)
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256" and header["kid"] == settings.jwt_public_keys[0][0]
    assert jwt.decode(token, pair[1], algorithms=["RS256"])["sub"] == "7"  # verifies with the PUBLIC key alone
    assert jwt_service.decode_token(token)["sub"] == "7"
    assert jwt_service.decode_typed_token(jwt_service.create_refresh_token(7), "refresh")["sub"] == "7"


def test_rs256_private_key_can_come_from_an_environment_style_value(pair):
    settings = Settings(
        _env_file=None, jwt_algorithm="RS256", db_user="u", db_password="p", db_name="d",
        jwt_private_key=pair[0].strip().replace("\n", "\\n"),
    )
    assert settings.jwt_signing_key.startswith("-----BEGIN PRIVATE KEY-----")


def test_jwks_publishes_public_keys_only(tmp_path, pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0])
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    (entry,) = jwt_service.jwks()["keys"]
    assert entry["kty"] == "RSA" and entry["alg"] == "RS256" and entry["use"] == "sig"
    assert entry["kid"] == settings.jwt_public_keys[0][0]
    assert not {"d", "p", "q", "dp", "dq", "qi"} & set(entry)


def test_jwks_endpoint_is_public_and_empty_under_hs256():
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    assert response.json() == {"keys": []}


def test_hs256_token_signed_with_the_public_key_is_rejected(tmp_path, pair, monkeypatch):
    # Algorithm confusion: the public key is public, so an attacker can use it
    # as an HMAC secret. It must never verify.
    settings = _rs_settings(tmp_path, pair[0], jwt_secret_key=None)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    forged = _forge_hs256(_claims(), pair[1])
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(forged)


def test_a_token_signed_by_someone_elses_key_or_unsigned_is_rejected(tmp_path, pair, other_pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0])
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(jwt.encode(_claims(), other_pair[0], algorithm="RS256"))
    tampered = jwt.encode(_claims(), pair[0], algorithm="RS256") + "x"
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(tampered)
    no_expiry = {k: v for k, v in _claims().items() if k != "exp"}
    with pytest.raises(ValueError, match="invalid"):
        jwt_service.decode_token(jwt.encode(no_expiry, pair[0], algorithm="RS256"))


def test_expired_rs256_token_is_reported_as_expired(tmp_path, pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0])
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    old = jwt.encode(_claims(exp=datetime.now(timezone.utc) - timedelta(minutes=1)), pair[0], algorithm="RS256")
    with pytest.raises(ValueError, match="expired"):
        jwt_service.decode_token(old)


def test_rs256_key_rotation_keeps_old_tokens_valid_until_they_expire(tmp_path, pair, other_pair, monkeypatch):
    old_public = tmp_path / "old_public.pem"
    old_public.write_text(other_pair[1])
    settings = _rs_settings(tmp_path, pair[0], jwt_previous_public_key_paths=str(old_public))
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    signed_by_old_key = jwt.encode(_claims(), other_pair[0], algorithm="RS256")
    assert jwt_service.decode_token(signed_by_old_key)["sub"] == "1"
    new_token, _ = jwt_service.create_access_token(1)
    jwt.decode(new_token, pair[1], algorithms=["RS256"])  # new tokens: current key only
    assert len(jwt_service.jwks()["keys"]) == 2  # verifiers can fetch both during the overlap


def test_tokens_issued_under_hs256_still_verify_right_after_switching_to_rs256(tmp_path, pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0], jwt_previous_secret_keys=OLD_HS_SECRET)
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    assert jwt_service.decode_token(jwt.encode(_claims(), HS_SECRET, algorithm="HS256"))["sub"] == "1"
    assert jwt_service.decode_token(jwt.encode(_claims(), OLD_HS_SECRET, algorithm="HS256"))["sub"] == "1"


def test_the_whole_login_flow_works_under_rs256(tmp_path, pair, monkeypatch):
    settings = _rs_settings(tmp_path, pair[0])
    monkeypatch.setattr(jwt_service, "get_settings", lambda: settings)
    email, tokens = register_and_login()
    assert jwt.get_unverified_header(tokens["access_token"])["alg"] == "RS256"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200 and me.json()["data"]["email"] == email
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"jwt_private_key_path": None}, "private key"),
        ({"jwt_private_key_path": "does-not-exist.pem"}, "cannot read"),
    ],
)
def test_rs256_needs_a_readable_private_key(tmp_path, pair, overrides, message):
    with pytest.raises(ValidationError, match=message):
        _rs_settings(tmp_path, pair[0], **overrides)


def test_rs256_refuses_garbage_weak_and_mismatched_keys(tmp_path, pair, other_pair):
    with pytest.raises(ValidationError, match="valid unencrypted PEM private key"):
        _rs_settings(tmp_path, "not a key")
    with pytest.raises(ValidationError, match="at least 2048 bits"):
        _rs_settings(tmp_path, _pem_pair(1024)[0])
    public = tmp_path / "other_public.pem"
    public.write_text(other_pair[1])
    with pytest.raises(ValidationError, match="does not belong"):
        _rs_settings(tmp_path, pair[0], jwt_public_key_path=str(public))
    matching = tmp_path / "public.pem"
    matching.write_text(pair[1])
    assert _rs_settings(tmp_path, pair[0], jwt_public_key_path=str(matching)).jwt_public_keys


def test_hs256_still_needs_a_strong_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(_env_file=None, jwt_algorithm="HS256", db_user="u", db_password="p", db_name="d")


def test_unknown_algorithms_are_still_refused():
    for algorithm in ("ES256", "none", "HS512"):
        with pytest.raises(ValidationError, match="JWT_ALGORITHM"):
            Settings(_env_file=None, jwt_algorithm=algorithm, jwt_secret_key=HS_SECRET, db_user="u", db_password="p", db_name="d")


# --------------------------------------------------------------------------
# 6. registering with an address that already has an account
# --------------------------------------------------------------------------
def test_registration_does_not_reveal_whether_an_email_exists():
    email = unique_email()
    body = {"email": email, "password": PASSWORD, "full_name": "Enumeration Test"}
    first = client.post("/api/v1/auth/register", json=body)
    again = client.post("/api/v1/auth/register", json=body)
    different_password = client.post("/api/v1/auth/register", json={**body, "password": "AnotherPassword789"})
    upper = client.post("/api/v1/auth/register", json={**body, "email": email.upper()})
    assert first.status_code == again.status_code == different_password.status_code == upper.status_code == 202
    # identical answers (meta.trace_id is per request, so compare the data)
    assert first.json()["data"] == again.json()["data"] == different_password.json()["data"] == upper.json()["data"]
    assert set(first.json()["data"]) == {"message"}  # no id, role or email of the account


def test_a_second_registration_creates_no_account_and_does_not_change_the_password():
    email = unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Owner"})
    client.post("/api/v1/auth/register", json={"email": email, "password": "AttackerPassword1", "full_name": "Attacker"})
    with SessionLocal() as db:
        users = db.query(User).filter(User.email == email).all()
    assert len(users) == 1 and users[0].full_name == "Owner"
    assert client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "AttackerPassword1"}).status_code == 401


def test_registration_costs_the_same_work_whether_or_not_the_email_exists(monkeypatch):
    from app.services import auth_service

    calls = []
    real = auth_service.hash_password
    monkeypatch.setattr(auth_service, "hash_password", lambda password: calls.append(1) or real(password))
    email = unique_email()
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert len(calls) == 2  # hashed for the new address AND for the duplicate


def test_a_duplicate_registration_is_recorded_for_administrators():
    email = unique_email()
    for _ in range(2):
        client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT count(*) FROM audit_logs WHERE action = 'register_duplicate'")
        ).scalar()
    assert rows >= 1


def test_simultaneous_registrations_of_one_address_end_up_as_one_account(monkeypatch):
    # Both requests pass the "does it exist yet?" check; the unique index lets
    # exactly one insert through and the other must answer like a duplicate.
    from app.services import auth_service

    email = unique_email()
    monkeypatch.setattr(auth_service, "get_user_by_email", lambda db, e: None)
    first = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    second = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert first.status_code == second.status_code == 202
    assert first.json()["data"] == second.json()["data"]
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == email).count() == 1
