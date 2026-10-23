from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.employee import (
    EmployeeCreateRequest,
    EmployeeLinkUserRequest,
    EmployeeResponse,
    EmployeeStatusUpdateRequest,
    EmployeeUpdateRequest,
)
from app.services.employee_service import (
    create_employee_record,
    get_employee_by_company_email,
    get_employee_for_user,
    link_employee_to_user,
    list_company_employees,
    soft_delete_employee,
    update_employee_record,
    update_employee_status,
)


router = APIRouter(
    prefix="/api/v1/employees",
    tags=["Employees"],
)

# Who can do what to an Employee lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("employee", "read"))
require_writer = require_roles(*allowed_roles("employee", "write"))
require_deleter = require_roles(*allowed_roles("employee", "delete"))
require_linker = require_roles(*allowed_roles("employee", "link_user"))


@router.get("")
def list_employees_endpoint(
    # Optional: omitting it means "every company" for an admin (see
    # employee_service.list_company_employees), or "my own company" for
    # anyone else — the Employees page's own default before a company is
    # explicitly picked.
    company_id: int | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_exited: bool = Query(default=False),
    # Partial, case-insensitive match on name or email (Module 9: Filtering
    # & Sorting) — see the matching comment in app/routes/supplier.py.
    search: str | None = Query(default=None),
    # Exact match on the Department master list's name — backs the
    # Departments page's "view employees in this department" drill-down.
    department: str | None = Query(default=None),
    sort_by: str = Query(default="id", pattern="^(id|created_at)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_company_employees(
        db,
        company_id,
        limit=limit,
        offset=offset,
        include_exited=include_exited,
        current_user=current_user,
        search=search,
        department=department,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    result["items"] = [
        EmployeeResponse.model_validate(employee).model_dump() for employee in result["items"]
    ]
    return api_ok(result)


@router.get("/by-email")
def get_employee_by_email_endpoint(
    company_id: int = Query(...),
    email: str = Query(...),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    # Declared before /{employee_id} — otherwise "by-email" would be parsed
    # as an employee_id and 422 before ever reaching this route.
    employee = get_employee_by_company_email(db, company_id, email, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.get("/{employee_id}")
def get_employee_endpoint(
    employee_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    employee = get_employee_for_user(db, employee_id, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.post("", status_code=201)
def create_employee_endpoint(
    data: EmployeeCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    employee = create_employee_record(db, data, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.put("/{employee_id}")
def update_employee_endpoint(
    employee_id: int,
    data: EmployeeUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    employee = update_employee_record(db, employee_id, data, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.patch("/{employee_id}/status")
def update_employee_status_endpoint(
    employee_id: int,
    data: EmployeeStatusUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    employee = update_employee_status(db, employee_id, data.status, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.patch("/{employee_id}/link-user")
def link_employee_user_endpoint(
    employee_id: int,
    data: EmployeeLinkUserRequest,
    current_user: User = Depends(require_linker),
    db: Session = Depends(get_db),
):
    employee = link_employee_to_user(db, employee_id, data.user_id, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())


@router.delete("/{employee_id}")
def delete_employee_endpoint(
    employee_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    employee = soft_delete_employee(db, employee_id, current_user)
    return api_ok(EmployeeResponse.model_validate(employee).model_dump())
