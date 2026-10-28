from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.master_item import (
    MasterItemCreateRequest,
    MasterItemResponse,
    MasterItemUpdateRequest,
)
from app.services.master_item_service import (
    create_master_item,
    deactivate_master_item,
    get_catalog,
    get_master_item,
    list_master_items,
    list_master_options,
    reactivate_master_item,
    to_response,
    update_master_item,
)

router = APIRouter(
    prefix="/api/v1/master-data",
    tags=["Master Data"],
)

# One permission entry for every list: everyone who can use the forms reads
# them (to fill dropdowns); only admin edits the shared lists. See
# app/core/permissions.py.
require_reader = require_roles(*allowed_roles("master_data", "read"))
require_writer = require_roles(*allowed_roles("master_data", "write"))
require_deleter = require_roles(*allowed_roles("master_data", "delete"))


def _one(db: Session, item) -> dict:
    return api_ok(to_response(db, item))


# NOTE: the fixed path (catalog) is declared before the
# /{master_type} routes so they are never read as a list name.
@router.get("/catalog")
def catalog_endpoint(current_user: User = Depends(require_reader), db: Session = Depends(get_db)):
    return api_ok(get_catalog(db))


@router.get("/{master_type}/options")
def options_endpoint(
    master_type: str,
    parent_id: int | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    return api_ok({"items": list_master_options(db, master_type, parent_id)})


@router.get("/{master_type}")
def list_endpoint(
    master_type: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str = Query(default="active"),
    search: str | None = Query(default=None, max_length=100),
    parent_id: int | None = Query(default=None),
    sort_by: str = Query(default="name"),
    sort_dir: str = Query(default="asc"),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_master_items(db, master_type, limit, offset, status, search, parent_id, sort_by, sort_dir)
    result["items"] = [MasterItemResponse.model_validate(i).model_dump() for i in result["items"]]
    return api_ok(result)


@router.get("/{master_type}/{item_id}")
def get_endpoint(
    master_type: str,
    item_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    return _one(db, get_master_item(db, master_type, item_id))


@router.post("/{master_type}", status_code=201)
def create_endpoint(
    master_type: str,
    data: MasterItemCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    return _one(db, create_master_item(db, master_type, data, current_user.id))


@router.put("/{master_type}/{item_id}")
def update_endpoint(
    master_type: str,
    item_id: int,
    data: MasterItemUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    return _one(db, update_master_item(db, master_type, item_id, data, current_user.id))


@router.delete("/{master_type}/{item_id}")
def deactivate_endpoint(
    master_type: str,
    item_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    return _one(db, deactivate_master_item(db, master_type, item_id, current_user.id))


@router.patch("/{master_type}/{item_id}/reactivate")
def reactivate_endpoint(
    master_type: str,
    item_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    return _one(db, reactivate_master_item(db, master_type, item_id, current_user.id))
