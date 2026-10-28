"""Reports module: authorization, company isolation, filters, sorting,
pagination, CSV export fidelity, export auditing, sensitive-field exclusion
and summary-vs-database accuracy.

Every test builds its own uniquely-named company/employees/suppliers/assets
(see conftest.unique_word) and asserts against those, so results are exact
even though the test database is shared and accumulates rows across runs.
"""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.csv_export import UTF8_BOM, build_csv, csv_cell
from app.core.permissions import allowed_roles
from app.database.database import SessionLocal
from app.models.asset import Asset
from app.models.company import Company
from app.models.employee import Employee
from app.models.supplier import Supplier
from app.models.user import User
from app.services import report_service
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word

SECURITY_KEYS = {"audit-activity", "user-activity", "auth-session-summary", "admin-changes"}
# Master Management reports: readable by every role (they follow the master_data permission) except the change
# history, which reads the audit log and is therefore admin-only like the Security & Audit reports.
MASTER_KEYS = {"master-summary", "master-values", "master-unused-values"}
MASTER_ADMIN_KEYS = {"master-changes"}
FORBIDDEN_FIELD_NAMES = {
    "phone_number", "address", "bank_account_number", "bank_ifsc", "pan_number",
    "aadhaar_number", "residence_proof_reference", "photo_reference", "linkedin_url",
    "password", "password_hash", "refresh_token_hash", "access_token_jti", "ip_address", "user_agent",
    "old_value", "new_value",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _headers(role: str, company_id: int | None = None) -> dict:
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    if company_id is not None:
        user.company_id = company_id
    db.commit()
    db.close()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


def _company(admin) -> tuple[int, str]:
    name = f"Reports {unique_word()}"
    created = client.post(
        "/api/v1/companies",
        json={"name": name, "address": "1 Test Street", "contact_email": "contact@example.com"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"], name


def _employee(admin, company_id, **extra) -> dict:
    payload = {
        "company_id": company_id,
        "first_name": extra.pop("first_name", unique_word()),
        "last_name": extra.pop("last_name", unique_word()),
        "email": unique_email(),
        **extra,
    }
    created = client.post("/api/v1/employees", json=payload, headers=admin)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _set_status(admin, employee_id, status):
    response = client.patch(f"/api/v1/employees/{employee_id}/status", json={"status": status}, headers=admin)
    assert response.status_code == 200, response.text


def _report(headers, key, **params):
    return client.get(f"/api/v1/reports/{key}", params=params, headers=headers)


def _items(headers, key, **params) -> list[dict]:
    response = _report(headers, key, limit=100, **params)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def _export(headers, key, **params):
    return client.get(f"/api/v1/reports/{key}/export", params=params, headers=headers)


def _parse_csv(response) -> list[list[str]]:
    text = response.content.decode("utf-8")
    assert text.startswith(UTF8_BOM)
    return list(csv.reader(io.StringIO(text.lstrip(UTF8_BOM))))


def _fresh_scope():
    admin = _headers("admin")
    company_id, company_name = _company(admin)
    return admin, company_id, company_name


# --------------------------------------------------------------------------
# catalog, authentication, authorization
# --------------------------------------------------------------------------
def test_catalog_only_lists_reports_the_role_may_read():
    admin_catalog = client.get("/api/v1/reports/catalog", headers=_headers("admin")).json()["data"]
    operator_catalog = client.get("/api/v1/reports/catalog", headers=_headers("operator")).json()["data"]
    reader_catalog = client.get("/api/v1/reports/catalog", headers=_headers("read_only")).json()["data"]

    admin_keys = {r["key"] for r in admin_catalog["reports"]}
    operator_keys = {r["key"] for r in operator_catalog["reports"]}
    reader_keys = {r["key"] for r in reader_catalog["reports"]}

    assert len(admin_keys) == 22 and SECURITY_KEYS <= admin_keys and (MASTER_KEYS | MASTER_ADMIN_KEYS) <= admin_keys
    assert operator_keys == admin_keys - SECURITY_KEYS - MASTER_ADMIN_KEYS
    assert "employee-directory" in operator_keys
    # read_only cannot read employee data under the existing permission matrix.
    assert "employee-directory" not in reader_keys
    assert not (SECURITY_KEYS & reader_keys)
    assert {"company-directory", "asset-inventory", "supplier-directory"} <= reader_keys
    # Categories listed are exactly those that still have a report.
    for catalog in (admin_catalog, operator_catalog, reader_catalog):
        used = {r["category"] for r in catalog["reports"]}
        assert {c["key"] for c in catalog["categories"]} == used


def test_catalog_matches_the_permission_matrix():
    for role in ("admin", "operator", "read_only"):
        catalog = client.get("/api/v1/reports/catalog", headers=_headers(role)).json()["data"]
        by_key = {r.key: r for r in report_service.REPORTS}
        for item in catalog["reports"]:
            assert role in allowed_roles(by_key[item["key"]].resource, "read")
        listed = {r["key"] for r in catalog["reports"]}
        for report in report_service.REPORTS:
            assert (report.key in listed) == (role in allowed_roles(report.resource, "read"))


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/catalog",
        "/api/v1/reports/summary",
        "/api/v1/reports/filter-options",
        "/api/v1/reports/employee-directory",
        "/api/v1/reports/employee-directory/export",
    ],
)
def test_reports_require_authentication(path):
    assert client.get(path).status_code == 401


def test_read_only_cannot_run_or_export_employee_reports():
    reader = _headers("read_only")
    for response in (_report(reader, "employee-directory"), _export(reader, "employee-directory")):
        assert response.status_code == 403
        assert response.json()["error_code"] == "AUTH_FORBIDDEN"


def test_operator_cannot_run_or_export_security_reports_and_denial_is_audited():
    admin = _headers("admin")
    operator = _headers("operator")
    operator_id = client.get("/api/v1/auth/me", headers=operator).json()["data"]["id"]
    for key in SECURITY_KEYS:
        assert _report(operator, key).status_code == 403
        assert _export(operator, key).status_code == 403

    denials = client.get(
        "/api/v1/audit-logs",
        params={"action": "access_denied", "resource_type": "rbac", "user_id": operator_id, "limit": 100},
        headers=admin,
    ).json()["data"]["items"]
    endpoints = {d["new_value"]["endpoint"] for d in denials}
    assert "/api/v1/reports/audit-activity" in endpoints
    assert "/api/v1/reports/audit-activity/export" in endpoints


def test_forbidden_export_does_not_write_an_export_audit_row():
    admin = _headers("admin")
    reader = _headers("read_only")
    reader_id = client.get("/api/v1/auth/me", headers=reader).json()["data"]["id"]
    _export(reader, "employee-directory")
    exports = client.get(
        "/api/v1/audit-logs", params={"action": "export", "user_id": reader_id}, headers=admin
    ).json()["data"]["items"]
    assert exports == []


def test_unknown_report_is_404():
    admin = _headers("admin")
    assert _report(admin, "does-not-exist").status_code == 404
    assert _export(admin, "does-not-exist").json()["error_code"] == "REPORT_NOT_FOUND"


# --------------------------------------------------------------------------
# company isolation
# --------------------------------------------------------------------------
def test_operator_only_sees_own_company_in_employee_and_company_reports():
    admin = _headers("admin")
    company_a, name_a = _company(admin)
    company_b, name_b = _company(admin)
    emp_a = _employee(admin, company_a)
    emp_b = _employee(admin, company_b)
    operator_a = _headers("operator", company_id=company_a)

    directory = _items(operator_a, "employee-directory")
    emails = {row["email"] for row in directory}
    assert emp_a["email"] in emails and emp_b["email"] not in emails
    assert {row["company"] for row in directory} == {name_a}

    assert {row["name"] for row in _items(operator_a, "company-directory")} == {name_a}
    assert {row["company"] for row in _items(operator_a, "company-employee-summary")} == {name_a}

    # Asking for someone else's company is the ordinary "not found", never a 403.
    other = _report(operator_a, "employee-directory", company_id=company_b)
    assert other.status_code == 404 and other.json()["error_code"] == "COMPANY_NOT_FOUND"
    assert _export(operator_a, "employee-directory", company_id=company_b).status_code == 404

    admin_view = {row["email"] for row in _items(admin, "employee-directory", company_id=company_b)}
    assert admin_view == {emp_b["email"]}


def test_cross_company_attempt_is_audited():
    admin = _headers("admin")
    company_a, _ = _company(admin)
    company_b, _ = _company(admin)
    operator_a = _headers("operator", company_id=company_a)
    operator_id = client.get("/api/v1/auth/me", headers=operator_a).json()["data"]["id"]
    _report(operator_a, "employee-directory", company_id=company_b)
    rows = client.get(
        "/api/v1/audit-logs",
        params={"action": "access_denied", "resource_type": "rbac", "user_id": operator_id},
        headers=admin,
    ).json()["data"]["items"]
    assert any(r["new_value"].get("reason") == "cross_company" for r in rows)


def test_unknown_company_filter_is_404_for_admin():
    admin = _headers("admin")
    response = _report(admin, "employee-directory", company_id=999999999)
    assert response.status_code == 404


def test_operator_without_a_company_sees_nothing():
    admin = _headers("admin")
    operator = _headers("operator")
    db = SessionLocal()
    email = client.get("/api/v1/auth/me", headers=operator).json()["data"]["email"]
    db.query(User).filter(User.email == email).update({"company_id": None})
    db.commit()
    db.close()
    assert _items(operator, "employee-directory") == []
    assert _items(operator, "company-directory") == []


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------
def test_status_filter_semantics_default_all_and_specific():
    admin, company_id, _ = _fresh_scope()
    onboarded = _employee(admin, company_id)
    active = _employee(admin, company_id)
    exited = _employee(admin, company_id)
    _set_status(admin, active["id"], "active")
    _set_status(admin, exited["id"], "exited")

    def emails(**params):
        return {r["email"] for r in _items(admin, "employee-directory", company_id=company_id, **params)}

    assert emails() == {onboarded["email"], active["email"]}  # default: current only
    assert emails(status="all") == {onboarded["email"], active["email"], exited["email"]}
    assert emails(status="exited") == {exited["email"]}
    assert emails(status="active") == {active["email"]}


def test_department_job_role_and_search_filters_narrow_results():
    admin, company_id, _ = _fresh_scope()
    dept_a, dept_b = unique_word(), unique_word()
    role = unique_word()
    needle = unique_word()
    a = _employee(admin, company_id, department=dept_a, job_role=role, last_name=needle)
    b = _employee(admin, company_id, department=dept_b)

    def emails(**params):
        return {r["email"] for r in _items(admin, "employee-directory", company_id=company_id, **params)}

    assert emails(department=dept_a) == {a["email"]}
    assert emails(department=dept_b) == {b["email"]}
    assert emails(job_role=role) == {a["email"]}
    assert emails(search=needle) == {a["email"]}
    assert emails(search=needle.upper()) == {a["email"]}  # case-insensitive
    assert emails(department=dept_a, job_role=role, search=needle) == {a["email"]}
    assert emails(department=dept_b, job_role=role) == set()
    # LIKE wildcards in a search are literal text, not "match anything":
    # "%" appears in no data, and `x_yz...` would only match `xyyz...` if "_"
    # were treated as a one-character wildcard instead of a literal underscore.
    assert emails(search="%") == set()
    assert emails(search=needle[0] + "_" + needle[2:]) == set()
    assert emails(search=needle[0] + needle[1] + needle[2:]) == {a["email"]}


def test_date_range_filter_uses_inclusive_days_and_changes_results():
    admin, company_id, _ = _fresh_scope()
    employee = _employee(admin, company_id)
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    yesterday = today - timedelta(days=1)

    def total(**params):
        return _report(admin, "employee-directory", company_id=company_id, **params).json()["data"]["total"]

    assert total() == 1
    assert total(date_from=today.isoformat(), date_to=today.isoformat()) == 1  # inclusive day
    assert total(date_from=yesterday.isoformat()) == 1
    assert total(date_from=tomorrow.isoformat()) == 0
    assert total(date_to=yesterday.isoformat()) == 0
    assert employee["email"]


def test_invalid_filters_are_rejected_not_ignored():
    admin = _headers("admin")
    cases = [
        ("company-directory", {"department": "x"}),  # unsupported for this report
        ("employee-directory", {"status": "retired"}),  # not an allowed value
        ("employee-directory", {"date_from": "2026-02-02", "date_to": "2026-01-01"}),
        ("employee-directory", {"search": "x" * 150}),  # over the 100-char cap, under the 200 query cap
        ("audit-activity", {"action": "teleport"}),
        ("admin-changes", {"action": "login_success"}),  # a security action, not an admin change
    ]
    for key, params in cases:
        response = _report(admin, key, **params)
        assert response.status_code == 400, (key, params, response.text)
        assert response.json()["error_code"] == "REPORT_INVALID_FILTER"
    assert _report(admin, "employee-directory", date_from="not-a-date").status_code == 422
    assert _report(admin, "employee-directory", company_id=0).status_code == 422
    assert _report(admin, "employee-directory", limit=101).status_code == 422
    assert _report(admin, "employee-directory", limit=0).status_code == 422
    assert _report(admin, "employee-directory", offset=-1).status_code == 422


def test_invalid_sort_is_rejected():
    admin = _headers("admin")
    response = _report(admin, "employee-directory", sort_by="email); DROP TABLE employees;--")
    assert response.status_code == 400 and response.json()["error_code"] == "REPORT_INVALID_SORT"
    assert _report(admin, "company-directory", sort_by="contact_email").status_code == 400  # not sortable
    assert _report(admin, "employee-directory", sort_dir="sideways").status_code == 422


# --------------------------------------------------------------------------
# sorting + pagination
# --------------------------------------------------------------------------
def test_sorting_and_pagination():
    admin, company_id, _ = _fresh_scope()
    names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo"]
    for first in reversed(names):
        _employee(admin, company_id, first_name=first, last_name="Zed")

    def page(limit, offset, **params):
        return _report(admin, "employee-directory", company_id=company_id, limit=limit, offset=offset, **params).json()["data"]

    asc = [r["name"] for r in page(100, 0, sort_by="name", sort_dir="asc")["items"]]
    assert asc == [f"{n} Zed" for n in names]
    desc = [r["name"] for r in page(100, 0, sort_by="name", sort_dir="desc")["items"]]
    assert desc == list(reversed(asc))

    first = page(2, 0, sort_by="name", sort_dir="asc")
    second = page(2, 2, sort_by="name", sort_dir="asc")
    last = page(2, 4, sort_by="name", sort_dir="asc")
    assert first["total"] == second["total"] == last["total"] == 5
    assert [r["name"] for r in first["items"]] == asc[0:2]
    assert [r["name"] for r in second["items"]] == asc[2:4]
    assert [r["name"] for r in last["items"]] == asc[4:5]
    assert first["has_more"] is True and second["has_more"] is True and last["has_more"] is False
    assert page(2, 10)["items"] == []  # past the end: empty page, correct total
    assert page(2, 10)["total"] == 5
    assert first["sort_by"] == "name" and first["sort_dir"] == "asc"


# --------------------------------------------------------------------------
# aggregate reports
# --------------------------------------------------------------------------
def test_employee_aggregate_reports_match_the_data():
    admin, company_id, _ = _fresh_scope()
    dept_one, dept_two = unique_word(), unique_word()
    role_one, role_two = unique_word(), unique_word()
    e1 = _employee(admin, company_id, department=dept_one, job_role=role_one)
    e2 = _employee(admin, company_id, department=dept_one, job_role=role_two)
    e3 = _employee(admin, company_id, department=dept_two, job_role=role_one)
    _employee(admin, company_id)  # no department -> "Unassigned"
    gone = _employee(admin, company_id, department=dept_two, job_role=role_two)
    _set_status(admin, e1["id"], "active")
    _set_status(admin, gone["id"], "exited")

    by_dept = {r["department"]: r for r in _items(admin, "employees-by-department", company_id=company_id)}
    assert by_dept[dept_one]["total"] == 2 and by_dept[dept_one]["active"] == 1
    assert by_dept[dept_two]["total"] == 1  # exited excluded by default
    assert by_dept["Unassigned"]["total"] == 1
    with_exited = {r["department"]: r for r in _items(admin, "employees-by-department", company_id=company_id, status="all")}
    assert with_exited[dept_two]["total"] == 2

    by_role = {r["job_role"]: r["total"] for r in _items(admin, "employees-by-job-role", company_id=company_id)}
    assert by_role[role_one] == 2 and by_role[role_two] == 1

    by_status = {r["status"]: r["total"] for r in _items(admin, "employees-by-status", company_id=company_id)}
    assert by_status == {"onboarded": 3, "active": 1, "exited": 1}
    filtered = {r["status"]: r["total"] for r in _items(admin, "employees-by-status", company_id=company_id, department=dept_one)}
    assert filtered == {"onboarded": 1, "active": 1}
    assert e2["id"] and e3["id"]


def test_company_reports_match_the_data():
    admin, company_id, name = _fresh_scope()
    a = _employee(admin, company_id)
    b = _employee(admin, company_id)
    c = _employee(admin, company_id)
    _set_status(admin, a["id"], "active")
    _set_status(admin, c["id"], "exited")

    summary = _items(admin, "company-employee-summary", company_id=company_id)
    assert len(summary) == 1
    row = summary[0]
    assert row["company"] == name
    assert (row["total"], row["active"], row["onboarded"], row["on_leave"], row["exited"]) == (2, 1, 1, 0, 1)

    directory = {r["name"]: r for r in _items(admin, "company-directory", search=name)}
    assert directory[name]["employee_count"] == 2 and directory[name]["status"] == "active"

    deactivated, deactivated_name = _company(admin)
    assert client.delete(f"/api/v1/companies/{deactivated}", headers=admin).status_code == 200
    inactive = {r["name"]: r for r in _items(admin, "company-directory", status="inactive", search=deactivated_name)}
    assert inactive[deactivated_name]["status"] == "inactive"
    assert name not in {r["name"] for r in _items(admin, "company-directory", status="inactive", search=name)}
    assert b["id"]

    totals = {r["status"]: r for r in _items(admin, "company-status-summary")}
    assert totals["active"]["total"] >= 1 and totals["inactive"]["total"] >= 1
    assert totals["active"]["internal"] + totals["active"]["external"] == totals["active"]["total"]


def test_asset_and_supplier_reports_match_the_data():
    admin = _headers("admin")
    category = unique_word()
    manufacturer = unique_word()
    model_one, model_two = unique_word(), unique_word()
    supplier = client.post(
        "/api/v1/suppliers", json={"name": f"Sup {unique_word()}", "category": category, "terms": "Net 30"}, headers=admin
    ).json()["data"]
    other = client.post(
        "/api/v1/suppliers", json={"name": f"Sup {unique_word()}", "category": category}, headers=admin
    ).json()["data"]
    # An asset may only reference an approved supplier (app/services/asset_service.py).
    approved = client.patch(f"/api/v1/suppliers/{supplier['id']}/status", json={"status": "approved"}, headers=admin)
    assert approved.status_code == 200, approved.text

    def asset(model, **extra):
        created = client.post(
            "/api/v1/assets",
            json={"asset_tag": f"AST-{unique_word()}", "manufacturer": manufacturer, "model": model,
                  "supplier_id": supplier["id"], **extra},
            headers=admin,
        )
        assert created.status_code == 201, created.text
        return created.json()["data"]

    first = asset(model_one, serial_number="SN-1", purchase_cost="1200.50", current_value="900.00", currency="INR")
    asset(model_one)
    third = asset(model_two)
    assert client.patch(
        f"/api/v1/assets/{third['id']}/status", json={"status": "in_repair"}, headers=admin
    ).status_code == 200

    inventory = {r["asset_tag"]: r for r in _items(admin, "asset-inventory", manufacturer=manufacturer)}
    assert len(inventory) == 3
    row = inventory[first["asset_tag"]]
    assert row["supplier"] == supplier["name"] and row["serial_number"] == "SN-1"
    assert float(row["purchase_cost"]) == 1200.50 and row["currency"] == "INR"
    assert {r["asset_tag"] for r in _items(admin, "asset-inventory", manufacturer=manufacturer, status="in_repair")} == {third["asset_tag"]}
    assert {r["asset_tag"] for r in _items(admin, "asset-inventory", manufacturer=manufacturer, model=model_one)} == {
        a["asset_tag"] for a in inventory.values() if a["model"] == model_one
    }
    assert {r["asset_tag"] for r in _items(admin, "asset-inventory", search=first["asset_tag"].lower())} == {first["asset_tag"]}

    assert {r["manufacturer"]: r["total"] for r in _items(admin, "assets-by-manufacturer")}[manufacturer] == 3
    by_model = {r["model"]: r["total"] for r in _items(admin, "assets-by-model", manufacturer=manufacturer)}
    assert by_model == {model_one: 2, model_two: 1}
    by_status = {r["status"]: r["total"] for r in _items(admin, "assets-by-status", manufacturer=manufacturer)}
    assert by_status == {"registered": 2, "in_repair": 1}

    directory = {r["name"] for r in _items(admin, "supplier-directory", category=category)}
    assert directory == {supplier["name"], other["name"]}
    assert {r["category"]: r["total"] for r in _items(admin, "suppliers-by-category")}[category] == 2
    statuses = {r["status"]: r for r in _items(admin, "supplier-status-summary", category=category)}
    assert (statuses["approved"]["total"], statuses["onboarded"]["total"]) == (1, 1)
    assert {r["name"] for r in _items(admin, "supplier-directory", category=category, status="approved")} == {supplier["name"]}


def test_security_reports_reflect_real_activity():
    admin = _headers("admin")
    operator_email, _ = register_and_login()
    # register_and_login logs in once, so this user has audit events + a session.
    activity = _items(admin, "user-activity", search=operator_email)
    assert len(activity) == 1
    row = activity[0]
    assert row["user"] == operator_email and row["logins"] >= 1 and row["events"] >= row["logins"]

    sessions = _items(admin, "auth-session-summary", search=operator_email)
    assert len(sessions) == 1 and sessions[0]["sessions"] >= 1 and sessions[0]["active_sessions"] >= 1

    logins = _items(admin, "audit-activity", action="login_success", search=operator_email)
    assert logins and all(r["action"] == "login_success" and r["user"] == operator_email for r in logins)

    changes = _items(admin, "admin-changes", resource_type="company")
    assert changes and all(r["resource_type"] == "company" for r in changes)
    assert not any(r["action"] in ("login_success", "login_failure", "access_denied") for r in _items(admin, "admin-changes"))

    # Role filter + date filter actually change results.
    assert all(r["role"] == "admin" for r in _items(admin, "user-activity", role="admin"))
    future = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    assert _items(admin, "audit-activity", date_from=future) == []


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def test_export_contains_exactly_the_filtered_results_in_sort_order():
    admin, company_id, company_name = _fresh_scope()
    dept = unique_word()
    for first in ("Cara", "Anna", "Bella"):
        _employee(admin, company_id, first_name=first, last_name="Exp", department=dept)
    _employee(admin, company_id, department=unique_word())  # must NOT appear

    params = {"company_id": company_id, "department": dept, "sort_by": "name", "sort_dir": "desc"}
    response = _export(admin, "employee-directory", **params)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "employee-directory-" in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.csv"')

    rows = _parse_csv(response)
    catalog = client.get("/api/v1/reports/catalog", headers=admin).json()["data"]["reports"]
    spec = next(r for r in catalog if r["key"] == "employee-directory")
    assert rows[0] == [c["label"] for c in spec["columns"]]

    json_data = _report(admin, "employee-directory", limit=100, **params).json()["data"]
    assert len(rows) - 1 == json_data["total"] == 3
    assert response.headers["x-report-row-count"] == "3"
    name_col = rows[0].index("Name")
    assert [r[name_col] for r in rows[1:]] == ["Cara Exp", "Bella Exp", "Anna Exp"]
    assert [r[name_col] for r in rows[1:]] == [r["name"] for r in json_data["items"]]
    assert {r[rows[0].index("Company")] for r in rows[1:]} == {company_name}


def test_export_returns_every_row_not_just_one_page():
    admin, company_id, _ = _fresh_scope()
    for _i in range(7):
        _employee(admin, company_id)
    page = _report(admin, "employee-directory", company_id=company_id, limit=3).json()["data"]
    assert len(page["items"]) == 3 and page["total"] == 7
    rows = _parse_csv(_export(admin, "employee-directory", company_id=company_id))
    assert len(rows) - 1 == 7


def test_export_is_audited_with_filters_and_count_but_no_data():
    admin, company_id, _ = _fresh_scope()
    employee = _employee(admin, company_id, department="AuditDept")
    admin_id = client.get("/api/v1/auth/me", headers=admin).json()["data"]["id"]
    assert _export(admin, "employee-directory", company_id=company_id, department="AuditDept").status_code == 200

    logs = client.get(
        "/api/v1/audit-logs",
        params={"action": "export", "resource_type": "report", "resource_id": "employee-directory", "user_id": admin_id},
        headers=admin,
    ).json()["data"]["items"]
    assert logs
    detail = logs[0]["new_value"]
    assert detail["report"] == "employee-directory" and detail["format"] == "csv"
    assert detail["row_count"] == 1
    assert detail["filters"] == {"company_id": company_id, "department": "AuditDept"}
    assert employee["email"] not in json.dumps(logs)  # row data never goes into the audit trail
    # The export shows up in the Audit Activity report too.
    exports = _items(admin, "audit-activity", action="export", resource_type="report")
    assert any(r["resource_id"] == "employee-directory" for r in exports)


def test_export_over_the_cap_is_refused_and_not_audited(monkeypatch):
    admin, company_id, _ = _fresh_scope()
    _employee(admin, company_id)
    _employee(admin, company_id)
    monkeypatch.setattr(report_service, "MAX_EXPORT_ROWS", 1)
    admin_id = client.get("/api/v1/auth/me", headers=admin).json()["data"]["id"]
    response = _export(admin, "employee-directory", company_id=company_id)
    assert response.status_code == 400 and response.json()["error_code"] == "REPORT_EXPORT_TOO_LARGE"
    monkeypatch.undo()
    logs = client.get(
        "/api/v1/audit-logs", params={"action": "export", "user_id": admin_id, "resource_id": "employee-directory"}, headers=admin
    ).json()["data"]["items"]
    assert all(entry["new_value"]["filters"].get("company_id") != company_id for entry in logs)


def test_every_report_runs_and_exports_for_admin():
    admin = _headers("admin")
    catalog = client.get("/api/v1/reports/catalog", headers=admin).json()["data"]["reports"]
    assert len(catalog) == 22
    for spec in catalog:
        response = _report(admin, spec["key"], limit=5)
        assert response.status_code == 200, (spec["key"], response.text)
        data = response.json()["data"]
        assert set(data) >= {"items", "total", "limit", "offset", "has_more", "report", "sort_by", "sort_dir", "filters"}
        expected = {c["key"] for c in spec["columns"]}
        for item in data["items"]:
            assert expected <= set(item), (spec["key"], expected - set(item))
        sortable = [c["key"] for c in spec["columns"] if c["sortable"]]
        assert sortable, spec["key"]
        for column in sortable:  # every advertised sortable column really sorts
            for direction in ("asc", "desc"):
                assert _report(admin, spec["key"], limit=5, sort_by=column, sort_dir=direction).status_code == 200, (
                    spec["key"], column, direction)
        # The two row-per-event reports grow without bound in a long-lived
        # test database, so narrow them (the export cap is exercised on its
        # own in test_export_over_the_cap_is_refused_and_not_audited).
        narrow = {"audit-activity": {"action": "export"}, "admin-changes": {"action": "role_change"}}.get(spec["key"], {})
        exported = _export(admin, spec["key"], **narrow)
        assert exported.status_code == 200 and exported.headers["content-type"].startswith("text/csv")
        assert _parse_csv(exported)[0] == [c["label"] for c in spec["columns"]]


# --------------------------------------------------------------------------
# sensitive data
# --------------------------------------------------------------------------
def test_sensitive_employee_fields_never_appear_in_reports_or_exports():
    admin, company_id, _ = _fresh_scope()
    secrets = {
        "phone_number": "9876501234",
        "address": f"Secret Street {unique_word()}",
        "pan_number": "ABCDE1234F",
        "aadhaar_number": "123456789012",
        "bank_account_number": "55512345678901",
        "bank_ifsc": "HDFC0001234",
    }
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": unique_word(), "last_name": unique_word(), "email": unique_email(), **secrets},
        headers=admin,
    )
    assert created.status_code == 201, created.text

    json_text = _report(admin, "employee-directory", company_id=company_id).text
    csv_response = _export(admin, "employee-directory", company_id=company_id)
    csv_text = csv_response.content.decode("utf-8")
    for value in secrets.values():
        assert value not in json_text and value not in csv_text
    for field in FORBIDDEN_FIELD_NAMES:  # no such key in the JSON rows...
        assert f'"{field}"' not in json_text, field
    headers = [h.lower().replace(" ", "_") for h in _parse_csv(csv_response)[0]]
    assert not (set(headers) & FORBIDDEN_FIELD_NAMES)  # ...and no such column in the CSV

    for key in report_service._BY_KEY:
        data = _report(admin, key, limit=100).json()["data"]
        for item in data["items"]:
            assert not (set(item) & FORBIDDEN_FIELD_NAMES), (key, set(item) & FORBIDDEN_FIELD_NAMES)


# --------------------------------------------------------------------------
# summary + filter options
# --------------------------------------------------------------------------
def test_summary_matches_the_database_for_admin():
    admin = _headers("admin")
    metrics = {m["key"]: m for m in client.get("/api/v1/reports/summary", headers=admin).json()["data"]["metrics"]}
    db = SessionLocal()
    try:
        assert metrics["total_employees"]["value"] == db.scalar(select(func.count(Employee.id)).where(Employee.status != "exited"))
        assert metrics["active_employees"]["value"] == db.scalar(select(func.count(Employee.id)).where(Employee.status == "active"))
        assert metrics["total_companies"]["value"] == db.scalar(select(func.count(Company.id)))
        assert metrics["total_assets"]["value"] == db.scalar(select(func.count(Asset.id)))
        assert metrics["total_suppliers"]["value"] == db.scalar(select(func.count(Supplier.id)))
    finally:
        db.close()
    assert "recent_admin_activity" in metrics


def test_summary_cards_link_to_reports_that_reproduce_their_numbers():
    admin = _headers("admin")
    metrics = client.get("/api/v1/reports/summary", headers=admin).json()["data"]["metrics"]
    for metric in metrics:
        total = _report(admin, metric["report"], limit=1, **metric["filters"]).json()["data"]["total"]
        assert total == metric["value"], (metric["key"], total, metric["value"])


def test_summary_is_scoped_and_permission_filtered_for_operator_and_reader():
    admin = _headers("admin")
    company_id, _ = _company(admin)
    _employee(admin, company_id)
    second = _employee(admin, company_id)
    _set_status(admin, second["id"], "active")
    operator = _headers("operator", company_id=company_id)
    reader = _headers("read_only", company_id=company_id)

    operator_metrics = {m["key"]: m for m in client.get("/api/v1/reports/summary", headers=operator).json()["data"]["metrics"]}
    assert operator_metrics["total_employees"]["value"] == 2
    assert operator_metrics["active_employees"]["value"] == 1
    assert operator_metrics["total_companies"]["value"] == 1  # own company only
    assert "recent_admin_activity" not in operator_metrics  # audit data is admin-only

    reader_keys = {m["key"] for m in client.get("/api/v1/reports/summary", headers=reader).json()["data"]["metrics"]}
    assert not ({"total_employees", "active_employees", "recent_admin_activity"} & reader_keys)
    assert {"total_companies", "total_assets", "total_suppliers"} <= reader_keys


def test_filter_options_are_scoped_to_what_the_caller_can_report_on():
    admin = _headers("admin")
    company_a, name_a = _company(admin)
    company_b, name_b = _company(admin)
    dept_a, dept_b = unique_word(), unique_word()
    _employee(admin, company_a, department=dept_a)
    _employee(admin, company_b, department=dept_b)
    operator_a = _headers("operator", company_id=company_a)
    reader = _headers("read_only")

    operator_options = client.get("/api/v1/reports/filter-options", headers=operator_a).json()["data"]
    assert dept_a in operator_options["departments"] and dept_b not in operator_options["departments"]
    assert operator_options["companies"] == [{"id": company_a, "name": name_a}]

    admin_options = client.get("/api/v1/reports/filter-options", headers=admin).json()["data"]
    assert {dept_a, dept_b} <= set(admin_options["departments"])
    assert {company_a, company_b} <= {c["id"] for c in admin_options["companies"]}

    reader_options = client.get("/api/v1/reports/filter-options", headers=reader).json()["data"]
    assert "departments" not in reader_options and "job_roles" not in reader_options


# --------------------------------------------------------------------------
# CSV helper
# --------------------------------------------------------------------------
def test_csv_cells_neutralise_spreadsheet_formulas_but_keep_real_numbers():
    for text in ("=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tTAB", "\rCR"):
        assert csv_cell(text).startswith("'"), text
    assert csv_cell(-5) == "-5" and csv_cell(3.5) == "3.5" and csv_cell(Decimal("-1200.50")) == "-1200.50"
    assert csv_cell(None) == "" and csv_cell(True) == "Yes" and csv_cell(False) == "No"
    assert csv_cell("normal") == "normal" and csv_cell("a-b") == "a-b"
    assert csv_cell(date(2026, 10, 26)) == "2026-10-26"
    assert csv_cell(datetime(2026, 10, 26, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))) == "2026-10-26T06:30:00+00:00"


def test_csv_round_trips_commas_quotes_and_newlines():
    rows = [["a,b", 'say "hi"', "line1\nline2"], ["=cmd", None, 7]]
    text = build_csv(["h1", "h2", "h3"], rows)
    assert text.startswith(UTF8_BOM) and "\r\n" in text
    parsed = list(csv.reader(io.StringIO(text.lstrip(UTF8_BOM))))
    assert parsed[0] == ["h1", "h2", "h3"]
    assert parsed[1] == ["a,b", 'say "hi"', "line1\nline2"]
    assert parsed[2] == ["'=cmd", "", "7"]
