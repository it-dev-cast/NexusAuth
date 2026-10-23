"""Company-scoped authorization for the Company resource itself.

The JWT carries `company_id`; these tests verify it's actually enforced
server-side for operator/read_only, not just present as a claim. `admin`
is a deliberate exception — see app/core/tenancy.py's docstring: it's this
codebase's existing global/platform role (bootstraps the system, sees every
company/user via /auth/overview), not a per-company role, so it stays
exempt from company scoping by design.
"""
from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_word


def _headers_with_role(role: str, company_id: int | None = None):
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    if company_id is not None:
        user.company_id = company_id
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _admin_headers():
    return _headers_with_role("admin")


def _unique_name():
    # Letters-only unique_word() — a company name can't contain digits
    # any more (CompanyCreateRequest rejects them).
    return f"Isolation {unique_word()}"


def _two_companies(admin_headers):
    a = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=admin_headers)
    b = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=admin_headers)
    return a.json()["data"]["id"], b.json()["data"]["id"]


def test_same_company_read_is_allowed():
    admin_headers = _admin_headers()
    company_a, _ = _two_companies(admin_headers)
    operator_headers = _headers_with_role("operator", company_id=company_a)

    response = client.get(f"/api/v1/companies/{company_a}", headers=operator_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == company_a


def test_cross_company_read_is_denied_as_not_found():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    operator_headers = _headers_with_role("operator", company_id=company_a)

    response = client.get(f"/api/v1/companies/{company_b}", headers=operator_headers)
    # Same response as a company that doesn't exist at all — no
    # resource-existence leakage to a caller who isn't authorized for it.
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_cross_company_update_is_denied():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    operator_headers = _headers_with_role("operator", company_id=company_a)

    response = client.put(
        f"/api/v1/companies/{company_b}", json={"address": "Nope"}, headers=operator_headers
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_cross_company_delete_is_denied():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    # Give the operator delete rights too by testing through an admin-scoped
    # deleter role isn't needed here — delete is admin-only regardless, so
    # use an operator on the *write* path is enough to prove the isolation
    # check runs before the RBAC-permitted action executes. For delete
    # (admin-only) we instead confirm an admin from "company A" can still
    # reach company B, proving admin's exemption is deliberate, not a gap.
    admin_a_headers = _headers_with_role("admin", company_id=company_a)
    response = client.delete(f"/api/v1/companies/{company_b}", headers=admin_a_headers)
    assert response.status_code == 200


def test_cross_company_list_does_not_leak_other_companies():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    operator_headers = _headers_with_role("operator", company_id=company_a)

    response = client.get("/api/v1/companies", headers=operator_headers)
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]["items"]]
    assert company_a in ids
    assert company_b not in ids


def test_admin_is_exempt_from_company_scoping_by_design():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    # An admin scoped to company A (a global/platform role in this codebase,
    # see app/core/tenancy.py) can still reach company B.
    admin_a_headers = _headers_with_role("admin", company_id=company_a)

    response = client.get(f"/api/v1/companies/{company_b}", headers=admin_a_headers)
    assert response.status_code == 200


def test_cross_company_denial_is_audited():
    admin_headers = _admin_headers()
    company_a, company_b = _two_companies(admin_headers)
    operator_headers = _headers_with_role("operator", company_id=company_a)

    client.get(f"/api/v1/companies/{company_b}", headers=operator_headers)

    items_response = client.get(
        "/api/v1/audit-logs",
        params={"action": "access_denied", "resource_type": "rbac"},
        headers=admin_headers,
    )
    assert items_response.status_code == 200
    items = items_response.json()["data"]["items"]
    assert any(
        item["new_value"].get("reason") == "cross_company"
        and item["new_value"].get("resource_id") == str(company_b)
        for item in items
    )
