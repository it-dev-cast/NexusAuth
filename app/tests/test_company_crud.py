from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_word


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
    # Letters-only unique_word(), not unique_email() — a company name
    # can't contain digits any more (CompanyCreateRequest/
    # CompanyUpdateRequest reject them), and unique_email() embeds a hex
    # id that's mostly digits.
    return f"Acme {unique_word()}"


def test_create_company_defaults_to_external():
    headers = _admin_headers()
    response = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["company_type"] == "external"
    assert data["is_active"] is True


def test_malformed_config_defaults_json_is_rejected():
    # Previously silently accepted, then swallowed to {} the first time
    # employee_service._company_defaults() tried to parse it — no error
    # anywhere, an admin could typo this and never find out.
    headers = _admin_headers()
    response = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "config_defaults": "{not valid json"},
        headers=headers,
    )
    assert response.status_code == 422


def test_config_defaults_must_be_a_json_object_not_a_scalar():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "config_defaults": "42"},
        headers=headers,
    )
    assert response.status_code == 422


def test_valid_config_defaults_json_is_accepted():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/companies",
        json={
            "name": _unique_name(),
            "address": "123 Test Street",
            "contact_email": "contact@example.com",
            "config_defaults": '{"default_job_role": "Technician", "default_department": "Ops"}',
        },
        headers=headers,
    )
    assert response.status_code == 201


def test_create_internal_company():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/companies",
        json={
            "name": _unique_name(),
            "company_type": "internal",
            "address": "123 Test Street",
            "contact_email": "contact@example.com",
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["data"]["company_type"] == "internal"


def test_invalid_company_type_rejected():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "company_type": "nonsense"},
        headers=headers,
    )
    assert response.status_code == 422


def test_duplicate_company_name_rejected():
    headers = _admin_headers()
    name = _unique_name()
    first = client.post("/api/v1/companies", json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    assert first.status_code == 201

    second = client.post("/api/v1/companies", json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    assert second.status_code == 400
    assert second.json()["error_code"] == "COMPANY_ALREADY_EXISTS"


def test_get_company_by_id():
    headers = _admin_headers()
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    response = client.get(f"/api/v1/companies/{company_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == company_id


def test_get_unknown_company_returns_404():
    headers = _admin_headers()
    response = client.get("/api/v1/companies/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "COMPANY_NOT_FOUND"


def test_list_companies_paginated():
    headers = _admin_headers()
    for _ in range(3):
        client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)

    response = client.get("/api/v1/companies?limit=1&offset=0", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["total"] >= 3
    assert data["limit"] == 1
    assert data["offset"] == 0


def test_sort_by_created_at_ascending_and_descending():
    # Scoped down to just these two rows via a shared search prefix — with
    # a real, larger dataset, "newest/oldest 100 overall" wouldn't
    # reliably include two just-created rows, so order is verified within
    # a search-narrowed result instead.
    headers = _admin_headers()
    prefix = f"SortTest {unique_word()}"
    first = client.post(
        "/api/v1/companies",
        json={"name": f"{prefix} A", "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/companies",
        json={"name": f"{prefix} B", "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]

    newest_first = client.get(f"/api/v1/companies?search={prefix}&sort_by=created_at&sort_dir=desc", headers=headers)
    ids_desc = [item["id"] for item in newest_first.json()["data"]["items"]]
    assert ids_desc == [second_id, first_id]

    oldest_first = client.get(f"/api/v1/companies?search={prefix}&sort_by=created_at&sort_dir=asc", headers=headers)
    ids_asc = [item["id"] for item in oldest_first.json()["data"]["items"]]
    assert ids_asc == [first_id, second_id]


def test_filter_by_company_type():
    headers = _admin_headers()
    internal = client.post(
        "/api/v1/companies",
        json={
            "name": _unique_name(),
            "address": "123 Test Street",
            "contact_email": "contact@example.com",
            "company_type": "internal",
        },
        headers=headers,
    )
    internal_id = internal.json()["data"]["id"]

    response = client.get("/api/v1/companies?company_type=internal&limit=100", headers=headers)
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]["items"]]
    assert internal_id in ids
    assert all(item["company_type"] == "internal" for item in response.json()["data"]["items"])


def test_filter_by_invalid_company_type_rejected():
    headers = _admin_headers()
    response = client.get("/api/v1/companies?company_type=not-a-real-type", headers=headers)
    assert response.status_code == 422


def test_update_company_details_and_config_defaults():
    headers = _admin_headers()
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/companies/{company_id}",
        json={"address": "1 Main St", "config_defaults": '{"default_department": "Support"}'},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["address"] == "1 Main St"
    assert data["config_defaults"] == '{"default_department": "Support"}'


def test_update_can_explicitly_null_out_a_previously_set_field():
    # contact_phone (still genuinely optional/nullable) stands in for
    # "a field that can be cleared" here — address/contact_email cover the
    # opposite case below, since they became mandatory and reject an
    # explicit null instead of clearing (test_update_cannot_null_out_a_mandatory_field).
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={
            "name": _unique_name(),
            "address": "1 Main St",
            "contact_email": "contact@example.com",
            "contact_phone": "555-0100",
        },
        headers=headers,
    )
    company_id = created.json()["data"]["id"]
    assert created.json()["data"]["contact_phone"] == "555-0100"

    response = client.put(
        f"/api/v1/companies/{company_id}", json={"contact_phone": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["contact_phone"] is None


def test_update_cannot_null_out_a_mandatory_field():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "address": "1 Main St", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]

    address_response = client.put(
        f"/api/v1/companies/{company_id}", json={"address": None}, headers=headers
    )
    assert address_response.status_code == 422

    email_response = client.put(
        f"/api/v1/companies/{company_id}", json={"contact_email": None}, headers=headers
    )
    assert email_response.status_code == 422

    # Neither rejected attempt actually changed anything.
    unchanged = client.get(f"/api/v1/companies/{company_id}", headers=headers)
    assert unchanged.json()["data"]["address"] == "1 Main St"
    assert unchanged.json()["data"]["contact_email"] == "contact@example.com"


def test_update_omitting_a_field_leaves_it_untouched():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "address": "1 Main St", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/companies/{company_id}", json={"contact_phone": "555-0100"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["address"] == "1 Main St"
    assert response.json()["data"]["contact_phone"] == "555-0100"


def test_update_company_name_uniqueness_enforced():
    headers = _admin_headers()
    name_a = _unique_name()
    name_b = _unique_name()
    client.post(
        "/api/v1/companies",
        json={"name": name_a, "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    created_b = client.post(
        "/api/v1/companies",
        json={"name": name_b, "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_b_id = created_b.json()["data"]["id"]

    response = client.put(
        f"/api/v1/companies/{company_b_id}", json={"name": name_a}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "COMPANY_ALREADY_EXISTS"


def test_soft_delete_company_marks_inactive():
    headers = _admin_headers()
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    response = client.delete(f"/api/v1/companies/{company_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False

    # Deactivated companies drop out of the default (active-only) list.
    listing = client.get("/api/v1/companies", headers=headers)
    ids = [item["id"] for item in listing.json()["data"]["items"]]
    assert company_id not in ids


def test_soft_delete_is_idempotent():
    headers = _admin_headers()
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    first = client.delete(f"/api/v1/companies/{company_id}", headers=headers)
    second = client.delete(f"/api/v1/companies/{company_id}", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["is_active"] is False


def test_deactivated_company_visible_with_include_inactive():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]
    client.delete(f"/api/v1/companies/{company_id}", headers=headers)

    # Absent from the default list...
    default_listing = client.get("/api/v1/companies?limit=100", headers=headers)
    assert company_id not in [item["id"] for item in default_listing.json()["data"]["items"]]

    # ...but visible with include_inactive=true, so deactivating is never
    # a dead end with no way to even see the record again.
    full_listing = client.get("/api/v1/companies?include_inactive=true&limit=100", headers=headers)
    ids = [item["id"] for item in full_listing.json()["data"]["items"]]
    assert company_id in ids

    # Direct GET by id also still works regardless of active status.
    direct = client.get(f"/api/v1/companies/{company_id}", headers=headers)
    assert direct.status_code == 200
    assert direct.json()["data"]["is_active"] is False


def test_reactivate_company():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]
    client.delete(f"/api/v1/companies/{company_id}", headers=headers)

    reactivated = client.patch(f"/api/v1/companies/{company_id}/reactivate", headers=headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["is_active"] is True

    # Back in the default (active-only) list.
    listing = client.get("/api/v1/companies?limit=100", headers=headers)
    assert company_id in [item["id"] for item in listing.json()["data"]["items"]]


def test_reactivate_is_idempotent():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]

    # Already active — reactivating a never-deactivated company is a no-op,
    # not an error.
    response = client.patch(f"/api/v1/companies/{company_id}/reactivate", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


def test_read_only_can_read_but_not_write_company():
    headers = _admin_headers()
    created = client.post("/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    company_id = created.json()["data"]["id"]

    # Same-company access: the reader belongs to the company it's reading.
    reader_headers = _headers_with_role("read_only", company_id=company_id)
    read = client.get(f"/api/v1/companies/{company_id}", headers=reader_headers)
    assert read.status_code == 200

    write = client.put(
        f"/api/v1/companies/{company_id}", json={"address": "X"}, headers=reader_headers
    )
    assert write.status_code == 403
    assert write.json()["error_code"] == "AUTH_FORBIDDEN"


def test_operator_can_write_but_not_delete_company():
    admin_headers = _admin_headers()
    created = client.post(
        "/api/v1/companies", json={"name": _unique_name(), "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=admin_headers
    )
    company_id = created.json()["data"]["id"]

    # Same-company access: the operator belongs to the company it's writing to.
    operator_headers = _headers_with_role("operator", company_id=company_id)
    write = client.put(
        f"/api/v1/companies/{company_id}", json={"address": "Y"}, headers=operator_headers
    )
    assert write.status_code == 200

    delete = client.delete(f"/api/v1/companies/{company_id}", headers=operator_headers)
    assert delete.status_code == 403
