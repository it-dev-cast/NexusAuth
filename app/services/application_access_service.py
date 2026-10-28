"""Who has access to which application.

An access grant is a row in employee_applications: "this employee is meant to
use this application". It records the decision only — nothing here signs the
employee in to, or creates an account in, the application itself.

Rules enforced here (the routes only decide *who may call*, see
app/core/permissions.py "application_access"):
  * grants are made to existing, non-exited employees only, and only for an
    active application (inactive -> 409 APPLICATION_INACTIVE);
  * one row per (employee, application): re-granting is reported as
    "already_assigned", never duplicated (the table's primary key backs this);
  * every employee lookup goes through get_employee_for_user, so company
    scoping is the same as on the Employees page;
  * revoking is allowed on inactive applications too (clean-up), and is the
    only thing that removes a grant — deactivating an application never does;
  * each grant and each revoke is its own audit event (grant_access /
    revoke_access on the application), which is the history of who had access
    when, since a revoked grant no longer has a row.
"""
from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.employee import Employee
from app.models.user import User
from app.repositories import (
    add_application_access,
    count_application_access,
    get_access_granted_at,
    get_assigned_employee_ids,
    list_access_candidates,
    list_application_access,
    list_employee_access,
    remove_application_access,
)
from app.schemas.application import ApplicationAccessEmployee, EmployeeApplicationAccess
from app.services.application_service import get_application
from app.services.audit_service import record_audit_event
from app.services.employee_service import get_employee_for_user


def _error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _access_row(employee: Employee, granted_at, granted_by: str | None) -> dict:
    return ApplicationAccessEmployee(
        employee_id=employee.id,
        employee_code=employee.employee_code,
        full_name=employee.full_name,
        email=employee.email,
        company_id=employee.company_id,
        status=employee.status,
        granted_at=granted_at,
        granted_by=granted_by,
    ).model_dump(mode="json")


def list_access_for_application(
    db: Session, application_id: int, search: str | None, limit: int, offset: int
) -> dict:
    get_application(db, application_id)  # 404 for an unknown application
    rows = list_application_access(db, application_id, search, limit, offset)
    total = count_application_access(db, application_id, search)
    return paginated([_access_row(*row) for row in rows], total, limit, offset)


def list_candidates_for_application(
    db: Session, application_id: int, search: str | None, limit: int
) -> list[dict]:
    get_application(db, application_id)
    return [_access_row(employee, None, None) for employee in list_access_candidates(db, application_id, search, limit)]


def grant_application_access(
    db: Session, application_id: int, employee_ids: list[int], current_user: User
) -> dict:
    application = get_application(db, application_id)
    if not application.is_active:
        raise _error(
            "APPLICATION_INACTIVE",
            f"'{application.name}' is inactive, so it cannot be given to anyone. Reactivate it first.",
            status_code=409,
        )

    # get_employee_for_user: 404 for an unknown id and for an employee in a
    # company the caller may not reach.
    employees = [get_employee_for_user(db, employee_id, current_user) for employee_id in employee_ids]
    exited = [e for e in employees if e.status == "exited"]
    if exited:
        raise _error(
            "EMPLOYEE_EXITED",
            "Access cannot be given to an exited employee: "
            + ", ".join(f"#{e.id}" for e in exited)
            + ".",
            status_code=409,
        )

    already = get_assigned_employee_ids(db, application_id, [e.id for e in employees])
    new_employees = [e for e in employees if e.id not in already]
    add_application_access(db, application_id, [e.id for e in new_employees], current_user.id)

    for employee in new_employees:
        record_audit_event(
            db,
            current_user.id,
            "grant_access",
            "application",
            application.id,
            old_value=None,
            new_value={
                "application_id": application.id,
                "application_code": application.code,
                "employee_id": employee.id,
                "employee_code": employee.employee_code,
            },
            company_id=employee.company_id,
        )
    return {
        "application_id": application.id,
        "granted": [e.id for e in new_employees],
        "already_assigned": [e.id for e in employees if e.id in already],
    }


def revoke_application_access(
    db: Session, application_id: int, employee_id: int, current_user: User
) -> dict:
    application = get_application(db, application_id)
    employee = get_employee_for_user(db, employee_id, current_user)
    held, granted_at = get_access_granted_at(db, application_id, employee.id)
    if not held:
        raise _error(
            "APPLICATION_ACCESS_NOT_FOUND",
            "This employee does not have access to this application.",
            status_code=404,
        )
    remove_application_access(db, application_id, employee.id)
    record_audit_event(
        db,
        current_user.id,
        "revoke_access",
        "application",
        application.id,
        old_value={
            "application_id": application.id,
            "application_code": application.code,
            "employee_id": employee.id,
            "employee_code": employee.employee_code,
            "granted_at": granted_at,
        },
        new_value=None,
        company_id=employee.company_id,
    )
    return {"application_id": application.id, "employee_id": employee.id}


def list_access_for_employee(db: Session, employee_id: int, current_user: User) -> list[dict]:
    employee = get_employee_for_user(db, employee_id, current_user)
    return [
        EmployeeApplicationAccess(
            application_id=application.id,
            name=application.name,
            code=application.code,
            category=application.category,
            is_active=application.is_active,
            granted_at=granted_at,
        ).model_dump(mode="json")
        for application, granted_at in list_employee_access(db, employee.id)
    ]
