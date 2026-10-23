from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.jwt_service import decode_typed_token
from app.core.logging import log_rbac_denied
from app.database.database import get_db
from app.models.revoked_token import RevokedToken
from app.models.user import User


security = HTTPBearer(auto_error=False)


def _token_error(code: str, message: str) -> AuthError:
    return AuthError(
        status_code=401,
        error_code=code,
        message=message,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    return _load_user(credentials, db, allow_revoked=False)


def get_logout_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    return _load_user(credentials, db, allow_revoked=True)


def _load_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    allow_revoked: bool,
) -> User:
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not credentials.credentials
    ):
        raise _token_error(
            "AUTH_MALFORMED_HEADER",
            "Missing or invalid Authorization header.",
        )

    try:
        payload = decode_typed_token(
            credentials.credentials,
            "access",
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "expired":
            raise _token_error("AUTH_TOKEN_EXPIRED", "Access token has expired.")
        if reason == "wrong_type":
            raise _token_error("AUTH_INVALID_TOKEN", "Invalid access token.")
        if reason == "missing_claim":
            raise _token_error("AUTH_INVALID_TOKEN", "Access token is missing required claims.")
        raise _token_error("AUTH_INVALID_TOKEN", "Invalid access token.") from exc

    revoked = (
        db.query(RevokedToken)
        .filter(RevokedToken.jti == payload["jti"])
        .first()
    )
    if revoked and not allow_revoked:
        raise _token_error(
            "AUTH_TOKEN_REVOKED",
            "Access token has been revoked.",
        )

    user = (
        db.query(User)
        .filter(User.id == int(payload["sub"]))
        .first()
    )

    if not user or not user.is_active:
        raise _token_error(
            "AUTH_INVALID_TOKEN",
            "Invalid access token.",
        )

    user.token_claims = payload
    return user


def _record_access_denied(db: Session, current_user: User, endpoint: str) -> None:
    # Local import: app.services.audit_service -> app.repositories -> (no
    # cycle back here), but importing at module level would still make this
    # file depend on the service layer, which core/ modules deliberately
    # don't. Doc: "Unauthorized access logging (403 denials)" (Module 8) —
    # distinct from log_rbac_denied's plain-text log line (Module 2/7).
    from app.services.audit_service import record_audit_event

    record_audit_event(
        db,
        current_user.id,
        "access_denied",
        "rbac",
        resource_id=current_user.id,
        old_value=None,
        new_value={"endpoint": endpoint, "role": current_user.role},
    )


def require_roles(*allowed: str):
    allowed_roles = set(allowed)

    def checker(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if current_user.role not in allowed_roles:
            log_rbac_denied(
                current_user.id,
                current_user.email,
                current_user.role,
                request.url.path,
            )
            _record_access_denied(db, current_user, request.url.path)
            raise AuthError(
                status_code=403,
                error_code="AUTH_FORBIDDEN",
                message="You do not have permission to access this resource.",
            )
        return current_user

    return checker


def get_admin_user(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if current_user.role != "admin":
        log_rbac_denied(
            current_user.id,
            current_user.email,
            current_user.role,
            request.url.path,
        )
        _record_access_denied(db, current_user, request.url.path)
        raise AuthError(
            status_code=403,
            error_code="AUTH_FORBIDDEN",
            message="You do not have permission to access this resource.",
        )
    return current_user
