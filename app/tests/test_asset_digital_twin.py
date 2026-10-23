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
        "/api/v1/suppliers", json={"name": f"Supplier {unique_email()}"}, headers=headers
    )
    supplier_id = created.json()["data"]["id"]
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=headers)
    return supplier_id


def _create_asset(headers, **overrides):
    supplier_id = _create_approved_supplier(headers)
    body = {
        "asset_tag": _unique_tag(),
        "manufacturer": "Dell",
        "model": "Latitude 5420",
        "supplier_id": supplier_id,
    }
    body.update(overrides)
    return client.post("/api/v1/assets", json=body, headers=headers).json()["data"]


# ---- Financials facet ----


def test_create_asset_with_financials():
    headers = _admin_headers()
    asset = _create_asset(headers, purchase_cost="450.00", current_value="300.50", currency="usd")
    assert float(asset["purchase_cost"]) == 450.00
    assert float(asset["current_value"]) == 300.50
    assert asset["currency"] == "USD"  # normalized to uppercase


def test_update_asset_financials():
    headers = _admin_headers()
    asset = _create_asset(headers)
    updated = client.put(
        f"/api/v1/assets/{asset['id']}", json={"current_value": "199.99"}, headers=headers
    )
    assert updated.status_code == 200
    assert float(updated.json()["data"]["current_value"]) == 199.99
    # purchase_cost wasn't touched — stays whatever it was (null here).
    assert updated.json()["data"]["purchase_cost"] is None


def test_negative_financials_rejected():
    headers = _admin_headers()
    supplier_id = _create_approved_supplier(headers)
    response = client.post(
        "/api/v1/assets",
        json={
            "asset_tag": _unique_tag(),
            "manufacturer": "Dell",
            "model": "Latitude 5420",
            "supplier_id": supplier_id,
            "purchase_cost": "-5.00",
        },
        headers=headers,
    )
    assert response.status_code == 422


# ---- Tags facet ----


def test_add_list_and_remove_asset_tag():
    headers = _admin_headers()
    asset = _create_asset(headers)

    added = client.post(f"/api/v1/assets/{asset['id']}/tags", json={"tag": "Fragile"}, headers=headers)
    assert added.status_code == 201
    assert added.json()["data"]["tag"] == "fragile"  # normalized to lowercase

    listed = client.get(f"/api/v1/assets/{asset['id']}/tags", headers=headers)
    assert listed.status_code == 200
    assert [t["tag"] for t in listed.json()["data"]] == ["fragile"]

    removed = client.delete(f"/api/v1/assets/{asset['id']}/tags/fragile", headers=headers)
    assert removed.status_code == 200

    listed_again = client.get(f"/api/v1/assets/{asset['id']}/tags", headers=headers)
    assert listed_again.json()["data"] == []


def test_duplicate_tag_rejected():
    headers = _admin_headers()
    asset = _create_asset(headers)
    client.post(f"/api/v1/assets/{asset['id']}/tags", json={"tag": "warranty"}, headers=headers)
    duplicate = client.post(f"/api/v1/assets/{asset['id']}/tags", json={"tag": "warranty"}, headers=headers)
    assert duplicate.status_code == 409


def test_removing_a_tag_that_does_not_exist_is_404():
    headers = _admin_headers()
    asset = _create_asset(headers)
    response = client.delete(f"/api/v1/assets/{asset['id']}/tags/not-a-real-tag", headers=headers)
    assert response.status_code == 404


def test_search_matches_a_tag():
    headers = _admin_headers()
    tag = f"warehouse-{unique_email()[:8]}"
    asset = _create_asset(headers)
    client.post(f"/api/v1/assets/{asset['id']}/tags", json={"tag": tag}, headers=headers)

    response = client.get(f"/api/v1/assets?search={tag}", headers=headers)
    assert response.status_code == 200
    ids = [a["id"] for a in response.json()["data"]["items"]]
    assert asset["id"] in ids


def test_read_only_cannot_write_tags():
    # Operator can write assets (see app/core/permissions.py's "asset"
    # entry) — read_only is the role actually restricted to reads.
    read_only_headers = _headers_with_role("read_only")
    admin_headers = _admin_headers()
    asset = _create_asset(admin_headers)

    response = client.post(
        f"/api/v1/assets/{asset['id']}/tags", json={"tag": "x"}, headers=read_only_headers
    )
    assert response.status_code == 403


# ---- Documents/Media/Attachments facet ----


def test_add_and_list_asset_attachment():
    headers = _admin_headers()
    asset = _create_asset(headers)

    added = client.post(
        f"/api/v1/assets/{asset['id']}/attachments",
        json={"attachment_type": "photo", "reference": "https://example.com/photo.jpg", "description": "Front view"},
        headers=headers,
    )
    assert added.status_code == 201
    assert added.json()["data"]["attachment_type"] == "photo"

    listed = client.get(f"/api/v1/assets/{asset['id']}/attachments", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["reference"] == "https://example.com/photo.jpg"


def test_invalid_attachment_type_rejected():
    headers = _admin_headers()
    asset = _create_asset(headers)
    response = client.post(
        f"/api/v1/assets/{asset['id']}/attachments",
        json={"attachment_type": "video", "reference": "https://example.com/x.mp4"},
        headers=headers,
    )
    assert response.status_code == 422


# ---- Timeline facet ----


def test_timeline_is_chronological_and_reflects_status_changes():
    headers = _admin_headers()
    asset = _create_asset(headers)
    client.patch(f"/api/v1/assets/{asset['id']}/status", json={"status": "in_repair"}, headers=headers)

    timeline = client.get(f"/api/v1/assets/{asset['id']}/timeline", headers=headers)
    assert timeline.status_code == 200
    items = timeline.json()["data"]
    event_types = [item["event_type"] for item in items]
    # Oldest first: the create event comes before the later status transition.
    assert event_types.index("asset.create") < event_types.index("asset.status_transition")
