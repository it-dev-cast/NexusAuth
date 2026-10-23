from datetime import timedelta

from jose import jwt

from app.core.config import get_settings
from app.core.jwt_service import create_access_token
from app.tests.conftest import client, register_and_login


def test_login_access_token_contains_required_claims():
    _, tokens = register_and_login()
    settings = get_settings()
    payload = jwt.decode(
        tokens["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["token_type"] == "access"
    assert payload["jti"]
    assert payload["sub"]
    assert "roles" in payload
    assert "user_id" in payload
    assert "company_id" in payload
    assert "iat" in payload
    assert "exp" in payload


def test_protected_endpoint_requires_access_token():
    missing = client.get("/protected")
    assert missing.status_code == 401
    _, tokens = register_and_login()
    ok = client.get(
        "/protected",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["email"]


def test_valid_access_token_returns_current_user():
    email, tokens = register_and_login()
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["email"] == email
    assert body["claims"]["token_type"] == "access"
    assert body["claims"]["jti"]
    assert body["claims"]["roles"] is not None


def test_expired_access_token_rejected():
    expired, _ = create_access_token(
        1,
        "user",
        expires_delta=timedelta(seconds=-5),
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_TOKEN_EXPIRED"


def test_modified_jwt_rejected():
    _, tokens = register_and_login()
    tampered = tokens["access_token"][:-4] + "abcd"
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID_TOKEN"


def test_missing_sub_claim_rejected():
    settings = get_settings()
    token = jwt.encode(
        {"token_type": "access", "jti": "abc"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "AUTH_INVALID_TOKEN"
