"""Permission-inheritance guarantee (Foundation Core Module 7).

Role.ADMIN must always be able to perform every permitted action on every
resource. Previously that only held because every single PERMISSIONS entry
remembered to list Role.ADMIN explicitly — nothing enforced it, so a new
resource/action added later without remembering to include admin would
silently lock admin out, with no test catching it. allowed_roles() now
unions Role.ADMIN in structurally; these tests assert that directly rather
than relying on every current and future PERMISSIONS entry getting it right.
"""
from app.core.permissions import PERMISSIONS, allowed_roles
from app.core.roles import Role


def test_admin_is_allowed_every_existing_resource_action():
    for resource, actions in PERMISSIONS.items():
        for action in actions:
            assert Role.ADMIN in allowed_roles(resource, action), (
                f"admin missing from {resource}/{action}"
            )


def test_admin_is_allowed_even_when_permissions_entry_lists_nobody():
    # A resource/action nobody else may perform (e.g. audit_log's "read" is
    # admin-only, PERMISSIONS itself records that as an empty set) must
    # still resolve to admin — this is the actual regression this guards:
    # forgetting to list Role.ADMIN in a PERMISSIONS entry must be
    # impossible to get wrong, not just currently correct.
    assert PERMISSIONS["audit_log"]["read"] == set()
    assert allowed_roles("audit_log", "read") == {Role.ADMIN}


def test_permissions_entries_do_not_need_to_list_admin_explicitly():
    # Documents the new contract: PERMISSIONS records only the non-admin
    # roles allowed for an action. If a future edit re-adds Role.ADMIN
    # directly to an entry it's harmless (union is idempotent) but
    # unnecessary — this test just pins today's entries to that contract.
    for actions in PERMISSIONS.values():
        for allowed in actions.values():
            assert Role.ADMIN not in allowed


def test_unknown_resource_or_action_still_raises():
    import pytest

    with pytest.raises(KeyError):
        allowed_roles("no_such_resource", "read")
    with pytest.raises(KeyError):
        allowed_roles("company", "no_such_action")


def test_permissions_for_role_matches_allowed_roles():
    from app.core.permissions import permissions_for_role

    for role in (Role.ADMIN, Role.OPERATOR, Role.READ_ONLY):
        granted = permissions_for_role(role)
        for resource, actions in PERMISSIONS.items():
            for action in actions:
                assert (action in granted.get(resource, [])) == (
                    role in allowed_roles(resource, action)
                ), f"{role} {resource}/{action}"


def test_me_returns_the_callers_permissions():
    from app.database.database import SessionLocal
    from app.models.user import User
    from app.tests.conftest import PASSWORD, client, register_and_login

    expected = {
        Role.OPERATOR: {"employee": ["read", "write"], "supplier": ["read", "write"]},
        Role.READ_ONLY: {"supplier": ["read"], "asset": ["read"]},
    }
    for role, must_include in expected.items():
        email, _ = register_and_login()
        db = SessionLocal()
        db.query(User).filter(User.email == email).update({"role": role})
        db.commit()
        db.close()
        access = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["data"]["access_token"]
        me = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
        ).json()["data"]
        for resource, actions in must_include.items():
            assert me["permissions"][resource] == actions
        # Admin-only areas never show up for these roles.
        assert "audit_log" not in me["permissions"]
        assert "event" not in me["permissions"]
    assert "employee" not in me["permissions"]  # read_only: PII stays hidden
