from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.asset_model import AssetModel
from app.models.department import Department
from app.models.job_role import JobRole
from app.models.manufacturer import Manufacturer
from app.models.master_item import MasterItem
from app.models.supplier import Supplier

# Which entity column stores each list's value (by name), so the page can show
# how many records use a value and refuse to rename one that is in use.
USAGE_COLUMNS = {
    "supplier_category": Supplier.category,
    "payment_terms": Supplier.terms,
    "application_category": Application.category,
}


def _escape_like(text_value: str) -> str:
    return text_value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_item_by_id(db: Session, item_id: int) -> MasterItem | None:
    return db.query(MasterItem).filter(MasterItem.id == item_id).first()


def find_item_by_name(db: Session, master_type: str, name: str, parent_id: int | None) -> MasterItem | None:
    query = db.query(MasterItem).filter(
        MasterItem.master_type == master_type,
        func.lower(MasterItem.name) == name.lower(),
    )
    query = query.filter(MasterItem.parent_id.is_(None) if parent_id is None else MasterItem.parent_id == parent_id)
    return query.first()


def find_item_by_code(db: Session, master_type: str, code: str) -> MasterItem | None:
    return (
        db.query(MasterItem)
        .filter(MasterItem.master_type == master_type, func.lower(MasterItem.code) == code.lower())
        .first()
    )


def find_active_item_by_name(db: Session, master_type: str, name: str) -> MasterItem | None:
    return (
        db.query(MasterItem)
        .filter(
            MasterItem.master_type == master_type,
            MasterItem.is_active == True,  # noqa: E712
            func.lower(MasterItem.name) == name.lower(),
        )
        .first()
    )


def create_item(db: Session, item: MasterItem) -> MasterItem:
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def _filtered(query, master_type: str, status: str, search: str | None, parent_id: int | None):
    query = query.filter(MasterItem.master_type == master_type)
    if status == "active":
        query = query.filter(MasterItem.is_active == True)  # noqa: E712
    elif status == "inactive":
        query = query.filter(MasterItem.is_active == False)  # noqa: E712
    if parent_id is not None:
        query = query.filter(MasterItem.parent_id == parent_id)
    if search:
        like = f"%{_escape_like(search.strip())}%"
        query = query.filter(
            MasterItem.name.ilike(like, escape="\\")
            | MasterItem.code.ilike(like, escape="\\")
            | MasterItem.description.ilike(like, escape="\\")
        )
    return query


_SORTS = {"name": MasterItem.name, "code": MasterItem.code, "created_at": MasterItem.created_at}


def list_items(
    db: Session,
    master_type: str,
    limit: int,
    offset: int,
    status: str = "active",
    search: str | None = None,
    parent_id: int | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
) -> list[MasterItem]:
    column = _SORTS.get(sort_by, MasterItem.name)
    order = column.desc() if sort_dir == "desc" else column.asc()
    query = _filtered(db.query(MasterItem), master_type, status, search, parent_id)
    return query.order_by(order, MasterItem.id.asc()).limit(limit).offset(offset).all()


def count_items(
    db: Session,
    master_type: str,
    status: str = "active",
    search: str | None = None,
    parent_id: int | None = None,
) -> int:
    query = _filtered(db.query(func.count(MasterItem.id)), master_type, status, search, parent_id)
    return query.scalar() or 0


def count_children(db: Session, item_id: int, active_only: bool = False) -> int:
    query = db.query(func.count(MasterItem.id)).filter(MasterItem.parent_id == item_id)
    if active_only:
        query = query.filter(MasterItem.is_active == True)  # noqa: E712
    return query.scalar() or 0


def children_counts(db: Session, item_ids: list[int]) -> dict[int, int]:
    if not item_ids:
        return {}
    rows = (
        db.query(MasterItem.parent_id, func.count(MasterItem.id))
        .filter(MasterItem.parent_id.in_(item_ids))
        .group_by(MasterItem.parent_id)
        .all()
    )
    return {parent_id: n for parent_id, n in rows}


def usage_counts(db: Session, master_type: str, names: list[str]) -> dict[str, int]:
    """How many records currently carry each name (case-insensitive). Empty
    for lists no other record references."""
    column = USAGE_COLUMNS.get(master_type)
    if column is None or not names:
        return {}
    lowered = [n.lower() for n in names]
    rows = (
        db.query(func.lower(column), func.count())
        .filter(func.lower(column).in_(lowered))
        .group_by(func.lower(column))
        .all()
    )
    found = {name: n for name, n in rows}
    return {n: found.get(n.lower(), 0) for n in names}


def list_option_items(db: Session, master_type: str, parent_id: int | None, limit: int) -> list[MasterItem]:
    query = db.query(MasterItem).filter(
        MasterItem.master_type == master_type, MasterItem.is_active == True  # noqa: E712
    )
    if parent_id is not None:
        query = query.filter(MasterItem.parent_id == parent_id)
    return query.order_by(MasterItem.name.asc(), MasterItem.id.asc()).limit(limit).all()


def get_items_by_ids(db: Session, ids: list[int]) -> dict[int, MasterItem]:
    if not ids:
        return {}
    return {i.id: i for i in db.query(MasterItem).filter(MasterItem.id.in_(ids)).all()}


def type_totals(db: Session) -> dict[str, tuple[int, int]]:
    """{master_type: (active, total)} for the catalog."""
    rows = (
        db.query(
            MasterItem.master_type,
            func.count(MasterItem.id).filter(MasterItem.is_active == True),  # noqa: E712
            func.count(MasterItem.id),
        )
        .group_by(MasterItem.master_type)
        .all()
    )
    return {t: (active, total) for t, active, total in rows}


# The masters that live in their own tables (see LINKED_MASTERS).
LINKED_MODELS = {
    "department": Department,
    "job_role": JobRole,
    "application": Application,
    "manufacturer": Manufacturer,
    "asset_model": AssetModel,
}


def linked_totals(db: Session) -> dict[str, tuple[int, int]]:
    """{linked master key: (active, total)}."""
    out = {}
    for key, model in LINKED_MODELS.items():
        active, total = db.query(
            func.count(model.id).filter(model.is_active == True),  # noqa: E712
            func.count(model.id),
        ).one()
        out[key] = (active, total)
    return out
