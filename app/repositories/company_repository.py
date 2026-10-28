from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Company
from app.core.list_query import apply_list_filters, list_order


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    return db.query(Company).filter(Company.id == company_id).first()


def get_company_by_name(db: Session, name: str) -> Company | None:
    return db.query(Company).filter(Company.name == name).first()


def create_company(db: Session, company: Company) -> Company:
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def _filtered(query, include_inactive: bool, search: str | None, company_type: str | None):
    if not include_inactive:
        query = query.filter(Company.is_active == True)  # noqa: E712
    if search:
        # Partial, case-insensitive match on name — same "contains" filter
        # style as the other list endpoints (Module 9: Filtering & Sorting).
        query = query.filter(Company.name.ilike(f"%{search}%"))
    if company_type:
        query = query.filter(Company.company_type == company_type)
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, Company)


def list_companies(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
    company_type: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> list[Company]:
    query = _filtered(db.query(Company), include_inactive, search, company_type)
    column = Company.created_at if sort_by == "created_at" else Company.id
    # Newest first by default: a plain list request has no way to reach a
    # row past the 100-row page the frontend requests, so a record created
    # after the first 100 already exist would never be visible under
    # ascending order — exactly the "I just created one and don't see it"
    # bug. Still fully overridable per-request via sort_dir.
    order = column.asc() if sort_dir == "asc" else column.desc()
    return query.order_by(*list_order(Company, order)).limit(limit).offset(offset).all()


def count_companies(
    db: Session,
    include_inactive: bool = False,
    search: str | None = None,
    company_type: str | None = None,
) -> int:
    query = _filtered(db.query(func.count(Company.id)), include_inactive, search, company_type)
    return query.scalar() or 0


def soft_delete_company(db: Session, company: Company) -> Company:
    company.is_active = False
    db.commit()
    db.refresh(company)
    return company
