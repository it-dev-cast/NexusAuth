"""Transaction/error handling (Foundation Core Module 9): integrity errors
translate into a proper API response instead of a raw 500/traceback, and
any other unhandled exception is masked behind a generic error body with no
stack trace, SQL, or internal detail — see main.py's exception handlers.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from app.tests.conftest import client, unique_word

# TestClient's default `raise_server_exceptions=True` re-raises an unhandled
# exception into the test process for debuggability, even when our
# `@app.exception_handler(Exception)` already produced and sent a real
# response — that handler is what a genuine deployed client actually
# receives (ASGI servers don't re-raise). To assert on the response body
# itself we need a client that behaves like that real client.
_no_raise_client = TestClient(app, raise_server_exceptions=False)


def _admin_headers():
    from app.database.database import SessionLocal
    from app.models.user import User
    from app.tests.conftest import PASSWORD, register_and_login

    email, tokens = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = "admin"
    db.commit()
    db.close()

    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    access = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access}"}


def test_integrity_error_race_becomes_409_not_500():
    headers = _admin_headers()
    name = f"Race {unique_word()}"
    first = client.post("/api/v1/companies", json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)
    assert first.status_code == 201

    # Simulate the TOCTOU race the pre-check can't fully close: the
    # uniqueness pre-check (get_company_by_name) says "free" right before a
    # second request slips a duplicate past it — the database's own unique
    # constraint is the real backstop, and it must come back as a clean 409,
    # not a raw IntegrityError / 500 with SQL in the body.
    with patch("app.services.company_service.get_company_by_name", return_value=None):
        second = client.post("/api/v1/companies", json={"name": name, "address": "123 Test Street", "contact_email": "contact@example.com"}, headers=headers)

    assert second.status_code == 409
    body = second.json()
    assert body["error_code"] == "RESOURCE_CONFLICT"
    assert "trace_id" in body
    body_text = second.text.lower()
    for forbidden in ("traceback", "duplicate key value violates", "psycopg", "insert into"):
        assert forbidden not in body_text

    # The session used for the failed request must not be left broken —
    # normal requests right after it still work.
    followup = client.get("/api/v1/companies", headers=headers)
    assert followup.status_code == 200


def test_unhandled_exception_becomes_generic_500_without_leaking_detail():
    headers = _admin_headers()
    secret_marker = "internal-detail-that-must-never-reach-the-client"

    with patch(
        "app.services.company_service.record_audit_event",
        side_effect=RuntimeError(secret_marker),
    ):
        response = _no_raise_client.post(
            "/api/v1/companies",
            json={
                "name": f"Boom {unique_word()}",
                "address": "123 Test Street",
                "contact_email": "contact@example.com",
            },
            headers=headers,
        )

    assert response.status_code == 500
    body = response.json()
    assert body["error_code"] == "INTERNAL_ERROR"
    assert "trace_id" in body
    assert secret_marker not in response.text
    assert "Traceback" not in response.text
