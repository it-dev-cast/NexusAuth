import logging

from app.core.config import get_settings
from app.tests.conftest import PASSWORD, client, register_and_login


def test_missing_and_malformed_headers():
    missing = client.get("/api/v1/auth/me")
    no_bearer = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Token abc"},
    )
    empty = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer "},
    )
    assert missing.status_code == 401
    assert no_bearer.status_code == 401
    assert empty.status_code == 401


def test_refresh_token_rejected_on_protected_api():
    _, tokens = register_and_login()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID_TOKEN"


def test_access_logs_do_not_contain_secrets(caplog):
    with caplog.at_level(logging.INFO):
        _, tokens = register_and_login()
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
    log_text = caplog.text
    assert PASSWORD not in log_text
    assert tokens["access_token"] not in log_text
    assert tokens["refresh_token"] not in log_text
    assert "Bearer eyJ" not in log_text
    assert get_settings().jwt_secret_key not in log_text
