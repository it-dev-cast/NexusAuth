from sqlalchemy.orm import Session

from app.core.asset_status import AssetStatus
from app.core.errors import AuthError
from app.core.pagination import paginated
from app.core.supplier_status import SupplierStatus, is_valid_transition
from app.models.supplier import Supplier
from app.repositories import (
    count_assets,
    count_suppliers,
    create_supplier,
    get_supplier_by_id,
    get_supplier_by_name,
    list_suppliers,
)
from app.schemas.supplier import SupplierCreateRequest, SupplierResponse, SupplierUpdateRequest
from app.services.audit_service import record_audit_event


def _supplier_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(supplier: Supplier) -> dict:
    return SupplierResponse.model_validate(supplier).model_dump(mode="json")


def create_supplier_record(db: Session, data: SupplierCreateRequest, actor_id: int | None) -> Supplier:
    if get_supplier_by_name(db, data.name):
        raise _supplier_error(
            "SUPPLIER_ALREADY_EXISTS",
            "A supplier with this name already exists.",
        )

    supplier = Supplier(
        name=data.name,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        terms=data.terms,
        category=data.category,
        rating=data.rating,
        status=SupplierStatus.ONBOARDED,
    )
    supplier = create_supplier(db, supplier)
    record_audit_event(
        db, actor_id, "create", "supplier", supplier.id, old_value=None, new_value=_snapshot(supplier)
    )
    return supplier


def get_supplier(db: Session, supplier_id: int) -> Supplier:
    supplier = get_supplier_by_id(db, supplier_id)
    if not supplier:
        raise _supplier_error(
            "SUPPLIER_NOT_FOUND",
            "Supplier not found.",
            status_code=404,
        )
    return supplier


def get_supplier_by_supplier_name(db: Session, name: str) -> Supplier:
    """Doc: "Read Supplier by name" — the create-time uniqueness check
    already used get_supplier_by_name(); this just exposes the same lookup
    with the standard 404 wrapping the other get_* functions use."""
    supplier = get_supplier_by_name(db, name)
    if not supplier:
        raise _supplier_error(
            "SUPPLIER_NOT_FOUND",
            "Supplier not found.",
            status_code=404,
        )
    return supplier


def list_supplier_records(
    db: Session,
    limit: int,
    offset: int,
    status: str | None,
    category: str | None,
    search: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> dict:
    items = list_suppliers(
        db,
        limit=limit,
        offset=offset,
        status=status,
        category=category,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total = count_suppliers(db, status=status, category=category, search=search)
    return paginated(items, total, limit, offset)


def update_supplier_record(
    db: Session,
    supplier_id: int,
    data: SupplierUpdateRequest,
    actor_id: int | None,
) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    old_snapshot = _snapshot(supplier)

    # All of these are nullable — distinguish "omitted" from "explicitly
    # sent as null" via model_fields_set so a client can clear one back out
    # once set, instead of every null in the payload being silently ignored.
    fields = data.model_fields_set
    if "contact_email" in fields:
        supplier.contact_email = data.contact_email
    if "contact_phone" in fields:
        supplier.contact_phone = data.contact_phone
    if "terms" in fields:
        supplier.terms = data.terms
    if "category" in fields:
        supplier.category = data.category
    if "rating" in fields:
        supplier.rating = data.rating

    db.commit()
    db.refresh(supplier)
    record_audit_event(
        db, actor_id, "update", "supplier", supplier.id, old_value=old_snapshot, new_value=_snapshot(supplier)
    )
    return supplier


def update_supplier_status(
    db: Session, supplier_id: int, new_status: str, actor_id: int | None
) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    old_status = supplier.status

    if not is_valid_transition(supplier.status, new_status):
        raise _supplier_error(
            "SUPPLIER_INVALID_STATUS_TRANSITION",
            f"Cannot move supplier from '{supplier.status}' to '{new_status}'.",
        )

    supplier.status = new_status
    db.commit()
    db.refresh(supplier)
    record_audit_event(
        db,
        actor_id,
        "status_transition",
        "supplier",
        supplier.id,
        old_value={"status": old_status},
        new_value={"status": supplier.status},
    )
    return supplier


def calculate_supplier_rating(db: Session, supplier_id: int) -> tuple[float | None, int, int]:
    """Doc: "Supplier rating calculation" (Module 5.9).

    No Refurbishment/Inventory module exists yet to source real order/QC
    history from (see the caveat on Supplier.rating), but Foundation Core
    already has one honest quality signal of its own: what happened to the
    Assets this supplier's items became, via the Asset lifecycle state
    machine (app/core/asset_status.py). An Asset that reached `certified`
    passed QC; one that was `disposed` did not make it there. `registered`/
    `in_repair` assets are still in progress and don't count either way yet.

    rating = 5.0 * certified / (certified + disposed), rounded to 2 places.
    Returns (rating, certified_count, resolved_count) — rating is None when
    resolved_count is 0 (nothing to calculate from yet), matching this
    codebase's existing pattern of degrading gracefully rather than forcing
    a number out of no data (see app/core/pii_crypto.py's get_fernet()).
    """
    certified = count_assets(db, status=AssetStatus.CERTIFIED, supplier_id=supplier_id)
    disposed = count_assets(db, status=AssetStatus.DISPOSED, supplier_id=supplier_id)
    resolved = certified + disposed
    if resolved == 0:
        return None, certified, resolved
    return round(5.0 * certified / resolved, 2), certified, resolved


def recalculate_supplier_rating(db: Session, supplier_id: int, actor_id: int | None) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    old_snapshot = _snapshot(supplier)

    new_rating, certified, resolved = calculate_supplier_rating(db, supplier_id)
    if new_rating is None:
        raise _supplier_error(
            "SUPPLIER_RATING_INSUFFICIENT_DATA",
            "No certified or disposed assets reference this supplier yet — "
            "there is nothing to calculate a rating from.",
            status_code=409,
        )

    supplier.rating = new_rating
    db.commit()
    db.refresh(supplier)
    record_audit_event(
        db,
        actor_id,
        "rating_recalculated",
        "supplier",
        supplier.id,
        old_value=old_snapshot,
        new_value={
            **_snapshot(supplier),
            "certified_assets": certified,
            "resolved_assets": resolved,
        },
    )
    return supplier


def validate_supplier_reference(db: Session, supplier_id: int) -> Supplier:
    """Entity-relationship guard for other modules (Assets in particular).

    Doc requirement: "Supplier reference validation (used by Assets)" — an
    Asset should only ever be allowed to point at a supplier that exists AND
    is currently approved. Called from app.services.asset_service on every
    asset creation, the same way employee_service calls
    company_service.get_company.
    """
    supplier = get_supplier(db, supplier_id)
    if supplier.status != SupplierStatus.APPROVED:
        raise _supplier_error(
            "SUPPLIER_NOT_APPROVED",
            "This supplier is not approved and cannot be referenced by an asset.",
            status_code=409,
        )
    return supplier
