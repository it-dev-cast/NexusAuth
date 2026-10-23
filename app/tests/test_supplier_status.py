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


def _create_supplier(headers):
    response = client.post(
        "/api/v1/suppliers",
        json={"name": f"Supplier {unique_email()}"},
        headers=headers,
    )
    return response.json()["data"]["id"]


def test_onboarded_to_approved_allowed():
    headers = _admin_headers()
    supplier_id = _create_supplier(headers)

    response = client.patch(
        f"/api/v1/suppliers/{supplier_id}/status",
        json={"status": "approved"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "approved"


def test_onboarded_to_suspended_rejected():
    headers = _admin_headers()
    supplier_id = _create_supplier(headers)

    response = client.patch(
        f"/api/v1/suppliers/{supplier_id}/status",
        json={"status": "suspended"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "SUPPLIER_INVALID_STATUS_TRANSITION"


def test_approved_to_suspended_and_back_to_approved():
    headers = _admin_headers()
    supplier_id = _create_supplier(headers)
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)

    suspended = client.patch(
        f"/api/v1/suppliers/{supplier_id}/status", json={"status": "suspended"}, headers=headers
    )
    assert suspended.status_code == 200
    assert suspended.json()["data"]["status"] == "suspended"

    reinstated = client.patch(
        f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers
    )
    assert reinstated.status_code == 200
    assert reinstated.json()["data"]["status"] == "approved"


def test_invalid_status_value_rejected_by_schema():
    headers = _admin_headers()
    supplier_id = _create_supplier(headers)

    response = client.patch(
        f"/api/v1/suppliers/{supplier_id}/status",
        json={"status": "banned"},
        headers=headers,
    )
    assert response.status_code == 422
