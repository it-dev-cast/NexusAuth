from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.manufacturer import Manufacturer
from app.repositories import (
    count_assets_by_manufacturer,
    count_manufacturers,
    create_manufacturer,
    get_manufacturer_by_id,
    get_manufacturer_by_name,
    list_manufacturers,
    soft_delete_manufacturer,
)
from app.schemas.manufacturer import (
    ManufacturerCreateRequest,
    ManufacturerResponse,
    ManufacturerUpdateRequest,
)
from app.services.audit_service import record_audit_event


def _manufacturer_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(manufacturer: Manufacturer) -> dict:
    return ManufacturerResponse.model_validate(manufacturer).model_dump(mode="json")


def _attach_asset_counts(db: Session, manufacturers: list[Manufacturer]) -> list[Manufacturer]:
    if not manufacturers:
        return manufacturers
    counts = count_assets_by_manufacturer(db)
    for manufacturer in manufacturers:
        manufacturer.asset_count = counts.get(manufacturer.name, 0)
    return manufacturers


def create_manufacturer_record(
    db: Session, data: ManufacturerCreateRequest, actor_id: int | None
) -> Manufacturer:
    if get_manufacturer_by_name(db, data.name):
        raise _manufacturer_error(
            "MANUFACTURER_ALREADY_EXISTS", "A manufacturer with this name already exists."
        )

    manufacturer = create_manufacturer(db, Manufacturer(name=data.name, is_active=True))
    manufacturer.asset_count = 0  # brand new, nothing registered against it yet
    record_audit_event(
        db, actor_id, "create", "manufacturer", manufacturer.id, old_value=None, new_value=_snapshot(manufacturer)
    )
    return manufacturer


def get_manufacturer(db: Session, manufacturer_id: int) -> Manufacturer:
    manufacturer = get_manufacturer_by_id(db, manufacturer_id)
    if not manufacturer:
        raise _manufacturer_error("MANUFACTURER_NOT_FOUND", "Manufacturer not found.", status_code=404)
    _attach_asset_counts(db, [manufacturer])
    return manufacturer


def list_manufacturer_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    search: str | None = None,
) -> dict:
    items = list_manufacturers(db, limit=limit, offset=offset, include_inactive=include_inactive, search=search)
    total = count_manufacturers(db, include_inactive=include_inactive, search=search)
    _attach_asset_counts(db, items)
    return paginated(items, total, limit, offset)


def update_manufacturer_record(
    db: Session, manufacturer_id: int, data: ManufacturerUpdateRequest, actor_id: int | None
) -> Manufacturer:
    manufacturer = get_manufacturer(db, manufacturer_id)
    old_snapshot = _snapshot(manufacturer)

    if data.name is not None:
        existing = get_manufacturer_by_name(db, data.name)
        if existing and existing.id != manufacturer.id:
            raise _manufacturer_error(
                "MANUFACTURER_ALREADY_EXISTS", "A manufacturer with this name already exists."
            )
        manufacturer.name = data.name

    db.commit()
    db.refresh(manufacturer)
    record_audit_event(
        db, actor_id, "update", "manufacturer", manufacturer.id, old_value=old_snapshot, new_value=_snapshot(manufacturer)
    )
    return manufacturer


def deactivate_manufacturer(db: Session, manufacturer_id: int, actor_id: int | None) -> Manufacturer:
    manufacturer = get_manufacturer(db, manufacturer_id)
    if not manufacturer.is_active:
        return manufacturer
    old_snapshot = _snapshot(manufacturer)
    manufacturer = soft_delete_manufacturer(db, manufacturer)
    record_audit_event(
        db, actor_id, "delete", "manufacturer", manufacturer.id, old_value=old_snapshot, new_value=_snapshot(manufacturer)
    )
    return manufacturer


def reactivate_manufacturer(db: Session, manufacturer_id: int, actor_id: int | None) -> Manufacturer:
    """Counterpart to deactivate_manufacturer — see
    department_service.reactivate_department's docstring for why this is
    needed (ManufacturerUpdateRequest only carries `name`, no is_active)."""
    manufacturer = get_manufacturer(db, manufacturer_id)
    if manufacturer.is_active:
        return manufacturer
    old_snapshot = _snapshot(manufacturer)
    manufacturer.is_active = True
    db.commit()
    db.refresh(manufacturer)
    _attach_asset_counts(db, [manufacturer])
    record_audit_event(
        db, actor_id, "update", "manufacturer", manufacturer.id, old_value=old_snapshot, new_value=_snapshot(manufacturer)
    )
    return manufacturer
