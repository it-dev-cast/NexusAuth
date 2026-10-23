from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email


def _admin_headers():
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = "admin"
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def _approved_supplier(headers):
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Supplier {unique_email()}"}, headers=headers
    )
    supplier_id = supplier.json()["data"]["id"]
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)
    return supplier_id


def _asset(headers, supplier_id):
    created = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": f"AST-{unique_email()}",
            "manufacturer": "Dell",
            "model": "X1",
            "supplier_id": supplier_id,
        },
        headers=headers,
    )
    return created.json()["data"]["id"]


def test_recalculate_with_no_resolved_assets_returns_409():
    headers = _admin_headers()
    supplier_id = _approved_supplier(headers)

    response = client.post(f"/api/v1/suppliers/{supplier_id}/rating/recalculate", headers=headers)
    assert response.status_code == 409
    assert response.json()["error_code"] == "SUPPLIER_RATING_INSUFFICIENT_DATA"


def test_recalculate_derives_rating_from_certified_and_disposed_assets():
    headers = _admin_headers()
    supplier_id = _approved_supplier(headers)

    # Two assets end up certified (good outcome), one is disposed without
    # ever certifying (bad outcome) -> 2 certified out of 3 resolved.
    for _ in range(2):
        asset_id = _asset(headers, supplier_id)
        client.patch(f"/api/v1/assets/{asset_id}/status", json={"status": "in_repair"}, headers=headers)
        client.patch(f"/api/v1/assets/{asset_id}/status", json={"status": "certified"}, headers=headers)

    disposed_asset = _asset(headers, supplier_id)
    client.delete(f"/api/v1/assets/{disposed_asset}", headers=headers)

    # A still-in-progress asset must not affect the calculation either way.
    _asset(headers, supplier_id)

    response = client.post(f"/api/v1/suppliers/{supplier_id}/rating/recalculate", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["rating"] == 3.33  # round(5 * 2/3, 2)


def test_recalculate_requires_write_role():
    headers = _admin_headers()
    supplier_id = _approved_supplier(headers)

    _, tokens = register_and_login()
    reader_headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    response = client.post(
        f"/api/v1/suppliers/{supplier_id}/rating/recalculate", headers=reader_headers
    )
    assert response.status_code == 403
