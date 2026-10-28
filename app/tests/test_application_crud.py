from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_code, unique_email


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
    return f"App {unique_email()}"


def test_create_application_success():
    headers = _admin_headers()
    response = client.post("/api/v1/applications", json={"name": _unique_name(), "code": unique_code()}, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_active"] is True
    assert data["employee_count"] == 0


def test_duplicate_application_name_rejected():
    headers = _admin_headers()
    name = _unique_name()
    client.post("/api/v1/applications", json={"name": name, "code": unique_code()}, headers=headers)
    response = client.post("/api/v1/applications", json={"name": name, "code": unique_code()}, headers=headers)
    assert response.status_code == 400


def test_operator_can_read_but_not_write_application():
    operator_headers = _headers_with_role("operator")

    listed = client.get("/api/v1/applications", headers=operator_headers)
    assert listed.status_code == 200

    created = client.post("/api/v1/applications", json={"name": _unique_name(), "code": unique_code()}, headers=operator_headers)
    assert created.status_code == 403


def test_update_application_name():
    headers = _admin_headers()
    created = client.post("/api/v1/applications", json={"name": _unique_name(), "code": unique_code()}, headers=headers)
    application_id = created.json()["data"]["id"]

    new_name = _unique_name()
    updated = client.put(
        f"/api/v1/applications/{application_id}", json={"name": new_name}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == new_name


def test_deactivate_and_reactivate_application():
    headers = _admin_headers()
    created = client.post("/api/v1/applications", json={"name": _unique_name(), "code": unique_code()}, headers=headers)
    application_id = created.json()["data"]["id"]

    deactivated = client.delete(f"/api/v1/applications/{application_id}", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["is_active"] is False

    listed = client.get("/api/v1/applications?limit=100", headers=headers)
    assert not any(a["id"] == application_id for a in listed.json()["data"]["items"])

    reactivated = client.patch(f"/api/v1/applications/{application_id}/reactivate", headers=headers)
    assert reactivated.status_code == 200
    assert reactivated.json()["data"]["is_active"] is True
