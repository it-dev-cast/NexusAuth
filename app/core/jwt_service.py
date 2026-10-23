from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import get_settings


def _settings():
    return get_settings()


def create_access_token(
    user_id: int,
    role: str | None = None,
    company_id: int | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, str]:
    settings = _settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    jti = str(uuid.uuid4())

    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "roles": [role] if role else [],
        "company_id": company_id,
        "jti": jti,
        "iat": now,
        "exp": expire,
        "token_type": "access",
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti


def create_refresh_token(
    user_id: int,
    expires_delta: timedelta | None = None,
) -> str:
    settings = _settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(days=settings.refresh_token_expire_days)
    )

    payload = {
        "sub": str(user_id),
        "user_id": user_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": expire,
        "token_type": "refresh",
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    settings = _settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except ExpiredSignatureError as exc:
        raise ValueError("expired") from exc
    except JWTError as exc:
        raise ValueError("invalid") from exc


def decode_typed_token(token: str, expected_type: str) -> dict:
    payload = decode_token(token)

    if payload.get("token_type") != expected_type:
        raise ValueError("wrong_type")

    if not payload.get("sub") or not payload.get("jti"):
        raise ValueError("missing_claim")

    return payload


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
