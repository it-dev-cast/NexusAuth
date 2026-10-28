from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session

from app.models.employee import Employee
from app.core.list_query import apply_list_filters, list_order


def get_employee_by_id(db: Session, employee_id: int) -> Employee | None:
    return db.query(Employee).filter(Employee.id == employee_id).first()


def get_employee_by_email(db: Session, company_id: int, email: str) -> Employee | None:
    return (
        db.query(Employee)
        .filter(Employee.company_id == company_id, Employee.email == email)
        .first()
    )


def get_employee_by_employee_code(
    db: Session, company_id: int, employee_code: str
) -> Employee | None:
    return (
        db.query(Employee)
        .filter(Employee.company_id == company_id, Employee.employee_code == employee_code)
        .first()
    )


def get_employee_by_user_id(db: Session, user_id: int) -> Employee | None:
    return db.query(Employee).filter(Employee.user_id == user_id).first()


def create_employee(db: Session, employee: Employee) -> Employee:
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def employee_search_clause(search: str):
    """Partial, case-insensitive match on name, email, employee_code, or
    designation (Module 9: Filtering & Sorting) - all plain String columns,
    not EncryptedString, so ILIKE works directly at the DB layer. The concat
    covers a "first last" combined search (e.g. something typed from the
    Employees table's own name column); first_name/last_name individually
    still catch a single-token search that concat alone would miss whenever
    it doesn't happen to land on the space boundary. Public because the
    application-access search reuses exactly this rule."""
    like = f"%{search}%"
    full_name = Employee.first_name + literal(" ") + Employee.last_name
    return or_(
        Employee.first_name.ilike(like),
        Employee.last_name.ilike(like),
        full_name.ilike(like),
        Employee.email.ilike(like),
        Employee.employee_code.ilike(like),
        Employee.designation.ilike(like),
    )


def _filtered(query, include_exited: bool, search: str | None, department: str | None = None):
    if not include_exited:
        query = query.filter(Employee.status != "exited")
    if search:
        query = query.filter(employee_search_clause(search))
    if department:
        # Exact match, not ILIKE - this is meant to back the Departments
        # page's "view employees in this department" drill-down, matching
        # a specific master-list name rather than free-text search.
        query = query.filter(Employee.department == department)
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, Employee)


def list_employees_by_company(
    db: Session,
    company_id: int,
    limit: int = 20,
    offset: int = 0,
    include_exited: bool = False,
    search: str | None = None,
    department: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> list[Employee]:
    query = _filtered(
        db.query(Employee).filter(Employee.company_id == company_id), include_exited, search, department
    )
    column = Employee.created_at if sort_by == "created_at" else Employee.id
    # Newest first by default — see the matching comment in
    # company_repository.py. Still fully overridable via sort_dir.
    order = column.asc() if sort_dir == "asc" else column.desc()
    return query.order_by(*list_order(Employee, order)).limit(limit).offset(offset).all()


def list_all_employees(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_exited: bool = False,
    search: str | None = None,
    department: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> list[Employee]:
    """Same as list_employees_by_company but across every company —
    admin-only "all companies" view (see employee_service.
    list_company_employees). Not company-scoped at all, so callers must
    have already established the caller is allowed to see this."""
    query = _filtered(db.query(Employee), include_exited, search, department)
    column = Employee.created_at if sort_by == "created_at" else Employee.id
    order = column.asc() if sort_dir == "asc" else column.desc()
    return query.order_by(*list_order(Employee, order)).limit(limit).offset(offset).all()


def count_all_employees(
    db: Session,
    include_exited: bool = False,
    search: str | None = None,
    department: str | None = None,
) -> int:
    query = _filtered(db.query(func.count(Employee.id)), include_exited, search, department)
    return query.scalar() or 0


def get_company_manager_map(db: Session, company_id: int) -> dict[int, int | None]:
    """Every (employee_id -> manager_id) pair for a company, unpaginated and
    including exited employees — used only for cycle detection
    (app.core.graph_utils.creates_cycle), which needs the complete graph,
    not a page of it. Never returned to a client directly."""
    rows = (
        db.query(Employee.id, Employee.manager_id)
        .filter(Employee.company_id == company_id)
        .all()
    )
    return {employee_id: manager_id for employee_id, manager_id in rows}


def count_employees_by_company(
    db: Session,
    company_id: int,
    include_exited: bool = False,
    search: str | None = None,
    department: str | None = None,
) -> int:
    query = _filtered(
        db.query(func.count(Employee.id)).filter(Employee.company_id == company_id),
        include_exited,
        search,
        department,
    )
    return query.scalar() or 0


def count_employees_by_department(db: Session) -> dict[str, int]:
    """Current headcount per department name, across every company (the
    Department master list is global — see app/models/department.py) and
    excluding exited employees, matching the "current headcount" the
    Departments list wants to show. Employee.department is a plain string,
    not a foreign key to Department, so this is a name match, not a join."""
    rows = (
        db.query(Employee.department, func.count(Employee.id))
        .filter(Employee.status != "exited", Employee.department.isnot(None))
        .group_by(Employee.department)
        .all()
    )
    return {department: count for department, count in rows}


def count_employees_by_job_role(db: Session) -> dict[str, int]:
    """Same as count_employees_by_department, but for JobRole — see that
    function's docstring.

    The Job Roles master fills the Employee form's Job role dropdown, which
    saves into both `designation` and `job_role`, so an employee counts toward
    a role when either field carries its name — once, even if both do.
    """
    by_job_role = db.query(Employee.id.label("employee_id"), Employee.job_role.label("name")).filter(
        Employee.status != "exited"
    )
    by_designation = db.query(Employee.id.label("employee_id"), Employee.designation.label("name")).filter(
        Employee.status != "exited", Employee.designation.isnot(None)
    )
    matched = by_job_role.union(by_designation).subquery()
    rows = db.query(matched.c.name, func.count(matched.c.employee_id)).group_by(matched.c.name).all()
    return {name: count for name, count in rows}
