from app.core.jwt_service import decode_token, hash_refresh_token
from app.database.database import SessionLocal
from app.models.revoked_token import RevokedToken
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email


def test_logout_revokes_access_and_is_idempotent():
    _, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    first = client.post("/api/v1/auth/logout", json={}, headers=headers)
    second = client.post("/api/v1/auth/logout", json={}, headers=headers)
    protected = client.get("/api/v1/auth/me", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert protected.status_code == 401
    assert protected.json()["error_code"] == "AUTH_TOKEN_REVOKED"

    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401


def test_logout_all_revokes_every_session_for_the_user():
    email, tokens_a = register_and_login(unique_email())
    login_b = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    tokens_b = login_b.json()["data"]

    headers_a = {"Authorization": f"Bearer {tokens_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {tokens_b['access_token']}"}

    # Both sessions work before logout-all.
    assert client.get("/api/v1/auth/me", headers=headers_a).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers_b).status_code == 200

    response = client.post("/api/v1/auth/logout-all", headers=headers_a)
    assert response.status_code == 200

    # Every session for this user is revoked — including the one that
    # didn't call logout-all itself.
    after_a = client.get("/api/v1/auth/me", headers=headers_a)
    after_b = client.get("/api/v1/auth/me", headers=headers_b)
    assert after_a.status_code == 401
    assert after_a.json()["error_code"] == "AUTH_TOKEN_REVOKED"
    assert after_b.status_code == 401
    assert after_b.json()["error_code"] == "AUTH_TOKEN_REVOKED"

    refresh_a = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]}
    )
    refresh_b = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens_b["refresh_token"]}
    )
    assert refresh_a.status_code == 401
    assert refresh_b.status_code == 401


def test_logout_records_both_access_and_refresh_in_revoked_tokens():
    """RevokedToken used to only ever get an "access" row on logout, leaving
    the refresh side (AuthSession.is_revoked) invisible to anyone querying
    "every revoked token" from one table. Logout should now write both."""
    _, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert response.status_code == 200

    access_jti = decode_token(tokens["access_token"])["jti"]
    refresh_hash = hash_refresh_token(tokens["refresh_token"])

    db = SessionLocal()
    try:
        access_row = db.query(RevokedToken).filter(RevokedToken.jti == access_jti).first()
        refresh_row = db.query(RevokedToken).filter(RevokedToken.jti == refresh_hash).first()
    finally:
        db.close()
    assert access_row is not None
    assert access_row.token_type == "access"
    assert refresh_row is not None
    assert refresh_row.token_type == "refresh"


def test_sessions_list_and_revoke():
    _, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    listed = client.get("/api/v1/auth/sessions", headers=headers)
    assert listed.status_code == 200
    sessions = listed.json()["data"]
    assert sessions
    session_id = sessions[0]["id"]

    revoked = client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert revoked.status_code == 200

    protected = client.get("/api/v1/auth/me", headers=headers)
    assert protected.status_code == 401
    assert protected.json()["error_code"] == "AUTH_TOKEN_REVOKED"
