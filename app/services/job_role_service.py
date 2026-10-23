from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.job_role import JobRole
from app.repositories import (
    count_employees_by_job_role,
    count_job_roles,
    create_job_role,
    get_job_role_by_id,
    get_job_role_by_name,
    list_job_roles,
    soft_delete_job_role,
)
from app.schemas.job_role import JobRoleCreateRequest, JobRoleResponse, JobRoleUpdateRequest
from app.services.audit_service import record_audit_event


def _job_role_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(job_role: JobRole) -> dict:
    return JobRoleResponse.model_validate(job_role).model_dump(mode="json")


def _attach_employee_counts(db: Session, job_roles: list[JobRole]) -> list[JobRole]:
    if not job_roles:
        return job_roles
    counts = count_employees_by_job_role(db)
    for job_role in job_roles:
        job_role.employee_count = counts.get(job_role.name, 0)
    return job_roles


def create_job_role_record(db: Session, data: JobRoleCreateRequest, actor_id: int | None) -> JobRole:
    if get_job_role_by_name(db, data.name):
        raise _job_role_error("JOB_ROLE_ALREADY_EXISTS", "A job role with this name already exists.")

    job_role = create_job_role(db, JobRole(name=data.name, is_active=True))
    job_role.employee_count = 0  # brand new, nobody assigned to it yet
    record_audit_event(
        db, actor_id, "create", "job_role", job_role.id, old_value=None, new_value=_snapshot(job_role)
    )
    return job_role


def get_job_role(db: Session, job_role_id: int) -> JobRole:
    job_role = get_job_role_by_id(db, job_role_id)
    if not job_role:
        raise _job_role_error("JOB_ROLE_NOT_FOUND", "Job role not found.", status_code=404)
    _attach_employee_counts(db, [job_role])
    return job_role


def list_job_role_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    search: str | None = None,
) -> dict:
    items = list_job_roles(db, limit=limit, offset=offset, include_inactive=include_inactive, search=search)
    total = count_job_roles(db, include_inactive=include_inactive, search=search)
    _attach_employee_counts(db, items)
    return paginated(items, total, limit, offset)


def update_job_role_record(
    db: Session, job_role_id: int, data: JobRoleUpdateRequest, actor_id: int | None
) -> JobRole:
    job_role = get_job_role(db, job_role_id)
    old_snapshot = _snapshot(job_role)

    if data.name is not None:
        existing = get_job_role_by_name(db, data.name)
        if existing and existing.id != job_role.id:
            raise _job_role_error("JOB_ROLE_ALREADY_EXISTS", "A job role with this name already exists.")
        job_role.name = data.name

    db.commit()
    db.refresh(job_role)
    record_audit_event(
        db, actor_id, "update", "job_role", job_role.id, old_value=old_snapshot, new_value=_snapshot(job_role)
    )
    return job_role


def deactivate_job_role(db: Session, job_role_id: int, actor_id: int | None) -> JobRole:
    job_role = get_job_role(db, job_role_id)
    if not job_role.is_active:
        return job_role
    old_snapshot = _snapshot(job_role)
    job_role = soft_delete_job_role(db, job_role)
    record_audit_event(
        db, actor_id, "delete", "job_role", job_role.id, old_value=old_snapshot, new_value=_snapshot(job_role)
    )
    return job_role


def reactivate_job_role(db: Session, job_role_id: int, actor_id: int | None) -> JobRole:
    """Counterpart to deactivate_job_role — see
    department_service.reactivate_department's docstring for why this is
    needed (JobRoleUpdateRequest only carries `name`, no is_active)."""
    job_role = get_job_role(db, job_role_id)
    if job_role.is_active:
        return job_role
    old_snapshot = _snapshot(job_role)
    job_role.is_active = True
    db.commit()
    db.refresh(job_role)
    _attach_employee_counts(db, [job_role])
    record_audit_event(
        db, actor_id, "update", "job_role", job_role.id, old_value=old_snapshot, new_value=_snapshot(job_role)
    )
    return job_role
