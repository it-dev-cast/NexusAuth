from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_code, unique_email, unique_word


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
    return f"Acme {unique_word()}"


def _create_company(headers):
    payload = {"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}
    created = client.post("/api/v1/companies", json=payload, headers=headers)
    return created.json()["data"]["id"]


def _create_application(headers, name=None):
    created = client.post(
        "/api/v1/applications", json={"name": name or f"App {unique_email()}", "code": unique_code()}, headers=headers
    )
    return created.json()["data"]["id"]


def test_create_employee_with_application_access():
    headers = _admin_headers()
    company_id = _create_company(headers)
    app_a = _create_application(headers)
    app_b = _create_application(headers)

    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Dashboard User", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [app_a, app_b],
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert sorted(data["application_ids"]) == sorted([app_a, app_b])
    assert len(data["application_names"]) == 2


def test_create_employee_with_unknown_application_id_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)

    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "No Such App", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [999999999],
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_APPLICATION_NOT_FOUND"


def test_create_employee_with_inactive_application_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)
    app_id = _create_application(headers)
    client.delete(f"/api/v1/applications/{app_id}", headers=headers)  # deactivate

    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Inactive App User", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [app_id],
        },
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_APPLICATION_INACTIVE"


def test_update_employee_application_access_replaces_the_list():
    headers = _admin_headers()
    company_id = _create_company(headers)
    app_a = _create_application(headers)
    app_b = _create_application(headers)

    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Replaceable Access", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [app_a],
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    updated = client.put(
        f"/api/v1/employees/{employee_id}",
        json={"application_ids": [app_b]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["application_ids"] == [app_b]


def test_update_employee_omitting_application_ids_leaves_access_unchanged():
    headers = _admin_headers()
    company_id = _create_company(headers)
    app_a = _create_application(headers)

    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Untouched Access", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [app_a],
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    # No application_ids key at all — a plain name change must not wipe
    # out existing access as a side effect.
    updated = client.put(
        f"/api/v1/employees/{employee_id}",
        json={"first_name": "Renamed, Still Has Access", "last_name": "Doe"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["application_ids"] == [app_a]


def test_update_employee_explicit_empty_list_clears_application_access():
    headers = _admin_headers()
    company_id = _create_company(headers)
    app_a = _create_application(headers)

    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Clearable Access", "last_name": "Doe",
            "email": unique_email(),
            "application_ids": [app_a],
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    updated = client.put(
        f"/api/v1/employees/{employee_id}",
        json={"application_ids": []},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["application_ids"] == []
