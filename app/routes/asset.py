from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.asset_status import AssetStatus
from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.asset import (
    AssetCreateRequest,
    AssetResponse,
    AssetStatusUpdateRequest,
    AssetUpdateRequest,
)
from app.schemas.asset_attachment import AssetAttachmentCreateRequest, AssetAttachmentResponse
from app.schemas.asset_tag import AssetTagCreateRequest, AssetTagResponse
from app.schemas.event import EventResponse
from app.services.asset_service import (
    add_asset_attachment,
    add_asset_tag,
    create_asset_record,
    get_asset,
    get_asset_by_asset_tag,
    get_asset_timeline,
    list_asset_attachments,
    list_asset_records,
    list_asset_tags,
    remove_asset_tag,
    soft_delete_asset,
    update_asset_record,
    update_asset_status,
)


router = APIRouter(
    prefix="/api/v1/assets",
    tags=["Assets"],
)

# Who can do what to an Asset lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("asset", "read"))
require_writer = require_roles(*allowed_roles("asset", "write"))
require_deleter = require_roles(*allowed_roles("asset", "delete"))


@router.get("")
def list_assets_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Doc: "invalid filter fields are rejected" — see the matching comment
    # in app/routes/supplier.py.
    status: Literal[
        AssetStatus.REGISTERED, AssetStatus.IN_REPAIR, AssetStatus.CERTIFIED, AssetStatus.DISPOSED
    ]
    | None = Query(default=None),
    supplier_id: int | None = Query(default=None),
    # Partial, case-insensitive match on asset_tag/manufacturer/model/
    # serial_number (Module 9: Filtering & Sorting) — see the matching
    # comment in app/routes/supplier.py.
    search: str | None = Query(default=None),
    sort_by: str = Query(default="id", pattern="^(id|created_at)$"),
    # Newest first by default — see the matching comment in
    # company_repository.py. Still fully overridable per-request; this
    # only changes what a plain, unsorted list request gets.
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_asset_records(
        db,
        limit=limit,
        offset=offset,
        status=status,
        supplier_id=supplier_id,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    result["items"] = [
        AssetResponse.model_validate(asset).model_dump() for asset in result["items"]
    ]
    return api_ok(result)


@router.get("/tag/{asset_tag}")
def get_asset_by_tag_endpoint(
    asset_tag: str,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    asset = get_asset_by_asset_tag(db, asset_tag)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


@router.get("/{asset_id}")
def get_asset_endpoint(
    asset_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    asset = get_asset(db, asset_id)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


@router.post("", status_code=201)
def create_asset_endpoint(
    data: AssetCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset = create_asset_record(db, data, current_user.id)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


@router.put("/{asset_id}")
def update_asset_endpoint(
    asset_id: int,
    data: AssetUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset = update_asset_record(db, asset_id, data, current_user.id)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


@router.patch("/{asset_id}/status")
def update_asset_status_endpoint(
    asset_id: int,
    data: AssetStatusUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset = update_asset_status(db, asset_id, data.status, current_user.id)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


@router.delete("/{asset_id}")
def delete_asset_endpoint(
    asset_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    asset = soft_delete_asset(db, asset_id, current_user.id)
    return api_ok(AssetResponse.model_validate(asset).model_dump())


# ---- Digital Twin facets (NEXUS_ONE_ARCHITECTURE_PLAN §2.7) ----
# Tags/Attachments/Timeline are sub-resources of Asset, not their own
# top-level resource — same read/write roles as the parent (require_reader/
# require_writer above), no separate app/core/permissions.py entry needed.


@router.get("/{asset_id}/tags")
def list_asset_tags_endpoint(
    asset_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    tags = list_asset_tags(db, asset_id)
    return api_ok([AssetTagResponse.model_validate(t).model_dump() for t in tags])


@router.post("/{asset_id}/tags", status_code=201)
def add_asset_tag_endpoint(
    asset_id: int,
    data: AssetTagCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    tag = add_asset_tag(db, asset_id, data.tag, current_user.id)
    return api_ok(AssetTagResponse.model_validate(tag).model_dump())


@router.delete("/{asset_id}/tags/{tag}")
def remove_asset_tag_endpoint(
    asset_id: int,
    tag: str,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    remove_asset_tag(db, asset_id, tag, current_user.id)
    return api_ok({"removed": True})


@router.get("/{asset_id}/attachments")
def list_asset_attachments_endpoint(
    asset_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    attachments = list_asset_attachments(db, asset_id)
    return api_ok([AssetAttachmentResponse.model_validate(a).model_dump() for a in attachments])


@router.post("/{asset_id}/attachments", status_code=201)
def add_asset_attachment_endpoint(
    asset_id: int,
    data: AssetAttachmentCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    attachment = add_asset_attachment(
        db, asset_id, data.attachment_type, data.reference, data.description, current_user.id
    )
    return api_ok(AssetAttachmentResponse.model_validate(attachment).model_dump())


@router.get("/{asset_id}/timeline")
def get_asset_timeline_endpoint(
    asset_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    events = get_asset_timeline(db, asset_id, limit=limit)
    return api_ok([EventResponse.model_validate(e).model_dump() for e in events])
