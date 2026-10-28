"""API standards, error handling and PII privacy rules added in the gap
remediation: page links, version header, trace ids, framework errors in the
envelope, out-of-range values, PII read auditing and error redaction."""
import logging

from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _headers(role: str = "admin", **extra) -> tuple[dict, int]:
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    db.commit()
    company_id = user.company_id
    db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}", **extra}, company_id


def test_list_responses_link_to_neighbouring_pages_and_keep_filters():
    headers, _ = _headers()
    for _ in range(3):
        client.post("/api/v1/suppliers", headers=headers, json={"name": f"Paging {unique_word()}"})
    data = client.get("/api/v1/suppliers?limit=1&offset=1&status=onboarded", headers=headers).json()["data"]
    assert data["has_more"] is True  # existing fields unchanged
    assert data["next"] == "/api/v1/suppliers?status=onboarded&limit=1&offset=2"
    assert data["previous"] == "/api/v1/suppliers?status=onboarded&limit=1&offset=0"
    first = client.get("/api/v1/suppliers?limit=1&offset=0", headers=headers).json()["data"]
    assert first["previous"] is None


def test_api_version_header_and_trace_id_match_the_request_id():
    headers, _ = _headers(**{"X-Request-Id": "trace-abc-123"})
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.headers["x-api-version"] == "v1"
    assert response.headers["x-request-id"] == "trace-abc-123"
    assert response.json()["meta"]["trace_id"] == "trace-abc-123"


def test_malformed_request_ids_are_replaced():
    response = client.get("/health", headers={"X-Request-Id": "x" * 500})
    assert response.headers["x-request-id"] != "x" * 500
    assert len(response.headers["x-request-id"]) <= 128


def test_framework_errors_use_the_standard_envelope():
    missing = client.get("/no-such-route", headers={"X-Request-Id": "rid-404"})
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "NOT_FOUND" and missing.json()["trace_id"] == "rid-404"
    wrong_method = client.post("/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error_code"] == "METHOD_NOT_ALLOWED"


def test_out_of_range_ids_are_validation_errors_not_server_errors():
    headers, _ = _headers()
    for path in ("/api/v1/companies/3000000000", "/api/v1/suppliers/3000000000", "/api/v1/assets/3000000000"):
        response = client.get(path, headers=headers)
        assert response.status_code == 422, path
        assert response.json()["error_code"] == "VALIDATION_ERROR"


def test_db_test_endpoint_requires_an_admin():
    assert client.get("/db-test").status_code == 401
    operator, _ = _headers("operator")
    assert client.get("/db-test", headers=operator).status_code == 403
    admin, _ = _headers()
    assert client.get("/db-test", headers=admin).status_code == 200


def test_unhandled_errors_still_get_an_access_log_line(caplog, monkeypatch):
    from app.routes import supplier as supplier_routes

    def boom(*args, **kwargs):
        raise RuntimeError("probe failure")

    monkeypatch.setattr(supplier_routes, "list_supplier_records", boom)
    headers, _ = _headers(**{"X-Request-Id": "rid-500"})
    with caplog.at_level(logging.INFO, logger="nexusauth.access"):
        from fastapi.testclient import TestClient
        from main import app

        response = TestClient(app, raise_server_exceptions=False).get("/api/v1/suppliers", headers=headers)
    assert response.status_code == 500
    assert response.json()["trace_id"] == "rid-500"
    assert any("-> 500" in r.getMessage() and "rid-500" in r.getMessage() for r in caplog.records)


def test_validation_errors_never_echo_pii_or_passwords():
    headers, company_id = _headers()
    response = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"company_id": company_id, "first_name": "A", "last_name": "B", "email": unique_email(),
              "aadhaar_number": "9999 8888 777", "pan_number": "SECRETPAN99"},
    )
    assert response.status_code == 422
    assert "9999 8888 777" not in response.text and "SECRETPAN99" not in response.text
    weak = client.post("/api/v1/auth/register", json={"email": unique_email(), "password": "tiny", "full_name": "x"})
    assert weak.status_code == 422 and "tiny" not in weak.text
    # Non-sensitive fields keep their detail.
    bad_type = client.post("/api/v1/companies", headers=headers, json={"name": 123})
    assert '"input":123' in bad_type.text.replace(" ", "")


def test_admin_reads_of_id_numbers_are_audited_without_values():
    headers, company_id = _headers()
    created = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"company_id": company_id, "first_name": "Pii", "last_name": unique_word(), "email": unique_email(),
              "pan_number": "ABCDE1234F"},
    ).json()["data"]
    client.get(f"/api/v1/employees/{created['id']}", headers=headers)
    db = SessionLocal()
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action == "pii_access", AuditLog.resource_id == str(created["id"]))
        .all()
    )
    db.close()
    assert rows, "admin read of PAN should be audited"
    assert "ABCDE1234F" not in (rows[-1].new_value or "")
    assert "pan_number" in rows[-1].new_value


def test_operator_reads_are_masked_so_not_audited_as_pii_access():
    operator, company_id = _headers("operator")
    created = client.post(
        "/api/v1/employees",
        headers=operator,
        json={"company_id": company_id, "first_name": "Op", "last_name": unique_word(), "email": unique_email(),
              "pan_number": "ABCDE1234F"},
    ).json()["data"]
    client.get(f"/api/v1/employees/{created['id']}", headers=operator)
    db = SessionLocal()
    count = db.query(AuditLog).filter(AuditLog.action == "pii_access", AuditLog.resource_id == str(created["id"])).count()
    db.close()
    assert count == 0


def test_employee_address_is_masked_in_audit_snapshots():
    headers, company_id = _headers()
    created = client.post(
        "/api/v1/employees",
        headers=headers,
        json={"company_id": company_id, "first_name": "Addr", "last_name": unique_word(), "email": unique_email(),
              "address": "42 Secret Lane, Bengaluru"},
    ).json()["data"]
    db = SessionLocal()
    row = db.query(AuditLog).filter(AuditLog.action == "create", AuditLog.resource_type == "employee",
                                    AuditLog.resource_id == str(created["id"])).first()
    db.close()
    assert "42 Secret Lane" not in row.new_value


def test_rbac_denial_log_masks_the_email(caplog):
    email, tokens = register_and_login()
    with caplog.at_level(logging.WARNING):
        client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    denied = [r.getMessage() for r in caplog.records if "RBAC_DENIED" in r.getMessage()]
    assert denied and all(email not in line for line in denied)
