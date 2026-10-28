"""Request-scoped transactions (#50), list filter operators / multi-sort /
unknown-parameter rejection (#23-#25) and the enriched OpenAPI spec (#27/#58)."""
import json
import re

from fastapi.testclient import TestClient

from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.supplier import Supplier
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word


def _headers(role: str = "admin") -> dict:
    email, _ = register_and_login()
    db = SessionLocal()
    db.query(User).filter(User.email == email).update({"role": role})
    db.commit()
    db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- #50: one transaction per request -------------------------------------

def test_a_failing_audit_write_rolls_back_the_business_change(monkeypatch):
    from app.services import audit_service

    def broken(*args, **kwargs):
        raise RuntimeError("audit table unavailable")

    headers = _headers()
    monkeypatch.setattr(audit_service, "create_audit_log", broken)
    name = f"Atomic {unique_word()}"
    response = TestClient(__import__("main").app, raise_server_exceptions=False).post(
        "/api/v1/suppliers", headers=headers, json={"name": name}
    )
    assert response.status_code == 500
    db = SessionLocal()
    assert db.query(Supplier).filter(Supplier.name == name).count() == 0
    db.close()


def test_successful_writes_and_their_audit_rows_are_committed():
    name = f"Committed {unique_word()}"
    created = client.post("/api/v1/suppliers", headers=_headers(), json={"name": name})
    assert created.status_code == 201
    supplier_id = created.json()["data"]["id"]
    db = SessionLocal()
    assert db.query(Supplier).filter(Supplier.id == supplier_id).count() == 1
    assert db.query(AuditLog).filter(AuditLog.resource_type == "supplier", AuditLog.resource_id == str(supplier_id),
                                     AuditLog.action == "create").count() == 1
    db.close()


def test_a_rejected_request_leaves_no_partial_change():
    # The status is assigned before the transition is refused; nothing may stick.
    headers = _headers()
    supplier_id = client.post("/api/v1/suppliers", headers=headers, json={"name": f"Partial {unique_word()}"}).json()["data"]["id"]
    refused = client.patch(f"/api/v1/suppliers/{supplier_id}/status", headers=headers, json={"status": "suspended"})
    assert refused.status_code == 400
    db = SessionLocal()
    assert db.query(Supplier).get(supplier_id).status == "onboarded"
    db.close()


def test_failed_logins_and_access_denials_are_still_recorded():
    email, tokens = register_and_login()
    client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword9"})
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    assert user.failed_login_attempts == 1
    assert db.query(AuditLog).filter(AuditLog.action == "login_failure", AuditLog.resource_id == str(user.id)).count() == 1
    db.close()

    denied = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert denied.status_code == 403
    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.action == "access_denied", AuditLog.user_id == user.id).count() >= 1
    db.close()


# --- #23-#25: filter operators, multi-sort, unknown parameters -------------

def _create_suppliers(headers, prefix: str, ratings: list[float]) -> list[int]:
    ids = []
    for rating in ratings:
        created = client.post("/api/v1/suppliers", headers=headers, json={"name": f"{prefix} {unique_word()}", "rating": rating})
        ids.append(created.json()["data"]["id"])
    return ids


def test_filter_operators_narrow_the_list_and_the_total():
    headers = _headers()
    prefix = f"Ops{unique_word()}"
    ids = _create_suppliers(headers, prefix, [1.0, 3.0, 4.5])
    base = f"/api/v1/suppliers?name[contains]={prefix}&limit=100"
    assert client.get(base, headers=headers).json()["data"]["total"] == 3
    high = client.get(base + "&rating[gte]=3", headers=headers).json()["data"]
    assert high["total"] == 2 and {s["id"] for s in high["items"]} == set(ids[1:])
    ranged = client.get(base + "&rating[range]=2,4", headers=headers).json()["data"]
    assert [s["id"] for s in ranged["items"]] == [ids[1]]
    chosen = client.get(base + f"&id[in]={ids[0]},{ids[2]}", headers=headers).json()["data"]
    assert {s["id"] for s in chosen["items"]} == {ids[0], ids[2]}


def test_multi_field_sort_with_directions():
    headers = _headers()
    prefix = f"Sort{unique_word()}"
    _create_suppliers(headers, prefix, [2.0, 5.0, 2.0])
    items = client.get(f"/api/v1/suppliers?name[contains]={prefix}&sort=-rating,id", headers=headers).json()["data"]["items"]
    assert [float(s["rating"]) for s in items] == [5.0, 2.0, 2.0]
    assert items[1]["id"] < items[2]["id"]


def test_contains_treats_wildcards_as_text():
    headers = _headers()
    assert client.get("/api/v1/suppliers?name[contains]=%25%25%25zz", headers=headers).json()["data"]["total"] == 0


def test_unknown_or_unsupported_parameters_are_rejected():
    headers = _headers()
    for query, fragment in [
        ("bogus=1", "Unknown query parameter"),
        ("rating[contains]=3", "isn't supported"),
        ("nope[eq]=1", "can't be filtered"),
        ("id[gt]=abc", "expected an integer"),
        ("sort=password_hash", "can't be sorted"),
        ("sort=a,b,c,d", "Sort by 1 to 3"),
    ]:
        response = client.get(f"/api/v1/suppliers?{query}", headers=headers)
        assert response.status_code == 422, query
        assert response.json()["error_code"] == "VALIDATION_ERROR"
        assert fragment in json.dumps(response.json()["details"]), query


def test_personal_data_columns_are_never_filterable():
    headers = _headers()
    for query in ("pan_number[eq]=ABCDE1234F", "email[contains]=a", "phone_number[eq]=1"):
        assert client.get(f"/api/v1/employees?{query}", headers=headers).status_code == 422, query


def test_existing_list_parameters_still_work():
    headers = _headers()
    for path in (
        "/api/v1/companies?limit=5&include_inactive=true&sort_by=created_at&sort_dir=desc",
        "/api/v1/employees?limit=5&include_exited=true",
        "/api/v1/suppliers?limit=5&status=approved",
        "/api/v1/assets?limit=5&status=registered",
        "/api/v1/departments?limit=5&include_inactive=true",
        "/api/v1/job-roles?limit=5&include_inactive=false",
        "/api/v1/manufacturers?limit=5&include_inactive=true",
        "/api/v1/asset-models?limit=5&include_inactive=true",
    ):
        assert client.get(path, headers=headers).status_code == 200, path


# --- #27/#58: OpenAPI contract ----------------------------------------------

def test_openapi_documents_errors_roles_and_typed_responses():
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    refs = set(re.findall(r'"\$ref": "#/components/schemas/([^"]+)"', json.dumps(spec)))
    assert refs <= set(schemas), refs - set(schemas)
    assert set(schemas["ErrorResponse"]["required"]) == {"error_code", "message", "trace_id"}

    secured = [op for path in spec["paths"].values() for op in path.values() if op.get("security")]
    assert secured and all(op.get("x-required-roles") for op in secured)
    assert spec["paths"]["/api/v1/audit-logs"]["get"]["x-required-roles"] == ["admin"]

    list_op = spec["paths"]["/api/v1/suppliers"]["get"]
    data = list_op["responses"]["200"]["content"]["application/json"]["schema"]["properties"]["data"]
    assert data["properties"]["items"]["items"] == {"$ref": "#/components/schemas/SupplierResponse"}
    assert "next" in data["properties"]
    for code in ("401", "403", "422", "500"):
        assert list_op["responses"][code]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}


def test_documented_error_shape_matches_real_errors():
    spec_fields = set(client.get("/openapi.json").json()["components"]["schemas"]["ErrorResponse"]["properties"])
    real = client.get("/api/v1/suppliers").json()
    assert set(real) <= spec_fields
