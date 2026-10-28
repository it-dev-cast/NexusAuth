from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.core.list_query import apply_list_filters, list_order


def get_supplier_by_id(db: Session, supplier_id: int) -> Supplier | None:
    return db.query(Supplier).filter(Supplier.id == supplier_id).first()


def get_supplier_by_name(db: Session, name: str) -> Supplier | None:
    return db.query(Supplier).filter(Supplier.name == name).first()


def create_supplier(db: Session, supplier: Supplier) -> Supplier:
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def _filtered(query, status: str | None, category: str | None, search: str | None):
    if status is not None:
        query = query.filter(Supplier.status == status)
    if category is not None:
        query = query.filter(Supplier.category == category)
    if search:
        # Partial, case-insensitive match on name (Module 9: Filtering & Sorting).
        query = query.filter(Supplier.name.ilike(f"%{search}%"))
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, Supplier)


def list_suppliers(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> list[Supplier]:
    query = _filtered(db.query(Supplier), status, category, search)
    column = Supplier.created_at if sort_by == "created_at" else Supplier.id
    # Newest first by default — see the matching comment in
    # company_repository.py. Still fully overridable via sort_dir.
    order = column.asc() if sort_dir == "asc" else column.desc()
    return query.order_by(*list_order(Supplier, order)).limit(limit).offset(offset).all()


def count_suppliers(
    db: Session,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> int:
    query = _filtered(db.query(func.count(Supplier.id)), status, category, search)
    return query.scalar() or 0
