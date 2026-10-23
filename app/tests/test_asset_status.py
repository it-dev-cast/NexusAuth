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


def _create_asset(headers):
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Supplier {unique_email()}"}, headers=headers
    )
    supplier_id = supplier.json()["data"]["id"]
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)

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


def test_registered_to_in_repair_allowed():
    headers = _admin_headers()
    asset_id = _create_asset(headers)

    response = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "in_repair"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "in_repair"


def test_registered_to_certified_rejected():
    headers = _admin_headers()
    asset_id = _create_asset(headers)

    response = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "certified"}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "ASSET_INVALID_STATUS_TRANSITION"


def test_full_lifecycle_and_rework():
    headers = _admin_headers()
    asset_id = _create_asset(headers)

    client.patch(f"/api/v1/assets/{asset_id}/status", json={"status": "in_repair"}, headers=headers)
    certified = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "certified"}, headers=headers
    )
    assert certified.status_code == 200

    # A certified asset found faulty later can go back for rework.
    rework = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "in_repair"}, headers=headers
    )
    assert rework.status_code == 200
    assert rework.json()["data"]["status"] == "in_repair"


def test_soft_delete_disposes_asset_and_is_terminal():
    headers = _admin_headers()
    asset_id = _create_asset(headers)

    response = client.delete(f"/api/v1/assets/{asset_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "disposed"

    # No transition out of disposed.
    blocked = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "registered"}, headers=headers
    )
    assert blocked.status_code == 400


def test_invalid_status_value_rejected_by_schema():
    headers = _admin_headers()
    asset_id = _create_asset(headers)

    response = client.patch(
        f"/api/v1/assets/{asset_id}/status", json={"status": "scrapped"}, headers=headers
    )
    assert response.status_code == 422
