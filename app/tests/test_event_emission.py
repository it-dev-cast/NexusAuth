import pytest
from sqlalchemy import delete, update
from sqlalchemy.exc import DBAPIError

from app.database.database import SessionLocal
from app.models.event import Event
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


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


def _event_items(headers, **params):
    response = client.get("/api/v1/events", params=params, headers=headers)
    assert response.status_code == 200
    return response.json()["data"]["items"]


def test_creating_a_company_publishes_an_event():
    headers = _admin_headers()
    name = f"Acme {unique_word()}"
    created = client.post(
        "/api/v1/companies",
        json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]

    items = _event_items(headers, resource_type="company", resource_id=str(company_id))
    assert len(items) == 1
    assert items[0]["event_type"] == "company.create"
    assert items[0]["payload"]["name"] == name


def test_updating_a_company_publishes_its_own_event():
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )
    company_id = created.json()["data"]["id"]

    client.put(f"/api/v1/companies/{company_id}", json={"address": "1 Main St"}, headers=headers)

    items = _event_items(headers, resource_type="company", resource_id=str(company_id), event_type="company.update")
    assert len(items) == 1
    assert items[0]["payload"]["address"] == "1 Main St"


def test_asset_status_transition_publishes_an_event_with_the_new_status():
    headers = _admin_headers()
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Supplier {unique_word()}"}, headers=headers
    ).json()["data"]
    client.patch(f"/api/v1/suppliers/{supplier['id']}/status", json={"status": "approved"}, headers=headers)

    asset = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": f"CLY-{unique_word()}",
            "manufacturer": "Dell",
            "model": "Latitude 5420",
            "supplier_id": supplier["id"],
        },
        headers=headers,
    ).json()["data"]

    client.patch(f"/api/v1/assets/{asset['id']}/status", json={"status": "in_repair"}, headers=headers)

    items = _event_items(headers, resource_type="asset", resource_id=str(asset["id"]), event_type="asset.status_transition")
    assert len(items) == 1
    assert items[0]["payload"]["status"] == "in_repair"


def test_company_event_carries_its_own_company_id():
    """Phase 2: "multi-tenant context propagation" — Company is one of the
    few resources that actually has a company_id (its own id), so its
    events should carry it, unlike Asset/Supplier/master-data events."""
    headers = _admin_headers()
    created = client.post(
        "/api/v1/companies",
        json={"name": f"Acme {unique_word()}", "address": "1", "contact_email": "a@example.com"},
        headers=headers,
    ).json()["data"]

    items = _event_items(headers, resource_type="company", resource_id=str(created["id"]))
    assert items[0]["company_id"] == created["id"]

    # Filtering by that same company_id finds it.
    filtered = _event_items(headers, company_id=created["id"], event_type="company.create")
    assert any(item["resource_id"] == str(created["id"]) for item in filtered)


def test_employee_event_carries_its_companys_id():
    headers = _admin_headers()
    company = client.post(
        "/api/v1/companies",
        json={"name": f"Acme {unique_word()}", "address": "1", "contact_email": "a@example.com"},
        headers=headers,
    ).json()["data"]

    employee = client.post(
        "/api/v1/employees",
        json={"company_id": company["id"], "first_name": "Priya Sharma", "last_name": "Doe", "email": unique_email()},
        headers=headers,
    ).json()["data"]

    items = _event_items(headers, resource_type="employee", resource_id=str(employee["id"]))
    assert items[0]["company_id"] == company["id"]


def test_asset_and_supplier_events_have_no_company_id():
    """Asset and Supplier have no company_id column at all (see
    app/core/tenancy.py's docstring — they are flat, company-wide catalogs
    by design) — their events should stay null, not silently guess one."""
    headers = _admin_headers()
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Supplier {unique_word()}"}, headers=headers
    ).json()["data"]

    items = _event_items(headers, resource_type="supplier", resource_id=str(supplier["id"]))
    assert items[0]["company_id"] is None


def test_event_read_requires_admin():
    operator_headers = _headers_with_role("operator")
    response = client.get("/api/v1/events", headers=operator_headers)
    assert response.status_code == 403

    read_only_headers = _headers_with_role("read_only")
    response = client.get("/api/v1/events", headers=read_only_headers)
    assert response.status_code == 403


def test_no_write_or_delete_route_exists_for_events():
    headers = _admin_headers()
    assert client.post("/api/v1/events", json={}, headers=headers).status_code in (404, 405)
    assert client.put("/api/v1/events/1", json={}, headers=headers).status_code in (404, 405)
    assert client.delete("/api/v1/events/1", headers=headers).status_code in (404, 405)


def test_event_rows_are_immutable_at_the_database_level():
    """Same guarantee as audit_logs (test_audit_log.py) — the database
    itself refuses a direct SQL UPDATE/DELETE, bypassing the API and the
    ORM's own service layer entirely."""
    headers = _admin_headers()
    client.post(
        "/api/v1/companies",
        json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"},
        headers=headers,
    )

    db = SessionLocal()
    try:
        any_row = db.query(Event).order_by(Event.id.desc()).first()
        assert any_row is not None

        with pytest.raises(DBAPIError):
            db.execute(update(Event).where(Event.id == any_row.id).values(event_type="tampered"))
            db.commit()
        db.rollback()

        with pytest.raises(DBAPIError):
            db.execute(delete(Event).where(Event.id == any_row.id))
            db.commit()
        db.rollback()

        still_there = db.query(Event).filter(Event.id == any_row.id).first()
        assert still_there is not None
        assert still_there.event_type == any_row.event_type
    finally:
        db.close()


def test_events_ordered_most_recent_first():
    headers = _admin_headers()
    first = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "1", "contact_email": "a@example.com"}, headers=headers
    ).json()["data"]
    second = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "2", "contact_email": "b@example.com"}, headers=headers
    ).json()["data"]

    items = _event_items(headers, event_type="company.create", limit=2)
    ids = [item["resource_id"] for item in items]
    assert ids.index(str(second["id"])) < ids.index(str(first["id"]))
