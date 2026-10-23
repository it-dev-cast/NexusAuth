from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.graph_utils import creates_cycle
from app.core.pagination import paginated
from app.models.department import Department
from app.repositories import (
    count_children_by_parent,
    count_departments,
    count_employees_by_department,
    create_department,
    get_department_by_id,
    get_department_by_name,
    get_department_names_by_id,
    get_department_parent_map,
    list_departments,
    soft_delete_department,
)
from app.schemas.department import DepartmentCreateRequest, DepartmentResponse, DepartmentUpdateRequest
from app.services.audit_service import record_audit_event


def _department_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(department: Department) -> dict:
    return DepartmentResponse.model_validate(department).model_dump(mode="json")


def _validate_parent_assignment(
    db: Session, department_id: int | None, parent_department_id: int | None
) -> None:
    """Mirrors employee_service._validate_manager_assignment for the same
    "Circular dependency detection" requirement (Module 7), applied to
    Department instead of Employee. department_id is None at create time —
    a brand-new department can't already be part of a cycle, so only
    existence is checked then."""
    if parent_department_id is None:
        return

    parent = get_department_by_id(db, parent_department_id)
    if not parent:
        raise _department_error(
            "DEPARTMENT_PARENT_NOT_FOUND", "The specified parent department was not found.", status_code=404
        )

    if department_id is not None:
        if parent_department_id == department_id:
            raise _department_error("DEPARTMENT_PARENT_CYCLE", "A department cannot be its own parent.")

        parent_of = get_department_parent_map(db)
        if creates_cycle(parent_of, department_id, parent_department_id):
            raise _department_error(
                "DEPARTMENT_PARENT_CYCLE",
                "That assignment would create a circular department hierarchy.",
            )


def _attach_derived_fields(db: Session, departments: list[Department]) -> list[Department]:
    """Batches every per-row computed field (never persisted columns) in
    one pass: headcount, live parent name, and direct-children count. Keeps
    list/get responses free of per-row queries (no N+1)."""
    if not departments:
        return departments
    employee_counts = count_employees_by_department(db)
    names_by_id = get_department_names_by_id(db)
    children_counts = count_children_by_parent(db)
    for department in departments:
        department.employee_count = employee_counts.get(department.name, 0)
        department.parent_department_name = (
            names_by_id.get(department.parent_department_id) if department.parent_department_id else None
        )
        department.children_count = children_counts.get(department.id, 0)
    return departments


def create_department_record(db: Session, data: DepartmentCreateRequest, actor_id: int | None) -> Department:
    if get_department_by_name(db, data.name):
        raise _department_error("DEPARTMENT_ALREADY_EXISTS", "A department with this name already exists.")
    _validate_parent_assignment(db, None, data.parent_department_id)

    department = create_department(
        db,
        Department(
            name=data.name,
            description=data.description,
            manager_name=data.manager_name,
            parent_department_id=data.parent_department_id,
            is_active=True,
        ),
    )
    _attach_derived_fields(db, [department])
    record_audit_event(
        db, actor_id, "create", "department", department.id, old_value=None, new_value=_snapshot(department)
    )
    return department


def get_department(db: Session, department_id: int) -> Department:
    department = get_department_by_id(db, department_id)
    if not department:
        raise _department_error("DEPARTMENT_NOT_FOUND", "Department not found.", status_code=404)
    _attach_derived_fields(db, [department])
    return department


def list_department_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    search: str | None = None,
    parent_department_id: int | None = None,
    top_level_only: bool = False,
) -> dict:
    items = list_departments(
        db,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
        search=search,
        parent_department_id=parent_department_id,
        top_level_only=top_level_only,
    )
    total = count_departments(
        db,
        include_inactive=include_inactive,
        search=search,
        parent_department_id=parent_department_id,
        top_level_only=top_level_only,
    )
    _attach_derived_fields(db, items)
    return paginated(items, total, limit, offset)


def update_department_record(
    db: Session, department_id: int, data: DepartmentUpdateRequest, actor_id: int | None
) -> Department:
    department = get_department(db, department_id)
    old_snapshot = _snapshot(department)

    if data.name is not None:
        existing = get_department_by_name(db, data.name)
        if existing and existing.id != department.id:
            raise _department_error("DEPARTMENT_ALREADY_EXISTS", "A department with this name already exists.")
        department.name = data.name

    # model_fields_set (not "is not None") — same reasoning as
    # EmployeeUpdateRequest.department/cost_center: a client must be able
    # to explicitly clear description/manager_name/parent_department_id,
    # not just set them, without every omitted field looking identical to
    # "clear this".
    fields = data.model_fields_set
    if "description" in fields:
        department.description = data.description
    if "manager_name" in fields:
        department.manager_name = data.manager_name
    if "parent_department_id" in fields:
        _validate_parent_assignment(db, department.id, data.parent_department_id)
        department.parent_department_id = data.parent_department_id

    db.commit()
    db.refresh(department)
    _attach_derived_fields(db, [department])
    record_audit_event(
        db, actor_id, "update", "department", department.id, old_value=old_snapshot, new_value=_snapshot(department)
    )
    return department


def deactivate_department(db: Session, department_id: int, actor_id: int | None) -> Department:
    department = get_department(db, department_id)
    if not department.is_active:
        return department
    old_snapshot = _snapshot(department)
    department = soft_delete_department(db, department)
    _attach_derived_fields(db, [department])
    record_audit_event(
        db, actor_id, "delete", "department", department.id, old_value=old_snapshot, new_value=_snapshot(department)
    )
    return department


def reactivate_department(db: Session, department_id: int, actor_id: int | None) -> Department:
    """Counterpart to deactivate_department — without this, a deactivated
    department was a dead end: nothing in the API could ever set
    is_active back to True (DepartmentUpdateRequest only carries `name`)."""
    department = get_department(db, department_id)
    if department.is_active:
        return department
    old_snapshot = _snapshot(department)
    department.is_active = True
    db.commit()
    db.refresh(department)
    _attach_derived_fields(db, [department])
    record_audit_event(
        db, actor_id, "update", "department", department.id, old_value=old_snapshot, new_value=_snapshot(department)
    )
    return department
