"""Regression tests for the critical findings of the 2026-10-27 audit:
operator-driven admin lockout, PII exposure to operators, password policy,
case-insensitive emails, and model/schema drift."""
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.database.database import Base, SessionLocal, engine
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _as_role(role: str, company_id: int | None = None):
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    if company_id is not None:
        user.company_id = company_id
    db.commit()
    user_id, user_company = user.id, user.company_id
    db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return user_id, user_company, {"Authorization": f"Bearer {token}"}


def _employee_body(company_id: int, **extra) -> dict:
    return {
        "company_id": company_id,
        "first_name": "Audit",
        "last_name": unique_word(),
        "email": unique_email(),
        **extra,
    }


# 1. Operators can't link accounts on create, and can't exit an admin-linked employee.
def test_operator_cannot_link_a_user_when_creating_an_employee():
    _, company_id, op = _as_role("operator")
    admin_id, _, _ = _as_role("admin", company_id)
    response = client.post("/api/v1/employees", headers=op, json=_employee_body(company_id, user_id=admin_id))
    assert response.status_code == 403
    assert response.json()["error_code"] == "EMPLOYEE_LINK_FORBIDDEN"
    db = SessionLocal()
    assert db.query(User).get(admin_id).is_active is True
    db.close()


def test_operator_cannot_exit_an_employee_linked_to_an_admin():
    _, company_id, op = _as_role("operator")
    admin_id, _, admin = _as_role("admin", company_id)
    created = client.post("/api/v1/employees", headers=admin, json=_employee_body(company_id, user_id=admin_id))
    assert created.status_code == 201
    employee_id = created.json()["data"]["id"]
    assert client.patch(f"/api/v1/employees/{employee_id}/status", headers=op, json={"status": "active"}).status_code == 200
    exited = client.patch(f"/api/v1/employees/{employee_id}/status", headers=op, json={"status": "exited"})
    assert exited.status_code == 403
    assert exited.json()["error_code"] == "EMPLOYEE_EXIT_FORBIDDEN"
    db = SessionLocal()
    assert db.query(User).get(admin_id).is_active is True
    db.close()


def test_admin_can_still_link_on_create():
    _, company_id, admin = _as_role("admin")
    target_id, _, _ = _as_role("read_only", company_id)
    response = client.post("/api/v1/employees", headers=admin, json=_employee_body(company_id, user_id=target_id))
    assert response.status_code == 201
    assert response.json()["data"]["user_id"] == target_id


# 5. PAN / Aadhaar / bank numbers are masked for everyone but admins.
def test_sensitive_numbers_are_masked_for_operators_but_not_admins():
    _, company_id, op = _as_role("operator")
    _, _, admin = _as_role("admin", company_id)
    created = client.post(
        "/api/v1/employees",
        headers=op,
        json=_employee_body(
            company_id,
            pan_number="ABCDE1234F",
            aadhaar_number="234567890123",
            bank_account_number="123456789012",
        ),
    )
    assert created.status_code == 201
    employee_id = created.json()["data"]["id"]
    assert created.json()["data"]["pan_number"] == "******234F"

    for path in (f"/api/v1/employees/{employee_id}", f"/api/v1/employees?company_id={company_id}&limit=100"):
        body = client.get(path, headers=op).json()["data"]
        row = body if "items" not in body else next(e for e in body["items"] if e["id"] == employee_id)
        assert row["pan_number"] == "******234F"
        assert row["aadhaar_number"] == "********0123"
        assert row["bank_account_number"] == "********9012"

    full = client.get(f"/api/v1/employees/{employee_id}", headers=admin).json()["data"]
    assert full["pan_number"] == "ABCDE1234F"
    assert full["aadhaar_number"] == "234567890123"
    assert full["bank_account_number"] == "123456789012"


# 3. Password policy.
def test_weak_passwords_are_rejected_at_registration():
    for weak in ("", "a", "short1", "allletters", "12345678"):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": unique_email(), "password": weak, "full_name": "Weak"},
        )
        assert response.status_code == 422, weak


def test_empty_password_login_is_rejected():
    email, _ = register_and_login()
    assert client.post("/api/v1/auth/login", json={"email": email, "password": ""}).status_code == 422


def test_change_password_enforces_the_policy():
    _, tokens = register_and_login()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "x"},
    )
    assert response.status_code == 422


def test_overlong_full_name_is_a_validation_error_not_a_crash():
    response = client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": PASSWORD, "full_name": "x" * 300},
    )
    assert response.status_code == 422


# 4. One account per mailbox, whatever the capitals.
def test_email_case_variants_are_the_same_account():
    email = unique_email()
    first = client.post("/api/v1/auth/register", json={"email": email.upper(), "password": PASSWORD, "full_name": "Case"})
    assert first.status_code == 202
    # The same address in other capitals is a duplicate: answered exactly like
    # the first (see test_registration_does_not_reveal_whether_an_email_exists)
    # and no second account is made.
    duplicate = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Case"})
    assert duplicate.status_code == 202
    assert duplicate.json()["data"] == first.json()["data"]
    for variant in (email, email.upper(), email.title()):
        assert client.post("/api/v1/auth/login", json={"email": variant, "password": PASSWORD}).status_code == 200


# 6. Models and database schema agree, so autogenerate won't drop anything.
def test_models_match_the_migrated_schema():
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": False})
        diff = compare_metadata(context, Base.metadata)
    assert diff == [], diff
