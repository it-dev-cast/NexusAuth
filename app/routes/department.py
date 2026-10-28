from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.core.list_query import LIST_QUERY_HELP, list_query
from app.models.department import Department
from app.models.user import User
from app.schemas.department import DepartmentCreateRequest, DepartmentResponse, DepartmentUpdateRequest
from app.services.department_service import (
    create_department_record,
    deactivate_department,
    get_department,
    list_department_records,
    reactivate_department,
    update_department_record,
)


router = APIRouter(
    prefix="/api/v1/departments",
    tags=["Departments"],
)

# Who can do what to a Department lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("department", "read"))
require_writer = require_roles(*allowed_roles("department", "write"))
require_deleter = require_roles(*allowed_roles("department", "delete"))


@router.get("", dependencies=[Depends(list_query(Department))], description=LIST_QUERY_HELP)
def list_departments_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None),
    parent_department_id: int | None = Query(
        default=None, description="Only return direct children of this department."
    ),
    top_level_only: bool = Query(
        default=False, description="Only return departments with no parent. Wins over parent_department_id."
    ),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_department_records(
        db,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
        search=search,
        parent_department_id=parent_department_id,
        top_level_only=top_level_only,
    )
    result["items"] = [
        DepartmentResponse.model_validate(department).model_dump() for department in result["items"]
    ]
    return api_ok(result)


@router.get("/{department_id}")
def get_department_endpoint(
    department_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    department = get_department(db, department_id)
    return api_ok(DepartmentResponse.model_validate(department).model_dump())


@router.post("", status_code=201)
def create_department_endpoint(
    data: DepartmentCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    department = create_department_record(db, data, current_user.id)
    return api_ok(DepartmentResponse.model_validate(department).model_dump())


@router.put("/{department_id}")
def update_department_endpoint(
    department_id: int,
    data: DepartmentUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    department = update_department_record(db, department_id, data, current_user.id)
    return api_ok(DepartmentResponse.model_validate(department).model_dump())


@router.delete("/{department_id}")
def delete_department_endpoint(
    department_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    department = deactivate_department(db, department_id, current_user.id)
    return api_ok(DepartmentResponse.model_validate(department).model_dump())


@router.patch("/{department_id}/reactivate")
def reactivate_department_endpoint(
    department_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    department = reactivate_department(db, department_id, current_user.id)
    return api_ok(DepartmentResponse.model_validate(department).model_dump())
