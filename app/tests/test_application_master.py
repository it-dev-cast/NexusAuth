"""Application Master: the extra fields (code, description, URL), list search /
filters / pagination, and employee access management (grant, revoke, inactive
rules, audit, authorization). The older CRUD and employee-form behaviour stays
covered by test_application_crud.py and test_employee_application_access.py."""
from sqlalchemy import text

from app.database.database import SessionLocal
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_code, unique_email, unique_word


def _headers(role, company_id=None):
    email, _ = register_and_login()
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    user.role = role
    if company_id is not None:
        user.company_id = company_id
    db.commit()
    db.close()
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}, email


def _admin():
    return _headers("admin")[0]


def _company(admin):
    created = client.post(
        "/api/v1/companies",
        json={"name": f"AM {unique_word()}", "address": "1 Test Street", "contact_email": "c@example.com"},
        headers=admin,
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"]


def _employee(admin, company_id, **extra):
    payload = {"company_id": company_id, "first_name": unique_word(), "last_name": unique_word(), "email": unique_email(), **extra}
    created = client.post("/api/v1/employees", json=payload, headers=admin)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _app(admin, **extra):
    payload = {"name": f"AppM {unique_word()}", "code": unique_code(), **extra}
    created = client.post("/api/v1/applications", json=payload, headers=admin)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _grant(admin, application_id, *employee_ids):
    return client.post(f"/api/v1/applications/{application_id}/access", json={"employee_ids": list(employee_ids)}, headers=admin)


def _access(admin, application_id, **params):
    response = client.get(f"/api/v1/applications/{application_id}/access", params=params, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _audit(admin, **params):
    response = client.get("/api/v1/audit-logs", params=params, headers=admin)
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


# ---------------- create / edit ----------------


def test_create_application_with_all_fields_and_normalised_code():
    admin = _admin()
    body = {
        "name": f"Full {unique_word()}",
        "code": "  hr module  ",
        "description": "  Leave, payroll and records.  ",
        "category": "People",
        "url": "https://hr.example.com/app",
    }
    # the code is globally unique: make this one unique too, keeping the shape
    suffix = unique_code("X")
    body["code"] = f"hr module {suffix.lower()}"
    created = client.post("/api/v1/applications", json=body, headers=admin)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["code"] == f"HR_MODULE_{suffix}"
    assert data["description"] == "Leave, payroll and records."
    assert data["url"] == "https://hr.example.com/app"
    assert data["is_active"] is True and data["employee_count"] == 0


def test_create_inactive_application_and_optional_fields_default_to_none():
    admin = _admin()
    data = _app(admin, is_active=False)
    assert data["is_active"] is False
    assert data["description"] is None and data["url"] is None and data["category"] is None


def test_code_is_required_and_validated():
    admin = _admin()
    missing = client.post("/api/v1/applications", json={"name": f"NoCode {unique_word()}"}, headers=admin)
    assert missing.status_code == 422
    for bad in ("", "   ", "A", "has/slash", "semi;colon", "-leading"):
        response = client.post("/api/v1/applications", json={"name": f"Bad {unique_word()}", "code": bad}, headers=admin)
        assert response.status_code == 422, bad


def test_url_must_be_http_or_https():
    admin = _admin()
    for bad in ("ftp://example.com", "example.com", "javascript:alert(1)", "https://"):
        response = client.post(
            "/api/v1/applications", json={"name": f"Url {unique_word()}", "code": unique_code(), "url": bad}, headers=admin
        )
        assert response.status_code == 422, bad
    blank = client.post(
        "/api/v1/applications", json={"name": f"Url {unique_word()}", "code": unique_code(), "url": "  "}, headers=admin
    )
    assert blank.status_code == 201 and blank.json()["data"]["url"] is None


def test_duplicate_code_rejected_on_create_and_update_case_insensitively():
    admin = _admin()
    first = _app(admin)
    duplicate = client.post(
        "/api/v1/applications",
        json={"name": f"Dup {unique_word()}", "code": first["code"].lower()},
        headers=admin,
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["error_code"] == "APPLICATION_CODE_ALREADY_EXISTS"

    second = _app(admin)
    clash = client.put(f"/api/v1/applications/{second['id']}", json={"code": first["code"]}, headers=admin)
    assert clash.status_code == 400 and clash.json()["error_code"] == "APPLICATION_CODE_ALREADY_EXISTS"

    # saving an application with its own, unchanged code is fine
    same = client.put(f"/api/v1/applications/{second['id']}", json={"code": second["code"], "description": "x"}, headers=admin)
    assert same.status_code == 200


def test_update_fields_clear_optional_values_and_toggle_status():
    admin = _admin()
    application = _app(admin, description="old", url="https://a.example.com", category="Core")
    updated = client.put(
        f"/api/v1/applications/{application['id']}",
        json={"description": None, "url": None, "category": None, "name": f"Renamed {unique_word()}"},
        headers=admin,
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()["data"]
    assert data["description"] is None and data["url"] is None and data["category"] is None

    # a field that is not sent is left alone
    again = client.put(f"/api/v1/applications/{application['id']}", json={"description": "kept"}, headers=admin)
    assert again.json()["data"]["description"] == "kept" and again.json()["data"]["name"] == data["name"]

    off = client.put(f"/api/v1/applications/{application['id']}", json={"is_active": False}, headers=admin)
    assert off.json()["data"]["is_active"] is False
    on = client.put(f"/api/v1/applications/{application['id']}", json={"is_active": True}, headers=admin)
    assert on.json()["data"]["is_active"] is True


# ---------------- list: search, filters, pagination ----------------


def test_list_search_by_name_or_code_and_status_and_category_filters():
    admin = _admin()
    token = unique_word()
    code_token = unique_code("ZQ")
    a = _app(admin, name=f"Alpha {token}", category="Core")
    b = _app(admin, name=f"Beta {token}", code=code_token, category="People")
    c = _app(admin, name=f"Gamma {token}", category="Core", is_active=False)

    def ids(**params):
        response = client.get("/api/v1/applications", params={"limit": 100, **params}, headers=admin)
        assert response.status_code == 200, response.text
        return {item["id"] for item in response.json()["data"]["items"]}

    assert ids(search=token, status="all") == {a["id"], b["id"], c["id"]}
    assert ids(search=code_token.lower(), status="all") == {b["id"]}  # by code, any case
    assert ids(search=token) == {a["id"], b["id"]}  # default hides inactive
    assert ids(search=token, status="inactive") == {c["id"]}
    assert ids(search=token, status="active", category="core") == {a["id"]}
    assert ids(search=token, status="all", category="Core") == {a["id"], c["id"]}
    assert ids(search=token, include_inactive="true") == {a["id"], b["id"], c["id"]}  # older parameter still works
    assert ids(search=token, include_inactive="true", status="active") == {a["id"], b["id"]}  # status wins


def test_list_pagination_and_categories():
    admin = _admin()
    token = unique_word()
    created = [_app(admin, name=f"Page{i} {token}", category=f"Cat {token}") for i in range(3)]
    first = client.get("/api/v1/applications", params={"search": token, "limit": 2, "offset": 0}, headers=admin).json()["data"]
    second = client.get("/api/v1/applications", params={"search": token, "limit": 2, "offset": 2}, headers=admin).json()["data"]
    assert first["total"] == 3 and len(first["items"]) == 2 and first["has_more"] is True
    assert len(second["items"]) == 1 and second["has_more"] is False
    assert {i["id"] for i in first["items"]} | {i["id"] for i in second["items"]} == {a["id"] for a in created}

    categories = client.get("/api/v1/applications/categories", headers=admin)
    assert categories.status_code == 200 and f"Cat {token}" in categories.json()["data"]


# ---------------- access management ----------------


def test_grant_several_employees_list_search_and_no_duplicates():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    e1 = _employee(admin, company, employee_code=unique_code("E"))
    e2 = _employee(admin, company)
    e3 = _employee(admin, company)

    granted = _grant(admin, application["id"], e1["id"], e2["id"])
    assert granted.status_code == 201, granted.text
    assert sorted(granted.json()["data"]["granted"]) == sorted([e1["id"], e2["id"]])

    # granting again (plus one new person) never duplicates
    again = _grant(admin, application["id"], e1["id"], e3["id"]).json()["data"]
    assert again["granted"] == [e3["id"]] and again["already_assigned"] == [e1["id"]]
    listing = _access(admin, application["id"])
    assert listing["total"] == 3
    assert len({row["employee_id"] for row in listing["items"]}) == 3
    db = SessionLocal()
    count = db.execute(
        text("SELECT count(*) FROM employee_applications WHERE application_id = :a"), {"a": application["id"]}
    ).scalar()
    db.close()
    assert count == 3

    # the headcount on the master list follows
    assert client.get(f"/api/v1/applications/{application['id']}", headers=admin).json()["data"]["employee_count"] == 3

    # search by name, email, and employee ID
    assert [r["employee_id"] for r in _access(admin, application["id"], search=e2["first_name"])["items"]] == [e2["id"]]
    assert [r["employee_id"] for r in _access(admin, application["id"], search=e3["email"])["items"]] == [e3["id"]]
    assert [r["employee_id"] for r in _access(admin, application["id"], search=e1["employee_code"])["items"]] == [e1["id"]]
    assert _access(admin, application["id"], search="no-such-person-zzz")["total"] == 0

    # each row carries status and when/who granted it
    row = next(r for r in listing["items"] if r["employee_id"] == e1["id"])
    assert row["status"] == "onboarded" and row["granted_at"] and row["granted_by"]
    assert set(row) >= {"employee_id", "employee_code", "full_name", "email", "company_id", "status", "granted_at", "granted_by"}


def test_access_list_is_paginated():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    ids = [_employee(admin, company)["id"] for _ in range(3)]
    _grant(admin, application["id"], *ids)
    page = client.get(f"/api/v1/applications/{application['id']}/access", params={"limit": 2}, headers=admin).json()["data"]
    assert page["total"] == 3 and len(page["items"]) == 2 and page["has_more"] is True


def test_candidates_exclude_holders_and_exited_employees():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    holder = _employee(admin, company)
    free = _employee(admin, company)
    gone = _employee(admin, company)
    _grant(admin, application["id"], holder["id"])
    assert client.delete(f"/api/v1/employees/{gone['id']}", headers=admin).status_code == 200

    def found(person):
        response = client.get(
            f"/api/v1/applications/{application['id']}/access/candidates", params={"search": person["email"]}, headers=admin
        )
        assert response.status_code == 200, response.text
        return [r["employee_id"] for r in response.json()["data"]]

    assert found(free) == [free["id"]]
    assert found(holder) == [] and found(gone) == []


def test_revoke_requires_a_confirmed_existing_grant_and_is_audited():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company)
    _grant(admin, application["id"], employee["id"])

    revoked = client.delete(f"/api/v1/applications/{application['id']}/access/{employee['id']}", headers=admin)
    assert revoked.status_code == 200, revoked.text
    assert _access(admin, application["id"])["total"] == 0

    again = client.delete(f"/api/v1/applications/{application['id']}/access/{employee['id']}", headers=admin)
    assert again.status_code == 404 and again.json()["error_code"] == "APPLICATION_ACCESS_NOT_FOUND"

    # revoking and regranting works, one row again
    assert _grant(admin, application["id"], employee["id"]).json()["data"]["granted"] == [employee["id"]]
    assert _access(admin, application["id"])["total"] == 1


def test_unknown_application_or_employee():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company)
    assert _grant(admin, 999999999, employee["id"]).status_code == 404
    missing_employee = _grant(admin, application["id"], 999999999)
    assert missing_employee.status_code == 404 and missing_employee.json()["error_code"] == "EMPLOYEE_NOT_FOUND"
    assert client.get("/api/v1/applications/999999999/access", headers=admin).status_code == 404
    assert client.post(f"/api/v1/applications/{application['id']}/access", json={"employee_ids": []}, headers=admin).status_code == 422
    # nothing was granted by the failed attempt that mixed a real and a missing id
    assert _grant(admin, application["id"], employee["id"], 999999999).status_code == 404
    assert _access(admin, application["id"])["total"] == 0


def test_exited_employee_cannot_be_granted_access():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company)
    client.delete(f"/api/v1/employees/{employee['id']}", headers=admin)
    response = _grant(admin, application["id"], employee["id"])
    assert response.status_code == 409 and response.json()["error_code"] == "EMPLOYEE_EXITED"


# ---------------- inactive applications ----------------


def test_inactive_application_rejects_new_grants_but_keeps_and_can_revoke_existing_ones():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    keeper = _employee(admin, company)
    newcomer = _employee(admin, company)
    _grant(admin, application["id"], keeper["id"])

    assert client.delete(f"/api/v1/applications/{application['id']}", headers=admin).status_code == 200

    blocked = _grant(admin, application["id"], newcomer["id"])
    assert blocked.status_code == 409 and blocked.json()["error_code"] == "APPLICATION_INACTIVE"
    # the existing grant is untouched, still listed, still counted
    assert [r["employee_id"] for r in _access(admin, application["id"])["items"]] == [keeper["id"]]
    assert client.get(f"/api/v1/applications/{application['id']}", headers=admin).json()["data"]["employee_count"] == 1

    # the employee's own view shows it, flagged inactive
    mine = client.get(f"/api/v1/employees/{keeper['id']}/applications", headers=admin).json()["data"]
    assert [(a["application_id"], a["is_active"]) for a in mine] == [(application["id"], False)]

    # a routine employee save (the form can't show inactive apps) does not drop it
    saved = client.put(f"/api/v1/employees/{keeper['id']}", json={"application_ids": []}, headers=admin)
    assert saved.status_code == 200 and saved.json()["data"]["application_ids"] == [application["id"]]

    # reactivation restores granting, without duplicating anything
    assert client.patch(f"/api/v1/applications/{application['id']}/reactivate", headers=admin).status_code == 200
    assert _grant(admin, application["id"], newcomer["id"], keeper["id"]).json()["data"]["already_assigned"] == [keeper["id"]]
    assert _access(admin, application["id"])["total"] == 2

    # revoke is allowed while inactive (clean-up)
    client.delete(f"/api/v1/applications/{application['id']}", headers=admin)
    assert client.delete(f"/api/v1/applications/{application['id']}/access/{keeper['id']}", headers=admin).status_code == 200


# ---------------- employee-centric view ----------------


def test_employee_applications_view_lists_grants_with_dates():
    admin = _admin()
    company = _company(admin)
    a = _app(admin, category="Core")
    b = _app(admin)
    employee = _employee(admin, company)
    _grant(admin, a["id"], employee["id"])
    _grant(admin, b["id"], employee["id"])
    rows = client.get(f"/api/v1/employees/{employee['id']}/applications", headers=admin).json()["data"]
    assert {r["application_id"] for r in rows} == {a["id"], b["id"]}
    first = next(r for r in rows if r["application_id"] == a["id"])
    assert first["code"] == a["code"] and first["category"] == "Core" and first["is_active"] is True and first["granted_at"]
    assert client.get("/api/v1/employees/999999999/applications", headers=admin).status_code == 404


def test_grants_without_a_recorded_date_still_list():
    """Compatibility: rows that predate granted_at have NULL there."""
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company, application_ids=[application["id"]])  # via the employee form
    db = SessionLocal()
    db.execute(
        text("UPDATE employee_applications SET granted_at = NULL WHERE application_id = :a"), {"a": application["id"]}
    )
    db.commit()
    db.close()
    row = _access(admin, application["id"])["items"][0]
    assert row["employee_id"] == employee["id"] and row["granted_at"] is None and row["granted_by"] is None
    mine = client.get(f"/api/v1/employees/{employee['id']}/applications", headers=admin).json()["data"]
    assert mine[0]["granted_at"] is None
    # and the existing employee payload is unchanged
    assert client.get(f"/api/v1/employees/{employee['id']}", headers=admin).json()["data"]["application_ids"] == [application["id"]]


# ---------------- authorization ----------------


def test_only_admin_can_manage_access_or_edit_applications():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company)
    _grant(admin, application["id"], employee["id"])
    base = f"/api/v1/applications/{application['id']}"

    for role in ("operator", "read_only"):
        headers, _ = _headers(role, company)
        assert client.get(f"{base}/access", headers=headers).status_code == 403
        assert client.get(f"{base}/access/candidates", headers=headers).status_code == 403
        assert client.post(f"{base}/access", json={"employee_ids": [employee["id"]]}, headers=headers).status_code == 403
        assert client.delete(f"{base}/access/{employee['id']}", headers=headers).status_code == 403
        assert client.put(base, json={"description": "nope"}, headers=headers).status_code == 403
        assert client.patch(f"{base}/reactivate", headers=headers).status_code == 403
        assert client.delete(base, headers=headers).status_code == 403
        # the master list itself stays readable (it fills the employee form)
        assert client.get(base, headers=headers).status_code == 200
        assert client.get("/api/v1/applications/categories", headers=headers).status_code == 200
    # nothing changed
    assert _access(admin, application["id"])["total"] == 1

    anonymous = client.post(f"{base}/access", json={"employee_ids": [employee["id"]]})
    assert anonymous.status_code in (401, 403)
    assert client.get(f"{base}/access").status_code in (401, 403)


def test_employee_applications_view_follows_company_scoping():
    admin = _admin()
    mine_company, other_company = _company(admin), _company(admin)
    application = _app(admin)
    mine = _employee(admin, mine_company, application_ids=[application["id"]])
    theirs = _employee(admin, other_company)
    operator, _ = _headers("operator", mine_company)
    assert client.get(f"/api/v1/employees/{mine['id']}/applications", headers=operator).status_code == 200
    assert client.get(f"/api/v1/employees/{theirs['id']}/applications", headers=operator).status_code == 404


# ---------------- audit ----------------


def test_create_edit_status_grant_and_revoke_are_audited():
    admin = _admin()
    company = _company(admin)
    application = _app(admin)
    employee = _employee(admin, company)
    app_id = str(application["id"])

    client.put(f"/api/v1/applications/{app_id}", json={"description": "audited change"}, headers=admin)
    client.delete(f"/api/v1/applications/{app_id}", headers=admin)  # deactivate
    client.patch(f"/api/v1/applications/{app_id}/reactivate", headers=admin)
    _grant(admin, application["id"], employee["id"])
    client.delete(f"/api/v1/applications/{app_id}/access/{employee['id']}", headers=admin)

    actions = [row["action"] for row in _audit(admin, resource_type="application", resource_id=app_id, limit=100)]
    for expected in ("create", "update", "delete", "grant_access", "revoke_access"):
        assert expected in actions, (expected, actions)

    grant = next(r for r in _audit(admin, resource_type="application", resource_id=app_id, action="grant_access"))
    assert str(employee["id"]) in str(grant["new_value"]) and application["code"] in str(grant["new_value"])
    revoke = next(r for r in _audit(admin, resource_type="application", resource_id=app_id, action="revoke_access"))
    assert str(employee["id"]) in str(revoke["old_value"])

    # a grant that changes nothing (already held) writes no new audit row
    _grant(admin, application["id"], employee["id"])
    before = len(_audit(admin, resource_type="application", resource_id=app_id, action="grant_access", limit=100))
    _grant(admin, application["id"], employee["id"])
    after = len(_audit(admin, resource_type="application", resource_id=app_id, action="grant_access", limit=100))
    assert before == after


# ---------------- front-end contracts (shipped files) ----------------

from pathlib import Path  # noqa: E402

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read(name):
    return (_FRONTEND / name).read_text(encoding="utf-8")


def test_application_master_screen_is_wired_into_the_page():
    html, app_js, js = _read("index.html"), _read("app.js"), _read("applications.js")
    assert html.index('src="/static/applications.js"') < html.index('src="/static/app.js"')
    panel = html[html.index('id="mm-panel-application"'): html.index('id="mm-panel-manufacturer"')]
    for needle in (
        "Application Master", "Add Application", 'id="applications-search"', 'id="applications-status-filter"',
        'id="applications-category-filter"', 'id="application-code"', 'id="application-url"', 'id="application-description"',
        'id="application-status"', 'id="applications-table"', 'id="applications-pager"',
    ):
        assert needle in panel, needle
    for header in ("Application Name", "Application Code", "Category", "Assigned Employees", "Status", "Updated At", "Actions"):
        assert f">{header}</th>" in js, header
    for needle in ("application-access-modal", "application-view-modal", 'id="employee-view-apps"'):
        assert needle in html, needle
    # the old inline-table code is gone from app.js and the new module owns the screen
    for removed in ("applications-include-inactive", "form-application", "btn-new-application", "renderApplicationsTable"):
        assert removed not in app_js, removed
    assert "NexusApplications" in app_js
    # the module only talks to existing/added API endpoints and asks before revoking or changing status
    for endpoint in ("/api/v1/applications", "/access", "/access/candidates", "/api/v1/employees/", "/applications/categories"):
        assert endpoint in js, endpoint
    assert js.count("confirmModal(") >= 3
    assert "access_token" not in js and "localStorage" not in js


def test_every_application_endpoint_the_screen_uses_exists_and_is_protected():
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/applications": {"get", "post"},
        "/api/v1/applications/categories": {"get"},
        "/api/v1/applications/{application_id}": {"get", "put", "delete"},
        "/api/v1/applications/{application_id}/reactivate": {"patch"},
        "/api/v1/applications/{application_id}/access": {"get", "post"},
        "/api/v1/applications/{application_id}/access/candidates": {"get"},
        "/api/v1/applications/{application_id}/access/{employee_id}": {"delete"},
        "/api/v1/employees/{employee_id}/applications": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths, path
        assert methods <= set(paths[path]), (path, methods)
