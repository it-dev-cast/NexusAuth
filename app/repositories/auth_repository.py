from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession
from app.models.revoked_token import RevokedToken
from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    # Email addresses are matched case-insensitively: "Ravi@x.com" and
    # "ravi@x.com" are the same mailbox, so they must be the same account for
    # both the register duplicate check and login. New accounts are stored
    # lowercased (RegisterRequest); lower() here also finds older rows saved
    # with capitals. If case-only duplicates already exist, the oldest wins.
    return (
        db.query(User)
        .filter(func.lower(User.email) == email.strip().lower())
        .order_by(User.id)
        .first()
    )


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user: User) -> User:
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def increment_failed_logins(db: Session, user: User, max_attempts: int, lock_minutes: int) -> None:
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= max_attempts:
        # locked_until is a naive DateTime column (no timezone=True) — store
        # a naive UTC value to match, not an aware one. datetime.utcnow() is
        # deprecated, so this gets a naive UTC datetime by stripping tzinfo
        # off an aware one instead (see login_user's comparison side, which
        # does the same before comparing).
        user.locked_until = (datetime.now(timezone.utc) + timedelta(minutes=lock_minutes)).replace(tzinfo=None)
    db.commit()


def reset_failed_logins(db: Session, user: User) -> None:
    """Admin unlock — clears the counter and any active lock without
    touching login_count/last_login_at (those belong to an actual
    successful login, see record_successful_login)."""
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()


def record_successful_login(db: Session, user: User) -> None:
    user.failed_login_attempts = 0
    user.locked_until = None
    user.login_count = (user.login_count or 0) + 1
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()


def list_users(db: Session, active_only: bool = False) -> list[User]:
    query = db.query(User)
    if active_only:
        query = query.filter(User.is_active == True)  # noqa: E712
    return query.order_by(User.id.asc()).all()


def count_users(db: Session, active_only: bool = False) -> int:
    query = db.query(func.count(User.id))
    if active_only:
        query = query.filter(User.is_active == True)  # noqa: E712
    return query.scalar() or 0


# active_only defaults to False on all three so bootstrap_admin's existing
# `count_users(db) == 0` "has any account ever been created" check keeps
# its original meaning — only the Overview dashboard opts into
# active-only, via an explicit True at its own call site below.
def sum_login_count(db: Session, active_only: bool = False) -> int:
    query = db.query(func.coalesce(func.sum(User.login_count), 0))
    if active_only:
        query = query.filter(User.is_active == True)  # noqa: E712
    return query.scalar() or 0


def sum_failed_logins(db: Session, active_only: bool = False) -> int:
    query = db.query(func.coalesce(func.sum(User.failed_login_attempts), 0))
    if active_only:
        query = query.filter(User.is_active == True)  # noqa: E712
    return query.scalar() or 0


def count_sessions(db: Session, active_only: bool | None = None) -> int:
    query = db.query(func.count(AuthSession.id))
    if active_only is True:
        query = query.filter(AuthSession.is_revoked == False)  # noqa: E712
    elif active_only is False:
        query = query.filter(AuthSession.is_revoked == True)  # noqa: E712
    return query.scalar() or 0


def list_recent_sessions(db: Session, limit: int = 25) -> list[tuple[AuthSession, str]]:
    return (
        db.query(AuthSession, User.email)
        .join(User, User.id == AuthSession.user_id)
        .order_by(AuthSession.id.desc())
        .limit(limit)
        .all()
    )


def count_active_sessions_for_user(db: Session, user_id: int) -> int:
    return (
        db.query(func.count(AuthSession.id))
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.is_revoked == False,  # noqa: E712
        )
        .scalar()
        or 0
    )


def count_active_sessions_by_user(db: Session) -> dict[int, int]:
    # Batched form of count_active_sessions_for_user for callers that need
    # this per-user (e.g. the admin overview, over every registered user) —
    # one GROUP BY query instead of one query per user. Calling
    # count_active_sessions_for_user in a loop over N users is an N+1 that
    # scales with the user count; this is what dashboard_overview() below
    # uses instead.
    rows = (
        db.query(AuthSession.user_id, func.count(AuthSession.id))
        .filter(AuthSession.is_revoked == False)  # noqa: E712
        .group_by(AuthSession.user_id)
        .all()
    )
    return {user_id: count for user_id, count in rows}


def create_session(db: Session, session: AuthSession) -> AuthSession:
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_by_refresh_hash(db: Session, token_hash: str) -> AuthSession | None:
    return (
        db.query(AuthSession)
        .filter(AuthSession.refresh_token_hash == token_hash)
        .first()
    )


def get_session_by_access_jti(db: Session, jti: str) -> AuthSession | None:
    return (
        db.query(AuthSession)
        .filter(AuthSession.access_token_jti == jti)
        .first()
    )


def get_session_for_user(db: Session, session_id: int, user_id: int) -> AuthSession | None:
    return (
        db.query(AuthSession)
        .filter(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
        )
        .first()
    )


def list_active_sessions(db: Session, user_id: int) -> list[AuthSession]:
    return (
        db.query(AuthSession)
        .filter(
            AuthSession.user_id == user_id,
            AuthSession.is_revoked == False,  # noqa: E712
        )
        .all()
    )


def touch_session(db: Session, session: AuthSession) -> None:
    session.last_used_at = datetime.now(timezone.utc)
    db.commit()


def revoke_session_row(db: Session, session: AuthSession, now: datetime) -> None:
    session.is_revoked = True
    session.revoked_at = now
    session.last_used_at = now


def add_revoked_token(
    db: Session,
    jti: str,
    user_id: int,
    expires_at: datetime,
    reason: str,
    token_type: str = "access",
) -> None:
    """Record a revoked token so it's queryable in one place.

    `jti` holds a real JWT `jti` claim for `token_type="access"`. Refresh
    tokens aren't looked up by jti anywhere (that side is checked via
    AuthSession.is_revoked, keyed by refresh_token_hash — see
    _revoke_session_fully), so for `token_type="refresh"` this column holds
    the session's refresh_token_hash instead: same column, same uniqueness
    guarantee, just a different kind of identifier. This means a maintainer
    querying "every revoked token" no longer has to check two tables to get
    the full picture — refresh revocations show up here too, even though
    the enforcement path for refresh tokens is unchanged.
    """
    existing = db.query(RevokedToken).filter(RevokedToken.jti == jti).first()
    if existing:
        return
    db.add(
        RevokedToken(
            jti=jti,
            user_id=user_id,
            token_type=token_type,
            expires_at=expires_at,
            revoked_at=datetime.now(timezone.utc),
            reason=reason,
        )
    )
    # Bug fix: this session is created with autoflush=False (see
    # app/database/database.py), so without an explicit flush the row just
    # added above isn't visible to the next SELECT run against this same
    # Session — only after commit. logout_all_sessions() calls this
    # function once for the current request's access-token jti and again,
    # in its session loop, for that same session's access_token_jti (they
    # are the same value in the common case where the caller's own session
    # is still active). Without this flush, the second call's "does this
    # jti already exist" check misses the first call's not-yet-flushed
    # insert, so both get added and the unique constraint on `jti` raises
    # an IntegrityError on commit — logout-all would fail for the ordinary
    # case of "revoke every session including the one you're calling from."
    db.flush()
