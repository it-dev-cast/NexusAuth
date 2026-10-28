from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.job_role import JobRole
from app.core.list_query import apply_list_filters, list_order


def get_job_role_by_id(db: Session, job_role_id: int) -> JobRole | None:
    return db.query(JobRole).filter(JobRole.id == job_role_id).first()


def get_job_role_by_name(db: Session, name: str) -> JobRole | None:
    # Case-insensitive: "ceo" and "CEO" are the same role, so the duplicate
    # checks in job_role_service refuse both (the unique index on `name` alone
    # would let a differently-cased copy through).
    return db.query(JobRole).filter(func.lower(JobRole.name) == name.lower()).first()


def create_job_role(db: Session, job_role: JobRole) -> JobRole:
    db.add(job_role)
    db.commit()
    db.refresh(job_role)
    return job_role


def _filtered(query, include_inactive: bool, search: str | None):
    if not include_inactive:
        query = query.filter(JobRole.is_active == True)  # noqa: E712
    if search:
        query = query.filter(JobRole.name.ilike(f"%{search}%"))
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, JobRole)


def list_job_roles(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
) -> list[JobRole]:
    query = _filtered(db.query(JobRole), include_inactive, search)
    return query.order_by(*list_order(JobRole, JobRole.name.asc())).limit(limit).offset(offset).all()


def count_job_roles(db: Session, include_inactive: bool = False, search: str | None = None) -> int:
    query = _filtered(db.query(func.count(JobRole.id)), include_inactive, search)
    return query.scalar() or 0


def soft_delete_job_role(db: Session, job_role: JobRole) -> JobRole:
    job_role.is_active = False
    db.commit()
    db.refresh(job_role)
    return job_role
