import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _headers_with_role(role: str):
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _admin_headers():
    return _headers_with_role("admin")


def _audit_items(headers, **params):
    response = client.get("/api/v1/audit-logs", params=params, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["items"]


def test_creating_a_company_writes_an_audit_row():
    headers = _admin_headers()
    name = f"Acme {unique_word()}"
    created = client.post("/api/v1/companies", json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    items = _audit_items(headers, resource_type="company", resource_id=str(company_id))
    assert len(items) == 1
    assert items[0]["action"] == "create"
    assert items[0]["old_value"] is None
    assert items[0]["new_value"]["name"] == name


def test_updating_a_company_captures_before_and_after():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    company_id = created.json()["data"]["id"]

    client.put(f"/api/v1/companies/{company_id}", json={"address": "1 Main St"}, headers=headers)

    items = _audit_items(headers, resource_type="company", resource_id=str(company_id), action="update")
    assert len(items) == 1
    assert items[0]["old_value"]["address"] == "123 Test Street"
    assert items[0]["new_value"]["address"] == "1 Main St"


def test_employee_pii_is_masked_in_audit_snapshot():
    headers = _admin_headers()
    company = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    company_id = company.json()["data"]["id"]

    email = unique_email()
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Priya Sharma", "last_name": "Doe",
            "email": email,
            "bank_account_number": "1234567890",
            "pan_number": "ABCDE1234F",
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    items = _audit_items(headers, resource_type="employee", resource_id=str(employee_id))
    assert len(items) == 1
    snapshot = items[0]["new_value"]
    # Masked: last 4 characters survive, nothing else does. The API response
    # for GET /employees still returns these fields raw (see EmployeeResponse
    # / SECURITY_CHECKLIST.md's PROTOTYPE-ONLY note) — masking is specific
    # to what lands in the audit trail.
    assert snapshot["email"] != email
    assert snapshot["email"].endswith(email[-4:])
    assert snapshot["bank_account_number"] != "1234567890"
    assert snapshot["bank_account_number"].endswith("7890")
    assert "1234567890" not in str(snapshot)
    assert "ABCDE1234F" not in str(snapshot)


def test_status_transition_is_audited_as_its_own_action():
    headers = _admin_headers()
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Supplier {unique_email()}"}, headers=headers
    )
    supplier_id = supplier.json()["data"]["id"]

    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)

    items = _audit_items(
        headers, resource_type="supplier", resource_id=str(supplier_id), action="status_transition"
    )
    assert len(items) == 1
    assert items[0]["old_value"] == {"status": "onboarded"}
    assert items[0]["new_value"] == {"status": "approved"}


def test_login_success_and_failure_are_audited():
    email, _ = register_and_login()
    admin_headers = _admin_headers()

    # Failure first.
    client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword1"})
    # Then success.
    client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})

    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user_id = user.id
    db.close()

    failures = _audit_items(admin_headers, resource_type="auth", action="login_failure", user_id=user_id)
    successes = _audit_items(admin_headers, resource_type="auth", action="login_success", user_id=user_id)
    assert len(failures) >= 1
    assert len(successes) >= 1
    # The attempted email is PII too — masked even on a failed attempt.
    assert failures[0]["new_value"]["attempted_email"] != email


def test_forbidden_write_is_audited_as_access_denied():
    reader_headers = _headers_with_role("read_only")
    admin_headers = _admin_headers()

    response = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=reader_headers
    )
    assert response.status_code == 403

    items = _audit_items(admin_headers, resource_type="rbac", action="access_denied")
    assert any(item["new_value"]["endpoint"] == "/api/v1/companies" for item in items)


def test_audit_log_read_requires_admin():
    operator_headers = _headers_with_role("operator")
    response = client.get("/api/v1/audit-logs", headers=operator_headers)
    assert response.status_code == 403
    assert response.json()["error_code"] == "AUTH_FORBIDDEN"


def test_no_write_or_delete_route_exists_for_audit_logs():
    admin_headers = _admin_headers()
    # There is no id-based path at all for this resource — nothing to PUT/DELETE.
    put_response = client.put("/api/v1/audit-logs/1", json={}, headers=admin_headers)
    delete_response = client.delete("/api/v1/audit-logs/1", headers=admin_headers)
    assert put_response.status_code in (404, 405)
    assert delete_response.status_code in (404, 405)


def test_audit_log_rows_are_immutable_at_the_database_level():
    """The previous test proves the API has no route for this. This proves
    the database itself refuses even a direct SQL UPDATE/DELETE, bypassing
    the API and the ORM's own service layer entirely — a real backstop, not
    just "no one built a button for it"."""
    headers = _admin_headers()
    client.post("/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)

    db = SessionLocal()
    try:
        any_row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert any_row is not None

        with pytest.raises(DBAPIError):
            db.execute(
                update(AuditLog).where(AuditLog.id == any_row.id).values(action="tampered")
            )
            db.commit()
        db.rollback()

        with pytest.raises(DBAPIError):
            db.execute(delete(AuditLog).where(AuditLog.id == any_row.id))
            db.commit()
        db.rollback()

        # The row is untouched by either attempt.
        still_there = db.query(AuditLog).filter(AuditLog.id == any_row.id).first()
        assert still_there is not None
        assert still_there.action == any_row.action
    finally:
        db.close()


def test_audit_logs_ordered_most_recent_first():
    headers = _admin_headers()
    company = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    company_id = company.json()["data"]["id"]
    client.put(f"/api/v1/companies/{company_id}", json={"address": "A"}, headers=headers)
    client.put(f"/api/v1/companies/{company_id}", json={"address": "B"}, headers=headers)

    items = _audit_items(headers, resource_type="company", resource_id=str(company_id))
    timestamps = [item["created_at"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)
