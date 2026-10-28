"""Master Management: the list masters (Application Category, Supplier Category,
Payment Terms), the catalog behind the page's dropdown (which also lists the
five masters that keep their own screens), and the page-level contracts.

The test database is shared and accumulates rows, so every test uses its own
uniquely-named items (conftest.unique_word) and asserts only against those.
"""
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.master_data import LINKED_MASTERS, MASTER_TYPES
from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_code, unique_word

BASE = "/api/v1/master-data"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
LISTS = list(MASTER_TYPES)


def _headers(role: str) -> dict:
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


def _name(prefix="Item") -> str:
    return f"{prefix} {unique_word()}"


def _ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()["data"]


def _create(admin, master_type, name=None, **extra):
    return client.post(f"{BASE}/{master_type}", json={"name": name or _name(), **extra}, headers=admin)


# --------------------------------------------------------------------------
# the catalog behind the dropdown
# --------------------------------------------------------------------------
def test_catalog_lists_every_master_grouped_for_the_dropdown(admin):
    data = _ok(client.get(f"{BASE}/catalog", headers=admin))
    masters = {m["key"]: m for m in data["masters"]}
    assert set(LINKED_MASTERS) | set(MASTER_TYPES) == set(masters)
    assert data["groups"] == ["People", "Assets", "Suppliers"]
    assert {m["group"] for m in masters.values()} <= set(data["groups"])
    assert {m["kind"] for m in masters.values()} == {"page", "list"}
    assert all(masters[k]["kind"] == "page" for k in LINKED_MASTERS)
    assert all(masters[k]["kind"] == "list" for k in MASTER_TYPES)
    # slugs are unique (they drive the URL and the dropdown values)
    assert len({m["slug"] for m in masters.values()}) == len(masters)


def test_catalog_counts_match_the_database(admin):
    tables = {"department": "departments", "job_role": "job_roles", "application": "applications",
              "manufacturer": "manufacturers", "asset_model": "asset_models"}
    masters = {m["key"]: m for m in _ok(client.get(f"{BASE}/catalog", headers=admin))["masters"]}
    db = SessionLocal()
    try:
        for key, table in tables.items():
            active, total = db.execute(text(f"select count(*) filter (where is_active), count(*) from {table}")).one()
            assert (masters[key]["active_count"], masters[key]["total_count"]) == (active, total), key
        for key in MASTER_TYPES:
            active, total = db.execute(
                text("select count(*) filter (where is_active), count(*) from master_items where master_type = :t"), {"t": key}
            ).one()
            assert (masters[key]["active_count"], masters[key]["total_count"]) == (active, total), key
    finally:
        db.close()


def test_catalog_is_ordered_by_group_then_page_before_list(admin):
    from app.core.master_data import GROUP_ORDER

    masters = _ok(client.get(f"{BASE}/catalog", headers=admin))["masters"]
    groups = [GROUP_ORDER.index(m["group"]) for m in masters]
    assert groups == sorted(groups)
    for g in set(groups):
        kinds = [{"page": 0, "list": 1}[m["kind"]] for m in masters if GROUP_ORDER.index(m["group"]) == g]
        assert kinds == sorted(kinds)


def test_linked_master_counts_follow_their_own_apis(admin):
    def entry():
        return {m["key"]: m for m in _ok(client.get(f"{BASE}/catalog", headers=admin))["masters"]}["manufacturer"]

    before = entry()
    assert client.post("/api/v1/manufacturers", json={"name": _name("Maker")}, headers=admin).status_code == 201
    after = entry()
    assert (after["total_count"], after["active_count"]) == (before["total_count"] + 1, before["active_count"] + 1)


def test_starter_values_cover_what_the_forms_used_to_hardcode(admin):
    def names(key):
        return {o["name"] for o in _ok(client.get(f"{BASE}/{key}/options", headers=admin))["items"]}

    assert {"Core", "People", "Assets", "Operations", "Administration"} <= names("application_category")
    assert {"Hardware", "Software", "Office Supplies", "Logistics", "Facilities", "Maintenance & Support", "Consulting", "Raw Materials"} <= names("supplier_category")
    assert {"Due on Receipt", "Net 15", "Net 30", "Net 45", "Net 60", "Net 90", "COD", "Advance Payment", "50% Advance, 50% on Delivery"} <= names("payment_terms")


# --------------------------------------------------------------------------
# list masters: CRUD, validation, duplicates, filters
# --------------------------------------------------------------------------
@pytest.mark.parametrize("master_type", LISTS)
def test_lifecycle(admin, master_type):
    name = _name()
    created = _ok(_create(admin, master_type, name, description="  A description  "), 201)
    assert (created["name"], created["master_type"], created["description"], created["is_active"]) == (name, master_type, "A description", True)
    assert created["usage_count"] == 0

    item_id = created["id"]
    assert _ok(client.get(f"{BASE}/{master_type}/{item_id}", headers=admin))["name"] == name
    assert _ok(client.put(f"{BASE}/{master_type}/{item_id}", json={"description": "Changed"}, headers=admin))["description"] == "Changed"
    assert _ok(client.put(f"{BASE}/{master_type}/{item_id}", json={"description": None}, headers=admin))["description"] is None

    renamed = _name("Renamed")
    assert _ok(client.put(f"{BASE}/{master_type}/{item_id}", json={"name": renamed}, headers=admin))["name"] == renamed

    assert _ok(client.delete(f"{BASE}/{master_type}/{item_id}", headers=admin))["is_active"] is False
    assert _ok(client.delete(f"{BASE}/{master_type}/{item_id}", headers=admin))["is_active"] is False  # idempotent
    assert _ok(client.get(f"{BASE}/{master_type}", params={"search": renamed}, headers=admin))["total"] == 0
    inactive = _ok(client.get(f"{BASE}/{master_type}", params={"search": renamed, "status": "inactive"}, headers=admin))
    assert [i["id"] for i in inactive["items"]] == [item_id]
    assert _ok(client.patch(f"{BASE}/{master_type}/{item_id}/reactivate", headers=admin))["is_active"] is True


def test_hyphenated_urls_work_and_unknown_lists_404(admin):
    created = _ok(client.post(f"{BASE}/supplier-category", json={"name": _name()}, headers=admin), 201)
    assert created["master_type"] == "supplier_category"
    assert client.get(f"{BASE}/nonsense", headers=admin).status_code == 404
    # the linked masters are not served by this API — they keep their own
    assert client.get(f"{BASE}/job_role", headers=admin).status_code == 404
    # an id from another list is not found through this one
    assert client.get(f"{BASE}/payment_terms/{created['id']}", headers=admin).status_code == 404
    assert client.put(f"{BASE}/payment_terms/{created['id']}", json={"description": "x"}, headers=admin).status_code == 404


def test_duplicates_rejected_case_insensitively_but_allowed_across_lists(admin):
    name = _name("Dup")
    _ok(_create(admin, "supplier_category", name), 201)
    again = _create(admin, "supplier_category", name.upper())
    assert again.status_code == 400 and again.json()["error_code"] == "MASTER_ITEM_ALREADY_EXISTS"
    assert _create(admin, "payment_terms", name).status_code == 201

    other = _ok(_create(admin, "supplier_category"), 201)
    clash = client.put(f"{BASE}/supplier_category/{other['id']}", json={"name": name.lower()}, headers=admin)
    assert clash.status_code == 400 and clash.json()["error_code"] == "MASTER_ITEM_ALREADY_EXISTS"


@pytest.mark.parametrize("payload", [{"name": ""}, {"name": "   "}, {"name": "x" * 151}, {"name": "ok", "description": "d" * 501}, {}])
def test_invalid_payloads_rejected(admin, payload):
    assert client.post(f"{BASE}/supplier_category", json=payload, headers=admin).status_code == 422


def test_codes_and_parents_are_not_part_of_these_lists(admin):
    refused = _create(admin, "supplier_category", code="ABC")
    assert refused.status_code == 400 and refused.json()["error_code"] == "MASTER_ITEM_CODE_NOT_SUPPORTED"
    parent = _ok(_create(admin, "supplier_category"), 201)
    refused = _create(admin, "payment_terms", parent_id=parent["id"])
    assert refused.status_code == 400 and refused.json()["error_code"] == "MASTER_ITEM_PARENT_NOT_ALLOWED"


def test_name_whitespace_is_normalised(admin):
    word = unique_word()
    assert _ok(_create(admin, "payment_terms", f"  Net    {word}  "), 201)["name"] == f"Net {word}"


def test_search_status_sort_and_pagination(admin):
    word = unique_word()
    names = [f"{word} {c}" for c in "cab"]
    ids = [_ok(_create(admin, "payment_terms", n, description=f"note {word}"), 201)["id"] for n in names]
    client.delete(f"{BASE}/payment_terms/{ids[0]}", headers=admin)

    def listing(**params):
        return _ok(client.get(f"{BASE}/payment_terms", params={"search": word, **params}, headers=admin))

    assert listing()["total"] == 2
    assert (listing(status="all")["total"], listing(status="inactive")["total"]) == (3, 1)
    assert [i["name"] for i in listing(status="all")["items"]] == sorted(names)
    assert [i["name"] for i in listing(status="all", sort_dir="desc")["items"]] == sorted(names, reverse=True)
    page1, page2 = listing(status="all", limit=2, offset=0), listing(status="all", limit=2, offset=2)
    assert (len(page1["items"]), page1["has_more"], len(page2["items"]), page2["has_more"]) == (2, True, 1, False)
    assert listing(search=word.upper(), status="all")["total"] == 3  # also matches the description, any case


def test_search_treats_wildcards_literally(admin):
    word = unique_word()
    _ok(_create(admin, "payment_terms", f"{word}ab"), 201)
    assert _ok(client.get(f"{BASE}/payment_terms", params={"search": f"{word}%"}, headers=admin))["total"] == 0
    assert _ok(client.get(f"{BASE}/payment_terms", params={"search": f"{word[:-1]}_b"}, headers=admin))["total"] == 0


@pytest.mark.parametrize("params", [{"status": "bogus"}, {"sort_by": "bogus"}, {"sort_dir": "sideways"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_invalid_list_parameters_rejected(admin, params):
    assert client.get(f"{BASE}/payment_terms", params=params, headers=admin).status_code in (400, 422)


def test_options_feed_has_only_active_values(admin):
    live, dead = _ok(_create(admin, "application_category"), 201), _ok(_create(admin, "application_category"), 201)
    client.delete(f"{BASE}/application_category/{dead['id']}", headers=admin)
    options = _ok(client.get(f"{BASE}/application_category/options", headers=admin))["items"]
    ids = {o["id"] for o in options}
    assert live["id"] in ids and dead["id"] not in ids
    assert set(options[0]) == {"id", "name", "code", "parent_id"}


# --------------------------------------------------------------------------
# usage guard, permissions, audit
# --------------------------------------------------------------------------
def test_a_value_in_use_cannot_be_renamed_but_can_be_deactivated(admin):
    name = _name("Used")
    item = _ok(_create(admin, "supplier_category", name), 201)
    created = client.post("/api/v1/suppliers", json={"name": f"Supplier {unique_word()}", "category": name}, headers=admin)
    assert created.status_code == 201
    assert _ok(client.get(f"{BASE}/supplier_category/{item['id']}", headers=admin))["usage_count"] == 1

    rename = client.put(f"{BASE}/supplier_category/{item['id']}", json={"name": _name("New")}, headers=admin)
    assert rename.status_code == 400 and rename.json()["error_code"] == "MASTER_ITEM_IN_USE"
    assert client.put(f"{BASE}/supplier_category/{item['id']}", json={"description": "ok"}, headers=admin).status_code == 200
    assert client.delete(f"{BASE}/supplier_category/{item['id']}", headers=admin).status_code == 200
    # the supplier keeps its value
    supplier = client.get(f"/api/v1/suppliers/{created.json()['data']['id']}", headers=admin).json()["data"]
    assert supplier["category"] == name


def test_application_category_usage_counts_applications(admin):
    name = _name("AppCat")
    item = _ok(_create(admin, "application_category", name), 201)
    app = client.post("/api/v1/applications", json={"name": f"App {unique_word()}", "code": unique_code(), "category": name}, headers=admin)
    assert app.status_code == 201, app.text
    assert _ok(client.get(f"{BASE}/application_category/{item['id']}", headers=admin))["usage_count"] == 1


@pytest.mark.parametrize("role", ["operator", "read_only"])
def test_non_admins_can_read_but_not_change(admin, role):
    headers = _headers(role)
    item = _ok(_create(admin, "payment_terms"), 201)
    for path in ("/catalog", "/payment_terms", "/payment_terms/options", f"/payment_terms/{item['id']}"):
        assert client.get(f"{BASE}{path}", headers=headers).status_code == 200, path
    assert client.post(f"{BASE}/payment_terms", json={"name": _name()}, headers=headers).status_code == 403
    assert client.put(f"{BASE}/payment_terms/{item['id']}", json={"description": "x"}, headers=headers).status_code == 403
    assert client.delete(f"{BASE}/payment_terms/{item['id']}", headers=headers).status_code == 403
    assert client.patch(f"{BASE}/payment_terms/{item['id']}/reactivate", headers=headers).status_code == 403
    assert _ok(client.get(f"{BASE}/payment_terms/{item['id']}", headers=admin))["is_active"] is True


def test_authentication_required():
    assert client.get(f"{BASE}/catalog").status_code == 401
    assert client.post(f"{BASE}/payment_terms", json={"name": "x"}).status_code == 401


def test_changes_are_audit_logged_and_rejections_are_not(admin):
    item = _ok(_create(admin, "supplier_category"), 201)
    client.post(f"{BASE}/supplier_category", json={"name": item["name"]}, headers=admin)  # duplicate: refused
    client.put(f"{BASE}/supplier_category/{item['id']}", json={"description": "x"}, headers=admin)
    client.delete(f"{BASE}/supplier_category/{item['id']}", headers=admin)
    client.patch(f"{BASE}/supplier_category/{item['id']}/reactivate", headers=admin)
    db = SessionLocal()
    try:
        actions = [
            r.action
            for r in db.query(AuditLog)
            .filter(AuditLog.resource_type == "master_item", AuditLog.resource_id == str(item["id"]))
            .order_by(AuditLog.id)
            .all()
        ]
    finally:
        db.close()
    assert actions == ["create", "update", "delete", "update"]


# --------------------------------------------------------------------------
# page contracts (front end)
# --------------------------------------------------------------------------
def _read(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def test_master_management_page_replaces_the_five_sidebar_items():
    html = _read("index.html")
    start = html.index('<nav class="sidebar-nav"')
    nav = html[start: html.index("</nav>", start)]
    for section in ("departments", "job-roles", "applications", "manufacturers", "asset-models"):
        assert f'data-section="section-{section}"' not in nav
        assert f'<section id="section-{section}"' not in html  # moved into Master Management
    # Master Management itself, plus one "Applications" shortcut into it
    # (data-hash="applications" -> the Application master); both admin-only.
    assert nav.count('data-section="section-masters"') == 2
    assert nav.count('data-hash="applications"') == 1
    assert re.search(r'data-section="section-masters" data-hash="applications"[^>]*admin-only|admin-only[^>]*data-section="section-masters" data-hash="applications"', nav)
    assert re.search(r'data-section="section-masters"[^>]*admin-only|admin-only[^>]*data-section="section-masters"', nav)
    page = html[html.index('<section id="section-masters"'): html.index("</section>", html.index('<section id="section-masters"'))]
    assert 'id="mm-select"' in page and 'id="mm-generic"' in page
    for panel in ("department", "job-role", "application", "manufacturer", "asset-model"):
        assert f'id="mm-panel-{panel}"' in page
    # every table/form id the existing scripts rely on is still in the page
    for element in ("departments-table", "job-roles-table", "applications-table", "manufacturers-table", "form-job-role", "form-department"):
        assert f'id="{element}"' in page, element


def test_old_addresses_still_resolve_to_the_page():
    js = _read("app.js")
    routes = js[js.index("const HASH_TO_SECTION"): js.index("const SECTION_TO_HASH")]
    for alias in ("departments", '"job-roles"', "applications", "manufacturers", "models", "masters"):
        assert re.search(rf'{re.escape(alias)}: "section-masters"', routes), alias
    assert "section-departments" not in routes and "section-job-roles" not in routes
    masters = _read("masters.js")
    for alias, slug in (("departments", "department"), ('"job-roles"', "job-role"), ("applications", "application"), ("manufacturers", "manufacturer"), ("models", "asset-model")):
        assert re.search(rf'{re.escape(alias)}: "{re.escape(slug)}"', masters), alias


def test_form_dropdowns_have_no_hardcoded_options_and_are_filled_from_masters():
    html = _read("index.html")
    for select_id in ("employee-designation-select", "supplier-category-select", "supplier-terms-select", "application-category-select"):
        block = re.search(rf'<select id="{select_id}">(.*?)</select>', html, re.S).group(1)
        values = re.findall(r'<option value="([^"]*)"', block)
        assert values == ["", "__other__"], (select_id, values)
    js = _read("app.js")
    for list_name, select_id in (("supplier_category", "supplier-category-select"), ("payment_terms", "supplier-terms-select"), ("application_category", "application-category-select")):
        assert f'{{ type: "{list_name}", select: "{select_id}" }}' in js


def test_employee_screens_say_job_role_not_designation():
    html, js = _read("index.html"), _read("app.js")
    block = html[html.index('id="employee-designation-select"') - 700: html.index('id="employee-designation-other"') + 120]
    assert "Job role" in block and "Custom job role" in block and "Type the job role" in block
    assert "Designation" not in block
    assert '"job role"' in js and '["Job role", employeeJobRole(employee)' in js
    assert '["Designation"' not in js and '"designation", "department", "status", "manager"' not in js
    assert "{ designation: value, job_role: value }" in js  # the dropdown writes both fields


def test_status_pills_are_neutral_not_green_or_red():
    css = _read("styles.css")
    block = css[css.index("Status is shown in words, not colour"):]
    block = block[: block.index("}")]
    for selector in (".status-pill,", ".status-pill.good,", ".status-pill.bad"):
        assert selector in block
    assert "background: transparent" in css[css.index("Status is shown in words, not colour"):][:600]
    # the rule that colours them (success-green / danger-red) is overridden, not used
    assert "color: var(--ink)" in css[css.index("Status is shown in words, not colour"):][:600]
