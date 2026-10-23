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
    return f"Dept {unique_email()}"


def test_create_department_success():
    headers = _admin_headers()
    response = client.post("/api/v1/departments", json={"name": _unique_name()}, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_active"] is True


def test_duplicate_department_name_rejected():
    headers = _admin_headers()
    name = _unique_name()
    client.post("/api/v1/departments", json={"name": name}, headers=headers)
    response = client.post("/api/v1/departments", json={"name": name}, headers=headers)
    assert response.status_code == 400


def test_operator_can_read_but_not_write_department():
    admin_headers = _admin_headers()
    operator_headers = _headers_with_role("operator")

    listed = client.get("/api/v1/departments", headers=operator_headers)
    assert listed.status_code == 200

    created = client.post("/api/v1/departments", json={"name": _unique_name()}, headers=operator_headers)
    assert created.status_code == 403


def test_read_only_can_read_department_list():
    read_only_headers = _headers_with_role("read_only")
    response = client.get("/api/v1/departments", headers=read_only_headers)
    assert response.status_code == 200


def test_update_department_name():
    headers = _admin_headers()
    created = client.post("/api/v1/departments", json={"name": _unique_name()}, headers=headers)
    department_id = created.json()["data"]["id"]

    new_name = _unique_name()
    updated = client.put(f"/api/v1/departments/{department_id}", json={"name": new_name}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == new_name


def test_deactivate_department_removes_it_from_default_list():
    headers = _admin_headers()
    name = _unique_name()
    created = client.post("/api/v1/departments", json={"name": name}, headers=headers)
    department_id = created.json()["data"]["id"]

    deactivated = client.delete(f"/api/v1/departments/{department_id}", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["is_active"] is False

    # search= (not a bare limit=100), since this suite's test database is
    # never truncated between runs (see conftest.py) — a plain "first 100,
    # alphabetical" listing silently missed this row once enough other
    # tests' departments had accumulated ahead of it.
    listed = client.get(f"/api/v1/departments?search={name}", headers=headers)
    assert not any(d["id"] == department_id for d in listed.json()["data"]["items"])

    listed_inactive = client.get(f"/api/v1/departments?include_inactive=true&search={name}", headers=headers)
    assert any(d["id"] == department_id for d in listed_inactive.json()["data"]["items"])


def test_search_matches_department_name():
    headers = _admin_headers()
    name = _unique_name()
    client.post("/api/v1/departments", json={"name": name}, headers=headers)

    response = client.get(f"/api/v1/departments?search={name}&limit=5", headers=headers)
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(d["name"] == name for d in items)
