"""Role -> Permission mapping (Foundation Core Module 7).

Single source of truth for which roles may perform which action on which
resource. Route files ask this module for the allowed-role set instead of
hardcoding Role.ADMIN / Role.OPERATOR combinations inline — so "who can
delete a company" has exactly one place to look, not one per route file.

This also completes what Module 2 (RBAC) deliberately deferred as its
"permission matrix enforcement" item, back when there was only one gated
resource to reason about.

Permission inheritance: Role.ADMIN is this codebase's global/platform role
(see app/core/tenancy.py) and must always be able to perform every action
on every resource. That used to depend on every single entry below
remembering to list Role.ADMIN explicitly — easy to get right today, easy
to silently forget the day someone adds a new resource/action and admin
quietly loses access to it, with nothing catching the omission. allowed_roles()
now unions Role.ADMIN into every result structurally, so PERMISSIONS itself
only needs to record the non-admin roles — there is no entry left to forget.
test_permissions.py asserts this invariant directly.
"""
from app.core.roles import Role

PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "company": {
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": {Role.OPERATOR},
        "delete": set(),
    },
    "employee": {
        # PII-bearing resource — read is intentionally NOT open to read_only,
        # unlike company data.
        "read": {Role.OPERATOR},
        "write": {Role.OPERATOR},
        "delete": set(),
        "link_user": set(),
    },
    "supplier": {
        # Not PII-bearing — same openness as company data. No "delete" entry:
        # the doc lists no soft-delete logic for Suppliers, only the
        # onboarded/approved/suspended status machine (suspend serves the
        # same "take this supplier out of use" purpose delete would).
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": {Role.OPERATOR},
    },
    "asset": {
        # Not PII-bearing — open reads like company/supplier. Has an explicit
        # DELETE endpoint per the doc's Foundation Core API list, so unlike
        # Supplier it does get a "delete" entry, admin-only like Company's.
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": {Role.OPERATOR},
        "delete": set(),
    },
    "job_role": {
        # Master/reference data shared by every company (the Employee
        # form's Job role dropdown) — every role needs read access to
        # populate that dropdown, but only admin can edit the shared list
        # itself, same reasoning as audit_log being admin-only: a change
        # here is global, not scoped to one operator's own company.
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": set(),
        "delete": set(),
    },
    "department": {
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": set(),
        "delete": set(),
    },
    "application": {
        # Master/reference data for the Employee form's application-access
        # checkboxes — same reasoning as job_role/department above: every
        # role needs read access to populate the checkbox list, only admin
        # can edit the shared master list itself.
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": set(),
        "delete": set(),
    },
    "manufacturer": {
        # Master/reference data for the Asset form's Manufacturer
        # dropdown — same reasoning as job_role/department/application
        # above.
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": set(),
        "delete": set(),
    },
    "asset_model": {
        # Master/reference data for the Asset form's Model dropdown —
        # same reasoning as job_role/department/application above.
        "read": {Role.OPERATOR, Role.READ_ONLY},
        "write": set(),
        "delete": set(),
    },
    "audit_log": {
        # The most sensitive resource in the system — it shows every change,
        # every login attempt, and every access denial across every other
        # module. Admin-only (which now falls out of allowed_roles() unioning
        # in Role.ADMIN below, since no other role is listed here at all),
        # and there is no "write"/"delete" entry at all: nothing in the app
        # is ever allowed to create or modify one through the API — see
        # app/services/audit_service.record_audit_event, the only writer,
        # called only from inside other services.
        "read": set(),
    },
    "event": {
        # Same sensitivity/shape as audit_log above — every event mirrors an
        # audit row 1:1 (see record_audit_event), so it carries the same
        # information. Admin-only read, no write/delete entry: the only
        # writer is app/services/event_service.publish_event, called only
        # from inside record_audit_event.
        "read": set(),
    },
}


def allowed_roles(resource: str, action: str) -> set[str]:
    try:
        roles = PERMISSIONS[resource][action]
    except KeyError as exc:
        raise KeyError(
            f"No permission entry for resource={resource!r} action={action!r}. "
            "Add one to app/core/permissions.py — don't hardcode roles in a route."
        ) from exc
    return roles | {Role.ADMIN}
