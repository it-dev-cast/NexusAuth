from sqlalchemy.orm import Session

from app.core.asset_status import AssetStatus, is_valid_transition
from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.asset import Asset
from app.models.asset_attachment import AssetAttachment
from app.models.asset_tag import AssetTag
from app.repositories import (
    count_assets,
    create_asset,
    create_asset_attachment,
    create_asset_tag,
    delete_asset_tag,
    get_asset_by_id,
    get_asset_by_tag,
    get_asset_tag,
    list_assets,
    list_attachments_for_asset,
    list_events,
    list_tags_for_asset,
)
from app.schemas.asset import AssetCreateRequest, AssetResponse, AssetUpdateRequest
from app.services.audit_service import record_audit_event
from app.services.supplier_service import validate_supplier_reference


def _asset_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(asset: Asset) -> dict:
    return AssetResponse.model_validate(asset).model_dump(mode="json")


def create_asset_record(db: Session, data: AssetCreateRequest, actor_id: int | None) -> Asset:
    if get_asset_by_tag(db, data.asset_tag):
        raise _asset_error(
            "ASSET_ALREADY_EXISTS",
            "An asset with this asset_tag already exists.",
        )

    # Entity relationship check, doc: "Supplier reference validation (foreign
    # key)" — the supplier must exist AND be approved (not just onboarded or
    # suspended) before an asset can be registered against it.
    validate_supplier_reference(db, data.supplier_id)

    asset = Asset(
        asset_tag=data.asset_tag,
        manufacturer=data.manufacturer,
        model=data.model,
        serial_number=data.serial_number,
        supplier_id=data.supplier_id,
        barcode_value=data.barcode_value,
        purchase_cost=data.purchase_cost,
        current_value=data.current_value,
        currency=data.currency,
        status=AssetStatus.REGISTERED,
    )
    asset = create_asset(db, asset)
    record_audit_event(
        db, actor_id, "create", "asset", asset.id, old_value=None, new_value=_snapshot(asset)
    )
    return asset


def get_asset(db: Session, asset_id: int) -> Asset:
    asset = get_asset_by_id(db, asset_id)
    if not asset:
        raise _asset_error(
            "ASSET_NOT_FOUND",
            "Asset not found.",
            status_code=404,
        )
    return asset


def get_asset_by_asset_tag(db: Session, asset_tag: str) -> Asset:
    asset = get_asset_by_tag(db, asset_tag)
    if not asset:
        raise _asset_error(
            "ASSET_NOT_FOUND",
            "Asset not found.",
            status_code=404,
        )
    return asset


def list_asset_records(
    db: Session,
    limit: int,
    offset: int,
    status: str | None,
    supplier_id: int | None,
    sort_by: str,
    sort_dir: str,
    search: str | None = None,
) -> dict:
    items = list_assets(
        db,
        limit=limit,
        offset=offset,
        status=status,
        supplier_id=supplier_id,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total = count_assets(db, status=status, supplier_id=supplier_id, search=search)
    return paginated(items, total, limit, offset)


def update_asset_record(
    db: Session, asset_id: int, data: AssetUpdateRequest, actor_id: int | None
) -> Asset:
    asset = get_asset(db, asset_id)
    old_snapshot = _snapshot(asset)

    # manufacturer/model are NOT NULL — "provided" always means "set to
    # this value", so these keep the plain not-None check.
    if data.manufacturer is not None:
        asset.manufacturer = data.manufacturer
    if data.model is not None:
        asset.model = data.model

    # serial_number/barcode_value are nullable — distinguish "omitted" from
    # "explicitly sent as null" via model_fields_set so a client can clear
    # one back out once set.
    fields = data.model_fields_set
    if "serial_number" in fields:
        asset.serial_number = data.serial_number
    if "barcode_value" in fields:
        asset.barcode_value = data.barcode_value
    if "purchase_cost" in fields:
        asset.purchase_cost = data.purchase_cost
    if "current_value" in fields:
        asset.current_value = data.current_value
    if "currency" in fields:
        asset.currency = data.currency

    db.commit()
    db.refresh(asset)
    record_audit_event(
        db, actor_id, "update", "asset", asset.id, old_value=old_snapshot, new_value=_snapshot(asset)
    )
    return asset


def update_asset_status(
    db: Session, asset_id: int, new_status: str, actor_id: int | None
) -> Asset:
    asset = get_asset(db, asset_id)
    old_status = asset.status

    if not is_valid_transition(asset.status, new_status):
        raise _asset_error(
            "ASSET_INVALID_STATUS_TRANSITION",
            f"Cannot move asset from '{asset.status}' to '{new_status}'.",
        )

    asset.status = new_status
    db.commit()
    db.refresh(asset)
    record_audit_event(
        db,
        actor_id,
        "status_transition",
        "asset",
        asset.id,
        old_value={"status": old_status},
        new_value={"status": asset.status},
    )
    return asset


# ---- Digital Twin: Tags facet (NEXUS_ONE_ARCHITECTURE_PLAN §2.7) ----


def add_asset_tag(db: Session, asset_id: int, tag: str, actor_id: int | None) -> AssetTag:
    get_asset(db, asset_id)  # 404s if the asset doesn't exist
    existing = get_asset_tag(db, asset_id, tag)
    if existing:
        raise _asset_error(
            "ASSET_TAG_ALREADY_EXISTS",
            "This asset already has that tag.",
            status_code=409,
        )
    created = create_asset_tag(db, AssetTag(asset_id=asset_id, tag=tag))
    record_audit_event(
        db, actor_id, "tag_added", "asset", asset_id, old_value=None, new_value={"tag": tag}
    )
    return created


def remove_asset_tag(db: Session, asset_id: int, tag: str, actor_id: int | None) -> None:
    get_asset(db, asset_id)
    existing = get_asset_tag(db, asset_id, tag)
    if not existing:
        raise _asset_error(
            "ASSET_TAG_NOT_FOUND",
            "This asset does not have that tag.",
            status_code=404,
        )
    delete_asset_tag(db, existing)
    record_audit_event(
        db, actor_id, "tag_removed", "asset", asset_id, old_value={"tag": tag}, new_value=None
    )


def list_asset_tags(db: Session, asset_id: int) -> list[AssetTag]:
    get_asset(db, asset_id)
    return list_tags_for_asset(db, asset_id)


# ---- Digital Twin: Documents/Media/Attachments facets (§2.7) ----


def add_asset_attachment(
    db: Session,
    asset_id: int,
    attachment_type: str,
    reference: str,
    description: str | None,
    actor_id: int | None,
) -> AssetAttachment:
    get_asset(db, asset_id)
    created = create_asset_attachment(
        db,
        AssetAttachment(
            asset_id=asset_id,
            attachment_type=attachment_type,
            reference=reference,
            description=description,
            uploaded_by=actor_id,
        ),
    )
    record_audit_event(
        db,
        actor_id,
        "attachment_added",
        "asset",
        asset_id,
        old_value=None,
        new_value={"attachment_type": attachment_type, "reference": reference},
    )
    return created


def list_asset_attachments(db: Session, asset_id: int) -> list[AssetAttachment]:
    get_asset(db, asset_id)
    return list_attachments_for_asset(db, asset_id)


# ---- Digital Twin: Timeline facet (§2.7) ----


def get_asset_timeline(db: Session, asset_id: int, limit: int = 100):
    """No dedicated history table — derived from the events table (Phase 2's
    event-emission infrastructure, see app/services/event_service.py),
    which already carries exactly this history as a side effect of every
    audited asset action. A second, duplicate table would violate §2.7's
    own "add facets they own, not duplicate fields" rule.

    Oldest-first (a timeline reads chronologically) — the admin Events
    page's own list_events() returns newest-first for a human scanning
    "what just happened"; this reverses that same page for a "how did this
    asset get here" read instead.
    """
    get_asset(db, asset_id)
    events = list_events(
        db,
        limit=limit,
        offset=0,
        event_type=None,
        resource_type="asset",
        resource_id=str(asset_id),
        company_id=None,
        start_date=None,
        end_date=None,
    )
    return list(reversed(events))


def soft_delete_asset(db: Session, asset_id: int, actor_id: int | None) -> Asset:
    asset = get_asset(db, asset_id)
    if asset.status == AssetStatus.DISPOSED:
        return asset
    # Same convention as Employee: route "delete" through the status
    # transition path so any future disposal cascade only has one place to live.
    return update_asset_status(db, asset_id, AssetStatus.DISPOSED, actor_id)
