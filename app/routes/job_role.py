from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.core.list_query import LIST_QUERY_HELP, list_query
from app.models.job_role import JobRole
from app.models.user import User
from app.schemas.job_role import JobRoleCreateRequest, JobRoleResponse, JobRoleUpdateRequest
from app.services.job_role_service import (
    create_job_role_record,
    deactivate_job_role,
    get_job_role,
    list_job_role_records,
    reactivate_job_role,
    update_job_role_record,
)


router = APIRouter(
    prefix="/api/v1/job-roles",
    tags=["Job Roles"],
)

# Who can do what to a JobRole lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("job_role", "read"))
require_writer = require_roles(*allowed_roles("job_role", "write"))
require_deleter = require_roles(*allowed_roles("job_role", "delete"))


@router.get("", dependencies=[Depends(list_query(JobRole))], description=LIST_QUERY_HELP)
def list_job_roles_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_job_role_records(
        db, limit=limit, offset=offset, include_inactive=include_inactive, search=search
    )
    result["items"] = [
        JobRoleResponse.model_validate(job_role).model_dump() for job_role in result["items"]
    ]
    return api_ok(result)


@router.get("/{job_role_id}")
def get_job_role_endpoint(
    job_role_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    job_role = get_job_role(db, job_role_id)
    return api_ok(JobRoleResponse.model_validate(job_role).model_dump())


@router.post("", status_code=201)
def create_job_role_endpoint(
    data: JobRoleCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    job_role = create_job_role_record(db, data, current_user.id)
    return api_ok(JobRoleResponse.model_validate(job_role).model_dump())


@router.put("/{job_role_id}")
def update_job_role_endpoint(
    job_role_id: int,
    data: JobRoleUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    job_role = update_job_role_record(db, job_role_id, data, current_user.id)
    return api_ok(JobRoleResponse.model_validate(job_role).model_dump())


@router.delete("/{job_role_id}")
def delete_job_role_endpoint(
    job_role_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    job_role = deactivate_job_role(db, job_role_id, current_user.id)
    return api_ok(JobRoleResponse.model_validate(job_role).model_dump())


@router.patch("/{job_role_id}/reactivate")
def reactivate_job_role_endpoint(
    job_role_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    job_role = reactivate_job_role(db, job_role_id, current_user.id)
    return api_ok(JobRoleResponse.model_validate(job_role).model_dump())
