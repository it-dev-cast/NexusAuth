from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.application import Application, employee_applications


def get_application_by_id(db: Session, application_id: int) -> Application | None:
    return db.query(Application).filter(Application.id == application_id).first()


def get_application_by_name(db: Session, name: str) -> Application | None:
    return db.query(Application).filter(Application.name == name).first()


def get_applications_by_ids(db: Session, application_ids: list[int]) -> list[Application]:
    if not application_ids:
        return []
    return db.query(Application).filter(Application.id.in_(application_ids)).all()


def create_application(db: Session, application: Application) -> Application:
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def _filtered(query, include_inactive: bool, search: str | None):
    if not include_inactive:
        query = query.filter(Application.is_active == True)  # noqa: E712
    if search:
        query = query.filter(Application.name.ilike(f"%{search}%"))
    return query


def list_applications(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
) -> list[Application]:
    query = _filtered(db.query(Application), include_inactive, search)
    return query.order_by(Application.name.asc()).limit(limit).offset(offset).all()


def count_applications(db: Session, include_inactive: bool = False, search: str | None = None) -> int:
    query = _filtered(db.query(func.count(Application.id)), include_inactive, search)
    return query.scalar() or 0


def soft_delete_application(db: Session, application: Application) -> Application:
    application.is_active = False
    db.commit()
    db.refresh(application)
    return application


def count_employees_by_application(db: Session) -> dict[int, int]:
    """Headcount per application, via a plain join over the association
    table — not a loaded relationship, since nothing here needs the actual
    Employee rows, just the count (same reasoning as
    employee_repository.count_employees_by_job_role's GROUP BY, applied to
    a many-to-many instead of a free-text column)."""
    rows = (
        db.query(employee_applications.c.application_id, func.count(employee_applications.c.employee_id))
        .group_by(employee_applications.c.application_id)
        .all()
    )
    return {application_id: count for application_id, count in rows}
