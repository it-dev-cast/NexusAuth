from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.orm import Session

from app.models.application import Application, employee_applications
from app.models.employee import Employee
from app.models.user import User
from app.repositories.employee_repository import employee_search_clause


def get_application_by_id(db: Session, application_id: int) -> Application | None:
    return db.query(Application).filter(Application.id == application_id).first()


def get_application_by_name(db: Session, name: str) -> Application | None:
    return db.query(Application).filter(Application.name == name).first()


def get_application_by_code(db: Session, code: str) -> Application | None:
    return db.query(Application).filter(Application.code == code).first()


def get_applications_by_ids(db: Session, application_ids: list[int]) -> list[Application]:
    if not application_ids:
        return []
    return db.query(Application).filter(Application.id.in_(application_ids)).all()


def create_application(db: Session, application: Application) -> Application:
    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def _filtered(
    query,
    include_inactive: bool,
    search: str | None,
    status: str | None = None,
    category: str | None = None,
):
    # An explicit status filter wins over include_inactive (which stays for
    # the callers that only ever wanted "active, or everything").
    if status == "active":
        query = query.filter(Application.is_active == True)  # noqa: E712
    elif status == "inactive":
        query = query.filter(Application.is_active == False)  # noqa: E712
    elif status != "all" and not include_inactive:
        query = query.filter(Application.is_active == True)  # noqa: E712
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Application.name.ilike(like), Application.code.ilike(like)))
    if category:
        query = query.filter(func.lower(Application.category) == category.lower())
    return query


def list_applications(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> list[Application]:
    query = _filtered(db.query(Application), include_inactive, search, status, category)
    return query.order_by(Application.name.asc()).limit(limit).offset(offset).all()


def count_applications(
    db: Session,
    include_inactive: bool = False,
    search: str | None = None,
    status: str | None = None,
    category: str | None = None,
) -> int:
    query = _filtered(db.query(func.count(Application.id)), include_inactive, search, status, category)
    return query.scalar() or 0


def list_application_categories(db: Session) -> list[str]:
    rows = (
        db.query(Application.category)
        .filter(Application.category.isnot(None))
        .distinct()
        .order_by(Application.category.asc())
        .all()
    )
    return [category for (category,) in rows]


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


# ---- access grants (the employee_applications rows) ----


def list_application_access(
    db: Session, application_id: int, search: str | None, limit: int, offset: int
) -> list[tuple[Employee, object, str | None]]:
    """(employee, granted_at, granted_by email) for everyone holding the
    application, searchable with the same rule the Employees page uses."""
    query = (
        db.query(Employee, employee_applications.c.granted_at, User.email)
        .join(employee_applications, employee_applications.c.employee_id == Employee.id)
        .outerjoin(User, User.id == employee_applications.c.granted_by_user_id)
        .filter(employee_applications.c.application_id == application_id)
    )
    if search:
        query = query.filter(employee_search_clause(search))
    return (
        query.order_by(Employee.first_name.asc(), Employee.last_name.asc(), Employee.id.asc())
        .limit(limit)
        .offset(offset)
        .all()
    )


def count_application_access(db: Session, application_id: int, search: str | None) -> int:
    query = (
        db.query(func.count(Employee.id))
        .join(employee_applications, employee_applications.c.employee_id == Employee.id)
        .filter(employee_applications.c.application_id == application_id)
    )
    if search:
        query = query.filter(employee_search_clause(search))
    return query.scalar() or 0


def list_access_candidates(db: Session, application_id: int, search: str | None, limit: int) -> list[Employee]:
    """Employees who could be given this application: not exited, and not
    already holding it."""
    already = select(employee_applications.c.employee_id).where(
        employee_applications.c.application_id == application_id
    )
    query = db.query(Employee).filter(Employee.status != "exited", Employee.id.notin_(already))
    if search:
        query = query.filter(employee_search_clause(search))
    return query.order_by(Employee.first_name.asc(), Employee.last_name.asc(), Employee.id.asc()).limit(limit).all()


def get_assigned_employee_ids(db: Session, application_id: int, employee_ids: list[int]) -> set[int]:
    if not employee_ids:
        return set()
    rows = db.execute(
        select(employee_applications.c.employee_id).where(
            employee_applications.c.application_id == application_id,
            employee_applications.c.employee_id.in_(employee_ids),
        )
    ).all()
    return {employee_id for (employee_id,) in rows}


def add_application_access(db: Session, application_id: int, employee_ids: list[int], granted_by: int | None) -> None:
    if not employee_ids:
        return
    db.execute(
        insert(employee_applications),
        [
            {"employee_id": employee_id, "application_id": application_id, "granted_by_user_id": granted_by}
            for employee_id in employee_ids
        ],
    )
    db.commit()


def get_access_granted_at(db: Session, application_id: int, employee_id: int):
    """(exists, granted_at) for one grant."""
    row = db.execute(
        select(employee_applications.c.granted_at).where(
            employee_applications.c.application_id == application_id,
            employee_applications.c.employee_id == employee_id,
        )
    ).first()
    return (row is not None, row[0] if row else None)


def remove_application_access(db: Session, application_id: int, employee_id: int) -> int:
    result = db.execute(
        delete(employee_applications).where(
            employee_applications.c.application_id == application_id,
            employee_applications.c.employee_id == employee_id,
        )
    )
    db.commit()
    return result.rowcount or 0


def list_employee_access(db: Session, employee_id: int) -> list[tuple[Application, object]]:
    return (
        db.query(Application, employee_applications.c.granted_at)
        .join(employee_applications, employee_applications.c.application_id == Application.id)
        .filter(employee_applications.c.employee_id == employee_id)
        .order_by(Application.name.asc())
        .all()
    )
