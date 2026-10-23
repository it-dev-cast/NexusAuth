from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AuthError
from app.core.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_typed_token,
    hash_refresh_token,
)
from app.core.logging import log_role_change
from app.core.password_service import hash_password, verify_password
from app.core.roles import ALL_ROLES, Role
from app.models.auth_session import AuthSession
from app.models.company import Company
from app.models.user import User
from app.repositories import (
    add_revoked_token,
    create_company,
    create_session,
    create_user,
    get_company_by_name,
    get_session_by_access_jti,
    get_session_by_refresh_hash,
    get_session_for_user,
    get_user_by_email,
    get_user_by_id,
    increment_failed_logins,
    list_active_sessions,
    list_recent_sessions,
    list_users,
    record_successful_login,
    reset_failed_logins,
    revoke_session_row,
    sum_failed_logins,
    sum_login_count,
    count_sessions,
    count_users,
    count_active_sessions_by_user,
    touch_session,
)
from app.services.audit_service import record_audit_event

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenData,
    UserResponse,
)


def _auth_error(code: str, message: str, status_code: int = 401) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _default_company_id(db: Session) -> int:
    """The internal Casterly company every user is scoped to until real
    multi-company assignment (Module 4+) exists. Self-heals on a fresh
    database where the migration's backfill hasn't run yet."""
    company = get_company_by_name(db, "Casterly")
    if company:
        return company.id
    company = create_company(
        db,
        Company(name="Casterly", company_type="internal", is_active=True),
    )
    return company.id


def _client_meta(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if user_agent and len(user_agent) > 512:
        user_agent = user_agent[:512]
    return ip_address, user_agent


def _exp_datetime(exp) -> datetime:
    now = datetime.now(timezone.utc)
    if isinstance(exp, int):
        return datetime.fromtimestamp(exp, tz=timezone.utc)
    return now


def _revoke_access_jti(
    db: Session,
    user_id: int,
    jti: str | None,
    expires_at: datetime,
    reason: str,
) -> None:
    if not jti:
        return
    add_revoked_token(db, jti, user_id, expires_at, reason)


def _revoke_session_fully(db: Session, session: AuthSession, now: datetime, reason: str) -> None:
    """Single entry point for revoking a session.

    RevokedToken (the access-token deny list) and AuthSession.is_revoked
    (the refresh-token side) used to be maintained independently — most
    call sites remembered to update both, but refresh_tokens() only ever
    flipped is_revoked on the session row, silently leaving that session's
    old access token usable (not deny-listed) until it naturally expired.
    Routing every "fully revoke this session" call through here means the
    two halves can no longer drift apart.

    Also writes a RevokedToken row for the refresh side (token_type=
    "refresh", identified by refresh_token_hash rather than a jti — see
    add_revoked_token's docstring). AuthSession.is_revoked remains the
    actual enforcement check for refresh tokens; this just makes
    RevokedToken a complete, single-table record of every revocation
    instead of only ever showing the access-token half.
    """
    revoke_session_row(db, session, now)
    _revoke_access_jti(db, session.user_id, session.access_token_jti, session.expires_at, reason)
    add_revoked_token(
        db,
        session.refresh_token_hash,
        session.user_id,
        session.expires_at,
        reason,
        token_type="refresh",
    )


# A fixed, precomputed bcrypt hash — never a real user's — used only to pay
# the same bcrypt cost on an unknown-email login attempt as a real one.
# Without this, `not user or not verify_password(...)` short-circuits and
# skips bcrypt entirely when the email doesn't exist, making that path
# measurably faster than "wrong password for a real account" — a timing
# side channel an attacker can use to enumerate valid emails even though
# both cases return the same 401 body.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-timing-decoy-only")


def issue_tokens(
    db: Session,
    user: User,
    request: Request | None = None,
) -> dict:
    settings = get_settings()
    access_token, access_jti = create_access_token(
        user.id,
        user.role,
        user.company_id or _default_company_id(db),
    )
    refresh_token = create_refresh_token(user.id)
    now = datetime.now(timezone.utc)
    ip_address, user_agent = _client_meta(request)

    create_session(
        db,
        AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_refresh_token(refresh_token),
            access_token_jti=access_jti,
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            is_revoked=False,
            ip_address=ip_address,
            user_agent=user_agent,
        ),
    )

    return TokenData(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
    ).model_dump()


def register_user(db: Session, data: RegisterRequest) -> User:
    if get_user_by_email(db, data.email):
        raise _auth_error(
            "AUTH_ACCOUNT_EXISTS",
            "Unable to create account.",
            status_code=400,
        )

    role = Role.READ_ONLY
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=role,
        company_id=_default_company_id(db),
        is_active=True,
        failed_login_attempts=0,
    )
    return create_user(db, user)


def _record_login_failure(db: Session, user: User | None, attempted_email: str, reason: str) -> None:
    # Doc: "Authentication attempt logging (success/failure)" + "PII marking
    # in audit (email, phone fields)" — the attempted email is PII even on a
    # failed attempt, so it goes through the same masking as everything else
    # (see app/core/audit.py's _MASK_PARTIAL set).
    record_audit_event(
        db,
        user.id if user else None,
        "login_failure",
        "auth",
        resource_id=user.id if user else None,
        old_value=None,
        new_value={"attempted_email": attempted_email, "reason": reason},
        company_id=user.company_id if user else None,
    )


def login_user(db: Session, data: LoginRequest, request: Request | None = None) -> dict:
    user = get_user_by_email(db, data.email)
    # Always run a bcrypt comparison, even when the email doesn't exist —
    # against the fixed decoy hash rather than skipping it — so an unknown
    # email and a wrong password for a real account cost the same amount
    # of time. See _DUMMY_PASSWORD_HASH's docstring.
    password_ok = verify_password(
        data.password, user.password_hash if user else _DUMMY_PASSWORD_HASH
    )

    # Checked before the credentials branch below (and regardless of
    # whether this attempt's password happens to be correct) — a locked
    # account rejects every login attempt until it unlocks or an admin
    # clears it, not just wrong-password ones. See
    # auth_repository.increment_failed_logins for where locked_until gets
    # set, and unlock_user_account for the admin override.
    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc).replace(tzinfo=None):
        _record_login_failure(db, user, data.email, "account_locked")
        raise _auth_error(
            "AUTH_ACCOUNT_LOCKED",
            "This account is temporarily locked due to repeated failed login "
            "attempts. Try again later or contact an administrator.",
            status_code=403,
        )

    if not user or not password_ok:
        if user:
            settings = get_settings()
            increment_failed_logins(
                db, user, settings.max_failed_login_attempts, settings.account_lockout_minutes
            )
        _record_login_failure(db, user, data.email, "invalid_credentials")
        raise _auth_error(
            "AUTH_INVALID_CREDENTIALS",
            "Invalid email or password.",
        )

    if not user.is_active:
        _record_login_failure(db, user, data.email, "inactive_account")
        raise _auth_error(
            "AUTH_INVALID_CREDENTIALS",
            "Invalid email or password.",
        )

    record_successful_login(db, user)
    record_audit_event(
        db, user.id, "login_success", "auth", resource_id=user.id, old_value=None, new_value=None,
        company_id=user.company_id,
    )
    return issue_tokens(db, user, request)


def refresh_tokens(
    db: Session,
    data: RefreshRequest,
    request: Request | None = None,
) -> dict:
    try:
        decode_typed_token(data.refresh_token, "refresh")
    except ValueError as exc:
        reason = str(exc)
        if reason == "expired":
            raise _auth_error("AUTH_TOKEN_EXPIRED", "Refresh token has expired.")
        if reason == "wrong_type":
            raise _auth_error("AUTH_INVALID_TOKEN", "Invalid refresh token.")
        raise _auth_error("AUTH_INVALID_TOKEN", "Invalid refresh token.") from exc

    session = get_session_by_refresh_hash(db, hash_refresh_token(data.refresh_token))
    if not session:
        raise _auth_error("AUTH_INVALID_TOKEN", "Invalid refresh token.")

    now = datetime.now(timezone.utc)
    if session.is_revoked:
        # A refresh token is one-time-use — rotation immediately revokes
        # it (below). Seeing an already-revoked one presented again means
        # either a replayed/stolen copy, or the legitimate client retrying
        # a request whose response it never received; we can't tell those
        # apart, so the safe response is the same one real IdPs use for
        # detected refresh-token reuse: revoke every session this user
        # has, not just the reused one, forcing a fresh login everywhere.
        _handle_suspected_refresh_reuse(db, session)
        raise _auth_error(
            "AUTH_TOKEN_REVOKED",
            "Refresh token has been revoked.",
        )

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        raise _auth_error("AUTH_TOKEN_EXPIRED", "Refresh token has expired.")

    user = get_user_by_id(db, session.user_id)
    if not user or not user.is_active:
        raise _auth_error("AUTH_INVALID_TOKEN", "Invalid refresh token.")

    _revoke_session_fully(db, session, now, "refresh_rotation")
    db.commit()
    return issue_tokens(db, user, request)


def _handle_suspected_refresh_reuse(db: Session, session: AuthSession) -> None:
    now = datetime.now(timezone.utc)
    for other in list_active_sessions(db, session.user_id):
        _revoke_session_fully(db, other, now, "refresh_reuse_detected")
    db.commit()
    # No company_id passed — AuthSession has no user relationship loaded
    # here, only the bare user_id, and this is a rare security event, not
    # worth an extra query just to populate one optional event field.
    record_audit_event(
        db,
        session.user_id,
        "refresh_reuse_detected",
        "auth",
        resource_id=session.user_id,
        old_value=None,
        new_value={"session_id": session.id},
    )


def logout_user(db: Session, current_user: User) -> dict:
    now = datetime.now(timezone.utc)
    claims = getattr(current_user, "token_claims", {})
    access_jti = claims.get("jti")
    _revoke_access_jti(
        db,
        current_user.id,
        access_jti,
        _exp_datetime(claims.get("exp")),
        "logout",
    )
    if access_jti:
        session = get_session_by_access_jti(db, access_jti)
        if session and not session.is_revoked:
            _revoke_session_fully(db, session, now, "logout")
    db.commit()
    return {"message": "Logged out successfully"}


def logout_all_sessions(db: Session, current_user: User) -> dict:
    now = datetime.now(timezone.utc)
    claims = getattr(current_user, "token_claims", {})
    _revoke_access_jti(
        db,
        current_user.id,
        claims.get("jti"),
        _exp_datetime(claims.get("exp")),
        "logout_all",
    )
    for session in list_active_sessions(db, current_user.id):
        _revoke_session_fully(db, session, now, "logout_all")
    db.commit()
    return {"message": "All sessions logged out"}


def current_user_payload(db: Session, current_user: User) -> dict:
    claims = getattr(current_user, "token_claims", {})
    access_jti = claims.get("jti")
    if access_jti:
        session = get_session_by_access_jti(db, access_jti)
        if session and not session.is_revoked:
            touch_session(db, session)
    return {
        **UserResponse.model_validate(current_user).model_dump(),
        "claims": {
            "user_id": claims.get("user_id") or claims.get("sub"),
            "roles": claims.get("roles"),
            "company_id": claims.get("company_id"),
            "jti": claims.get("jti"),
            "iat": claims.get("iat"),
            "exp": claims.get("exp"),
            "token_type": claims.get("token_type"),
        },
    }


def list_user_sessions(db: Session, current_user: User) -> list[dict]:
    return [
        {
            "id": session.id,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
            "last_used_at": session.last_used_at,
            "is_revoked": session.is_revoked,
            "ip_address": session.ip_address,
            "user_agent": session.user_agent,
        }
        for session in list_active_sessions(db, current_user.id)
    ]


def revoke_user_session(db: Session, current_user: User, session_id: int) -> dict:
    session = get_session_for_user(db, session_id, current_user.id)
    if not session:
        raise _auth_error(
            "AUTH_SESSION_NOT_FOUND",
            "Session not found.",
            status_code=404,
        )
    now = datetime.now(timezone.utc)
    if not session.is_revoked:
        _revoke_session_fully(db, session, now, "session_revoke")
        db.commit()
    return {"message": "Session revoked"}


def dashboard_overview(db: Session) -> dict:
    # One GROUP BY query for every user's active-session count instead of
    # one query per user inside the loop below — that N+1 (2,888 extra
    # round trips on the current seed data) was the entire reason this
    # endpoint took 2+ seconds while every sibling endpoint stayed under
    # 350ms, and it's on the hot path now that every Save/Edit/Delete
    # reloads the page and re-hits this endpoint.
    active_sessions_by_user = count_active_sessions_by_user(db)
    users = []
    # active_only=True — the Users page's own table draws from this same
    # list, and a deactivated test/seed account isn't meant to still show
    # up there just because its row hasn't been (and, per audit-log
    # immutability, can't be) physically deleted.
    for user in list_users(db, active_only=True):
        users.append(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "company_id": user.company_id,
                "is_active": user.is_active,
                "login_count": user.login_count or 0,
                "failed_login_attempts": user.failed_login_attempts or 0,
                "locked_until": user.locked_until,
                "last_login_at": user.last_login_at,
                "created_at": user.created_at,
                "active_sessions": active_sessions_by_user.get(user.id, 0),
            }
        )

    sessions = []
    for session, email in list_recent_sessions(db):
        sessions.append(
            {
                "id": session.id,
                "user_id": session.user_id,
                "email": email,
                "created_at": session.created_at,
                "expires_at": session.expires_at,
                "last_used_at": session.last_used_at,
                "is_revoked": session.is_revoked,
                "ip_address": session.ip_address,
            }
        )

    return {
        # active_only=True — the dashboard's own "how many accounts/logins
        # actually matter right now" view, not a raw count of every user
        # row that has ever existed (a deactivated test account's old
        # login_count still exists on its row, but it shouldn't inflate
        # what the currently-real accounts show).
        "registered_users": count_users(db, active_only=True),
        "total_logins": int(sum_login_count(db, active_only=True)),
        "failed_logins": int(sum_failed_logins(db, active_only=True)),
        "active_sessions": count_sessions(db, active_only=True),
        "revoked_sessions": count_sessions(db, active_only=False),
        "users": users,
        "sessions": sessions,
    }


def bootstrap_admin(db: Session) -> None:
    if db.query(User).filter(User.role == Role.ADMIN).first():
        return
    admin = db.query(User).filter(User.email == "admin@casterly.com").first()
    if admin:
        admin.role = Role.ADMIN
        db.commit()
        return
    if count_users(db) == 0:
        create_user(
            db,
            User(
                email="admin@casterly.com",
                password_hash=hash_password("ExamplePasswordOnly"),
                full_name="Administrator",
                role=Role.ADMIN,
                company_id=_default_company_id(db),
                is_active=True,
                failed_login_attempts=0,
            ),
        )
        return
    first = db.query(User).order_by(User.id.asc()).first()
    if first:
        first.role = Role.ADMIN
        db.commit()


def update_user_role(db: Session, actor: User, user_id: int, role: str) -> User:
    role = (role or "").strip().lower()
    if role not in ALL_ROLES:
        raise _auth_error(
            "AUTH_INVALID_ROLE",
            f"Role must be one of: {', '.join(sorted(ALL_ROLES))}.",
            status_code=400,
        )
    target = get_user_by_id(db, user_id)
    if not target:
        raise _auth_error(
            "AUTH_USER_NOT_FOUND",
            "User not found.",
            status_code=404,
        )
    if target.id == actor.id and role != Role.ADMIN:
        admin_count = db.query(User).filter(User.role == Role.ADMIN).count()
        if admin_count <= 1:
            raise _auth_error(
                "AUTH_FORBIDDEN",
                "Cannot remove the last admin.",
                status_code=403,
            )
    old_role = target.role
    target.role = role
    db.commit()
    db.refresh(target)
    log_role_change(actor.id, actor.email, target.id, old_role, target.role)
    # Doc: audit coverage for state transitions — a role change is a
    # security-relevant state change on the target user, same class of
    # event as Employee/Supplier/Asset status_transition, and belongs in
    # the queryable audit trail, not just the plain-text rbac log line
    # log_role_change() already writes.
    record_audit_event(
        db,
        actor.id,
        "role_change",
        "user",
        target.id,
        old_value={"role": old_role},
        new_value={"role": target.role},
        company_id=target.company_id,
    )
    return target


def unlock_user_account(db: Session, actor: User, user_id: int) -> User:
    """Doc: "Account unlock mechanism" (NEXUS_ONE_ARCHITECTURE_PLAN §3,
    Module 10: Security) — the admin-only counterpart to the automatic
    lock login_user applies after max_failed_login_attempts. Clears both
    the lock and the counter (reset_failed_logins), not just locked_until,
    so the user doesn't immediately re-lock on their very next attempt
    with a stale near-threshold count."""
    target = get_user_by_id(db, user_id)
    if not target:
        raise _auth_error("AUTH_USER_NOT_FOUND", "User not found.", status_code=404)

    was_locked = target.locked_until is not None
    old_snapshot = {"locked_until": target.locked_until, "failed_login_attempts": target.failed_login_attempts}
    reset_failed_logins(db, target)
    db.refresh(target)
    if was_locked:
        record_audit_event(
            db,
            actor.id,
            "update",
            "user",
            target.id,
            old_value=old_snapshot,
            new_value={"locked_until": None, "failed_login_attempts": 0},
            company_id=target.company_id,
        )
    return target


def change_password(db: Session, current_user: User, current_password: str, new_password: str) -> None:
    """Doc: "User password update" (Module 10: User & Identity Management).
    Requires the caller's current password (not just an active session) —
    same "prove you still are who you say you are" pattern a bank/OS uses
    before letting you change your own credential. Logs out every other
    session afterward (same reasoning as a detected refresh-token reuse:
    a changed password should invalidate whatever else was already logged
    in, in case the change was prompted by a compromised credential).
    """
    if not verify_password(current_password, current_user.password_hash):
        raise _auth_error("AUTH_INVALID_CREDENTIALS", "Current password is incorrect.")
    current_user.password_hash = hash_password(new_password)
    db.commit()
    record_audit_event(
        db, current_user.id, "password_change", "user", current_user.id, old_value=None, new_value=None,
        company_id=current_user.company_id,
    )
    logout_all_sessions(db, current_user)
