from app.database.database import SessionLocal
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


def _create_company(headers):
    created = client.post("/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    return created.json()["data"]["id"]


def _create_employee(headers, company_id):
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Test Emp", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    return created.json()["data"]["id"]


def test_onboarded_to_active_allowed():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "active"


def test_onboarded_to_on_leave_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "on_leave"}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_INVALID_STATUS_TRANSITION"


def test_full_lifecycle_active_on_leave_active_exited():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers)
    on_leave = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "on_leave"}, headers=headers
    )
    assert on_leave.status_code == 200

    back_active = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers
    )
    assert back_active.status_code == 200

    exited = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "exited"}, headers=headers
    )
    assert exited.status_code == 200


def test_no_transition_out_of_exited():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers)
    client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": "exited"}, headers=headers)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers
    )
    assert response.status_code == 400


def test_onboarded_can_be_cancelled_directly_to_exited():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "exited"}, headers=headers
    )
    assert response.status_code == 200


def test_invalid_status_value_rejected_by_schema():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/status", json={"status": "on_vacation"}, headers=headers
    )
    assert response.status_code == 422


def test_soft_delete_marks_exited():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.delete(f"/api/v1/employees/{employee_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "exited"


def test_link_user_success_and_exit_cascades_to_deactivate_user():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    # Register a fresh user, force it into the same company as the employee.
    user_email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == user_email).first()
    user.company_id = company_id
    db.commit()
    user_id = user.id
    db.close()

    link = client.patch(
        f"/api/v1/employees/{employee_id}/link-user", json={"user_id": user_id}, headers=headers
    )
    assert link.status_code == 200
    assert link.json()["data"]["user_id"] == user_id

    client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": "active"}, headers=headers)
    client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": "exited"}, headers=headers)

    db = SessionLocal()
    refreshed_user = db.query(User).filter(User.id == user_id).first()
    is_active = refreshed_user.is_active
    db.close()
    assert is_active is False


def test_link_user_rejects_company_mismatch():
    headers = _admin_headers()
    company_a = _create_company(headers)
    company_b = _create_company(headers)
    employee_id = _create_employee(headers, company_a)

    user_email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == user_email).first()
    user.company_id = company_b
    db.commit()
    user_id = user.id
    db.close()

    response = client.patch(
        f"/api/v1/employees/{employee_id}/link-user", json={"user_id": user_id}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_USER_COMPANY_MISMATCH"


def test_link_user_rejects_already_linked_user():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_a = _create_employee(headers, company_id)
    employee_b = _create_employee(headers, company_id)

    user_email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == user_email).first()
    user.company_id = company_id
    db.commit()
    user_id = user.id
    db.close()

    client.patch(f"/api/v1/employees/{employee_a}/link-user", json={"user_id": user_id}, headers=headers)
    response = client.patch(
        f"/api/v1/employees/{employee_b}/link-user", json={"user_id": user_id}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_USER_ALREADY_LINKED"


def test_link_user_rejects_unknown_user():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    response = client.patch(
        f"/api/v1/employees/{employee_id}/link-user", json={"user_id": 999999}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_USER_NOT_FOUND"


def test_link_user_requires_admin_not_operator():
    headers = _admin_headers()
    company_id = _create_company(headers)
    employee_id = _create_employee(headers, company_id)

    user_email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == user_email).first()
    user.company_id = company_id
    db.commit()
    user_id = user.id
    db.close()

    operator_headers = _headers_with_role("operator")
    response = client.patch(
        f"/api/v1/employees/{employee_id}/link-user",
        json={"user_id": user_id},
        headers=operator_headers,
    )
    assert response.status_code == 403
