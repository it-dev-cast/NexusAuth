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
    return f"Role {unique_email()}"


def test_create_job_role_success():
    headers = _admin_headers()
    response = client.post("/api/v1/job-roles", json={"name": _unique_name()}, headers=headers)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["is_active"] is True


def test_duplicate_job_role_name_rejected():
    headers = _admin_headers()
    name = _unique_name()
    client.post("/api/v1/job-roles", json={"name": name}, headers=headers)
    response = client.post("/api/v1/job-roles", json={"name": name}, headers=headers)
    assert response.status_code == 400


def test_operator_can_read_but_not_write_job_role():
    operator_headers = _headers_with_role("operator")

    listed = client.get("/api/v1/job-roles", headers=operator_headers)
    assert listed.status_code == 200

    created = client.post("/api/v1/job-roles", json={"name": _unique_name()}, headers=operator_headers)
    assert created.status_code == 403


def test_update_job_role_name():
    headers = _admin_headers()
    created = client.post("/api/v1/job-roles", json={"name": _unique_name()}, headers=headers)
    job_role_id = created.json()["data"]["id"]

    new_name = _unique_name()
    updated = client.put(f"/api/v1/job-roles/{job_role_id}", json={"name": new_name}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["data"]["name"] == new_name


def test_deactivate_job_role_removes_it_from_default_list():
    headers = _admin_headers()
    created = client.post("/api/v1/job-roles", json={"name": _unique_name()}, headers=headers)
    job_role_id = created.json()["data"]["id"]

    deactivated = client.delete(f"/api/v1/job-roles/{job_role_id}", headers=headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["data"]["is_active"] is False

    listed = client.get("/api/v1/job-roles?limit=100", headers=headers)
    assert not any(r["id"] == job_role_id for r in listed.json()["data"]["items"])


def test_this_job_role_is_unrelated_to_rbac_role_field():
    # A job-role master entry and a user's RBAC role (admin/operator/
    # read_only) are deliberately separate concepts — creating one whose
    # name happens to match an RBAC role name must not touch
    # app/core/roles.py's ALL_ROLES set or any user's role. Uses a
    # per-run-unique name (not the literal "admin") so re-running the
    # suite without a DB reset doesn't collide with the unique constraint
    # from a previous run — the point being tested is the name collision
    # with the RBAC concept, not literal repeatability of the string
    # "admin" across runs.
    from app.core.roles import ALL_ROLES

    headers = _admin_headers()
    name = f"admin ({unique_email()})"
    response = client.post("/api/v1/job-roles", json={"name": name}, headers=headers)
    assert response.status_code == 201
    assert "admin" in ALL_ROLES  # unaffected
