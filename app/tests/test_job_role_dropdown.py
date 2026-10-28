"""Job Roles master <-> Employee form dropdown consistency.

The Employee form's role dropdown (Designation) used to be a hardcoded list of
16 titles. It is now filled from the Job Roles master, so these tests check:
every former option exists (active, no duplicates) in the master; the page no
longer hardcodes options; every change to the master is visible through the
same API the dropdown reads; existing employee assignments, audit logging and
permissions are preserved; and the Job Roles page's employee counts agree with
what the dropdown assigns.
"""
import re
from pathlib import Path

from app.database.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User
from app.tests.conftest import PASSWORD, client, register_and_login, unique_email, unique_word

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

# The exact options of the old hardcoded designation <select>.
FORMER_DROPDOWN_OPTIONS = [
    "Founder", "CEO", "CTO", "COO", "CFO", "Engineering Manager", "Product Manager",
    "Software Engineer", "Senior Software Engineer", "Designer", "Marketing Manager",
    "Sales Manager", "Account Executive", "Customer Support", "HR Manager", "Intern",
]


def _headers(role="admin"):
    email, _ = register_and_login()
    db = SessionLocal()
    db.query(User).filter(User.email == email).first().role = role
    db.commit()
    db.close()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _all_roles(admin, include_inactive=True):
    items, offset = [], 0
    while True:
        page = client.get(
            "/api/v1/job-roles",
            params={"limit": 100, "offset": offset, "include_inactive": include_inactive},
            headers=admin,
        ).json()["data"]
        items += page["items"]
        if not page["has_more"]:
            return items
        offset += 100


def _role(admin, name=None):
    name = name or f"Role {unique_word()}"
    created = client.post("/api/v1/job-roles", json={"name": name}, headers=admin)
    assert created.status_code == 201, created.text
    return created.json()["data"]


def _company(admin):
    created = client.post(
        "/api/v1/companies",
        json={"name": f"Roles {unique_word()}", "address": "1 Test Street", "contact_email": "c@example.com"},
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


# --------------------------------------------------------------------------
# the master contains every role the dropdown used to list
# --------------------------------------------------------------------------
def test_every_former_dropdown_option_exists_active_in_the_master():
    active = {r["name"].lower() for r in _all_roles(_headers(), include_inactive=False)}
    missing = [n for n in FORMER_DROPDOWN_OPTIONS if n.lower() not in active]
    assert not missing, f"missing from the active Job Roles master: {missing}"


def test_job_roles_master_has_no_case_insensitive_duplicates():
    names = [r["name"].lower() for r in _all_roles(_headers())]
    assert len(names) == len(set(names))


def test_creating_or_renaming_to_an_existing_role_is_refused_whatever_the_capitalisation():
    admin = _headers()
    for name in ("CEO", "ceo", "  Ceo  "):
        refused = client.post("/api/v1/job-roles", json={"name": name}, headers=admin)
        assert refused.status_code == 400 and refused.json()["error_code"] == "JOB_ROLE_ALREADY_EXISTS", name
    other = _role(admin)
    clash = client.put(f"/api/v1/job-roles/{other['id']}", json={"name": "cto"}, headers=admin)
    assert clash.status_code == 400 and clash.json()["error_code"] == "JOB_ROLE_ALREADY_EXISTS"
    # changing only the capitalisation of a role's own name is still allowed
    own = client.put(f"/api/v1/job-roles/{other['id']}", json={"name": other["name"].upper()}, headers=admin)
    assert own.status_code == 200


# --------------------------------------------------------------------------
# the page no longer hardcodes the options
# --------------------------------------------------------------------------
def test_designation_select_in_the_page_has_no_hardcoded_roles():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    block = re.search(r'<select id="employee-designation-select">(.*?)</select>', html, re.S).group(1)
    assert re.findall(r'<option value="([^"]*)"', block) == ["", "__other__"]


def test_designation_select_is_filled_from_the_job_roles_master_in_the_script():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    body = js[js.index("async function loadJobRoles()"):]
    body = body[: body.index("\n}\n")]
    assert 'populateMasterDataSelect(' in body and '"employee-designation-select"' in body
    assert "is_active" in body  # active roles only


# --------------------------------------------------------------------------
# changes in the master are what the dropdown reads
# --------------------------------------------------------------------------
def test_add_rename_deactivate_reactivate_are_reflected_in_the_dropdown_feed():
    admin = _headers()
    role = _role(admin)

    def active_names():
        return {r["name"] for r in _all_roles(admin, include_inactive=False)}

    assert role["name"] in active_names()

    renamed = f"Renamed {unique_word()}"
    assert client.put(f"/api/v1/job-roles/{role['id']}", json={"name": renamed}, headers=admin).status_code == 200
    assert renamed in active_names() and role["name"] not in active_names()

    assert client.delete(f"/api/v1/job-roles/{role['id']}", headers=admin).status_code == 200
    assert renamed not in active_names()
    assert renamed in {r["name"] for r in _all_roles(admin, include_inactive=True)}  # still in the master

    assert client.patch(f"/api/v1/job-roles/{role['id']}/reactivate", headers=admin).status_code == 200
    assert renamed in active_names()


def test_master_changes_are_audit_logged():
    admin = _headers()
    role = _role(admin)
    client.put(f"/api/v1/job-roles/{role['id']}", json={"name": f"Edited {unique_word()}"}, headers=admin)
    client.delete(f"/api/v1/job-roles/{role['id']}", headers=admin)
    client.patch(f"/api/v1/job-roles/{role['id']}/reactivate", headers=admin)
    db = SessionLocal()
    try:
        actions = [
            r.action
            for r in db.query(AuditLog)
            .filter(AuditLog.resource_type == "job_role", AuditLog.resource_id == str(role["id"]))
            .order_by(AuditLog.id)
            .all()
        ]
    finally:
        db.close()
    assert actions == ["create", "update", "delete", "update"]


def test_only_admin_can_change_the_master_but_everyone_can_read_it():
    admin = _headers()
    for role in ("operator", "read_only"):
        headers = _headers(role)
        assert client.get("/api/v1/job-roles", headers=headers).status_code == 200
        assert client.post("/api/v1/job-roles", json={"name": f"X {unique_word()}"}, headers=headers).status_code == 403
    assert client.post("/api/v1/job-roles", json={"name": f"Y {unique_word()}"}, headers=admin).status_code == 201


# --------------------------------------------------------------------------
# existing employee assignments are preserved
# --------------------------------------------------------------------------
def test_deactivating_or_renaming_a_role_never_touches_employees_assigned_to_it():
    admin = _headers()
    role = _role(admin)
    company_id = _company(admin)
    employee = _employee(admin, company_id, designation=role["name"], job_role=role["name"])

    client.put(f"/api/v1/job-roles/{role['id']}", json={"name": f"Other {unique_word()}"}, headers=admin)
    client.delete(f"/api/v1/job-roles/{role['id']}", headers=admin)

    stored = client.get(f"/api/v1/employees/{employee['id']}", headers=admin).json()["data"]
    assert stored["designation"] == role["name"]
    # ...and the record can still be edited normally with the old value in place.
    edit = client.put(
        f"/api/v1/employees/{employee['id']}",
        json={"designation": role["name"], "department": "Anything"},
        headers=admin,
    )
    assert edit.status_code == 200 and edit.json()["data"]["designation"] == role["name"]


def test_a_title_not_in_the_master_is_still_accepted_for_an_employee():
    # The form's "Other (type below)" path: free-text designations that are
    # not master roles keep working exactly as before.
    admin = _headers()
    custom = f"Custom Title {unique_word()}"
    employee = _employee(admin, _company(admin), designation=custom)
    assert employee["designation"] == custom


# --------------------------------------------------------------------------
# the Job Roles page's counts agree with what the dropdown assigns
# --------------------------------------------------------------------------
def test_employee_count_counts_role_or_designation_once_and_skips_exited():
    admin = _headers()
    role = _role(admin)
    name = role["name"]
    company_id = _company(admin)

    _employee(admin, company_id, designation=name)                    # via the dropdown
    _employee(admin, company_id, job_role=name)                       # via the job_role field
    _employee(admin, company_id, designation=name, job_role=name)     # both: still one person
    gone = _employee(admin, company_id, designation=name)             # exited: not counted
    client.patch(f"/api/v1/employees/{gone['id']}/status", json={"status": "exited"}, headers=admin)

    fetched = client.get(f"/api/v1/job-roles/{role['id']}", headers=admin).json()["data"]
    assert fetched["employee_count"] == 3
    listed = client.get("/api/v1/job-roles", params={"search": name}, headers=admin).json()["data"]["items"]
    assert [r["employee_count"] for r in listed if r["id"] == role["id"]] == [3]
