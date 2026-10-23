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


def _create_company(headers):
    created = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    return created.json()["data"]["id"]


def _create_employee(headers, company_id, name="Employee"):
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": name,
            "last_name": unique_word(),
            "email": unique_email(),
        },
        headers=headers,
    )
    return created.json()["data"]["id"]


def test_assigning_a_valid_manager_succeeds():
    headers = _admin_headers()
    company_id = _create_company(headers)
    manager_id = _create_employee(headers, company_id, "Manager")
    report_id = _create_employee(headers, company_id, "Report")

    response = client.put(
        f"/api/v1/employees/{report_id}", json={"manager_id": manager_id}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["manager_id"] == manager_id


def test_employee_cannot_be_own_manager():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.put(
        f"/api/v1/employees/{employee_id}", json={"manager_id": employee_id}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_MANAGER_CYCLE"


def test_direct_cycle_is_rejected():
    """A manages B; trying to make B manage A (a 2-node cycle) must fail."""
    headers = _admin_headers()
    company_id = _create_company(headers)
    a = _create_employee(headers, company_id, "A")
    b = _create_employee(headers, company_id, "B")

    first = client.put(f"/api/v1/employees/{b}", json={"manager_id": a}, headers=headers)
    assert first.status_code == 200

    second = client.put(f"/api/v1/employees/{a}", json={"manager_id": b}, headers=headers)
    assert second.status_code == 400
    assert second.json()["error_code"] == "EMPLOYEE_MANAGER_CYCLE"


def test_transitive_cycle_is_rejected():
    """A -> B -> C (C reports to B, B reports to A). Making A report to C
    would close a 3-node loop and must be rejected, not just direct ones."""
    headers = _admin_headers()
    company_id = _create_company(headers)
    a = _create_employee(headers, company_id, "A")
    b = _create_employee(headers, company_id, "B")
    c = _create_employee(headers, company_id, "C")

    assert client.put(f"/api/v1/employees/{b}", json={"manager_id": a}, headers=headers).status_code == 200
    assert client.put(f"/api/v1/employees/{c}", json={"manager_id": b}, headers=headers).status_code == 200

    closing_loop = client.put(f"/api/v1/employees/{a}", json={"manager_id": c}, headers=headers)
    assert closing_loop.status_code == 400
    assert closing_loop.json()["error_code"] == "EMPLOYEE_MANAGER_CYCLE"


def test_manager_must_be_in_the_same_company():
    headers = _admin_headers()
    company_a = _create_company(headers)
    company_b = _create_company(headers)
    employee_in_a = _create_employee(headers, company_a)
    manager_in_b = _create_employee(headers, company_b)

    response = client.put(
        f"/api/v1/employees/{employee_in_a}",
        json={"manager_id": manager_in_b},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_MANAGER_NOT_FOUND"


def test_manager_can_be_cleared_back_to_null():
    headers = _admin_headers()
    company_id = _create_company(headers)
    manager_id = _create_employee(headers, company_id, "Manager")
    report_id = _create_employee(headers, company_id, "Report")
    client.put(f"/api/v1/employees/{report_id}", json={"manager_id": manager_id}, headers=headers)

    cleared = client.put(
        f"/api/v1/employees/{report_id}", json={"manager_id": None}, headers=headers
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["manager_id"] is None
