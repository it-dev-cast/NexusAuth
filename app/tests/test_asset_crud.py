from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email


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


def _unique_tag():
    return f"AST-{unique_email()}"


def _create_approved_supplier(headers):
    created = client.post(
        "/api/v1/suppliers",
        json={"name": f"Supplier {unique_email()}"},
        headers=headers,
    )
    supplier_id = created.json()["data"]["id"]
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)
    return supplier_id


def test_search_matches_manufacturer_and_excludes_others():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    # Full unique_email() output, not a truncated slice — unique_email()
    # is "intern_<12 hex chars>@casterly.com", so a short slice like [:8]
    # only captures "intern_" plus a single hex digit (16 possible
    # values), which collided for real once the test DB accumulated
    # enough runs (it isn't rolled back between pytest invocations).
    unique_mfr = f"ZylexCorp{unique_email()}"
    client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": unique_mfr,
            "model": "Model X",
            "supplier_id": supplier_id,
        },
        headers=headers,
    )
    response = client.get(f"/api/v1/assets?search={unique_mfr}&limit=10", headers=headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["manufacturer"] == unique_mfr


def test_search_matches_asset_tag():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    tag = _unique_tag()
    client.post(
        "/api/v1/assets",
        json={"asset_tag": tag, "manufacturer": "Dell", "model": "X1", "supplier_id": supplier_id},
        headers=headers,
    )
    response = client.get(f"/api/v1/assets?search={tag}&limit=10", headers=headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(a["asset_tag"] == tag for a in items)


def test_create_asset_success():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)

    response = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": "Dell",
            "model": "Latitude 5420",
            "serial_number": "SN12345",
            "supplier_id": supplier_id,
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "registered"
    assert data["supplier_id"] == supplier_id


def test_create_asset_rejects_unapproved_supplier():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/suppliers",
        json={"name": f"Supplier {unique_email()}"},
        headers=headers,
    )
    supplier_id = created.json()["data"]["id"]  # still "onboarded", not approved

    response = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": "HP",
            "model": "EliteBook",
            "supplier_id": supplier_id,
        },
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "SUPPLIER_NOT_APPROVED"


def test_create_asset_rejects_unknown_supplier():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": "HP",
            "model": "EliteBook",
            "supplier_id": 999999,
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error_code"] == "SUPPLIER_NOT_FOUND"


def test_duplicate_asset_tag_rejected():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    tag = _unique_tag()

    first = client.post(
        "/api/v1/assets",
        json={"asset_tag": tag, "manufacturer": "Dell", "model": "X1", "supplier_id": supplier_id},
        headers=headers,
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/assets",
        json={"asset_tag": tag, "manufacturer": "Dell", "model": "X2", "supplier_id": supplier_id},
        headers=headers,
    )
    assert second.status_code == 400
    assert second.json()["error_code"] == "ASSET_ALREADY_EXISTS"


def test_asset_tag_is_immutable():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    created = client.post(
        "/api/v1/assets",
        json={"asset_tag": _unique_tag(), "manufacturer": "Dell", "model": "X1", "supplier_id": supplier_id},
        headers=headers,
    )
    asset_id = created.json()["data"]["id"]

    # asset_tag isn't even an accepted field on the update schema.
    response = client.put(
        f"/api/v1/assets/{asset_id}",
        json={"asset_tag": "SHOULD-NOT-CHANGE", "model": "X2 Updated"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["model"] == "X2 Updated"
    assert data["asset_tag"] != "SHOULD-NOT-CHANGE"


def test_get_asset_by_tag():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    tag = _unique_tag()
    client.post(
        "/api/v1/assets",
        json={"asset_tag": tag, "manufacturer": "Dell", "model": "X1", "supplier_id": supplier_id},
        headers=headers,
    )

    response = client.get(f"/api/v1/assets/tag/{tag}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["asset_tag"] == tag


def test_list_assets_filtered_by_supplier_and_sorted_desc():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    client.post(
        "/api/v1/assets",
        json={"asset_tag": _unique_tag(), "manufacturer": "Dell", "model": "A", "supplier_id": supplier_id},
        headers=headers,
    )
    client.post(
        "/api/v1/assets",
        json={"asset_tag": _unique_tag(), "manufacturer": "Dell", "model": "B", "supplier_id": supplier_id},
        headers=headers,
    )

    response = client.get(
        f"/api/v1/assets?supplier_id={supplier_id}&sort_by=id&sort_dir=desc",
        headers=headers,
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 2
    assert items[0]["id"] > items[1]["id"]


def test_read_only_can_read_but_not_write_asset():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    created = client.post(
        "/api/v1/assets",
        json={"asset_tag": _unique_tag(), "manufacturer": "Dell", "model": "X1", "supplier_id": supplier_id},
        headers=headers,
    )
    asset_id = created.json()["data"]["id"]

    reader_headers = _headers_with_role("read_only")
    read = client.get(f"/api/v1/assets/{asset_id}", headers=reader_headers)
    assert read.status_code == 200

    write = client.put(f"/api/v1/assets/{asset_id}", json={"model": "X2"}, headers=reader_headers)
    assert write.status_code == 403


def test_list_assets_rejects_invalid_status_filter():
    headers = _admin_headers()
    response = client.get("/api/v1/assets?status=bogus", headers=headers)
    assert response.status_code == 422


def test_update_can_explicitly_null_out_serial_number_once_set():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    created = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": "Dell",
            "model": "X1",
            "serial_number": "SN999",
            "supplier_id": supplier_id,
        },
        headers=headers,
    )
    asset_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/assets/{asset_id}", json={"serial_number": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["serial_number"] is None


def test_get_unknown_asset_returns_404():
    headers = _admin_headers()
    response = client.get("/api/v1/assets/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "ASSET_NOT_FOUND"
