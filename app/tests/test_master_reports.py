"""Master Management reports: Master Summary, Master Values, Unused Master
Values and Master Changes — access, accuracy against the database, filters,
sorting/paging, export, and audit logging.

The test database is shared and accumulates rows, so every test creates its own
uniquely-named values and asserts against those.
"""
import csv
import io

import pytest
from sqlalchemy import text

from app.core.csv_export import UTF8_BOM
from app.core.master_data import LINKED_MASTERS, MASTER_TYPES
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_code, unique_email, unique_word

ALL_MASTERS = set(LINKED_MASTERS) | set(MASTER_TYPES)
MASTER_REPORTS = {"master-summary", "master-values", "master-unused-values", "master-changes"}


def _headers(role="admin"):
    email, _ = register_and_login()
    db = SessionLocal()
    db.query(User).filter(User.email == email).first().role = role
    db.commit()
    db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin():
    return _headers("admin")


def _report(headers, key, **params):
    return client.get(f"/api/v1/reports/{key}", params=params, headers=headers)


def _rows(headers, key, **params):
    response = _report(headers, key, limit=100, **params)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


def _name(prefix="Val"):
    return f"{prefix} {unique_word()}"


def _company(admin):
    created = client.post(
        "/api/v1/companies",
        json={"name": f"MR {unique_word()}", "address": "1 Test Street", "contact_email": "c@example.com"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _employee(admin, company_id, **extra):
    created = client.post(
        "/api/v1/employees",
        json={"company_id": company_id, "first_name": unique_word(), "last_name": unique_word(), "email": unique_email(), **extra},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _value_row(rows, name):
    match = [r for r in rows if r["name"] == name]
    assert len(match) == 1, (name, match)
    return match[0]


# --------------------------------------------------------------------------
# catalog and access
# --------------------------------------------------------------------------
def test_catalog_has_a_master_management_category_for_every_role():
    for role, expected in (("admin", MASTER_REPORTS), ("operator", MASTER_REPORTS - {"master-changes"}), ("read_only", MASTER_REPORTS - {"master-changes"})):
        catalog = client.get("/api/v1/reports/catalog", headers=_headers(role)).json()["data"]
        keys = {r["key"] for r in catalog["reports"] if r["category"] == "master"}
        assert keys == expected, role
        assert "master" in {c["key"] for c in catalog["categories"]}
    catalog = client.get("/api/v1/reports/catalog", headers=_headers("admin")).json()["data"]
    assert [c["label"] for c in catalog["categories"] if c["key"] == "master"] == ["Master Management"]


@pytest.mark.parametrize("role", ["operator", "read_only"])
def test_non_admins_can_run_the_value_reports_but_not_the_change_history(role):
    headers = _headers(role)
    for key in ("master-summary", "master-values", "master-unused-values"):
        assert _report(headers, key).status_code == 200, key
        assert client.get(f"/api/v1/reports/{key}/export", headers=headers).status_code == 200, key
    for path in ("master-changes", "master-changes/export"):
        denied = client.get(f"/api/v1/reports/{path}", headers=headers)
        assert denied.status_code == 403, path
    db = SessionLocal()
    try:
        denials = db.query(AuditLog).filter(AuditLog.action == "access_denied", AuditLog.resource_type == "rbac").count()
    finally:
        db.close()
    assert denials > 0


def test_authentication_required():
    for key in MASTER_REPORTS:
        assert client.get(f"/api/v1/reports/{key}").status_code == 401


# --------------------------------------------------------------------------
# summary + values agree with the database
# --------------------------------------------------------------------------
def test_summary_lists_every_master_with_counts_matching_the_database(admin):
    rows = {r["master"]: r for r in _rows(admin, "master-summary")}
    assert len(rows) == len(ALL_MASTERS)
    plural = {**{m.key: m.plural for m in LINKED_MASTERS.values()}, **{t.key: t.plural for t in MASTER_TYPES.values()}}
    tables = {"department": "departments", "job_role": "job_roles", "application": "applications", "manufacturer": "manufacturers", "asset_model": "asset_models"}
    db = SessionLocal()
    try:
        for key, table in tables.items():
            active, inactive, total = db.execute(
                text(f"select count(*) filter (where is_active), count(*) filter (where not is_active), count(*) from {table}")
            ).one()
            row = rows[plural[key]]
            assert (row["active"], row["inactive"], row["total"]) == (active, inactive, total), key
        for key in MASTER_TYPES:
            active, inactive, total = db.execute(
                text("select count(*) filter (where is_active), count(*) filter (where not is_active), count(*) from master_items where master_type = :t"),
                {"t": key},
            ).one()
            row = rows[plural[key]]
            assert (row["active"], row["inactive"], row["total"]) == (active, inactive, total), key
    finally:
        db.close()
    assert all(r["active"] + r["inactive"] == r["total"] and r["in_use"] <= r["total"] for r in rows.values())
    assert {r["group"] for r in rows.values()} == {"People", "Assets", "Suppliers"}


def test_values_total_equals_the_sum_of_the_summary(admin):
    summary = _rows(admin, "master-summary")
    total = _report(admin, "master-values", limit=1).json()["data"]["total"]
    assert total == sum(r["total"] for r in summary)
    active = _report(admin, "master-values", limit=1, status="active").json()["data"]["total"]
    inactive = _report(admin, "master-values", limit=1, status="inactive").json()["data"]["total"]
    assert (active, inactive) == (sum(r["active"] for r in summary), sum(r["inactive"] for r in summary))


def test_master_filter_narrows_both_reports_to_one_master(admin):
    one = _rows(admin, "master-summary", master="job_role")
    assert [r["master"] for r in one] == ["Job Roles"]
    values = _rows(admin, "master-values", master="payment_terms")
    assert values and {r["master"] for r in values} == {"Payment Terms"}


# --------------------------------------------------------------------------
# "in use" is accurate for each kind of master
# --------------------------------------------------------------------------
def test_in_use_counts_follow_each_masters_own_rule(admin):
    company_id = _company(admin)

    # Job role: counted once whether on designation, job_role, or both; exited excluded.
    role = client.post("/api/v1/job-roles", json={"name": _name("Role")}, headers=admin).json()["data"]
    _employee(admin, company_id, designation=role["name"])
    _employee(admin, company_id, job_role=role["name"])
    _employee(admin, company_id, designation=role["name"], job_role=role["name"])
    gone = _employee(admin, company_id, designation=role["name"])
    client.patch(f"/api/v1/employees/{gone['id']}/status", json={"status": "exited"}, headers=admin)

    # Department by name.
    dept = client.post("/api/v1/departments", json={"name": _name("Dept")}, headers=admin).json()["data"]
    _employee(admin, company_id, department=dept["name"])

    # Manufacturer / model by name, on a registered (non-disposed) asset.
    maker = client.post("/api/v1/manufacturers", json={"name": _name("Maker")}, headers=admin).json()["data"]
    model = client.post("/api/v1/asset-models", json={"name": _name("Model")}, headers=admin).json()["data"]
    supplier_id = client.post("/api/v1/suppliers", json={"name": f"S {unique_word()}"}, headers=admin).json()["data"]["id"]
    client.patch(f"/api/v1/suppliers/{supplier_id}/status", json={"status": "approved"}, headers=admin)
    asset = client.post(
        "/api/v1/assets",
        json={"asset_tag": f"T-{unique_word()}", "manufacturer": maker["name"], "model": model["name"], "supplier_id": supplier_id},
        headers=admin,
    )
    assert asset.status_code == 201, asset.text

    # A list master used by a supplier (any capitalisation).
    category = client.post("/api/v1/master-data/supplier_category", json={"name": _name("Cat")}, headers=admin).json()["data"]
    client.post("/api/v1/suppliers", json={"name": f"S2 {unique_word()}", "category": category["name"].upper()}, headers=admin)


    def one(master, name):
        return _value_row(_rows(admin, "master-values", master=master, search=name), name)

    assert one("job_role", role["name"])["in_use"] == 3
    assert one("department", dept["name"])["in_use"] == 1
    assert one("manufacturer", maker["name"])["in_use"] == 1
    assert one("asset_model", model["name"])["in_use"] == 1
    assert one("supplier_category", category["name"])["in_use"] == 1

    # Disposing the asset takes it out of the manufacturer/model counts.
    client.patch(f"/api/v1/assets/{asset.json()['data']['id']}/status", json={"status": "disposed"}, headers=admin)
    assert one("manufacturer", maker["name"])["in_use"] == 0
    assert one("asset_model", model["name"])["in_use"] == 0


def test_application_access_and_category_usage(admin):
    company_id = _company(admin)
    cat = client.post("/api/v1/master-data/application_category", json={"name": _name("AppCat")}, headers=admin).json()["data"]
    app = client.post("/api/v1/applications", json={"name": _name("App"), "code": unique_code(), "category": cat["name"]}, headers=admin)
    assert app.status_code == 201, app.text
    application = app.json()["data"]
    _employee(admin, company_id, application_ids=[application["id"]])
    _employee(admin, company_id, application_ids=[application["id"]])
    assert _value_row(_rows(admin, "master-values", master="application", search=application["name"]), application["name"])["in_use"] == 2
    assert _value_row(_rows(admin, "master-values", master="application_category", search=cat["name"]), cat["name"])["in_use"] == 1


# --------------------------------------------------------------------------
# unused values
# --------------------------------------------------------------------------
def test_unused_report_lists_active_values_with_no_records(admin):
    name = _name("Idle")
    item = client.post("/api/v1/master-data/payment_terms", json={"name": name}, headers=admin).json()["data"]
    assert name in {r["name"] for r in _rows(admin, "master-unused-values", master="payment_terms", search=name)}

    client.post("/api/v1/suppliers", json={"name": f"U {unique_word()}", "terms": name}, headers=admin)
    assert name not in {r["name"] for r in _rows(admin, "master-unused-values", master="payment_terms", search=name)}

    other = client.post("/api/v1/master-data/payment_terms", json={"name": _name("Gone")}, headers=admin).json()["data"]
    client.delete(f"/api/v1/master-data/payment_terms/{other['id']}", headers=admin)
    assert other["name"] not in {r["name"] for r in _rows(admin, "master-unused-values", master="payment_terms", search=other["name"])}


def test_every_unused_row_really_has_zero_in_use(admin):
    rows = _rows(admin, "master-unused-values")
    assert rows and all(r["status"] == "active" and r["in_use"] == 0 for r in rows)


# --------------------------------------------------------------------------
# filters, sorting, paging, validation
# --------------------------------------------------------------------------
def test_search_status_dates_sorting_and_paging(admin):
    word = unique_word()
    names = [f"{word} {c}" for c in "cab"]
    ids = [client.post("/api/v1/master-data/application_category", json={"name": n}, headers=admin).json()["data"]["id"] for n in names]
    client.delete(f"/api/v1/master-data/application_category/{ids[0]}", headers=admin)

    rows = _rows(admin, "master-values", search=word.upper())
    assert sorted(r["name"] for r in rows) == sorted(names)
    assert {r["status"] for r in _rows(admin, "master-values", search=word, status="inactive")} == {"inactive"}
    assert [r["name"] for r in _rows(admin, "master-values", search=word, sort_by="name", sort_dir="desc")] == sorted(names, reverse=True)

    page1 = _report(admin, "master-values", search=word, limit=2, offset=0).json()["data"]
    page2 = _report(admin, "master-values", search=word, limit=2, offset=2).json()["data"]
    assert (page1["total"], len(page1["items"]), page1["has_more"], len(page2["items"]), page2["has_more"]) == (3, 2, True, 1, False)

    from datetime import date, timedelta

    today = date.today().isoformat()
    assert _rows(admin, "master-values", search=word, date_from=today, date_to=today)
    future = (date.today() + timedelta(days=2)).isoformat()
    assert _rows(admin, "master-values", search=word, date_from=future) == []


def test_search_treats_wildcards_literally(admin):
    word = unique_word()
    client.post("/api/v1/master-data/application_category", json={"name": f"{word}ab"}, headers=admin)
    assert _rows(admin, "master-values", search=f"{word}%") == []
    assert _rows(admin, "master-values", search=f"{word[:-1]}_b") == []


@pytest.mark.parametrize(
    "key,params",
    [
        ("master-values", {"master": "nonsense"}),
        ("master-values", {"status": "bogus"}),
        ("master-values", {"sort_by": "bogus"}),
        ("master-summary", {"status": "active"}),  # not a filter of this report
        ("master-unused-values", {"status": "inactive"}),
        ("master-changes", {"master": "nonsense"}),
        ("master-changes", {"action": "login_success"}),
    ],
)
def test_invalid_filters_and_sorts_are_rejected(admin, key, params):
    assert _report(admin, key, **params).status_code == 400


# --------------------------------------------------------------------------
# change history
# --------------------------------------------------------------------------
def test_changes_report_shows_master_changes_with_who_and_which_master(admin):
    item = client.post("/api/v1/master-data/supplier_category", json={"name": _name("Chg")}, headers=admin).json()["data"]
    client.put(f"/api/v1/master-data/supplier_category/{item['id']}", json={"description": "x"}, headers=admin)
    client.delete(f"/api/v1/master-data/supplier_category/{item['id']}", headers=admin)
    role = client.post("/api/v1/job-roles", json={"name": _name("ChgRole")}, headers=admin).json()["data"]

    mine = [r for r in _rows(admin, "master-changes", master="supplier_category") if r["resource_id"] == str(item["id"])]
    assert sorted(r["action"] for r in mine) == ["create", "delete", "update"]
    assert {r["master"] for r in mine} == {"Supplier Categories"}
    assert all(r["user"].endswith("@casterly.com") for r in mine)

    roles = [r for r in _rows(admin, "master-changes", master="job_role") if r["resource_id"] == str(role["id"])]
    assert [r["action"] for r in roles] == ["create"] and roles[0]["master"] == "Job Roles"

    # The master filter really separates them, and the action filter works.
    assert not [r for r in _rows(admin, "master-changes", master="job_role") if r["resource_id"] == str(item["id"]) and r["master"] == "Supplier Categories"]
    deletes = _rows(admin, "master-changes", action="delete", search=str(item["id"]))
    assert any(r["resource_id"] == str(item["id"]) for r in deletes)
    assert {r["master"] for r in _rows(admin, "master-changes")} <= {m.plural for m in LINKED_MASTERS.values()} | {t.plural for t in MASTER_TYPES.values()}


def test_changes_report_never_exposes_before_after_values(admin):
    rows = _rows(admin, "master-changes")
    assert rows and not ({"old_value", "new_value"} & set(rows[0]))


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
@pytest.mark.parametrize("key", sorted(MASTER_REPORTS))
def test_export_matches_the_filtered_results_and_is_audited(admin, key):
    params = {"master": "payment_terms"}
    shown = _report(admin, key, limit=100, **params).json()["data"]
    response = client.get(f"/api/v1/reports/{key}/export", params=params, headers=admin)
    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert body.startswith(UTF8_BOM)
    rows = list(csv.reader(io.StringIO(body.lstrip(UTF8_BOM))))
    assert len(rows) - 1 == shown["total"] == int(response.headers["X-Report-Row-Count"])
    db = SessionLocal()
    try:
        latest = db.query(AuditLog).filter(AuditLog.action == "export", AuditLog.resource_type == "report").order_by(AuditLog.id.desc()).first()
    finally:
        db.close()
    assert latest is not None
