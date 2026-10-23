"""Field-level encryption at rest for Employee PII (SECURITY_CHECKLIST.md's
flagged, previously-unfixed risk; see app/core/pii_crypto.py,
app/database/encrypted_types.py). Verifies the DB column itself holds
ciphertext while the API keeps returning plain text to authorized callers —
i.e. encryption changed storage, not behavior.
"""
from app.database.database import SessionLocal
from app.models.employee import Employee
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


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


def _raw_column_value(employee_id: int, column: str) -> str | None:
    # Bypass the ORM (and therefore the EncryptedString decrypt step) to see
    # exactly what's stored on disk.
    from sqlalchemy import text

    db = SessionLocal()
    try:
        row = db.execute(
            text(f"SELECT {column} FROM employees WHERE id = :id"), {"id": employee_id}
        ).first()
        return row[0] if row else None
    finally:
        db.close()


def test_pii_is_encrypted_at_rest_but_decrypted_in_api_response():
    headers = _admin_headers()
    company = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    company_id = company.json()["data"]["id"]

    pan = "ABCDE1234F"
    bank_account = "1234567890"
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Encrypted PII", "last_name": "Doe",
            "email": unique_email(),
            "pan_number": pan,
            "bank_account_number": bank_account,
        },
        headers=headers,
    )
    assert created.status_code == 201
    employee_id = created.json()["data"]["id"]

    # API response: still plain text, API behavior unchanged.
    assert created.json()["data"]["pan_number"] == pan
    assert created.json()["data"]["bank_account_number"] == bank_account

    # Raw DB column: NOT the plaintext value — actually encrypted.
    raw_pan = _raw_column_value(employee_id, "pan_number")
    raw_bank = _raw_column_value(employee_id, "bank_account_number")
    assert raw_pan != pan
    assert raw_bank != bank_account
    assert pan not in raw_pan
    assert bank_account not in raw_bank

    # GET still round-trips to the original plain text via the ORM.
    fetched = client.get(f"/api/v1/employees/{employee_id}", headers=headers)
    assert fetched.json()["data"]["pan_number"] == pan
    assert fetched.json()["data"]["bank_account_number"] == bank_account

    # Direct ORM access also decrypts transparently.
    db = SessionLocal()
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    assert employee.pan_number == pan
    db.close()


def test_pii_fields_are_still_masked_in_audit_regardless_of_encryption():
    headers = _admin_headers()
    company = client.post(
        "/api/v1/companies", json={"name": f"Acme {unique_word()}", "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers
    )
    company_id = company.json()["data"]["id"]

    aadhaar = "123456789012"
    created = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id,
            "first_name": "Audit Masking", "last_name": "Doe",
            "email": unique_email(),
            "aadhaar_number": aadhaar,
        },
        headers=headers,
    )
    employee_id = created.json()["data"]["id"]

    audit = client.get(
        "/api/v1/audit-logs",
        params={"resource_type": "employee", "resource_id": str(employee_id)},
        headers=headers,
    )
    items = audit.json()["data"]["items"]
    assert len(items) == 1
    snapshot = items[0]["new_value"]
    # The audit snapshot is built from the decrypted (plain text) value and
    # then PII-masked, same as before encryption existed — audit masking
    # and at-rest encryption are two independent, both-applied protections.
    assert snapshot["aadhaar_number"] != aadhaar
    assert snapshot["aadhaar_number"].endswith(aadhaar[-4:])
    assert aadhaar not in str(snapshot)
