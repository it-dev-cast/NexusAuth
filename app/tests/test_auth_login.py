from app.core.password_service import hash_password, verify_password
from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login


def test_password_hash_and_verify():
    hashed_password = hash_password(PASSWORD)
    assert hashed_password != PASSWORD
    assert hashed_password.startswith("$2b$")
    assert verify_password(PASSWORD, hashed_password) is True
    assert verify_password("WrongPassword", hashed_password) is False


def test_login_success_creates_tokens_and_session():
    _, tokens = register_and_login()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 900


def test_wrong_password_and_unknown_email_same_message():
    email, _ = register_and_login()
    wrong = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123"},
    )
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@casterly.com", "password": PASSWORD},
    )
    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"
    assert unknown.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"
    assert wrong.json()["message"] == unknown.json()["message"]


def test_wrong_password_records_failed_attempt():
    email, _ = register_and_login()
    client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword123"},
    )
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user.failed_login_attempts >= 1
    db.close()


def test_inactive_user_gets_no_token():
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.is_active = False
    db.commit()
    db.close()

    inactive = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )

    assert inactive.status_code == 401
    assert inactive.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"
    assert "access_token" not in inactive.text


def test_registration_rejects_password_longer_than_bcrypt_limit():
    from app.tests.conftest import unique_email

    response = client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "a" * 73, "full_name": "Too Long"},
    )
    assert response.status_code == 422


def test_registration_accepts_password_at_bcrypt_limit():
    from app.tests.conftest import unique_email

    response = client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "a" * 72, "full_name": "Exactly 72"},
    )
    assert response.status_code == 201


def test_login_timing_is_not_measurably_faster_for_unknown_email():
    # Not a precise timing assertion (too flaky in CI) — this instead
    # verifies the code path itself: verify_password is called even when
    # the account doesn't exist, matching the fix in auth_service.login_user
    # (previously `not user or not verify_password(...)` short-circuited
    # and skipped bcrypt entirely for unknown emails).
    from unittest.mock import patch

    import app.services.auth_service as auth_service_module

    with patch.object(
        auth_service_module, "verify_password", wraps=auth_service_module.verify_password
    ) as spy:
        client.post(
            "/api/v1/auth/login",
            json={"email": "definitely-does-not-exist@casterly.com", "password": "whatever123"},
        )
    assert spy.called


def test_password_is_stored_as_bcrypt_hash():
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user.password_hash.startswith("$2b$")
    assert user.password_hash != PASSWORD
    assert PASSWORD not in user.password_hash
    assert user.full_name == "Intern Demo"
    db.close()
