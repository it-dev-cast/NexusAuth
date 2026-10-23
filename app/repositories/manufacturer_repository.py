from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.manufacturer import Manufacturer


def get_manufacturer_by_id(db: Session, manufacturer_id: int) -> Manufacturer | None:
    return db.query(Manufacturer).filter(Manufacturer.id == manufacturer_id).first()


def get_manufacturer_by_name(db: Session, name: str) -> Manufacturer | None:
    return db.query(Manufacturer).filter(Manufacturer.name == name).first()


def create_manufacturer(db: Session, manufacturer: Manufacturer) -> Manufacturer:
    db.add(manufacturer)
    db.commit()
    db.refresh(manufacturer)
    return manufacturer


def _filtered(query, include_inactive: bool, search: str | None):
    if not include_inactive:
        query = query.filter(Manufacturer.is_active == True)  # noqa: E712
    if search:
        query = query.filter(Manufacturer.name.ilike(f"%{search}%"))
    return query


def list_manufacturers(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
) -> list[Manufacturer]:
    query = _filtered(db.query(Manufacturer), include_inactive, search)
    return query.order_by(Manufacturer.name.asc()).limit(limit).offset(offset).all()


def count_manufacturers(db: Session, include_inactive: bool = False, search: str | None = None) -> int:
    query = _filtered(db.query(func.count(Manufacturer.id)), include_inactive, search)
    return query.scalar() or 0


def soft_delete_manufacturer(db: Session, manufacturer: Manufacturer) -> Manufacturer:
    manufacturer.is_active = False
    db.commit()
    db.refresh(manufacturer)
    return manufacturer
