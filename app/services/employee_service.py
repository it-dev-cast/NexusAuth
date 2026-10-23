import json

from sqlalchemy.orm import Session

from app.core.employee_status import is_valid_transition
from app.core.errors import AuthError
from app.core.graph_utils import creates_cycle
from app.core.pagination import paginated
from app.core.roles import Role
from app.core.tenancy import enforce_company_scope
from app.models.application import Application
from app.models.company import Company
from app.models.employee import Employee
from app.repositories import (
    count_all_employees,
    count_employees_by_company,
    create_employee,
    get_applications_by_ids,
    get_company_manager_map,
    get_employee_by_email,
    get_employee_by_employee_code,
    get_employee_by_id,
    get_employee_by_user_id,
    get_user_by_id,
    list_all_employees,
    list_employees_by_company,
)
from app.schemas.employee import EmployeeCreateRequest, EmployeeResponse, EmployeeUpdateRequest
from app.services.audit_service import record_audit_event
from app.services.company_service import get_company

# Deliberately imported directly rather than added to app.repositories'
# public surface — this is an internal cascade detail of Employee status
# transitions, not something other modules should call independently.
from app.models.user import User


def _employee_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _employee_not_found() -> AuthError:
    return _employee_error("EMPLOYEE_NOT_FOUND", "Employee not found.", status_code=404)


def _company_not_found() -> AuthError:
    return _employee_error("COMPANY_NOT_FOUND", "Company not found.", status_code=404)


def _snapshot(employee: Employee) -> dict:
    return EmployeeResponse.model_validate(employee).model_dump(mode="json")


def _company_defaults(company: Company) -> dict:
    """Doc: "Employee role inheritance from Company defaults". config_defaults
    is stored as a free-form JSON-in-text string (see app/models/company.py);
    parse it defensively — a company with no defaults, or a non-JSON /
    non-object value, just yields no inheritable defaults rather than an error.
    """
    if not company.config_defaults:
        return {}
    try:
        parsed = json.loads(company.config_defaults)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _check_employee_code_available(
    db: Session, company_id: int, employee_code: str | None, exclude_employee_id: int | None
) -> None:
    """employee_code is optional but, like email, unique per company (see
    Employee.__table_args__) — checked proactively here for a clean 400
    error rather than letting a raw IntegrityError bubble up from the
    unique constraint at insert/commit time."""
    if not employee_code:
        return
    existing = get_employee_by_employee_code(db, company_id, employee_code)
    if existing and existing.id != exclude_employee_id:
        raise _employee_error(
            "EMPLOYEE_CODE_ALREADY_EXISTS",
            "An employee with this employee_code already exists in this company.",
        )


def _validate_user_link(db: Session, company_id: int, user_id: int | None) -> None:
    if user_id is None:
        return

    user = get_user_by_id(db, user_id)
    if not user:
        raise _employee_error(
            "EMPLOYEE_USER_NOT_FOUND",
            "Linked user account not found.",
            status_code=404,
        )
    if user.company_id != company_id:
        raise _employee_error(
            "EMPLOYEE_USER_COMPANY_MISMATCH",
            "The linked user account belongs to a different company.",
        )

    existing_link = get_employee_by_user_id(db, user_id)
    if existing_link:
        raise _employee_error(
            "EMPLOYEE_USER_ALREADY_LINKED",
            "This user account is already linked to another employee.",
        )


def _validate_manager_assignment(
    db: Session, company_id: int, employee_id: int | None, manager_id: int | None
) -> None:
    """Doc: "Circular dependency detection" (Module 7) — the first place in
    this codebase app.core.graph_utils.creates_cycle actually gets called.

    employee_id is None when validating at create time (a brand-new
    employee can't be part of an existing cycle yet, but the manager must
    still exist and be in the same company).
    """
    if manager_id is None:
        return

    manager = get_employee_by_id(db, manager_id)
    if not manager or manager.company_id != company_id:
        raise _employee_error(
            "EMPLOYEE_MANAGER_NOT_FOUND",
            "The specified manager was not found in this company.",
            status_code=404,
        )

    if employee_id is not None:
        if manager_id == employee_id:
            raise _employee_error(
                "EMPLOYEE_MANAGER_CYCLE",
                "An employee cannot be their own manager.",
            )
        parent_of = get_company_manager_map(db, company_id)
        if creates_cycle(parent_of, employee_id, manager_id):
            raise _employee_error(
                "EMPLOYEE_MANAGER_CYCLE",
                "This assignment would create a management cycle "
                "(the proposed manager reports, directly or indirectly, "
                "to this employee already).",
            )


def _validate_application_ids(db: Session, application_ids: list[int]) -> list[Application]:
    """Resolves the checked application ids to real, active Application
    rows — every id must exist (unlike job_role/department's free-text
    "Other" escape hatch, there's no way to check a box for an application
    that doesn't exist in the master list) and be active (an inactive
    application shouldn't gain new employees, same reasoning as
    create_employee_record's inactive-company check)."""
    if not application_ids:
        return []
    applications = get_applications_by_ids(db, application_ids)
    found_ids = {application.id for application in applications}
    missing = set(application_ids) - found_ids
    if missing:
        raise _employee_error(
            "EMPLOYEE_APPLICATION_NOT_FOUND",
            f"Application id(s) not found: {', '.join(str(i) for i in sorted(missing))}.",
            status_code=404,
        )
    inactive = [application.name for application in applications if not application.is_active]
    if inactive:
        raise _employee_error(
            "EMPLOYEE_APPLICATION_INACTIVE",
            f"Cannot grant access to inactive application(s): {', '.join(inactive)}.",
        )
    return applications


def create_employee_record(db: Session, data: EmployeeCreateRequest, current_user: User) -> Employee:
    actor_id = current_user.id
    # Ensures the company is real (raises 404 otherwise) — same lookup
    # Company Management already uses.
    company = get_company(db, data.company_id)

    # Company isolation: an operator may only create employees under their
    # own company — not just any company that happens to exist.
    enforce_company_scope(db, current_user, company.id, _company_not_found(), "employee", None)

    # Cascade rule: an inactive (soft-deleted) company can't gain new
    # employees. Existing employees under it are left untouched — a company
    # going inactive doesn't retroactively erase its history.
    if not company.is_active:
        raise _employee_error(
            "EMPLOYEE_COMPANY_INACTIVE",
            "Cannot add an employee to an inactive company.",
        )

    if get_employee_by_email(db, data.company_id, data.email):
        raise _employee_error(
            "EMPLOYEE_ALREADY_EXISTS",
            "An employee with this email already exists in this company.",
        )

    _check_employee_code_available(db, data.company_id, data.employee_code, None)

    _validate_user_link(db, data.company_id, data.user_id)
    _validate_manager_assignment(db, data.company_id, None, data.manager_id)
    applications = _validate_application_ids(db, data.application_ids)

    # Role inheritance from Company defaults: only kicks in when the caller
    # didn't explicitly ask for something. config_defaults can hold
    # {"default_job_role": "...", "default_department": "..."}.
    defaults = _company_defaults(company)
    job_role = data.job_role or defaults.get("default_job_role") or "Employee"
    department = data.department if data.department is not None else defaults.get("default_department")

    employee = Employee(
        company_id=data.company_id,
        user_id=data.user_id,
        first_name=data.first_name,
        last_name=data.last_name,
        email=data.email,
        employee_code=data.employee_code,
        designation=data.designation,
        phone_number=data.phone_number,
        address=data.address,
        linkedin_url=data.linkedin_url,
        job_role=job_role,
        department=department,
        cost_center=data.cost_center,
        manager_id=data.manager_id,
        status="onboarded",
        applications=applications,
        bank_account_number=data.bank_account_number,
        bank_ifsc=data.bank_ifsc,
        pan_number=data.pan_number,
        aadhaar_number=data.aadhaar_number,
        residence_proof_reference=data.residence_proof_reference,
        photo_reference=data.photo_reference,
    )
    employee = create_employee(db, employee)
    record_audit_event(
        db, actor_id, "create", "employee", employee.id, old_value=None, new_value=_snapshot(employee),
        company_id=employee.company_id,
    )
    return employee


def get_employee(db: Session, employee_id: int) -> Employee:
    """Unscoped existence lookup for internal use only — see get_company's
    docstring for the same reasoning. Routes must use
    get_employee_for_user instead."""
    employee = get_employee_by_id(db, employee_id)
    if not employee:
        raise _employee_not_found()
    return employee


def get_employee_for_user(db: Session, employee_id: int, current_user: User) -> Employee:
    """Company-scoped lookup for the `/employees/{id}` routes. Admin is
    exempt (global role); everyone else may only reach an employee in their
    own company — any other id, existing or not, comes back as
    EMPLOYEE_NOT_FOUND (avoids leaking that a different company's employee
    id exists)."""
    employee = get_employee(db, employee_id)
    enforce_company_scope(
        db, current_user, employee.company_id, _employee_not_found(), "employee", employee.id
    )
    return employee


def get_employee_by_company_email(
    db: Session, company_id: int, email: str, current_user: User
) -> Employee:
    """Doc: "Read Employee by email" — email is only unique per Company, so
    the lookup needs both, same as get_employee_by_email() in the repository.
    """
    enforce_company_scope(db, current_user, company_id, _employee_not_found(), "employee", None)
    employee = get_employee_by_email(db, company_id, email)
    if not employee:
        raise _employee_not_found()
    return employee


def list_company_employees(
    db: Session,
    company_id: int | None,
    limit: int,
    offset: int,
    include_exited: bool,
    current_user: User,
    search: str | None = None,
    department: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> dict:
    if company_id is not None:
        # Existing, single-company behavior — unchanged. Ensures the
        # company is real before listing its employees, and enforces the
        # same company-isolation check every other scoped lookup uses.
        company = get_company(db, company_id)
        enforce_company_scope(db, current_user, company.id, _company_not_found(), "employee", None)

        items = list_employees_by_company(
            db,
            company_id,
            limit=limit,
            offset=offset,
            include_exited=include_exited,
            search=search,
            department=department,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total = count_employees_by_company(
            db, company_id, include_exited=include_exited, search=search, department=department
        )
        return paginated(items, total, limit, offset)

    # No company_id given — "all companies" view (Employees page default,
    # matching the "don't hide things behind a filter by default" pattern
    # already used for Companies/Departments/Job Roles/Assets/Suppliers).
    if current_user.role != Role.ADMIN:
        # Employee is PII-bearing, company-scoped data — a non-admin never
        # gets a cross-company view no matter what they ask for. Silently
        # fall back to their own company (same result as if they'd passed
        # their own company_id explicitly) rather than erroring, since
        # this is the page's own default state, not a malformed request.
        if current_user.company_id is None:
            return paginated([], 0, limit, offset)
        items = list_employees_by_company(
            db,
            current_user.company_id,
            limit=limit,
            offset=offset,
            include_exited=include_exited,
            search=search,
            department=department,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        total = count_employees_by_company(
            db, current_user.company_id, include_exited=include_exited, search=search, department=department
        )
        return paginated(items, total, limit, offset)

    # Admin, no company filter — genuinely every employee across every
    # company at once.
    items = list_all_employees(
        db,
        limit=limit,
        offset=offset,
        include_exited=include_exited,
        search=search,
        department=department,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total = count_all_employees(db, include_exited=include_exited, search=search, department=department)
    return paginated(items, total, limit, offset)


def update_employee_record(
    db: Session,
    employee_id: int,
    data: EmployeeUpdateRequest,
    current_user: User,
) -> Employee:
    actor_id = current_user.id
    employee = get_employee_for_user(db, employee_id, current_user)
    old_snapshot = _snapshot(employee)
    fields = data.model_fields_set

    # Moving an employee to a different company — a corrective fix for the
    # wrong company picked at creation, not a general HR transfer
    # workflow. Restricted to Admin: a company-scoped Operator could
    # otherwise write an employee into a company they have no other access
    # to (get_employee_for_user above only checked the employee's CURRENT
    # company, not the destination).
    target_company_id = employee.company_id
    company_changed = "company_id" in fields and data.company_id is not None and data.company_id != employee.company_id
    if company_changed:
        if current_user.role != Role.ADMIN:
            raise _employee_error(
                "EMPLOYEE_COMPANY_CHANGE_FORBIDDEN",
                "Only an admin can move an employee to a different company.",
                status_code=403,
            )
        new_company = get_company(db, data.company_id)
        if not new_company:
            raise _company_not_found()
        # Same rule create_employee_record applies to a brand-new employee
        # — an inactive company can't gain employees, whether by creation
        # or by being moved into.
        if not new_company.is_active:
            raise _employee_error(
                "EMPLOYEE_COMPANY_INACTIVE",
                "Cannot move an employee to an inactive company.",
            )
        target_company_id = data.company_id

    # first_name/last_name/email/job_role are NOT NULL — "provided" always
    # means "set to this value", so these keep the plain not-None check.
    # Email uniqueness is per-company (see Employee.__table_args__), so a
    # company change alone can collide even when the email itself isn't
    # changing — checked against target_company_id (the new company when
    # one was given) either way.
    final_email = data.email if data.email is not None else employee.email
    if (data.email is not None and data.email != employee.email) or company_changed:
        if get_employee_by_email(db, target_company_id, final_email):
            raise _employee_error(
                "EMPLOYEE_ALREADY_EXISTS",
                "An employee with this email already exists in this company.",
            )
    if data.email is not None:
        employee.email = data.email

    # employee_code is nullable, unlike email above, so it uses the same
    # model_fields_set pattern as department/cost_center further down
    # (explicit null clears it) rather than a plain not-None check — but
    # still needs the same per-company uniqueness guard email gets, so it's
    # handled here rather than in that generic nullable-fields block.
    final_employee_code = data.employee_code if "employee_code" in fields else employee.employee_code
    if (("employee_code" in fields and data.employee_code != employee.employee_code) or company_changed) and final_employee_code:
        _check_employee_code_available(db, target_company_id, final_employee_code, employee.id)
    if "employee_code" in fields:
        employee.employee_code = data.employee_code

    if data.first_name is not None:
        employee.first_name = data.first_name
    if data.last_name is not None:
        employee.last_name = data.last_name
    if data.job_role is not None:
        employee.job_role = data.job_role
    if "designation" in fields:
        employee.designation = data.designation
    if "phone_number" in fields:
        employee.phone_number = data.phone_number
    if "linkedin_url" in fields:
        employee.linkedin_url = data.linkedin_url
    if "address" in fields:
        employee.address = data.address

    if company_changed:
        # A manager must belong to the same company as their report
        # (_validate_manager_assignment) — one carried over from the old
        # company is no longer valid, so it's cleared here rather than
        # left pointing at someone in a different company. An explicit
        # manager_id sent in this same request (handled below, against
        # the now-updated employee.company_id) overrides this.
        employee.manager_id = None
        # Same reasoning for a linked login account — _validate_user_link
        # requires the user and employee to share a company.
        employee.user_id = None
        employee.company_id = target_company_id

    # Everything below is nullable — distinguish "omitted" from "explicitly
    # sent as null" via model_fields_set, so a client can actually clear
    # department/cost_center/PII fields once set, rather than every null
    # in the payload being silently ignored.
    if "department" in fields:
        employee.department = data.department
    if "cost_center" in fields:
        employee.cost_center = data.cost_center
    if "manager_id" in fields:
        _validate_manager_assignment(db, employee.company_id, employee.id, data.manager_id)
        employee.manager_id = data.manager_id
    if "application_ids" in fields:
        # None (omitted) never reaches here — "application_ids" only lands
        # in model_fields_set when the caller actually sent the key, so an
        # explicit [] correctly clears all access rather than being
        # indistinguishable from "didn't mention it".
        employee.applications = _validate_application_ids(db, data.application_ids or [])
    if "bank_account_number" in fields:
        employee.bank_account_number = data.bank_account_number
    if "bank_ifsc" in fields:
        employee.bank_ifsc = data.bank_ifsc
    if "pan_number" in fields:
        employee.pan_number = data.pan_number
    if "aadhaar_number" in fields:
        employee.aadhaar_number = data.aadhaar_number
    if "residence_proof_reference" in fields:
        employee.residence_proof_reference = data.residence_proof_reference
    if "photo_reference" in fields:
        employee.photo_reference = data.photo_reference

    db.commit()
    db.refresh(employee)
    record_audit_event(
        db,
        actor_id,
        "update",
        "employee",
        employee.id,
        old_value=old_snapshot,
        new_value=_snapshot(employee),
        company_id=employee.company_id,
    )
    return employee


def update_employee_status(
    db: Session, employee_id: int, new_status: str, current_user: User
) -> Employee:
    actor_id = current_user.id
    employee = get_employee_for_user(db, employee_id, current_user)
    old_status = employee.status

    if not is_valid_transition(employee.status, new_status):
        raise _employee_error(
            "EMPLOYEE_INVALID_STATUS_TRANSITION",
            f"Cannot move employee from '{employee.status}' to '{new_status}'.",
        )

    employee.status = new_status

    # Cascade rule: exiting an employee revokes their system login too —
    # someone who has left shouldn't keep an active account. This is a
    # deliberate cascade (soft-delete on Employee -> soft-disable on User),
    # not a hard delete of the User row.
    if new_status == "exited" and employee.user_id is not None:
        linked_user = db.query(User).filter(User.id == employee.user_id).first()
        if linked_user and linked_user.is_active:
            linked_user.is_active = False

    db.commit()
    db.refresh(employee)
    record_audit_event(
        db,
        actor_id,
        "status_transition",
        "employee",
        employee.id,
        old_value={"status": old_status},
        new_value={"status": employee.status},
        company_id=employee.company_id,
    )
    return employee


def link_employee_to_user(
    db: Session, employee_id: int, user_id: int, current_user: User
) -> Employee:
    actor_id = current_user.id
    employee = get_employee_for_user(db, employee_id, current_user)
    old_user_id = employee.user_id
    _validate_user_link(db, employee.company_id, user_id)
    employee.user_id = user_id
    db.commit()
    db.refresh(employee)
    record_audit_event(
        db,
        actor_id,
        "link_user",
        "employee",
        employee.id,
        old_value={"user_id": old_user_id},
        new_value={"user_id": employee.user_id},
        company_id=employee.company_id,
    )
    return employee


def soft_delete_employee(db: Session, employee_id: int, current_user: User) -> Employee:
    employee = get_employee_for_user(db, employee_id, current_user)
    if employee.status == "exited":
        return employee
    # Route "delete" through the same status-transition path so the
    # exit -> deactivate-linked-user cascade always applies, regardless of
    # whether the caller used the status endpoint or the delete endpoint.
    # This also means the audit trail records it as a "status_transition"
    # to "exited", not a separate "delete" action — one event, one entry.
    return update_employee_status(db, employee_id, "exited", current_user)
