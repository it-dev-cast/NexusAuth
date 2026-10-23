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


def _unique_name():
    return f"Supplier {unique_email()}"


def test_create_supplier_success():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/suppliers",
        json={"name": _unique_name(), "terms": "Net 30", "category": "Hardware"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "onboarded"
    assert data["terms"] == "Net 30"


def test_duplicate_supplier_name_rejected():
    headers = _admin_headers()
    name = _unique_name()
    first = client.post("/api/v1/suppliers", json={"name": name}, headers=headers)
    assert first.status_code == 201

    second = client.post("/api/v1/suppliers", json={"name": name}, headers=headers)
    assert second.status_code == 400
    assert second.json()["error_code"] == "SUPPLIER_ALREADY_EXISTS"


def test_rating_out_of_range_rejected_by_schema():
    headers = _admin_headers()
    response = client.post(
        "/api/v1/suppliers",
        json={"name": _unique_name(), "rating": 7},
        headers=headers,
    )
    assert response.status_code == 422


def test_read_only_can_read_but_not_write_supplier():
    headers = _admin_headers()
    created = client.post("/api/v1/suppliers", json={"name": _unique_name()}, headers=headers)
    supplier_id = created.json()["data"]["id"]

    reader_headers = _headers_with_role("read_only")
    read = client.get(f"/api/v1/suppliers/{supplier_id}", headers=reader_headers)
    assert read.status_code == 200

    write = client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={"category": "Logistics"},
        headers=reader_headers,
    )
    assert write.status_code == 403
    assert write.json()["error_code"] == "AUTH_FORBIDDEN"


def test_list_suppliers_filtered_by_category():
    headers = _admin_headers()
    client.post(
        "/api/v1/suppliers",
        json={"name": _unique_name(), "category": "Logistics"},
        headers=headers,
    )
    client.post(
        "/api/v1/suppliers",
        json={"name": _unique_name(), "category": "Hardware"},
        headers=headers,
    )

    response = client.get("/api/v1/suppliers?category=Hardware", headers=headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert all(item["category"] == "Hardware" for item in items)


def test_update_supplier_rating_and_terms():
    headers = _admin_headers()
    created = client.post("/api/v1/suppliers", json={"name": _unique_name()}, headers=headers)
    supplier_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/suppliers/{supplier_id}",
        json={"rating": 4.5, "terms": "Net 45"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["rating"] == 4.5
    assert data["terms"] == "Net 45"


def test_list_suppliers_rejects_invalid_status_filter():
    headers = _admin_headers()
    response = client.get("/api/v1/suppliers?status=bogus", headers=headers)
    assert response.status_code == 422


def test_update_can_explicitly_null_out_category_once_set():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/suppliers", json={"name": _unique_name(), "category": "Hardware"}, headers=headers
    )
    supplier_id = created.json()["data"]["id"]

    response = client.put(
        f"/api/v1/suppliers/{supplier_id}", json={"category": None}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["category"] is None


def test_get_unknown_supplier_returns_404():
    headers = _admin_headers()
    response = client.get("/api/v1/suppliers/999999", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "SUPPLIER_NOT_FOUND"


def test_get_supplier_by_name():
    headers = _admin_headers()
    name = _unique_name()
    created = client.post("/api/v1/suppliers", json={"name": name}, headers=headers)
    supplier_id = created.json()["data"]["id"]

    from urllib.parse import quote

    response = client.get(f"/api/v1/suppliers/by-name/{quote(name, safe='')}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == supplier_id


def test_get_supplier_by_name_not_found():
    headers = _admin_headers()
    response = client.get("/api/v1/suppliers/by-name/does-not-exist", headers=headers)
    assert response.status_code == 404
    assert response.json()["error_code"] == "SUPPLIER_NOT_FOUND"
