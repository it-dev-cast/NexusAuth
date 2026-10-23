"""Company-scoped authorization for the Employee resource (has a real
company_id column). See app/core/tenancy.py and test_company_isolation.py
for the admin-exemption rationale.
"""
from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


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
    # any more (CompanyCreateRequest rejects them). unique_email() below
    # is still used as-is for actual employee email addresses.
    return f"Isolation {unique_word()}"


def _create_company(admin_headers):
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=admin_headers)
    return created.json()["data"]["id"]


def _create_employee(admin_headers, company_id):
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Isolation Test", "last_name": "Doe", "email": unique_email()},
        headers=admin_headers,
    )
    return created.json()["data"]["id"]


def test_same_company_operator_can_read_and_write_employee():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    employee_id = _create_employee(admin_headers, company_a)
    operator_a = _headers_with_role("operator", company_id=company_a)

    read = client.get(f"/api/v1/employees/{employee_id}", headers=operator_a)
    assert read.status_code == 200

    write = client.put(
        f"/api/v1/employees/{employee_id}", json={"department": "Ops"}, headers=operator_a
    )
    assert write.status_code == 200


def test_cross_company_get_is_denied_as_not_found():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    employee_in_b = _create_employee(admin_headers, company_b)
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.get(f"/api/v1/employees/{employee_in_b}", headers=operator_a)
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"


def test_cross_company_update_is_denied():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    employee_in_b = _create_employee(admin_headers, company_b)
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.put(
        f"/api/v1/employees/{employee_in_b}", json={"department": "Hijacked"}, headers=operator_a
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"


def test_cross_company_status_transition_is_denied():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    employee_in_b = _create_employee(admin_headers, company_b)
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.patch(
        f"/api/v1/employees/{employee_in_b}/status", json={"status": "active"}, headers=operator_a
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"

    # And the employee's status really is unchanged, not silently applied.
    db = SessionLocal()
    from app.models.employee import Employee

    employee = db.query(Employee).filter(Employee.id == employee_in_b).first()
    status = employee.status
    db.close()
    assert status == "onboarded"


def test_cross_company_create_is_denied():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.post(
        "/api/v1/employees",
        json={"company_id": company_b, "first_name": "Should Not Exist", "last_name": "Doe", "email": unique_email()},
        headers=operator_a,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_cross_company_list_is_denied():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    _create_employee(admin_headers, company_b)
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.get(f"/api/v1/employees?company_id={company_b}", headers=operator_a)
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_cross_company_lookup_by_email_is_denied():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    email = unique_email()
    client.post(
        "/api/v1/employees",
        json={"company_id": company_b, "first_name": "By Email", "last_name": "Doe", "email": email},
        headers=admin_headers,
    )
    operator_a = _headers_with_role("operator", company_id=company_a)

    response = client.get(
        f"/api/v1/employees/by-email?company_id={company_b}&email={email}", headers=operator_a
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"


def test_admin_is_exempt_from_employee_company_scoping():
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    employee_in_b = _create_employee(admin_headers, company_b)
    admin_a = _headers_with_role("admin", company_id=company_a)

    response = client.get(f"/api/v1/employees/{employee_in_b}", headers=admin_a)
    assert response.status_code == 200
