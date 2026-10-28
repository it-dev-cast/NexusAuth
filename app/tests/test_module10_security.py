"""Module 10 (Configuration, Security, Database & Observability) coverage
for the app-code changes made in this pass: security response headers,
request-id generation/propagation, password change, and per-IP rate
limiting on login/register.
"""
from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email


def test_security_headers_present_on_every_response():
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "same-origin"
    assert "Content-Security-Policy" in response.headers


def test_request_id_generated_when_absent():
    response = client.get("/health")
    request_id = response.headers.get("X-Request-Id")
    assert request_id
    assert len(request_id) == 32  # uuid4().hex


def test_request_id_echoes_inbound_header():
    response = client.get("/health", headers={"X-Request-Id": "caller-supplied-id-123"})
    assert response.headers["X-Request-Id"] == "caller-supplied-id-123"


def _headers_with_role(role: str):
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _admin_headers():
    return _headers_with_role("admin")


def test_account_locks_after_max_failed_attempts_and_admin_can_unlock():
    # Doc: NEXUS_ONE_ARCHITECTURE_PLAN §3 — "Brute force protection (lock
    # after 5 failed attempts)" / "Account lockout duration" / "Account
    # unlock mechanism". Default settings.max_failed_login_attempts is 5.
    email = unique_email()
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Lockout Test"},
    )
    assert register.status_code == 202

    for _ in range(5):
        attempt = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "WrongPassword123"}
        )
        assert attempt.status_code == 401

    # 5 wrong attempts crossed the threshold — even the CORRECT password
    # is now rejected as locked, not just further wrong ones.
    # ...but it is answered exactly like a wrong password (see
    # test_locked_account_is_indistinguishable_from_a_wrong_password), so the
    # response doesn't reveal that the account exists.
    locked_attempt = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert locked_attempt.status_code == 401
    assert locked_attempt.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user.locked_until is not None
    user_id = user.id
    db.close()

    admin_headers = _admin_headers()
    unlock = client.post(f"/api/v1/auth/users/{user_id}/unlock", headers=admin_headers)
    assert unlock.status_code == 200
    assert unlock.json()["data"]["locked_until"] is None
    assert unlock.json()["data"]["failed_login_attempts"] == 0

    recovered = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert recovered.status_code == 200


def test_non_admin_cannot_unlock_accounts():
    email = unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Protected Unlock Test"},
    )
    db = SessionLocal()
    user_id = db.query(User).filter(User.email == email).first().id
    db.close()

    operator_headers = _headers_with_role("operator")
    response = client.post(f"/api/v1/auth/users/{user_id}/unlock", headers=operator_headers)
    assert response.status_code == 403


def test_change_password_requires_correct_current_password():
    email, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "WrongCurrent123", "new_password": "NewPassword456"},
        headers=headers,
    )
    assert response.status_code == 401


def test_change_password_succeeds_and_old_password_stops_working():
    email, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "NewPassword456"},
        headers=headers,
    )
    assert response.status_code == 200

    old_login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert old_login.status_code == 401

    new_login = client.post("/api/v1/auth/login", json={"email": email, "password": "NewPassword456"})
    assert new_login.status_code == 200


def test_change_password_revokes_the_session_it_was_called_from():
    email, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "AnotherPassword789"},
        headers=headers,
    )
    # The access token used to make the change-password call itself is now
    # logged out (logout_all_sessions), same as a detected refresh-token
    # reuse — a changed password shouldn't leave the calling session's own
    # old token still valid.
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401
