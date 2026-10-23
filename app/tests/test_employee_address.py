"""Employee address: optional, cleaned, editable, clearable, and encrypted at rest like phone_number."""
from sqlalchemy import text

from app.database.database import SessionLocal
from app.tests.conftest import client, unique_email
from app.tests.test_employee_crud import _admin_headers, _create_company


def _create(headers, company_id, **extra):
    body = {"company_id": company_id, "first_name": "Asha", "last_name": "Rao", "email": unique_email(), **extra}
    response = client.post("/api/v1/employees", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_address_is_optional():
    headers = _admin_headers()
    assert _create(headers, _create_company(headers))["address"] is None


def test_address_is_cleaned_and_returned():
    headers = _admin_headers()
    employee = _create(headers, _create_company(headers), address="  No. 12, MG Road \n\n Bengaluru 560001 ")
    assert employee["address"] == "No. 12, MG Road\nBengaluru 560001"
    fetched = client.get(f"/api/v1/employees/{employee['id']}", headers=headers).json()["data"]
    assert fetched["address"] == "No. 12, MG Road\nBengaluru 560001"


def test_address_can_be_changed_and_cleared():
    headers = _admin_headers()
    employee = _create(headers, _create_company(headers), address="Old address")
    url = f"/api/v1/employees/{employee['id']}"
    assert client.put(url, json={"address": "New address"}, headers=headers).json()["data"]["address"] == "New address"
    assert client.put(url, json={"first_name": "Asha"}, headers=headers).json()["data"]["address"] == "New address"
    assert client.put(url, json={"address": "   "}, headers=headers).json()["data"]["address"] is None


def test_address_is_limited_to_300_characters():
    headers = _admin_headers()
    body = {"company_id": _create_company(headers), "first_name": "A", "last_name": "B", "email": unique_email(),
            "address": "x" * 301}
    assert client.post("/api/v1/employees", json=body, headers=headers).status_code == 422


def test_address_is_not_stored_in_plain_text():
    """With PII encryption configured the column holds ciphertext; the API still returns plain text."""
    from app.core.config import get_settings

    headers = _admin_headers()
    employee = _create(headers, _create_company(headers), address="Secret Street 42")
    db = SessionLocal()
    try:
        raw = db.execute(text("SELECT address FROM employees WHERE id = :id"), {"id": employee["id"]}).scalar()
    finally:
        db.close()
    assert employee["address"] == "Secret Street 42"
    if getattr(get_settings(), "pii_encryption_key", None):
        assert raw != "Secret Street 42"
