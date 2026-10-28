"""Company-scoped authorization (Foundation Core architecture requirement).

The JWT carries `company_id`, but until now nothing server-side actually
enforced it: any `admin`/`operator` could read or write any Company's or
Employee's data by simply passing a different id, regardless of their own
`company_id`. This module is the single, centralized place that check lives
— call it from the service layer (not scattered per-route) for every
company-scoped resource lookup.

Scope of what's enforced here, matching how this repo's roles actually
work (see app/core/roles.py, app/core/permissions.py):

- `admin` is a global/platform role in this codebase today (it already sees
  every user and company via `GET /auth/overview`, bootstraps the system,
  and can change anyone's role) — it stays exempt from company scoping,
  the same "legitimate internal/global operation" carve-out the task
  describes. `operator` and `read_only` are scoped to their own company.
- Only Company and Employee are scoped here — both actually carry a
  `company_id`. Supplier and Asset have no `company_id` column at all; per
  the existing architecture (see app/models/supplier.py), they are one
  flat, company-wide catalog every company's data can reference, not a
  per-company resource — so there is nothing to scope there without a
  schema change out of bounds for this pass.

On a mismatch, the caller gets the exact same "not found" error the
resource's normal missing-id path already returns — never a distinguishable
403 — so a non-admin can't use this endpoint to fingerprint which ids exist
in other companies (avoids resource-existence leakage).
"""
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.roles import Role
from app.models.user import User


def enforce_company_scope(
    db: Session,
    current_user: User,
    resource_company_id: int,
    not_found_error: AuthError,
    resource_type: str,
    resource_id: str | int | None,
) -> None:
    """Raise `not_found_error` if current_user may not touch this company's data.

    `db` + `resource_type`/`resource_id` are only used to record the audit
    event for the denial (doc: authorization failures must be audited) —
    imported locally to avoid a core -> services import cycle, same pattern
    already used by app/core/dependencies.py's _record_access_denied.
    """
    if current_user.role == Role.ADMIN:
        return
    if current_user.company_id == resource_company_id:
        return

    from app.database.database import commit_now
    from app.services.audit_service import record_audit_event

    # The request is about to fail: drop anything it wrote so far, then keep
    # only the denial record (committed now, since the failing request's
    # transaction is rolled back).
    actor_id, actor_role = current_user.id, current_user.role
    db.rollback()
    record_audit_event(
        db,
        actor_id,
        "access_denied",
        "rbac",
        resource_id=actor_id,
        old_value=None,
        new_value={
            "reason": "cross_company",
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id is not None else None,
            "role": actor_role,
        },
    )
    commit_now(db)
    raise not_found_error
