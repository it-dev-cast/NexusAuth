"""Read-only queries behind the Reports module (app/services/report_service.py).

Every report is one function that builds a SQLAlchemy SELECT whose labelled
columns are exactly the report's column keys; one shared runner then adds
sorting, counting and pagination, so filtering/sorting/paging behave
identically across all reports and never load more than one page into
memory (exports are the only caller that asks for a full result, and the
service caps that).

What these queries deliberately never select, regardless of report:
- Employee's encrypted columns (phone_number, address, bank/PAN/Aadhaar
  fields, residence_proof_reference, photo_reference) — see
  app/models/employee.py / app/core/pii_crypto.py;
- User.password_hash, and AuthSession's refresh_token_hash / access_token_jti
  / ip_address / user_agent;
- AuditLog.old_value / new_value (the already-masked before/after snapshots
  stay confined to the Audit log page).

Scope: callers pass a ReportScope. Admin is global (same carve-out as
app/core/tenancy.py); every other role is pinned to its own company_id for
the company-scoped tables (Company, Employee). Supplier and Asset have no
company_id in this schema, so they're a single shared catalog and are not
scoped. AuditLog has no company_id either, which is why the security
reports are admin-only (enforced in the service via the audit_log
permission) rather than scoped.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, String, and_, case, cast, false, func, literal_column, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.master_data import LINKED_MASTERS, MASTER_TYPES
from app.models.application import Application, employee_applications
from app.models.asset import Asset
from app.models.asset_model import AssetModel
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession
from app.models.company import Company
from app.models.department import Department
from app.models.employee import Employee
from app.models.job_role import JobRole
from app.models.manufacturer import Manufacturer
from app.models.master_item import MasterItem
from app.models.supplier import Supplier
from app.models.user import User

# Audit actions that represent someone *changing* data or access — the
# "Administrative Changes" report and the "Recent Administrative Activity"
# card. Sign-in/out, denials and token events are security activity, not
# administrative changes, so they're excluded here (and covered by the
# Audit Activity / User Activity reports instead). Values come from the
# action names record_audit_event() is actually called with.
ADMIN_CHANGE_ACTIONS = (
    "create",
    "update",
    "delete",
    "status_transition",
    "role_change",
    "link_user",
    "tag_added",
    "tag_removed",
    "attachment_added",
    "rating_recalculated",
)
SECURITY_ACTIONS = (
    "login_success",
    "login_failure",
    "password_change",
    "refresh_reuse_detected",
    "access_denied",
)
AUDIT_RESOURCE_TYPES = (
    "company",
    "employee",
    "supplier",
    "asset",
    "user",
    "auth",
    "rbac",
    "department",
    "job_role",
    "application",
    "manufacturer",
    "asset_model",
    "master_item",
    "report",
)


@dataclass(frozen=True)
class ReportScope:
    is_admin: bool
    company_id: int | None


@dataclass(frozen=True)
class ReportFilters:
    search: str | None = None
    company_id: int | None = None
    department: str | None = None
    job_role: str | None = None
    status: str | None = None
    company_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None
    action: str | None = None
    resource_type: str | None = None
    role: str | None = None
    master: str | None = None
    date_from: datetime | None = None
    # Exclusive upper bound (the service turns an inclusive "to" date into
    # the start of the following day).
    date_to: datetime | None = None


def _const(value: str):
    """An inlined SQL string literal for the fixed, code-authored labels used
    below ("Unassigned", "active", ...). Never called with user input. Used
    instead of a bind parameter so the same expression can appear in both
    SELECT and GROUP BY without Postgres seeing two different parameters."""
    assert "'" not in value
    return literal_column(f"'{value}'")


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ilike(column, text: str):
    return column.ilike(_like(text), escape="\\")


def _date_clauses(column, f: ReportFilters) -> list:
    clauses = []
    if f.date_from is not None:
        clauses.append(column >= f.date_from)
    if f.date_to is not None:
        clauses.append(column < f.date_to)
    return clauses


# --------------------------------------------------------------------------
# Scope / status helpers
# --------------------------------------------------------------------------
def _employee_scope(scope: ReportScope, f: ReportFilters) -> list:
    if scope.is_admin:
        return [Employee.company_id == f.company_id] if f.company_id is not None else []
    if scope.company_id is None:
        return [false()]
    return [Employee.company_id == scope.company_id]


def _company_scope(scope: ReportScope, f: ReportFilters | None = None) -> list:
    if scope.is_admin:
        if f is not None and f.company_id is not None:
            return [Company.id == f.company_id]
        return []
    if scope.company_id is None:
        return [false()]
    return [Company.id == scope.company_id]


def _employee_status(status: str | None) -> list:
    # Same default as the Employees page: exited employees are hidden unless
    # asked for. "all" means every status, including exited.
    if status is None:
        return [Employee.status != "exited"]
    if status == "all":
        return []
    return [Employee.status == status]


# --------------------------------------------------------------------------
# Employee reports
# --------------------------------------------------------------------------
def _employee_directory(scope, f):
    manager = aliased(Employee)
    name = func.concat(Employee.first_name, _const(" "), Employee.last_name)
    manager_name = case(
        (manager.id.is_(None), None),
        else_=func.concat(manager.first_name, _const(" "), manager.last_name),
    )
    clauses = _employee_scope(scope, f) + _employee_status(f.status)
    if f.department:
        clauses.append(Employee.department == f.department)
    if f.job_role:
        clauses.append(Employee.job_role == f.job_role)
    if f.search:
        clauses.append(
            or_(
                _ilike(name, f.search),
                _ilike(Employee.email, f.search),
                _ilike(Employee.employee_code, f.search),
                _ilike(Employee.designation, f.search),
            )
        )
    clauses += _date_clauses(Employee.created_at, f)
    stmt = (
        select(
            Employee.id.label("id"),
            Employee.employee_code.label("employee_code"),
            name.label("name"),
            Employee.email.label("email"),
            Company.name.label("company"),
            Employee.department.label("department"),
            Employee.job_role.label("job_role"),
            Employee.designation.label("designation"),
            Employee.status.label("status"),
            manager_name.label("manager"),
            Employee.created_at.label("created_at"),
        )
        .select_from(Employee)
        .join(Company, Company.id == Employee.company_id)
        .outerjoin(manager, manager.id == Employee.manager_id)
        .where(*clauses)
    )
    sort = {
        "name": name,
        "employee_code": Employee.employee_code,
        "email": Employee.email,
        "company": Company.name,
        "department": Employee.department,
        "job_role": Employee.job_role,
        "designation": Employee.designation,
        "status": Employee.status,
        "manager": manager_name,
        "created_at": Employee.created_at,
    }
    return stmt, sort, Employee.id


def _employees_grouped(scope, f, *, with_status_filter=True, with_dept=False, with_role=False):
    clauses = _employee_scope(scope, f)
    if with_status_filter:
        clauses += _employee_status(f.status)
    if with_dept and f.department:
        clauses.append(Employee.department == f.department)
    if with_role and f.job_role:
        clauses.append(Employee.job_role == f.job_role)
    clauses += _date_clauses(Employee.created_at, f)
    return clauses


def _employees_by_department(scope, f):
    label = func.coalesce(Employee.department, _const("Unassigned"))
    total = func.count(Employee.id)
    active = func.count(case((Employee.status == "active", 1)))
    clauses = _employees_grouped(scope, f, with_role=True)
    stmt = (
        select(label.label("department"), total.label("total"), active.label("active"))
        .where(*clauses)
        .group_by(label)
    )
    return stmt, {"department": label, "total": total, "active": active}, label


def _employees_by_job_role(scope, f):
    label = Employee.job_role
    total = func.count(Employee.id)
    active = func.count(case((Employee.status == "active", 1)))
    clauses = _employees_grouped(scope, f, with_dept=True)
    stmt = (
        select(label.label("job_role"), total.label("total"), active.label("active"))
        .where(*clauses)
        .group_by(label)
    )
    return stmt, {"job_role": label, "total": total, "active": active}, label


def _employees_by_status(scope, f):
    label = Employee.status
    total = func.count(Employee.id)
    clauses = _employees_grouped(scope, f, with_status_filter=False, with_dept=True, with_role=True)
    stmt = select(label.label("status"), total.label("total")).where(*clauses).group_by(label)
    return stmt, {"status": label, "total": total}, label


# --------------------------------------------------------------------------
# Company reports
# --------------------------------------------------------------------------
def _company_status_label():
    return case((Company.is_active.is_(True), _const("active")), else_=_const("inactive"))


def _company_directory(scope, f):
    status = _company_status_label()
    employee_count = (
        select(func.count(Employee.id))
        .where(Employee.company_id == Company.id, Employee.status != "exited")
        .correlate(Company)
        .scalar_subquery()
    )
    clauses = _company_scope(scope)
    if f.company_type:
        clauses.append(Company.company_type == f.company_type)
    if f.status:
        clauses.append(status == f.status)
    if f.search:
        clauses.append(or_(_ilike(Company.name, f.search), _ilike(Company.contact_email, f.search)))
    clauses += _date_clauses(Company.created_at, f)
    stmt = select(
        Company.id.label("id"),
        Company.name.label("name"),
        Company.company_type.label("company_type"),
        status.label("status"),
        Company.contact_email.label("contact_email"),
        Company.contact_phone.label("contact_phone"),
        employee_count.label("employee_count"),
        Company.created_at.label("created_at"),
    ).where(*clauses)
    sort = {
        "name": Company.name,
        "company_type": Company.company_type,
        "status": status,
        "employee_count": employee_count,
        "created_at": Company.created_at,
    }
    return stmt, sort, Company.id


def _company_employee_summary(scope, f):
    def count_status(value):
        return func.count(case((Employee.status == value, 1)))

    total = func.count(case((Employee.status != "exited", 1)))
    active = count_status("active")
    onboarded = count_status("onboarded")
    on_leave = count_status("on_leave")
    exited = count_status("exited")
    clauses = _company_scope(scope, f)
    if f.company_type:
        clauses.append(Company.company_type == f.company_type)
    if f.search:
        clauses.append(_ilike(Company.name, f.search))
    stmt = (
        select(
            Company.name.label("company"),
            Company.company_type.label("company_type"),
            total.label("total"),
            active.label("active"),
            onboarded.label("onboarded"),
            on_leave.label("on_leave"),
            exited.label("exited"),
        )
        .select_from(Company)
        .outerjoin(Employee, Employee.company_id == Company.id)
        .where(*clauses)
        .group_by(Company.id, Company.name, Company.company_type)
    )
    sort = {
        "company": Company.name,
        "company_type": Company.company_type,
        "total": total,
        "active": active,
        "onboarded": onboarded,
        "on_leave": on_leave,
        "exited": exited,
    }
    return stmt, sort, Company.id


def _company_status_summary(scope, f):
    status = _company_status_label()
    internal = func.count(case((Company.company_type == "internal", 1)))
    external = func.count(case((Company.company_type == "external", 1)))
    total = func.count(Company.id)
    clauses = _company_scope(scope) + _date_clauses(Company.created_at, f)
    stmt = (
        select(status.label("status"), internal.label("internal"), external.label("external"), total.label("total"))
        .where(*clauses)
        .group_by(status)
    )
    return stmt, {"status": status, "internal": internal, "external": external, "total": total}, status


# --------------------------------------------------------------------------
# Asset reports (Asset has no assignee/location column — see the service's
# note — so there is deliberately no assignment report here.)
# --------------------------------------------------------------------------
def _asset_clauses(f: ReportFilters, *, status=True, manufacturer=True, model=True):
    clauses = []
    if status and f.status:
        clauses.append(Asset.status == f.status)
    if manufacturer and f.manufacturer:
        clauses.append(Asset.manufacturer == f.manufacturer)
    if model and f.model:
        clauses.append(Asset.model == f.model)
    clauses += _date_clauses(Asset.created_at, f)
    return clauses


def _asset_inventory(scope, f):
    clauses = _asset_clauses(f)
    if f.search:
        clauses.append(
            or_(
                _ilike(Asset.asset_tag, f.search),
                _ilike(Asset.serial_number, f.search),
                _ilike(Asset.manufacturer, f.search),
                _ilike(Asset.model, f.search),
                _ilike(Supplier.name, f.search),
            )
        )
    stmt = (
        select(
            Asset.id.label("id"),
            Asset.asset_tag.label("asset_tag"),
            Asset.manufacturer.label("manufacturer"),
            Asset.model.label("model"),
            Asset.serial_number.label("serial_number"),
            Asset.status.label("status"),
            Supplier.name.label("supplier"),
            Asset.purchase_cost.label("purchase_cost"),
            Asset.current_value.label("current_value"),
            Asset.currency.label("currency"),
            Asset.created_at.label("created_at"),
        )
        .select_from(Asset)
        .join(Supplier, Supplier.id == Asset.supplier_id)
        .where(*clauses)
    )
    sort = {
        "asset_tag": Asset.asset_tag,
        "manufacturer": Asset.manufacturer,
        "model": Asset.model,
        "serial_number": Asset.serial_number,
        "status": Asset.status,
        "supplier": Supplier.name,
        "purchase_cost": Asset.purchase_cost,
        "current_value": Asset.current_value,
        "created_at": Asset.created_at,
    }
    return stmt, sort, Asset.id


def _assets_by_manufacturer(scope, f):
    label = Asset.manufacturer
    total = func.count(Asset.id)
    stmt = (
        select(label.label("manufacturer"), total.label("total"))
        .where(*_asset_clauses(f, manufacturer=False, model=False))
        .group_by(label)
    )
    return stmt, {"manufacturer": label, "total": total}, label


def _assets_by_model(scope, f):
    label = Asset.model
    total = func.count(Asset.id)
    stmt = (
        select(label.label("model"), total.label("total"))
        .where(*_asset_clauses(f, model=False))
        .group_by(label)
    )
    return stmt, {"model": label, "total": total}, label


def _assets_by_status(scope, f):
    label = Asset.status
    total = func.count(Asset.id)
    stmt = (
        select(label.label("status"), total.label("total"))
        .where(*_asset_clauses(f, status=False))
        .group_by(label)
    )
    return stmt, {"status": label, "total": total}, label


# --------------------------------------------------------------------------
# Supplier reports
# --------------------------------------------------------------------------
def _supplier_clauses(f: ReportFilters, *, status=True, category=True):
    clauses = []
    if status and f.status:
        clauses.append(Supplier.status == f.status)
    if category and f.category:
        clauses.append(Supplier.category == f.category)
    clauses += _date_clauses(Supplier.created_at, f)
    return clauses


def _supplier_directory(scope, f):
    clauses = _supplier_clauses(f)
    if f.search:
        clauses.append(or_(_ilike(Supplier.name, f.search), _ilike(Supplier.contact_email, f.search)))
    stmt = select(
        Supplier.id.label("id"),
        Supplier.name.label("name"),
        Supplier.category.label("category"),
        Supplier.status.label("status"),
        Supplier.rating.label("rating"),
        Supplier.terms.label("terms"),
        Supplier.contact_email.label("contact_email"),
        Supplier.contact_phone.label("contact_phone"),
        Supplier.created_at.label("created_at"),
    ).where(*clauses)
    sort = {
        "name": Supplier.name,
        "category": Supplier.category,
        "status": Supplier.status,
        "rating": Supplier.rating,
        "created_at": Supplier.created_at,
    }
    return stmt, sort, Supplier.id


def _suppliers_by_category(scope, f):
    label = func.coalesce(Supplier.category, _const("Uncategorized"))
    total = func.count(Supplier.id)
    stmt = (
        select(label.label("category"), total.label("total"))
        .where(*_supplier_clauses(f, category=False))
        .group_by(label)
    )
    return stmt, {"category": label, "total": total}, label


def _supplier_status_summary(scope, f):
    label = Supplier.status
    total = func.count(Supplier.id)
    average = func.round(func.avg(Supplier.rating), 2)
    stmt = (
        select(label.label("status"), total.label("total"), average.label("average_rating"))
        .where(*_supplier_clauses(f, status=False))
        .group_by(label)
    )
    return stmt, {"status": label, "total": total, "average_rating": average}, label


# --------------------------------------------------------------------------
# Security & audit reports (admin-only — enforced by the service)
# --------------------------------------------------------------------------
def _audit_rows(scope, f, *, changes_only: bool):
    clauses = _date_clauses(AuditLog.created_at, f)
    if changes_only:
        clauses.append(AuditLog.action.in_(ADMIN_CHANGE_ACTIONS))
    if f.action:
        clauses.append(AuditLog.action == f.action)
    if f.resource_type:
        clauses.append(AuditLog.resource_type == f.resource_type)
    if f.search:
        clauses.append(or_(_ilike(User.email, f.search), _ilike(AuditLog.resource_id, f.search)))
    user_label = func.coalesce(User.email, _const("System"))
    stmt = (
        select(
            AuditLog.id.label("id"),
            AuditLog.created_at.label("created_at"),
            user_label.label("user"),
            AuditLog.action.label("action"),
            AuditLog.resource_type.label("resource_type"),
            AuditLog.resource_id.label("resource_id"),
        )
        .select_from(AuditLog)
        .outerjoin(User, User.id == AuditLog.user_id)
        .where(*clauses)
    )
    sort = {
        "created_at": AuditLog.created_at,
        "user": user_label,
        "action": AuditLog.action,
        "resource_type": AuditLog.resource_type,
        "resource_id": AuditLog.resource_id,
    }
    return stmt, sort, AuditLog.id


def _audit_activity(scope, f):
    return _audit_rows(scope, f, changes_only=False)


def _admin_changes(scope, f):
    return _audit_rows(scope, f, changes_only=True)


def _user_activity(scope, f):
    events = func.count(AuditLog.id)
    changes = func.count(case((AuditLog.action.in_(ADMIN_CHANGE_ACTIONS), 1)))
    logins = func.count(case((AuditLog.action == "login_success", 1)))
    failed = func.count(case((AuditLog.action == "login_failure", 1)))
    denied = func.count(case((AuditLog.action == "access_denied", 1)))
    last = func.max(AuditLog.created_at)
    clauses = _date_clauses(AuditLog.created_at, f)
    if f.role:
        clauses.append(User.role == f.role)
    if f.search:
        clauses.append(_ilike(User.email, f.search))
    stmt = (
        select(
            User.email.label("user"),
            User.role.label("role"),
            events.label("events"),
            changes.label("changes"),
            logins.label("logins"),
            failed.label("failed_logins"),
            denied.label("access_denied"),
            last.label("last_activity"),
        )
        .select_from(AuditLog)
        .join(User, User.id == AuditLog.user_id)
        .where(*clauses)
        .group_by(User.id, User.email, User.role)
    )
    sort = {
        "user": User.email,
        "role": User.role,
        "events": events,
        "changes": changes,
        "logins": logins,
        "failed_logins": failed,
        "access_denied": denied,
        "last_activity": last,
    }
    return stmt, sort, User.id


def _auth_session_summary(scope, f):
    sessions = func.count(AuthSession.id)
    active = func.count(
        case(((AuthSession.is_revoked.is_(False)) & (AuthSession.expires_at > func.now()), 1))
    )
    revoked = func.count(case((AuthSession.is_revoked.is_(True), 1)))
    last_sign_in = func.max(AuthSession.created_at)
    last_activity = func.max(AuthSession.last_used_at)
    clauses = _date_clauses(AuthSession.created_at, f)
    if f.role:
        clauses.append(User.role == f.role)
    if f.search:
        clauses.append(_ilike(User.email, f.search))
    stmt = (
        select(
            User.email.label("user"),
            User.role.label("role"),
            sessions.label("sessions"),
            active.label("active_sessions"),
            revoked.label("revoked_sessions"),
            last_sign_in.label("last_sign_in"),
            last_activity.label("last_activity"),
        )
        .select_from(AuthSession)
        .join(User, User.id == AuthSession.user_id)
        .where(*clauses)
        .group_by(User.id, User.email, User.role)
    )
    sort = {
        "user": User.email,
        "role": User.role,
        "sessions": sessions,
        "active_sessions": active,
        "revoked_sessions": revoked,
        "last_sign_in": last_sign_in,
        "last_activity": last_activity,
    }
    return stmt, sort, User.id


# --------------------------------------------------------------------------
# Master Management reports
# --------------------------------------------------------------------------
# Every master the Master Management page offers — the five with their own
# tables (Departments, Job Roles, ...) and the three simple lists in
# master_items — viewed as one set of (master, value) rows. Labels and groups
# come from app/core/master_data.py, so a master added there is reported on
# with no change here beyond its "in use" rule below.
MASTER_INFO = {
    **{m.key: (m.plural, m.group) for m in LINKED_MASTERS.values()},
    **{t.key: (t.plural, t.group) for t in MASTER_TYPES.values()},
}
# Audit resource types the master changes are recorded under.
MASTER_AUDIT_TYPES = ("master_item", "department", "job_role", "application", "manufacturer", "asset_model")


def _master_part(key: str, model, name, in_use, *, extra=()):
    plural, group = MASTER_INFO[key]
    return select(
        func.concat(_const(f"{key}:"), cast(model.id, String)).label("row_key"),
        _const(key).label("master_key"),
        _const(plural).label("master"),
        _const(group).label("grp"),
        name.label("name"),
        model.is_active.label("is_active"),
        in_use.label("in_use"),
        model.created_at.label("created_at"),
        model.updated_at.label("updated_at"),
    ).where(*extra)


def _master_values_union():
    """One row per master value, whichever table it lives in. `in_use` is how
    many records currently carry the value — the same rule each master's own
    page uses (exited employees and disposed assets don't count; a record
    stores the value's name as text, so it is a name match)."""
    employees = Employee
    parts = [
        _master_part(
            "department", Department, Department.name,
            select(func.count(employees.id)).where(employees.department == Department.name, employees.status != "exited").correlate(Department).scalar_subquery(),
        ),
        _master_part(
            "job_role", JobRole, JobRole.name,
            select(func.count(employees.id))
            .where(employees.status != "exited", or_(employees.job_role == JobRole.name, employees.designation == JobRole.name))
            .correlate(JobRole)
            .scalar_subquery(),
        ),
        _master_part(
            "application", Application, Application.name,
            select(func.count()).select_from(employee_applications).where(employee_applications.c.application_id == Application.id).correlate(Application).scalar_subquery(),
        ),
        _master_part(
            "manufacturer", Manufacturer, Manufacturer.name,
            select(func.count(Asset.id)).where(Asset.manufacturer == Manufacturer.name, Asset.status != "disposed").correlate(Manufacturer).scalar_subquery(),
        ),
        _master_part(
            "asset_model", AssetModel, AssetModel.name,
            select(func.count(Asset.id)).where(Asset.model == AssetModel.name, Asset.status != "disposed").correlate(AssetModel).scalar_subquery(),
        ),
    ]
    list_usage = {
        "supplier_category": select(func.count(Supplier.id)).where(func.lower(Supplier.category) == func.lower(MasterItem.name)),
        "payment_terms": select(func.count(Supplier.id)).where(func.lower(Supplier.terms) == func.lower(MasterItem.name)),
        "application_category": select(func.count(Application.id)).where(func.lower(Application.category) == func.lower(MasterItem.name)),
    }
    for key in MASTER_TYPES:
        parts.append(
            _master_part(
                key, MasterItem, MasterItem.name,
                list_usage[key].correlate(MasterItem).scalar_subquery(),
                extra=(MasterItem.master_type == key,),
            )
        )
    return parts[0].union_all(*parts[1:]).subquery("master_values")


def _master_value_clauses(u, f: ReportFilters) -> list:
    clauses = []
    if f.master:
        clauses.append(u.c.master_key == f.master)
    if f.search:
        clauses.append(_ilike(u.c.name, f.search))
    clauses.extend(_date_clauses(u.c.created_at, f))
    return clauses


def _master_values_stmt(u, clauses):
    status = case((u.c.is_active.is_(True), _const("active")), else_=_const("inactive"))
    stmt = select(
        u.c.master.label("master"),
        u.c.grp.label("group"),
        u.c.name.label("name"),
        status.label("status"),
        u.c.in_use.label("in_use"),
        u.c.created_at.label("created_at"),
        u.c.updated_at.label("updated_at"),
    ).where(*clauses)
    sort = {
        "master": u.c.master,
        "group": u.c.grp,
        "name": u.c.name,
        "status": status,
        "in_use": u.c.in_use,
        "created_at": u.c.created_at,
        "updated_at": u.c.updated_at,
    }
    return stmt, sort, u.c.row_key


def _master_values(scope, f):
    u = _master_values_union()
    clauses = _master_value_clauses(u, f)
    if f.status == "active":
        clauses.append(u.c.is_active.is_(True))
    elif f.status == "inactive":
        clauses.append(u.c.is_active.is_(False))
    return _master_values_stmt(u, clauses)


def _master_unused_values(scope, f):
    """Active values no record currently uses — candidates to deactivate."""
    u = _master_values_union()
    clauses = _master_value_clauses(u, f) + [u.c.is_active.is_(True), u.c.in_use == 0]
    return _master_values_stmt(u, clauses)


def _master_summary(scope, f):
    u = _master_values_union()
    clauses = []
    if f.master:
        clauses.append(u.c.master_key == f.master)
    if f.search:
        clauses.append(_ilike(u.c.master, f.search))
    active = func.count(u.c.row_key).filter(u.c.is_active.is_(True))
    inactive = func.count(u.c.row_key).filter(u.c.is_active.is_(False))
    total = func.count(u.c.row_key)
    in_use = func.count(u.c.row_key).filter(u.c.in_use > 0)
    stmt = (
        select(
            u.c.master.label("master"),
            u.c.grp.label("group"),
            active.label("active"),
            inactive.label("inactive"),
            total.label("total"),
            in_use.label("in_use"),
        )
        .where(*clauses)
        .group_by(u.c.master_key, u.c.master, u.c.grp)
    )
    sort = {"master": u.c.master, "group": u.c.grp, "active": active, "inactive": inactive, "total": total, "in_use": in_use}
    return stmt, sort, u.c.master_key


def _master_changes(scope, f):
    """Who changed which master, and when (admin-only: it reads the audit
    log). Before/after values are never selected."""
    item = aliased(MasterItem)
    master_key = case((AuditLog.resource_type == "master_item", item.master_type), else_=AuditLog.resource_type)
    master_label = case(
        *[(master_key == key, _const(plural)) for key, (plural, _group) in MASTER_INFO.items()],
        else_=_const("Other"),
    )
    clauses = _date_clauses(AuditLog.created_at, f) + [AuditLog.resource_type.in_(MASTER_AUDIT_TYPES)]
    if f.action:
        clauses.append(AuditLog.action == f.action)
    if f.master:
        clauses.append(master_key == f.master)
    if f.search:
        clauses.append(or_(_ilike(User.email, f.search), _ilike(AuditLog.resource_id, f.search)))
    user_label = func.coalesce(User.email, _const("System"))
    stmt = (
        select(
            AuditLog.id.label("id"),
            AuditLog.created_at.label("created_at"),
            user_label.label("user"),
            AuditLog.action.label("action"),
            master_label.label("master"),
            AuditLog.resource_id.label("resource_id"),
        )
        .select_from(AuditLog)
        .outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(item, and_(AuditLog.resource_type == "master_item", cast(item.id, String) == AuditLog.resource_id))
        .where(*clauses)
    )
    sort = {
        "created_at": AuditLog.created_at,
        "user": user_label,
        "action": AuditLog.action,
        "master": master_label,
        "resource_id": AuditLog.resource_id,
    }
    return stmt, sort, AuditLog.id


REPORT_QUERIES = {
    "master-summary": _master_summary,
    "master-values": _master_values,
    "master-unused-values": _master_unused_values,
    "master-changes": _master_changes,
    "employee-directory": _employee_directory,
    "employees-by-department": _employees_by_department,
    "employees-by-job-role": _employees_by_job_role,
    "employees-by-status": _employees_by_status,
    "company-directory": _company_directory,
    "company-employee-summary": _company_employee_summary,
    "company-status-summary": _company_status_summary,
    "asset-inventory": _asset_inventory,
    "assets-by-manufacturer": _assets_by_manufacturer,
    "assets-by-model": _assets_by_model,
    "assets-by-status": _assets_by_status,
    "supplier-directory": _supplier_directory,
    "suppliers-by-category": _suppliers_by_category,
    "supplier-status-summary": _supplier_status_summary,
    "audit-activity": _audit_activity,
    "user-activity": _user_activity,
    "auth-session-summary": _auth_session_summary,
    "admin-changes": _admin_changes,
}


def fetch_report(
    db: Session,
    key: str,
    scope: ReportScope,
    filters: ReportFilters,
    sort_by: str,
    sort_dir: str,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Run one report: returns (rows for this page, total matching rows).

    `sort_by` must already be validated against the report's sortable
    columns by the service — it's looked up in the builder's own whitelist
    here, so even a bad key can never reach the SQL as raw text.
    """
    stmt, sort_columns, tiebreak = REPORT_QUERIES[key](scope, filters)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar() or 0
    column = sort_columns[sort_by]
    primary = column.asc().nulls_last() if sort_dir == "asc" else column.desc().nulls_last()
    ordered: Select = stmt.order_by(primary, tiebreak.asc())
    rows = db.execute(ordered.limit(limit).offset(offset)).mappings().all()
    return [dict(row) for row in rows], total


# --------------------------------------------------------------------------
# Summary cards + filter option lists
# --------------------------------------------------------------------------
def summary_employee_counts(db: Session, scope: ReportScope) -> dict[str, int]:
    base = _employee_scope(scope, ReportFilters())
    total = db.execute(select(func.count(Employee.id)).where(*base, Employee.status != "exited")).scalar() or 0
    active = db.execute(select(func.count(Employee.id)).where(*base, Employee.status == "active")).scalar() or 0
    return {"total": total, "active": active}


def summary_company_counts(db: Session, scope: ReportScope) -> dict[str, int]:
    base = _company_scope(scope)
    total = db.execute(select(func.count(Company.id)).where(*base)).scalar() or 0
    active = db.execute(select(func.count(Company.id)).where(*base, Company.is_active.is_(True))).scalar() or 0
    return {"total": total, "active": active}


def summary_asset_counts(db: Session) -> dict[str, int]:
    total = db.execute(select(func.count(Asset.id))).scalar() or 0
    disposed = db.execute(select(func.count(Asset.id)).where(Asset.status == "disposed")).scalar() or 0
    return {"total": total, "disposed": disposed}


def summary_supplier_counts(db: Session) -> dict[str, int]:
    total = db.execute(select(func.count(Supplier.id))).scalar() or 0
    approved = db.execute(select(func.count(Supplier.id)).where(Supplier.status == "approved")).scalar() or 0
    return {"total": total, "approved": approved}


def count_admin_changes_since(db: Session, since: datetime) -> int:
    return (
        db.execute(
            select(func.count(AuditLog.id)).where(
                AuditLog.action.in_(ADMIN_CHANGE_ACTIONS), AuditLog.created_at >= since
            )
        ).scalar()
        or 0
    )


def _distinct(db: Session, column, *clauses) -> list[str]:
    rows = db.execute(select(column).where(column.isnot(None), *clauses).distinct().order_by(column.asc())).all()
    return [row[0] for row in rows if row[0]]


def list_employee_filter_values(db: Session, scope: ReportScope) -> dict[str, list[str]]:
    base = _employee_scope(scope, ReportFilters())
    return {
        "departments": _distinct(db, Employee.department, *base),
        "job_roles": _distinct(db, Employee.job_role, *base),
    }


def list_company_filter_values(db: Session, scope: ReportScope) -> list[dict]:
    rows = db.execute(
        select(Company.id, Company.name).where(*_company_scope(scope)).order_by(Company.name.asc())
    ).all()
    return [{"id": row[0], "name": row[1]} for row in rows]


def list_asset_filter_values(db: Session) -> dict[str, list[str]]:
    return {
        "manufacturers": _distinct(db, Asset.manufacturer),
        "models": _distinct(db, Asset.model),
    }


def list_supplier_categories(db: Session) -> list[str]:
    return _distinct(db, Supplier.category)
