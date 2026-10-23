from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _headers_with_role(role: str, company_id: int | None = None):
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    if company_id is not None:
        # Company isolation is enforced by company_id, not role — put this
        # test user in the target company so "same-company access" tests
        # actually exercise same-company access.
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


def _create_company(headers, config_defaults=None):
    payload = {"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}
    if config_defaults is not None:
        payload["config_defaults"] = config_defaults
    created = client.post("/api/v1/companies", json=payload, headers=headers)
    return created.json()["data"]["id"]


def test_invalid_pan_number_format_is_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)
    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Priya Sharma", "last_name": "Doe",
            "email": unique_email(),
            "pan_number": "not-a-pan",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_valid_pan_number_format_is_accepted():
    headers = _admin_headers()
    company_id = _create_company(headers)
    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Priya Sharma", "last_name": "Doe",
            "email": unique_email(),
            "pan_number": "ABCDE1234F",
        },
        headers=headers,
    )
    assert response.status_code == 201


def test_invalid_aadhaar_number_format_is_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)
    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Priya Sharma", "last_name": "Doe",
            "email": unique_email(),
            "aadhaar_number": "12345",
        },
        headers=headers,
    )
    assert response.status_code == 422


def test_valid_aadhaar_number_with_separators_is_accepted():
    headers = _admin_headers()
    company_id = _create_company(headers)
    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Priya Sharma", "last_name": "Doe",
            "email": unique_email(),
            "aadhaar_number": "1234 5678 9012",
        },
        headers=headers,
    )
    assert response.status_code == 201


def test_create_employee_defaults_job_role_to_employee():
    headers = _admin_headers()
    company_id = _create_company(headers)

    response = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Priya Sharma", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["job_role"] == "Employee"
    assert data["status"] == "onboarded"


def test_employee_inherits_job_role_and_department_from_company_defaults():
    headers = _admin_headers()
    company_id = _create_company(
        headers, config_defaults='{"default_job_role": "Technician", "default_department": "Refurb"}'
    )

    response = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "No Overrides", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["job_role"] == "Technician"
    assert data["department"] == "Refurb"


def test_explicit_job_role_overrides_company_default():
    headers = _admin_headers()
    company_id = _create_company(headers, config_defaults='{"default_job_role": "Technician"}')

    response = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Override", "last_name": "Doe",
            "email": unique_email(),
            "job_role": "Manager",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["job_role"] == "Manager"


def test_malformed_company_defaults_does_not_break_employee_creation():
    # The API itself now rejects malformed config_defaults at company
    # create/update time (see test_company_crud.py's
    # test_malformed_config_defaults_json_is_rejected) — that validator
    # only protects the validated API path, though. A row written before
    # that validator existed, or written directly to the DB outside the
    # API, could still hold malformed JSON; employee_service.
    # _company_defaults() has its own try/except fallback to {} for
    # exactly that case, and this test exercises that fallback directly by
    # writing the bad value straight to the DB, bypassing the schema
    # validator on purpose.
    from app.database.database import SessionLocal
    from app.models.company import Company

    headers = _admin_headers()
    company_id = _create_company(headers)
    db = SessionLocal()
    db.query(Company).filter(Company.id == company_id).update({"config_defaults": "not valid json"})
    db.commit()
    db.close()

    response = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Fallback", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["job_role"] == "Employee"


def test_duplicate_email_in_same_company_rejected():
    headers = _admin_headers()
    company_id = _create_company(headers)
    email = unique_email()

    first = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "First", "last_name": "Doe", "email": email},
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Second", "last_name": "Doe", "email": email},
        headers=headers,
    )
    assert second.status_code == 400
    assert second.json()["error_code"] == "EMPLOYEE_ALREADY_EXISTS"


def test_same_email_allowed_in_different_company():
    headers = _admin_headers()
    company_a = _create_company(headers)
    company_b = _create_company(headers)
    email = unique_email()

    first = client.post(
        "/api/v1/employees",
        json={"company_id": company_a, "first_name": "First", "last_name": "Doe", "email": email},
        headers=headers,
    )
    second = client.post(
        "/api/v1/employees",
        json={"company_id": company_b, "first_name": "Second", "last_name": "Doe", "email": email},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 201


def test_create_employee_rejects_unknown_company():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/employees",
        json={"company_id": 999999, "first_name": "Nobody", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_create_employee_rejects_inactive_company():
    headers = _admin_headers()
    company_id = _create_company(headers)
    client.delete(f"/api/v1/companies/{company_id}", headers=headers)

    response = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "Too Late", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_COMPANY_INACTIVE"


def test_get_employee_by_id():
    headers = _admin_headers()
    company_id = _create_company(headers)
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    response = client.get(f"/api/v1/employees/{employee_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == employee_id


def test_get_unknown_employee_returns_404():
    headers = _admin_headers()
    response = client.get("/api/v1/employees/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"


def test_get_employee_by_email():
    headers = _admin_headers()
    company_id = _create_company(headers)
    email = unique_email()
    client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "By Email", "last_name": "Doe", "email": email},
        headers=headers,
    )

    response = client.get(
        f"/api/v1/employees/by-email?company_id={company_id}&email={email}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == email


def test_get_employee_by_email_not_found():
    headers = _admin_headers()
    company_id = _create_company(headers)

    response = client.get(
        f"/api/v1/employees/by-email?company_id={company_id}&email=nobody@casterly.com",
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "EMPLOYEE_NOT_FOUND"


def test_list_employees_without_company_id_shows_all_companies_for_admin():
    # company_id is optional by design — omitting it is the Employees
    # page's own default view ("All companies"), not an error. For an
    # admin specifically, that means employees from more than one company
    # can show up in the same unscoped list.
    headers = _admin_headers()
    company_a = _create_company(headers)
    company_b = _create_company(headers)
    first_a, last_a = "AllCompaniesA", unique_word()
    first_b, last_b = "AllCompaniesB", unique_word()
    name_a = f"{first_a} {last_a}"
    name_b = f"{first_b} {last_b}"
    client.post(
        "/api/v1/employees",
        json={"company_id": company_a, "first_name": first_a, "last_name": last_a, "email": unique_email()},
        headers=headers,
    )
    client.post(
        "/api/v1/employees",
        json={"company_id": company_b, "first_name": first_b, "last_name": last_b, "email": unique_email()},
        headers=headers,
    )

    response = client.get(f"/api/v1/employees?search={name_a}&limit=100", headers=headers)
    assert response.status_code == 200
    names = [item["full_name"] for item in response.json()["data"]["items"]]
    assert name_a in names

    # Same again for company_b's employee, proving this single unscoped
    # request can see employees from two different companies, not just
    # whichever one happens to be "current".
    response_b = client.get(f"/api/v1/employees?search={name_b}&limit=100", headers=headers)
    names_b = [item["full_name"] for item in response_b.json()["data"]["items"]]
    assert name_b in names_b


def test_list_employees_without_company_id_scopes_non_admin_to_own_company():
    # A non-admin must never get a cross-company view, even via the "all
    # companies" default — omitting company_id for them silently falls
    # back to their own company instead of acting like an admin's "every
    # company" request.
    admin_headers = _admin_headers()
    company_a = _create_company(admin_headers)
    company_b = _create_company(admin_headers)
    first_a, last_a = "ScopeTestA", unique_word()
    first_b, last_b = "ScopeTestB", unique_word()
    name_a = f"{first_a} {last_a}"
    name_b = f"{first_b} {last_b}"
    client.post(
        "/api/v1/employees",
        json={"company_id": company_a, "first_name": first_a, "last_name": last_a, "email": unique_email()},
        headers=admin_headers,
    )
    client.post(
        "/api/v1/employees",
        json={"company_id": company_b, "first_name": first_b, "last_name": last_b, "email": unique_email()},
        headers=admin_headers,
    )

    operator_headers = _headers_with_role("operator", company_id=company_a)
    response = client.get("/api/v1/employees?limit=100", headers=operator_headers)
    assert response.status_code == 200
    names = [item["full_name"] for item in response.json()["data"]["items"]]
    assert name_a in names
    assert name_b not in names


def test_list_employees_by_company():
    headers = _admin_headers()
    company_id = _create_company(headers)
    client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "B", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )

    response = client.get(f"/api/v1/employees?company_id={company_id}", headers=headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_list_employees_rejects_unknown_company():
    headers = _admin_headers()
    response = client.get("/api/v1/employees?company_id=999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_update_employee_fields_and_pii():
    headers = _admin_headers()
    company_id = _create_company(headers)
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/employees/{employee_id}",
        json={
            "department": "Finance",
            "bank_account_number": "9988776655",
            "pan_number": "ZZZZZ0000Z",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["department"] == "Finance"
    assert data["bank_account_number"] == "9988776655"
    assert data["pan_number"] == "ZZZZZ0000Z"


def test_update_can_explicitly_null_out_department_and_pii():
    headers = _admin_headers()
    company_id = _create_company(headers)
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "A", "last_name": "Doe",
            "email": unique_email(),
            "department": "Finance",
            "pan_number": "ABCDE1234F",
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]
    assert created.json()["data"]["department"] == "Finance"

    response = client.put(
        f"/api/v1/employees/{employee_id}",
        json={"department": None, "pan_number": None},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["department"] is None
    assert data["pan_number"] is None
    # first_name/last_name weren't touched by this update at all.
    assert data["first_name"] == "A"
    assert data["last_name"] == "Doe"
    assert data["full_name"] == "A Doe"


def test_update_employee_email_uniqueness_enforced():
    headers = _admin_headers()
    company_id = _create_company(headers)
    email_a = unique_email()
    email_b = unique_email()

    client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": email_a},
        headers=headers,
    )
    create_b = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "B", "last_name": "Doe", "email": email_b},
        headers=headers,
    )
    b_id = create_b.json()["data"]["id"]

    response = client.put(f"/api/v1/employees/{b_id}", json={"email": email_a}, headers=headers)
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMPLOYEE_ALREADY_EXISTS"


def test_read_only_cannot_read_employees_pii_is_stricter_than_company():
    headers = _admin_headers()
    company_id = _create_company(headers)
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    reader_headers = _headers_with_role("read_only")
    response = client.get(f"/api/v1/employees/{employee_id}", headers=reader_headers)
    assert response.status_code == 403


def test_operator_can_read_and_write_employee():
    admin_headers = _admin_headers()
    company_id = _create_company(admin_headers)
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=admin_headers,
    )
    employee_id = created.json()["data"]["id"]

    # Same-company access: the operator belongs to the employee's company.
    operator_headers = _headers_with_role("operator", company_id=company_id)
    read = client.get(f"/api/v1/employees/{employee_id}", headers=operator_headers)
    assert read.status_code == 200

    write = client.put(
        f"/api/v1/employees/{employee_id}", json={"department": "Ops"}, headers=operator_headers
    )
    assert write.status_code == 200


def test_operator_cannot_delete_employee_admin_only():
    admin_headers = _admin_headers()
    company_id = _create_company(admin_headers)
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": "A", "last_name": "Doe", "email": unique_email()},
        headers=admin_headers,
    )
    employee_id = created.json()["data"]["id"]

    operator_headers = _headers_with_role("operator")
    response = client.delete(f"/api/v1/employees/{employee_id}", headers=operator_headers)
    assert response.status_code == 403
