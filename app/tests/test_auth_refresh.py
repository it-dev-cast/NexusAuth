from datetime import timedelta

from app.core.jwt_service import create_refresh_token
from app.tests.conftest import client, register_and_login


def test_refresh_success_and_wrong_token_type():
    _, tokens = register_and_login()
    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["access_token"]

    access_as_refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert access_as_refresh.status_code == 401
    assert access_as_refresh.json()["error_code"] == "AUTH_INVALID_TOKEN"


def test_expired_refresh_token_rejected():
    expired = create_refresh_token(1, expires_delta=timedelta(seconds=-5))
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_TOKEN_EXPIRED"
    assert "access_token" not in response.text


def test_revoked_session_cannot_refresh():
    _, tokens = register_and_login()
    client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    refresh = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 401
    assert refresh.json()["error_code"] in {"AUTH_TOKEN_REVOKED", "AUTH_INVALID_TOKEN"}
