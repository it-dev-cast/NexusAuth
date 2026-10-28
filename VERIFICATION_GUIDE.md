# Verification guide — how to check everything actually works

Last run: 24 Aug 2026. Covers Auth (Module 1), RBAC (Module 2), Company (Module 3),
Employee (Module 4), Supplier (Module 5), Asset (Module 6), Entity Relationships
& cascades (Module 7), Audit & Change Tracking (Module 8).

## 0. Full logic-by-logic audit (24 Aug 2026)

Went through every logic listed in the architecture doc for Modules 1–8
(~91 items) one by one against the actual code, not just re-running the
existing test suite. Found and fixed three real gaps:

- **Employee: "Read Employee by email"** was listed in the doc but had no
  API route — `get_employee_by_email` only existed as an internal
  uniqueness check. Added `GET /employees/by-email?company_id=&email=`.
- **Employee: "role inheritance from Company defaults"** was not
  implemented at all — `job_role` always hardcoded to `"Employee"`, and
  `department` was never backed by anything on Company. Fixed: Company's
  `config_defaults` (already a free-form JSON-in-text field) can now hold
  `{"default_job_role": "...", "default_department": "..."}`, consumed by
  `employee_service._company_defaults()` — only applied when the caller
  didn't explicitly specify a value. Malformed/non-JSON `config_defaults`
  degrades to no defaults, not an error.
- **Supplier: "Read Supplier by name"** — same gap as Employee's, added
  `GET /suppliers/by-name/{name}`.

One item flagged as a **deliberate scope decision, not a bug**: RBAC's
"Company-scoped role checking" (Module 2) isn't enforced — an Operator can
write to any Company/Employee/Supplier/Asset regardless of which company
they belong to. `ARCHITECTURE.md` already documents this project as
single-tenant for now (`company_id` is a JWT claim only); building real
per-company RBAC scoping would be a deliberate multi-tenancy effort, not a
quick fix, so it was left alone rather than guessed at.

Also closed a known test-coverage gap: Company and Employee never had their
own automated test files (this doc said so above, for months) — added
`test_company_crud.py`, `test_employee_crud.py`, `test_employee_status.py`.

## 1. Automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests -v
```

Expect **110 passed**. Covers login, logout, refresh, token claims,
middleware, RBAC on `/overview` and `/admin`, password hashing, the
circular-dependency utility, Company CRUD (`test_company_crud.py`), Employee
CRUD + full status lifecycle + user-linking cascades (`test_employee_crud.py`,
`test_employee_status.py` — including role inheritance from Company
defaults), Supplier CRUD + status transitions (`test_supplier_crud.py`,
`test_supplier_status.py`), Asset CRUD + status transitions
(`test_asset_crud.py`, `test_asset_status.py`), and the audit trail itself
(`test_audit_log.py`).

## 2. Start the server correctly (avoid the zombie-process trap)

Before starting, always confirm nothing stale is already bound to the port —
a `--reload` restart can leave an orphaned worker behind that keeps answering
requests with old code, while you think you're testing the new version:

```powershell
netstat -ano | findstr ":8000" | findstr LISTENING
```

If something's there and you don't trust it, kill it **with the tree flag**,
not just by PID (a plain kill can leave the reloader's child process alive):

```powershell
taskkill /PID <pid> /T /F
```

Then start clean:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

Confirm it's serving the *current* code, not a stale copy:

```powershell
curl http://127.0.0.1:8000/openapi.json
# check the path list actually includes /api/v1/employees etc.
```

## 3. Manual smoke test, module by module

Use Swagger UI (`http://127.0.0.1:8000/docs`) or curl/PowerShell. Login as
`admin@casterly.com` / `ExamplePasswordOnly` first and use `Authorize` /
`Authorization: Bearer <token>` for the rest.

| # | Check | Expect |
|---|---|---|
| 1 | `POST /auth/login` as admin | 200, tokens returned |
| 2 | `GET /auth/overview` as admin | 200, full user list |
| 3 | `POST /auth/register` a new user | 202 `{"message": ...}` — the same answer for an email that is already registered, so it never reveals which addresses have accounts; sign in to get the account (`role: "read_only"`) |
| 4 | That new user hits `GET /auth/overview` | **403** |
| 5 | `POST /companies` as admin | 201 |
| 6 | `read_only` user does `GET /companies/{id}` | **200** (company reads are open) |
| 7 | `read_only` user does `PUT /companies/{id}` | **403** (writes are admin/operator only) |
| 8 | `read_only` user does `GET /employees?company_id=X` | **403** (employee reads are stricter — PII) |
| 9 | `POST /employees` under that company | 201, `status: "onboarded"` |
| 10 | Create a second employee with the same email in the same company | **400** `EMPLOYEE_ALREADY_EXISTS` |
| 11 | `PATCH /employees/{id}/status` → `on_leave` directly from `onboarded` | **400** — invalid transition (must go through `active` first) |
| 12 | `DELETE /companies/{id}` (soft-delete it) | 200, `is_active: false` |
| 13 | `POST /employees` under that now-inactive company | **400** `EMPLOYEE_COMPANY_INACTIVE` |
| 14 | Link an employee to a user in a *different* company | **400** `EMPLOYEE_USER_COMPANY_MISMATCH` |
| 15 | Link an employee to a user in the *same* company, then `PATCH .../status` → `exited` | Linked user's `is_active` flips to `false` |
| 16 | Try to hard-delete a `Company` row directly in the DB while a `User`/`Employee` still references it | Postgres refuses — `RestrictViolation` |
| 17 | `POST /suppliers` as admin | 201, `status: "onboarded"` |
| 18 | `read_only` user does `GET /suppliers/{id}` | **200** (supplier reads are open, like company — no PII on this resource) |
| 19 | `read_only` user does `PUT /suppliers/{id}` | **403** (writes are admin/operator only) |
| 20 | `PATCH /suppliers/{id}/status` → `suspended` directly from `onboarded` | **400** `SUPPLIER_INVALID_STATUS_TRANSITION` — must go through `approved` first |
| 21 | `approved` → `suspended` → `approved` | 200 at each step — unlike Employee, Supplier has no terminal state |
| 22 | Create a second supplier with the same `name` | **400** `SUPPLIER_ALREADY_EXISTS` |
| 23 | `POST /assets` against a supplier still `onboarded` (not yet `approved`) | **409** `SUPPLIER_NOT_APPROVED` |
| 24 | `POST /assets` against an `approved` supplier | 201, `status: "registered"` |
| 25 | `PUT /assets/{id}` with an `asset_tag` field in the body | 200, but the tag is unchanged — the field isn't on the update schema at all |
| 26 | `PATCH /assets/{id}/status` → `certified` directly from `registered` | **400** `ASSET_INVALID_STATUS_TRANSITION` — must go through `in_repair` first |
| 27 | `certified` → `in_repair` (rework) | 200 — unlike Employee's `exited`, Asset's `certified` is not terminal |
| 28 | `DELETE /assets/{id}` then try any further status transition | First call 200 `status: "disposed"`; the second **400**, `disposed` is terminal |
| 29 | `GET /audit-logs?resource_type=employee&resource_id=X` after creating an employee with a real bank account number/PAN | 200, row present, but `new_value.bank_account_number` / `.pan_number` / `.email` come back **masked** — never the raw value |
| 30 | `read_only` or `operator` calls `GET /audit-logs` | **403** — audit is admin-only, stricter than every other resource |
| 31 | `PATCH /suppliers/{id}/status` → `approved`, then `GET /audit-logs?action=status_transition` | Row's `old_value` / `new_value` are just `{"status": ...}`, not a full snapshot |
| 32 | Log in with a wrong password, then check `GET /audit-logs?action=login_failure` as admin | Row present; `attempted_email` is masked even though the login itself failed |
| 33 | Trigger any 403 (e.g. `read_only` hitting `POST /companies`), then `GET /audit-logs?action=access_denied` | Row present with the denied `endpoint` and the caller's `role` |
| 34 | Create a Company with `config_defaults: {"default_job_role": "Field Technician", "default_department": "Ops"}`, then `POST /employees` with no `job_role`/`department` given | 201, employee comes back with `job_role: "Field Technician"`, `department: "Ops"` |
| 35 | Same as #34 but the employee request *does* specify `job_role` | 201, the explicit value wins over the company default |
| 36 | `GET /employees/by-email?company_id=X&email=...` | 200 for a real employee, `EMPLOYEE_NOT_FOUND` (404) for one that doesn't exist |
| 37 | `GET /suppliers/by-name/{name}` | 200 for a real supplier, `SUPPLIER_NOT_FOUND` (404) otherwise |

**All 16 rows in the original write-up, plus rows 34–37 above, were
re-verified live against a running server** (`uvicorn main:app`, real login,
real curl calls, checked against `/openapi.json` to confirm the routes exist
at all). Rows 17–33 (Supplier, Asset, Audit) were verified via the automated
suite rather than a fresh manual pass. #14–16 exposed one real gap while
testing: **there's currently no API endpoint to register a user directly
into a company other than the default "Casterly"** — every self-registration
lands in the default company. Worth adding once there's a real
multi-company onboarding flow.

## 5. Employee profile fields (28 Sep 2026)

Added to the Employee record/form/API, per a direct ask for "first name,
last name, email, job role, department, employee id, designation, phone
number, photo, linkedin url" on the Employee page:

- `full_name` was **split into `first_name` + `last_name`** (both required)
  — not kept alongside a separate full_name column. `full_name` still
  appears in every API response, but as a read-only computed property
  (`Employee.full_name` in app/models/employee.py); there is no longer a
  code path that can set it directly.
- New fields: `employee_code` (optional, unique per company — the "Employee
  ID" the request asked for), `designation` (optional free text, distinct
  from the existing `job_role` dropdown-backed field), `phone_number`
  (optional, encrypted at rest like the other PII fields), `linkedin_url`
  (optional, must start with `http(s)://`).
- "Photo" maps to the **pre-existing** `photo_reference` field — it wasn't
  a new column, just newly exposed on the Employee form (it previously
  existed in the API/model but nothing in the UI surfaced it).
- Migration `2b6f8e1a4c73` backfills existing rows by splitting `full_name`
  on its first space (single-word names get an empty `last_name`, not a
  guessed surname).

Checks worth re-running:

| # | Check | Expect |
|---|---|---|
| 38 | `POST /employees` with `employee_code` already used by another employee in the same company | **400** `EMPLOYEE_CODE_ALREADY_EXISTS` |
| 39 | Same `employee_code` in a *different* company | 201 — unique per company, not globally |
| 40 | `POST /employees` with `linkedin_url: "not-a-url"` | **422** — must start with `http://`/`https://` |
| 41 | `GET /employees?search=<part of first or last name>` | Matches — search covers first_name, last_name, the "first last" combined form, employee_code, and designation (see employee_repository.py's `_filtered`) |
| 42 | Employee page → New employee: fill First/Last name, Employee ID, Designation, Phone number, Photo, LinkedIn URL, save, then Edit it back open | Every field round-trips correctly into the form |

**Bug found and fixed while doing this** (unrelated to the fields above):
`scripts/create_test_db.py` built its subprocess `env` as
`{"DATABASE_URL": test_url, **os.environ}` — since `os.environ` was merged
*after* the explicit key, its own `DATABASE_URL` (the real dev DB) silently
won, so this script had been migrating the **dev** database instead of the
test one every time it ran. Fixed the merge order
(`{**os.environ, "DATABASE_URL": test_url}`). Worth confirming the test
suite still passes against a genuinely fresh `nexus_auth_test` after this.

## 6. Employee photo: real upload, not a typed URL (28 Sep 2026)

The Photo field's URL text box didn't work for anyone who actually had a
photo file rather than an already-hosted image URL — replaced with a real
file picker. `app/core/uploads.py` + `app/routes/upload.py`
(`POST /api/v1/uploads/employee-photo`) validate the file **by its content**
(magic-number sniff — JPEG/PNG/GIF/WEBP), not by the client's filename or
`Content-Type` (both attacker-controlled), enforce a 5MB cap while
streaming (not after buffering it all), save it under a fresh UUID filename
(no path-traversal surface from the original filename), and serve it back
from a new `/uploads` static mount. The Employee form's Photo field still
just holds a URL string underneath (`photo_reference`, unchanged) — the
upload only changes *how* that URL gets populated; nothing else about the
Employee API changed.

Checks worth re-running:

| # | Check | Expect |
|---|---|---|
| 43 | Employee form → Photo → pick a real `.jpg`/`.png`/`.gif`/`.webp` file | Uploads immediately, shows "Uploaded.", a thumbnail preview appears, hidden `photo_reference` gets the returned `/uploads/employee_photos/...` URL |
| 44 | Pick a `.txt` file, or an executable renamed to `photo.jpg` | **400** `UPLOAD_INVALID_IMAGE` — rejected by content, not by extension |
| 45 | Pick a file over 5MB | **400** `UPLOAD_TOO_LARGE` |
| 46 | `read_only` role calls `POST /uploads/employee-photo` directly | **403** — same permission as Employee write |
| 47 | `GET` the returned `/uploads/employee_photos/<uuid>.<ext>` URL directly, no auth header | 200 — **known, documented gap**: uploaded photos are unauthenticated static files (see `SECURITY_CHECKLIST.md`'s new "Employee photo upload" section) |
| 48 | Edit an employee that already has a photo | Existing photo shows as the preview immediately, before picking a new file |

**Test-suite side effect avoided, not just noted:** the suite's own upload
tests (`test_employee_photo_upload.py`) would otherwise write real files
into the project's `uploads/` folder on every run, same problem the
database isolation at the top of `conftest.py` already solved for
Postgres — fixed the same way: `UPLOAD_DIR` is pointed at a fresh OS temp
directory for the whole test session before `main` is ever imported.

## 7. Cleanup after manual testing

Test data respects the same `RESTRICT` constraints production data will —
delete in this order, or Postgres will correctly refuse:

1. Assets (reference Suppliers)
2. Employees (they reference both Company and User)
3. Users (and their `auth_sessions` / `revoked_tokens` rows)
4. Companies, then Suppliers

Commit between each step if scripting it — a bulk delete on Companies while
pending User deletes haven't flushed yet will fail with the same
`RestrictViolation`, which is the constraint working correctly, not a bug.
