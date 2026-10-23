from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email


def test_user_cannot_access_admin_overview():
    _, tokens = register_and_login()
    response = client.get(
        "/api/v1/auth/overview",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "AUTH_FORBIDDEN"


def test_user_cannot_access_admin_route():
    _, tokens = register_and_login()
    response = client.get(
        "/admin",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 403


def test_admin_can_access_overview_and_change_role():
    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = "admin"
    db.commit()
    db.close()

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    access = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    overview = client.get("/api/v1/auth/overview", headers=headers)
    assert overview.status_code == 200
    assert "users" in overview.json()["data"]

    admin_route = client.get("/admin", headers=headers)
    assert admin_route.status_code == 200

    other_email, _ = register_and_login(unique_email())
    db = SessionLocal()
    other = db.query(User).filter(User.email == other_email).first()
    other_id = other.id
    db.close()

    changed = client.patch(
        f"/api/v1/auth/users/{other_id}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["role"] == "admin"

    # Doc: role changes must be audited, not just logged as a plain-text
    # rbac log line.
    audit = client.get(
        "/api/v1/audit-logs",
        params={"resource_type": "user", "resource_id": str(other_id), "action": "role_change"},
        headers=headers,
    )
    assert audit.status_code == 200
    items = audit.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["old_value"] == {"role": "read_only"}
    assert items[0]["new_value"] == {"role": "admin"}
