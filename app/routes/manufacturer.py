from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.manufacturer import (
    ManufacturerCreateRequest,
    ManufacturerResponse,
    ManufacturerUpdateRequest,
)
from app.services.manufacturer_service import (
    create_manufacturer_record,
    deactivate_manufacturer,
    get_manufacturer,
    list_manufacturer_records,
    reactivate_manufacturer,
    update_manufacturer_record,
)


router = APIRouter(
    prefix="/api/v1/manufacturers",
    tags=["Manufacturers"],
)

# Who can do what to a Manufacturer lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("manufacturer", "read"))
require_writer = require_roles(*allowed_roles("manufacturer", "write"))
require_deleter = require_roles(*allowed_roles("manufacturer", "delete"))


@router.get("")
def list_manufacturers_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_manufacturer_records(
        db, limit=limit, offset=offset, include_inactive=include_inactive, search=search
    )
    result["items"] = [
        ManufacturerResponse.model_validate(manufacturer).model_dump() for manufacturer in result["items"]
    ]
    return api_ok(result)


@router.get("/{manufacturer_id}")
def get_manufacturer_endpoint(
    manufacturer_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    manufacturer = get_manufacturer(db, manufacturer_id)
    return api_ok(ManufacturerResponse.model_validate(manufacturer).model_dump())


@router.post("", status_code=201)
def create_manufacturer_endpoint(
    data: ManufacturerCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    manufacturer = create_manufacturer_record(db, data, current_user.id)
    return api_ok(ManufacturerResponse.model_validate(manufacturer).model_dump())


@router.put("/{manufacturer_id}")
def update_manufacturer_endpoint(
    manufacturer_id: int,
    data: ManufacturerUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    manufacturer = update_manufacturer_record(db, manufacturer_id, data, current_user.id)
    return api_ok(ManufacturerResponse.model_validate(manufacturer).model_dump())


@router.delete("/{manufacturer_id}")
def delete_manufacturer_endpoint(
    manufacturer_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    manufacturer = deactivate_manufacturer(db, manufacturer_id, current_user.id)
    return api_ok(ManufacturerResponse.model_validate(manufacturer).model_dump())


@router.patch("/{manufacturer_id}/reactivate")
def reactivate_manufacturer_endpoint(
    manufacturer_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    manufacturer = reactivate_manufacturer(db, manufacturer_id, current_user.id)
    return api_ok(ManufacturerResponse.model_validate(manufacturer).model_dump())
