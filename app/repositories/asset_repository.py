from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_tag import AssetTag


def get_asset_by_id(db: Session, asset_id: int) -> Asset | None:
    return db.query(Asset).filter(Asset.id == asset_id).first()


def get_asset_by_tag(db: Session, asset_tag: str) -> Asset | None:
    return db.query(Asset).filter(Asset.asset_tag == asset_tag).first()


def create_asset(db: Session, asset: Asset) -> Asset:
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _filtered(query, status: str | None, supplier_id: int | None, search: str | None):
    if status is not None:
        query = query.filter(Asset.status == status)
    if supplier_id is not None:
        query = query.filter(Asset.supplier_id == supplier_id)
    if search:
        # Partial, case-insensitive match across the fields a caller would
        # actually search by — asset_tag, manufacturer, model, serial_number,
        # and now Digital Twin "Tags" (§2.7's "Search Metadata" facet) —
        # matching the search param already implemented for Company/
        # Supplier/Employee (Module 9: Filtering & Sorting). The tags match
        # is a correlated EXISTS, not a JOIN, so a asset with two matching
        # tags doesn't come back as two duplicate rows.
        like = f"%{search}%"
        query = query.filter(
            or_(
                Asset.asset_tag.ilike(like),
                Asset.manufacturer.ilike(like),
                Asset.model.ilike(like),
                Asset.serial_number.ilike(like),
                Asset.id.in_(
                    select(AssetTag.asset_id).where(AssetTag.tag.ilike(like))
                ),
            )
        )
    return query


_SORTABLE_COLUMNS = {
    "id": Asset.id,
    "created_at": Asset.created_at,
}


def list_assets(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
    supplier_id: int | None = None,
    search: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "asc",
) -> list[Asset]:
    query = _filtered(db.query(Asset), status, supplier_id, search)
    column = _SORTABLE_COLUMNS.get(sort_by, Asset.id)
    order = column.desc() if sort_dir == "desc" else column.asc()
    return query.order_by(order).limit(limit).offset(offset).all()


def count_assets(
    db: Session,
    status: str | None = None,
    supplier_id: int | None = None,
    search: str | None = None,
) -> int:
    query = _filtered(db.query(func.count(Asset.id)), status, supplier_id, search)
    return query.scalar() or 0


def count_assets_by_manufacturer(db: Session) -> dict[str, int]:
    """Current in-use count per manufacturer name, excluding disposed
    assets (that module's terminal status, same idea as excluding exited
    employees in count_employees_by_department). Asset.manufacturer is a
    plain string, not a foreign key to Manufacturer, so this is a name
    match, not a join — same pattern as employee_repository's
    count_employees_by_department/job_role."""
    rows = (
        db.query(Asset.manufacturer, func.count(Asset.id))
        .filter(Asset.status != "disposed")
        .group_by(Asset.manufacturer)
        .all()
    )
    return {manufacturer: count for manufacturer, count in rows}


def count_assets_by_model(db: Session) -> dict[str, int]:
    """Same as count_assets_by_manufacturer, but for AssetModel — see that
    function's docstring."""
    rows = (
        db.query(Asset.model, func.count(Asset.id))
        .filter(Asset.status != "disposed")
        .group_by(Asset.model)
        .all()
    )
    return {model: count for model, count in rows}
