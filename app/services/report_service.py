"""Reports module: catalog, authorization, validation, execution and export.

Design notes (so the next reader doesn't have to rediscover them):

- No new permission entries. A report is readable by exactly the roles that
  may already *read the underlying resource* (app/core/permissions.py):
  employee reports follow ("employee", "read"), company reports
  ("company", "read"), asset/supplier likewise, and the security reports
  follow ("audit_log", "read") — which is admin-only. So the existing
  permission matrix stays the single place that decides who can see what;
  adding a role to it automatically extends the matching reports.
- Company isolation reuses app/core/tenancy.py: admin is global, every
  other role is pinned to its own company for Company/Employee data, and
  asking for another company's id gets the same "not found" an ordinary
  lookup gives. Supplier/Asset are a shared catalog (no company_id column),
  and AuditLog has no company_id either — which is the reason the audit and
  session reports are admin-only instead of scoped.
- The catalog below is the single description of every report (title,
  columns, filters). The API serves it to the frontend, so the UI never
  hardcodes a second copy that could drift, and a role only ever sees the
  reports it is allowed to run.
- Reports that cannot be built from the current schema are deliberately
  absent: there is no Asset Assignment report because Asset has no
  assignee/location/employee column (see app/models/asset.py).
- Exports write an audit row (action "export", resource_type "report") with
  the report key, the filters used and the row count — never the data.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.asset_status import ALL_STATUSES as ASSET_STATUSES
from app.core.csv_export import build_csv
from app.core.employee_status import ALL_STATUSES as EMPLOYEE_STATUSES
from app.core.errors import AuthError
from app.core.dependencies import record_access_denied
from app.core.logging import log_rbac_denied
from app.core.master_data import GROUP_ORDER
from app.core.pagination import paginated
from app.core.permissions import allowed_roles
from app.core.roles import ALL_ROLES, Role
from app.core.supplier_status import ALL_STATUSES as SUPPLIER_STATUSES
from app.core.tenancy import enforce_company_scope
from app.models.user import User
from app.repositories import (
    ADMIN_CHANGE_ACTIONS,
    AUDIT_RESOURCE_TYPES,
    MASTER_INFO,
    SECURITY_ACTIONS,
    ReportFilters,
    ReportScope,
    count_admin_changes_since,
    fetch_report,
    get_company_by_id,
    list_asset_filter_values,
    list_company_filter_values,
    list_employee_filter_values,
    list_supplier_categories,
    summary_asset_counts,
    summary_company_counts,
    summary_employee_counts,
    summary_supplier_counts,
)
from app.schemas.report import ReportQuery
from app.services.audit_service import record_audit_event

# Exports are built in memory and returned as one file. A cap keeps that
# safe (and a CSV this large is a sign the filters should be narrower).
MAX_EXPORT_ROWS = 50_000
MAX_TEXT_FILTER_LENGTH = 100
SUMMARY_WINDOW_DAYS = 7

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


# --------------------------------------------------------------------------
# Catalog definitions
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"  # text | number | money | status | datetime | email
    sortable: bool = False


@dataclass(frozen=True)
class FilterDef:
    name: str
    label: str
    kind: str  # text | select | source | company | date
    options: tuple = ()  # (value, label) pairs for kind == "select"
    source: str | None = None  # key into get_filter_options() for kind == "source"
    placeholder: str | None = None


@dataclass(frozen=True)
class ReportDef:
    key: str
    title: str
    category: str
    description: str
    resource: str  # which permission resource gates it (app/core/permissions.py)
    columns: tuple
    filters: tuple
    default_sort: str
    default_dir: str = "asc"
    note: str | None = None


CATEGORIES = (
    ("employee", "Employee Reports", "Headcount, structure and records for employees."),
    ("company", "Company Reports", "Company records and how their employees are distributed."),
    ("asset", "Asset Reports", "Asset inventory and breakdowns by manufacturer, model and status."),
    ("supplier", "Supplier Reports", "Supplier records, categories and approval status."),
    ("master", "Master Management", "Every master list: how many values it has, which are in use, and what changed."),
    ("security", "Security & Audit", "Sign-in, session and change activity. Administrators only."),
)


def _humanize(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _ordered(statuses, preferred: tuple) -> tuple:
    """Lifecycle order for dropdowns (onboarded -> active -> ...), with any
    status added to the enums later appended alphabetically instead of being
    silently dropped."""
    known = set(statuses)
    return tuple(s for s in preferred if s in known) + tuple(sorted(known - set(preferred)))


_EMPLOYEE_ORDER = _ordered(EMPLOYEE_STATUSES, ("onboarded", "active", "on_leave", "exited"))
_ASSET_ORDER = _ordered(ASSET_STATUSES, ("registered", "in_repair", "certified", "disposed"))
_SUPPLIER_ORDER = _ordered(SUPPLIER_STATUSES, ("onboarded", "approved", "suspended"))


def _options(first: tuple, values) -> tuple:
    return (first,) + tuple((v, _humanize(v)) for v in values)


def _search(placeholder: str) -> FilterDef:
    return FilterDef("search", "Search", "text", placeholder=placeholder)


def _dates(prefix: str) -> tuple:
    return (
        FilterDef("date_from", f"{prefix} from", "date"),
        FilterDef("date_to", f"{prefix} to", "date"),
    )


F_COMPANY = FilterDef("company_id", "Company", "company")
F_DEPARTMENT = FilterDef("department", "Department", "source", source="departments")
F_JOB_ROLE = FilterDef("job_role", "Job role", "source", source="job_roles")
F_EMPLOYEE_STATUS = FilterDef(
    "status",
    "Status",
    "select",
    options=_options(("", "Current (excludes exited)"), ("all",) + _EMPLOYEE_ORDER),
)
F_COMPANY_TYPE = FilterDef(
    "company_type",
    "Type",
    "select",
    options=(("", "All types"), ("internal", "Internal"), ("external", "External")),
)
F_COMPANY_STATUS = FilterDef(
    "status", "Status", "select", options=(("", "All"), ("active", "Active"), ("inactive", "Inactive"))
)
F_ASSET_STATUS = FilterDef("status", "Status", "select", options=_options(("", "All statuses"), _ASSET_ORDER))
F_MANUFACTURER = FilterDef("manufacturer", "Manufacturer", "source", source="manufacturers")
F_MODEL = FilterDef("model", "Model", "source", source="models")
F_SUPPLIER_STATUS = FilterDef(
    "status", "Status", "select", options=_options(("", "All statuses"), _SUPPLIER_ORDER)
)
F_CATEGORY = FilterDef("category", "Category", "source", source="categories")
F_ROLE = FilterDef("role", "Role", "select", options=_options(("", "All roles"), ("admin", "operator", "read_only")))
F_RESOURCE_TYPE = FilterDef(
    "resource_type", "Resource type", "select", options=_options(("", "All"), AUDIT_RESOURCE_TYPES)
)
F_AUDIT_ACTION = FilterDef(
    "action",
    "Action",
    "select",
    options=_options(("", "All"), ADMIN_CHANGE_ACTIONS + SECURITY_ACTIONS + ("export",)),
)
F_CHANGE_ACTION = FilterDef(
    "action", "Action", "select", options=_options(("", "All changes"), ADMIN_CHANGE_ACTIONS)
)
# One entry per master, grouped order: the five with their own pages first, as on the Master Management page.
F_MASTER = FilterDef(
    "master",
    "Master",
    "select",
    options=(("", "All masters"),) + tuple(
        (key, plural)
        for key, (plural, group) in sorted(MASTER_INFO.items(), key=lambda kv: (GROUP_ORDER.index(kv[1][1]), kv[1][0]))
    ),
)
F_MASTER_STATUS = FilterDef(
    "status", "Status", "select", options=(("", "All"), ("active", "Active"), ("inactive", "Inactive"))
)

_EMPLOYEE_NOTE = (
    "Reports include work details only. Phone numbers, addresses, bank details and "
    "government IDs are never included."
)

REPORTS: tuple[ReportDef, ...] = (
    # ---- Employee -------------------------------------------------------
    ReportDef(
        "employee-directory",
        "Employee Directory",
        "employee",
        "Every employee with their company, department, job role, status and manager. "
        "Use Export CSV for a full records export of whatever the filters show.",
        "employee",
        (
            Column("employee_code", "Employee ID", sortable=True),
            Column("name", "Name", sortable=True),
            Column("email", "Email", "email", sortable=True),
            Column("company", "Company", sortable=True),
            Column("department", "Department", sortable=True),
            Column("job_role", "Job role", sortable=True),
            Column("designation", "Designation", sortable=True),
            Column("status", "Status", "status", sortable=True),
            Column("manager", "Manager", sortable=True),
            Column("created_at", "Added", "datetime", sortable=True),
        ),
        (_search("Name, email, ID or designation"), F_COMPANY, F_DEPARTMENT, F_JOB_ROLE, F_EMPLOYEE_STATUS)
        + _dates("Added"),
        "name",
        note=_EMPLOYEE_NOTE,
    ),
    ReportDef(
        "employees-by-department",
        "Employees by Department",
        "employee",
        "Headcount per department.",
        "employee",
        (
            Column("department", "Department", sortable=True),
            Column("total", "Employees", "number", sortable=True),
            Column("active", "Active", "number", sortable=True),
        ),
        (F_COMPANY, F_JOB_ROLE, F_EMPLOYEE_STATUS) + _dates("Added"),
        "total",
        "desc",
    ),
    ReportDef(
        "employees-by-job-role",
        "Employees by Job Role",
        "employee",
        "Headcount per job role. Job roles are job titles, not access roles.",
        "employee",
        (
            Column("job_role", "Job role", sortable=True),
            Column("total", "Employees", "number", sortable=True),
            Column("active", "Active", "number", sortable=True),
        ),
        (F_COMPANY, F_DEPARTMENT, F_EMPLOYEE_STATUS) + _dates("Added"),
        "total",
        "desc",
    ),
    ReportDef(
        "employees-by-status",
        "Employees by Status",
        "employee",
        "How many employees are onboarded, active, on leave or exited.",
        "employee",
        (
            Column("status", "Status", "status", sortable=True),
            Column("total", "Employees", "number", sortable=True),
        ),
        (F_COMPANY, F_DEPARTMENT, F_JOB_ROLE) + _dates("Added"),
        "total",
        "desc",
    ),
    # ---- Company --------------------------------------------------------
    ReportDef(
        "company-directory",
        "Company Directory",
        "company",
        "Every company you can see, with its type, status, contact details and current headcount.",
        "company",
        (
            Column("name", "Company", sortable=True),
            Column("company_type", "Type", "status", sortable=True),
            Column("status", "Status", "status", sortable=True),
            Column("contact_email", "Contact email", "email"),
            Column("contact_phone", "Contact phone"),
            Column("employee_count", "Employees", "number", sortable=True),
            Column("created_at", "Added", "datetime", sortable=True),
        ),
        (_search("Company name or contact email"), F_COMPANY_TYPE, F_COMPANY_STATUS) + _dates("Added"),
        "name",
        note="Employees counts everyone except exited employees.",
    ),
    ReportDef(
        "company-employee-summary",
        "Company-wise Employee Summary",
        "company",
        "Employees per company, broken down by status.",
        "company",
        (
            Column("company", "Company", sortable=True),
            Column("company_type", "Type", "status", sortable=True),
            Column("total", "Current", "number", sortable=True),
            Column("active", "Active", "number", sortable=True),
            Column("onboarded", "Onboarded", "number", sortable=True),
            Column("on_leave", "On leave", "number", sortable=True),
            Column("exited", "Exited", "number", sortable=True),
        ),
        (_search("Company name"), F_COMPANY, F_COMPANY_TYPE),
        "total",
        "desc",
        note="Current is every employee who has not exited.",
    ),
    ReportDef(
        "company-status-summary",
        "Company Status Summary",
        "company",
        "Active versus inactive companies, split by internal and external.",
        "company",
        (
            Column("status", "Status", "status", sortable=True),
            Column("internal", "Internal", "number", sortable=True),
            Column("external", "External", "number", sortable=True),
            Column("total", "Total", "number", sortable=True),
        ),
        _dates("Added"),
        "total",
        "desc",
    ),
    # ---- Asset ----------------------------------------------------------
    ReportDef(
        "asset-inventory",
        "Asset Inventory",
        "asset",
        "Every asset with its manufacturer, model, serial number, status, supplier and value.",
        "asset",
        (
            Column("asset_tag", "Asset tag", sortable=True),
            Column("manufacturer", "Manufacturer", sortable=True),
            Column("model", "Model", sortable=True),
            Column("serial_number", "Serial number", sortable=True),
            Column("status", "Status", "status", sortable=True),
            Column("supplier", "Supplier", sortable=True),
            Column("purchase_cost", "Purchase cost", "money", sortable=True),
            Column("current_value", "Current value", "money", sortable=True),
            Column("currency", "Currency"),
            Column("created_at", "Registered", "datetime", sortable=True),
        ),
        (_search("Tag, serial, manufacturer, model or supplier"), F_ASSET_STATUS, F_MANUFACTURER, F_MODEL)
        + _dates("Registered"),
        "asset_tag",
        note="Amounts are shown in each asset's own currency and are not added together.",
    ),
    ReportDef(
        "assets-by-manufacturer",
        "Assets by Manufacturer",
        "asset",
        "Number of assets per manufacturer.",
        "asset",
        (Column("manufacturer", "Manufacturer", sortable=True), Column("total", "Assets", "number", sortable=True)),
        (F_ASSET_STATUS, F_MODEL) + _dates("Registered"),
        "total",
        "desc",
    ),
    ReportDef(
        "assets-by-model",
        "Assets by Model",
        "asset",
        "Number of assets per model.",
        "asset",
        (Column("model", "Model", sortable=True), Column("total", "Assets", "number", sortable=True)),
        (F_ASSET_STATUS, F_MANUFACTURER) + _dates("Registered"),
        "total",
        "desc",
    ),
    ReportDef(
        "assets-by-status",
        "Assets by Status",
        "asset",
        "Number of assets that are registered, in repair, certified or disposed.",
        "asset",
        (Column("status", "Status", "status", sortable=True), Column("total", "Assets", "number", sortable=True)),
        (F_MANUFACTURER, F_MODEL) + _dates("Registered"),
        "total",
        "desc",
    ),
    # ---- Supplier -------------------------------------------------------
    ReportDef(
        "supplier-directory",
        "Supplier Directory",
        "supplier",
        "Every supplier with its category, status, rating and contact details.",
        "supplier",
        (
            Column("name", "Supplier", sortable=True),
            Column("category", "Category", sortable=True),
            Column("status", "Status", "status", sortable=True),
            Column("rating", "Rating", "number", sortable=True),
            Column("terms", "Terms"),
            Column("contact_email", "Contact email", "email"),
            Column("contact_phone", "Contact phone"),
            Column("created_at", "Added", "datetime", sortable=True),
        ),
        (_search("Supplier name or contact email"), F_CATEGORY, F_SUPPLIER_STATUS) + _dates("Added"),
        "name",
    ),
    ReportDef(
        "suppliers-by-category",
        "Suppliers by Category",
        "supplier",
        "Number of suppliers per category. Suppliers with no category are grouped as Uncategorized.",
        "supplier",
        (Column("category", "Category", sortable=True), Column("total", "Suppliers", "number", sortable=True)),
        (F_SUPPLIER_STATUS,) + _dates("Added"),
        "total",
        "desc",
    ),
    ReportDef(
        "supplier-status-summary",
        "Supplier Status Report",
        "supplier",
        "Suppliers by onboarded, approved or suspended, with their average rating.",
        "supplier",
        (
            Column("status", "Status", "status", sortable=True),
            Column("total", "Suppliers", "number", sortable=True),
            Column("average_rating", "Average rating", "number", sortable=True),
        ),
        (F_CATEGORY,) + _dates("Added"),
        "total",
        "desc",
    ),
    # ---- Security & audit (admin-only via the audit_log permission) ------
    # ---- Master Management ---------------------------------------------
    ReportDef(
        "master-summary",
        "Master Summary",
        "master",
        "Every master with how many values it has: active, inactive, total, and how many values records currently use.",
        "master_data",
        (
            Column("master", "Master", sortable=True),
            Column("group", "Group", sortable=True),
            Column("active", "Active", "number", sortable=True),
            Column("inactive", "Inactive", "number", sortable=True),
            Column("total", "Total", "number", sortable=True),
            Column("in_use", "Values in use", "number", sortable=True),
        ),
        (_search("Master name"), F_MASTER),
        "master",
        note="\"In use\" counts values that at least one current employee, asset, supplier or application carries.",
    ),
    ReportDef(
        "master-values",
        "Master Values",
        "master",
        "Every value of every master, with its status and how many records use it.",
        "master_data",
        (
            Column("master", "Master", sortable=True),
            Column("name", "Value", sortable=True),
            Column("status", "Status", "status", sortable=True),
            Column("in_use", "In use", "number", sortable=True),
            Column("created_at", "Added", "datetime", sortable=True),
            Column("updated_at", "Updated", "datetime", sortable=True),
        ),
        (_search("Value name"), F_MASTER, F_MASTER_STATUS) + _dates("Added"),
        "master",
        note="In use means current records: exited employees and disposed assets are not counted.",
    ),
    ReportDef(
        "master-unused-values",
        "Unused Master Values",
        "master",
        "Active values that no record uses — candidates to deactivate or tidy up.",
        "master_data",
        (
            Column("master", "Master", sortable=True),
            Column("name", "Value", sortable=True),
            Column("created_at", "Added", "datetime", sortable=True),
            Column("updated_at", "Updated", "datetime", sortable=True),
        ),
        (_search("Value name"), F_MASTER) + _dates("Added"),
        "master",
    ),
    ReportDef(
        "master-changes",
        "Master Changes",
        "master",
        "Who added, edited, deactivated or reactivated a master value, and when. Administrators only.",
        "audit_log",
        (
            Column("created_at", "When", "datetime", sortable=True),
            Column("user", "Changed by", "email", sortable=True),
            Column("action", "Action", "status", sortable=True),
            Column("master", "Master", sortable=True),
            Column("resource_id", "Value ID", sortable=True),
        ),
        (_search("User email or value ID"), F_MASTER, F_CHANGE_ACTION) + _dates("Changed"),
        "created_at",
        "desc",
        note="Before/after values are not included; open the Audit log page for those.",
    ),
    ReportDef(
        "audit-activity",
        "Audit Activity",
        "security",
        "Every audited event: sign-ins, denials, changes and exports.",
        "audit_log",
        (
            Column("created_at", "When", "datetime", sortable=True),
            Column("user", "User", "email", sortable=True),
            Column("action", "Action", "status", sortable=True),
            Column("resource_type", "Resource", "status", sortable=True),
            Column("resource_id", "Resource ID", sortable=True),
        ),
        (_search("User email or resource ID"), F_AUDIT_ACTION, F_RESOURCE_TYPE) + _dates("Activity"),
        "created_at",
        "desc",
        note="Before/after values are not included; open the Audit log page for those.",
    ),
    ReportDef(
        "user-activity",
        "User Activity",
        "security",
        "Per-user totals built from audit events: changes made, sign-ins, failures and denied requests.",
        "audit_log",
        (
            Column("user", "User", "email", sortable=True),
            Column("role", "Role", "status", sortable=True),
            Column("events", "Events", "number", sortable=True),
            Column("changes", "Changes", "number", sortable=True),
            Column("logins", "Sign-ins", "number", sortable=True),
            Column("failed_logins", "Failed sign-ins", "number", sortable=True),
            Column("access_denied", "Access denied", "number", sortable=True),
            Column("last_activity", "Last activity", "datetime", sortable=True),
        ),
        (_search("User email"), F_ROLE) + _dates("Activity"),
        "events",
        "desc",
        note="Only users with at least one audited event appear. Failed sign-ins for unknown emails have no user and are not counted here.",
    ),
    ReportDef(
        "auth-session-summary",
        "Authentication & Sessions",
        "security",
        "Per-user session totals: sessions opened, still active, revoked, and the most recent sign-in.",
        "audit_log",
        (
            Column("user", "User", "email", sortable=True),
            Column("role", "Role", "status", sortable=True),
            Column("sessions", "Sessions", "number", sortable=True),
            Column("active_sessions", "Active", "number", sortable=True),
            Column("revoked_sessions", "Revoked", "number", sortable=True),
            Column("last_sign_in", "Last sign-in", "datetime", sortable=True),
            Column("last_activity", "Last activity", "datetime", sortable=True),
        ),
        (_search("User email"), F_ROLE) + _dates("Session started"),
        "sessions",
        "desc",
        note="Active means not revoked and not yet expired. IP addresses and device details are not included.",
    ),
    ReportDef(
        "admin-changes",
        "Administrative Changes",
        "security",
        "Changes made to records and access: creates, updates, deletes, status changes and role changes.",
        "audit_log",
        (
            Column("created_at", "When", "datetime", sortable=True),
            Column("user", "Changed by", "email", sortable=True),
            Column("action", "Action", "status", sortable=True),
            Column("resource_type", "Resource", "status", sortable=True),
            Column("resource_id", "Resource ID", sortable=True),
        ),
        (_search("User email or resource ID"), F_CHANGE_ACTION, F_RESOURCE_TYPE) + _dates("Changed"),
        "created_at",
        "desc",
    ),
)
_BY_KEY = {report.key: report for report in REPORTS}


# --------------------------------------------------------------------------
# Authorization helpers
# --------------------------------------------------------------------------
def _scope(user: User) -> ReportScope:
    return ReportScope(is_admin=user.role == Role.ADMIN, company_id=user.company_id)


def _can_read(user: User, resource: str) -> bool:
    return user.role in allowed_roles(resource, "read")


def _report_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _require_report(db: Session, user: User, key: str, endpoint: str) -> ReportDef:
    report = _BY_KEY.get(key)
    if report is None:
        raise _report_error("REPORT_NOT_FOUND", "Report not found.", 404)
    if not _can_read(user, report.resource):
        log_rbac_denied(user.id, user.email, user.role, endpoint)
        # Same denial record as every other 403 (committed despite the error).
        record_access_denied(db, user, endpoint)
        raise AuthError(
            status_code=403,
            error_code="AUTH_FORBIDDEN",
            message="You do not have permission to access this resource.",
        )
    return report


# --------------------------------------------------------------------------
# Catalog / options / summary
# --------------------------------------------------------------------------
def _filter_payload(f: FilterDef) -> dict:
    return {
        "name": f.name,
        "label": f.label,
        "kind": f.kind,
        "options": [{"value": value, "label": label} for value, label in f.options],
        "source": f.source,
        "placeholder": f.placeholder,
    }


def get_report_catalog(user: User) -> dict:
    available = [r for r in REPORTS if _can_read(user, r.resource)]
    present = {r.category for r in available}
    return {
        "categories": [
            {"key": key, "label": label, "description": description}
            for key, label, description in CATEGORIES
            if key in present
        ],
        "reports": [
            {
                "key": r.key,
                "title": r.title,
                "category": r.category,
                "description": r.description,
                "note": r.note,
                "default_sort": r.default_sort,
                "default_dir": r.default_dir,
                "columns": [
                    {"key": c.key, "label": c.label, "kind": c.kind, "sortable": c.sortable} for c in r.columns
                ],
                "filters": [_filter_payload(f) for f in r.filters],
            }
            for r in available
        ],
    }


def get_filter_options(db: Session, user: User) -> dict:
    """Values for the dropdown filters, drawn from the data the caller is
    actually allowed to report on (an operator only ever sees their own
    company's departments, for example)."""
    scope = _scope(user)
    options: dict = {}
    if _can_read(user, "employee"):
        options.update(list_employee_filter_values(db, scope))
    if _can_read(user, "company"):
        options["companies"] = list_company_filter_values(db, scope)
    if _can_read(user, "asset"):
        options.update(list_asset_filter_values(db))
    if _can_read(user, "supplier"):
        options["categories"] = list_supplier_categories(db)
    return options


def _window_start() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=SUMMARY_WINDOW_DAYS - 1)


def get_report_summary(db: Session, user: User) -> dict:
    """Headline numbers, each one only if the caller may read that data, each
    computed straight from the database and scoped like the reports are.
    `report`/`filters` say which report (and filters) reproduce the number,
    so a card can link to the rows behind it."""
    scope = _scope(user)
    metrics: list[dict] = []
    if _can_read(user, "employee"):
        counts = summary_employee_counts(db, scope)
        metrics.append(
            {"key": "total_employees", "label": "Total employees", "value": counts["total"],
             "hint": "Excludes exited", "report": "employee-directory", "filters": {}}
        )
        metrics.append(
            {"key": "active_employees", "label": "Active employees", "value": counts["active"],
             "hint": None, "report": "employee-directory", "filters": {"status": "active"}}
        )
    if _can_read(user, "company"):
        counts = summary_company_counts(db, scope)
        metrics.append(
            {"key": "total_companies", "label": "Total companies", "value": counts["total"],
             "hint": f"{counts['active']} active", "report": "company-directory", "filters": {}}
        )
    if _can_read(user, "asset"):
        counts = summary_asset_counts(db)
        metrics.append(
            {"key": "total_assets", "label": "Total assets", "value": counts["total"],
             "hint": f"{counts['disposed']} disposed" if counts["disposed"] else None,
             "report": "asset-inventory", "filters": {}}
        )
    if _can_read(user, "supplier"):
        counts = summary_supplier_counts(db)
        metrics.append(
            {"key": "total_suppliers", "label": "Total suppliers", "value": counts["total"],
             "hint": f"{counts['approved']} approved", "report": "supplier-directory", "filters": {}}
        )
    if _can_read(user, "audit_log"):
        since = _window_start()
        since_dt = datetime(since.year, since.month, since.day, tzinfo=timezone.utc)
        metrics.append(
            {"key": "recent_admin_activity", "label": "Recent administrative activity",
             "value": count_admin_changes_since(db, since_dt),
             "hint": f"Changes in the last {SUMMARY_WINDOW_DAYS} days",
             "report": "admin-changes", "filters": {"date_from": since.isoformat()}}
        )
    return {"metrics": metrics, "generated_at": datetime.now(timezone.utc)}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _clean_text(name: str, value: str) -> str | None:
    cleaned = _CONTROL_CHARS.sub("", value).strip()
    if len(cleaned) > MAX_TEXT_FILTER_LENGTH:
        raise _report_error(
            "REPORT_INVALID_FILTER",
            f"Filter '{name}' is too long (maximum {MAX_TEXT_FILTER_LENGTH} characters).",
        )
    return cleaned or None


def _start_of_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)


def _build_filters(db: Session, user: User, report: ReportDef, query: ReportQuery) -> tuple[ReportFilters, dict]:
    provided = query.provided_filters()
    supported = {f.name: f for f in report.filters}
    unsupported = sorted(set(provided) - set(supported))
    if unsupported:
        raise _report_error(
            "REPORT_INVALID_FILTER",
            f"This report does not support the filter(s): {', '.join(unsupported)}.",
        )

    values: dict = {}
    applied: dict = {}
    for name, raw in provided.items():
        definition = supported[name]
        if definition.kind == "select":
            allowed = {value for value, _ in definition.options if value}
            if raw not in allowed:
                raise _report_error("REPORT_INVALID_FILTER", f"'{raw}' is not a valid value for filter '{name}'.")
            values[name] = raw
        elif definition.kind in ("text", "source"):
            cleaned = _clean_text(name, str(raw))
            if cleaned is not None:
                values[name] = cleaned
        elif definition.kind == "company":
            if raw < 1:
                raise _report_error("REPORT_INVALID_FILTER", "Filter 'company_id' must be a positive number.")
            company = get_company_by_id(db, raw)
            if company is None:
                raise _report_error("COMPANY_NOT_FOUND", "Company not found.", 404)
            # Same isolation rule every company-scoped lookup uses: a
            # non-admin asking for another company gets the ordinary
            # not-found (and an audited denial), never a distinguishable 403.
            enforce_company_scope(
                db, user, company.id, _report_error("COMPANY_NOT_FOUND", "Company not found.", 404),
                "report", report.key,
            )
            values[name] = raw
        elif definition.kind == "date":
            values[name] = raw
        applied[name] = values[name].isoformat() if isinstance(values.get(name), date) else values.get(name)

    date_from = values.get("date_from")
    date_to = values.get("date_to")
    if date_from and date_to and date_from > date_to:
        raise _report_error("REPORT_INVALID_FILTER", "The 'from' date cannot be after the 'to' date.")

    filters = ReportFilters(
        search=values.get("search"),
        company_id=values.get("company_id"),
        department=values.get("department"),
        job_role=values.get("job_role"),
        status=values.get("status"),
        company_type=values.get("company_type"),
        manufacturer=values.get("manufacturer"),
        model=values.get("model"),
        category=values.get("category"),
        action=values.get("action"),
        resource_type=values.get("resource_type"),
        role=values.get("role"),
        master=values.get("master"),
        date_from=_start_of_day(date_from) if date_from else None,
        # Inclusive "to" day -> exclusive start of the next day.
        date_to=_start_of_day(date_to) + timedelta(days=1) if date_to else None,
    )
    return filters, {k: v for k, v in applied.items() if v is not None}


def _validate_sort(report: ReportDef, query: ReportQuery) -> tuple[str, str]:
    sortable = {c.key for c in report.columns if c.sortable}
    sort_by = query.sort_by or report.default_sort
    sort_dir = query.sort_dir or report.default_dir
    if sort_by not in sortable:
        raise _report_error(
            "REPORT_INVALID_SORT", f"Cannot sort this report by '{sort_by}'. Sortable columns: {', '.join(sorted(sortable))}."
        )
    if sort_dir not in ("asc", "desc"):
        raise _report_error("REPORT_INVALID_SORT", "sort_dir must be 'asc' or 'desc'.")
    return sort_by, sort_dir


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------
def run_report(db: Session, user: User, key: str, query: ReportQuery, limit: int, offset: int) -> dict:
    report = _require_report(db, user, key, f"/api/v1/reports/{key}")
    filters, applied = _build_filters(db, user, report, query)
    sort_by, sort_dir = _validate_sort(report, query)
    rows, total = fetch_report(db, key, _scope(user), filters, sort_by, sort_dir, limit, offset)
    result = paginated(rows, total, limit, offset)
    result.update(
        {
            "report": {"key": report.key, "title": report.title, "category": report.category},
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "filters": applied,
            "generated_at": datetime.now(timezone.utc),
        }
    )
    return result


def export_report_csv(db: Session, user: User, key: str, query: ReportQuery) -> tuple[str, str, int]:
    """Returns (csv_text, filename, row_count) for the *entire* filtered
    result (not just one page), subject to MAX_EXPORT_ROWS, and records the
    export in the audit log."""
    report = _require_report(db, user, key, f"/api/v1/reports/{key}/export")
    filters, applied = _build_filters(db, user, report, query)
    sort_by, sort_dir = _validate_sort(report, query)
    rows, total = fetch_report(db, key, _scope(user), filters, sort_by, sort_dir, MAX_EXPORT_ROWS + 1, 0)
    if total > MAX_EXPORT_ROWS:
        raise _report_error(
            "REPORT_EXPORT_TOO_LARGE",
            f"This report has {total} rows and exports are limited to {MAX_EXPORT_ROWS}. Narrow the filters and try again.",
        )
    text = build_csv(
        [c.label for c in report.columns],
        [[row.get(c.key) for c in report.columns] for row in rows],
    )
    record_audit_event(
        db,
        user.id,
        "export",
        "report",
        resource_id=key,
        old_value=None,
        new_value={"report": key, "format": "csv", "row_count": len(rows), "filters": applied},
        company_id=user.company_id,
    )
    filename = f"{key}-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return text, filename, len(rows)
