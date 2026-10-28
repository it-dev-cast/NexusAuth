from datetime import datetime, timedelta, timezone
import hashlib
import uuid

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import get_settings


def _settings():
    return get_settings()


def _encode(payload: dict) -> str:
    """Sign with the configured algorithm: the shared secret under HS256, the
    RSA private key (plus a `kid` header naming the matching public key, so a
    verifier can pick the right one after a rotation) under RS256."""
    settings = _settings()
    return jwt.encode(
        payload,
        settings.jwt_signing_key,
        algorithm=settings.jwt_algorithm,
        headers=settings.jwt_signing_headers,
    )


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

    return _encode(payload), jti


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

    return _encode(payload)


def _unverified_header_field(token: str, name: str):
    try:
        return jwt.get_unverified_header(token).get(name)
    except JWTError:
        return None


def decode_token(token: str) -> dict:
    """Verify with the current key, then any keys being rotated out
    (JWT_PREVIOUS_SECRET_KEYS / JWT_PREVIOUS_PUBLIC_KEY_PATHS). Every key is
    tried only with its own algorithm — never the token's own `alg` header, so
    a token can't pick how it is verified — and every token must carry an
    expiry: one without `exp` would never expire."""
    settings = _settings()
    verifiers = settings.jwt_verifiers
    # A `kid` naming one of our public keys goes first; it's only a hint, the
    # signature still has to verify.
    kid = _unverified_header_field(token, "kid")
    if kid:
        verifiers = sorted(verifiers, key=lambda v: v[0] != kid)
    for _kid, key, algorithm in verifiers:
        try:
            return jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                options={"require_exp": True},
            )
        except ExpiredSignatureError as exc:
            # The signature matched this key; the token is just old.
            raise ValueError("expired") from exc
        except JWTError:
            continue
    raise ValueError("invalid")


def decode_typed_token(token: str, expected_type: str) -> dict:
    payload = decode_token(token)

    if payload.get("token_type") != expected_type:
        raise ValueError("wrong_type")

    if not payload.get("sub") or not payload.get("jti"):
        raise ValueError("missing_claim")

    return payload


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def jwks() -> dict:
    """The public keys tokens can be verified with, as a JSON Web Key Set
    (served at /.well-known/jwks.json). Only public halves are ever included;
    empty under HS256, where verifying needs the shared secret."""
    from jose import jwk

    keys = []
    for kid, pem in _settings().jwt_public_keys:
        entry = jwk.construct(pem, "RS256").to_dict()
        entry.update({"kid": kid, "use": "sig", "alg": "RS256"})
        keys.append(entry)
    return {"keys": keys}
