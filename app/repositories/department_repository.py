from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.department import Department
from app.core.list_query import apply_list_filters, list_order


def get_department_by_id(db: Session, department_id: int) -> Department | None:
    return db.query(Department).filter(Department.id == department_id).first()


def get_department_by_name(db: Session, name: str) -> Department | None:
    return db.query(Department).filter(Department.name == name).first()


def create_department(db: Session, department: Department) -> Department:
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def _filtered(
    query,
    include_inactive: bool,
    search: str | None,
    parent_department_id: int | None = None,
    top_level_only: bool = False,
):
    if not include_inactive:
        query = query.filter(Department.is_active == True)  # noqa: E712
    if search:
        query = query.filter(Department.name.ilike(f"%{search}%"))
    # top_level_only wins over parent_department_id if a caller somehow
    # passes both — "show me roots" is the more specific ask.
    if top_level_only:
        query = query.filter(Department.parent_department_id.is_(None))
    elif parent_department_id is not None:
        query = query.filter(Department.parent_department_id == parent_department_id)
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, Department)


def list_departments(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
    parent_department_id: int | None = None,
    top_level_only: bool = False,
) -> list[Department]:
    query = _filtered(db.query(Department), include_inactive, search, parent_department_id, top_level_only)
    return query.order_by(*list_order(Department, Department.name.asc())).limit(limit).offset(offset).all()


def count_departments(
    db: Session,
    include_inactive: bool = False,
    search: str | None = None,
    parent_department_id: int | None = None,
    top_level_only: bool = False,
) -> int:
    query = _filtered(
        db.query(func.count(Department.id)), include_inactive, search, parent_department_id, top_level_only
    )
    return query.scalar() or 0


def soft_delete_department(db: Session, department: Department) -> Department:
    department.is_active = False
    db.commit()
    db.refresh(department)
    return department


def get_department_parent_map(db: Session) -> dict[int, int | None]:
    """Every (department_id -> parent_department_id) pair, unpaginated and
    including inactive rows — needed for cycle detection (app.core.
    graph_utils.creates_cycle), which must see the complete graph, not one
    page of it. Mirrors employee_repository.get_company_manager_map."""
    rows = db.query(Department.id, Department.parent_department_id).all()
    return {department_id: parent_id for department_id, parent_id in rows}


def get_department_names_by_id(db: Session) -> dict[int, str]:
    """id -> name for every department, used to resolve parent_department_name
    in batch (not per-row) when serializing a list."""
    rows = db.query(Department.id, Department.name).all()
    return {department_id: name for department_id, name in rows}


def count_children_by_parent(db: Session) -> dict[int, int]:
    """parent_department_id -> number of direct children, batched the same
    way count_employees_by_department groups by name."""
    rows = (
        db.query(Department.parent_department_id, func.count(Department.id))
        .filter(Department.parent_department_id.isnot(None))
        .group_by(Department.parent_department_id)
        .all()
    )
    return {parent_id: count for parent_id, count in rows}
