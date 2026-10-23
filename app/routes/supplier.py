from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.core.supplier_status import SupplierStatus
from app.database.database import get_db
from app.models.user import User
from app.schemas.supplier import (
    SupplierCreateRequest,
    SupplierResponse,
    SupplierStatusUpdateRequest,
    SupplierUpdateRequest,
)
from app.services.supplier_service import (
    create_supplier_record,
    get_supplier,
    get_supplier_by_supplier_name,
    list_supplier_records,
    recalculate_supplier_rating,
    update_supplier_record,
    update_supplier_status,
)


router = APIRouter(
    prefix="/api/v1/suppliers",
    tags=["Suppliers"],
)

# Who can do what to a Supplier lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("supplier", "read"))
require_writer = require_roles(*allowed_roles("supplier", "write"))


@router.get("")
def list_suppliers_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Doc: "invalid filter fields are rejected" — was a bare `str | None`,
    # so `?status=bogus` silently matched nothing and came back as an
    # empty list rather than telling the caller their filter value was
    # invalid. A Literal built from SupplierStatus's own values (not
    # duplicated string literals) gives FastAPI a real enum here: 422 on
    # anything else, and it shows up correctly in /docs.
    status: Literal[
        SupplierStatus.ONBOARDED, SupplierStatus.APPROVED, SupplierStatus.SUSPENDED
    ]
    | None = Query(default=None),
    category: str | None = Query(default=None),
    # Partial, case-insensitive match on name (Module 9: Filtering & Sorting).
    search: str | None = Query(default=None),
    sort_by: str = Query(default="id", pattern="^(id|created_at)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_supplier_records(
        db,
        limit=limit,
        offset=offset,
        status=status,
        category=category,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    result["items"] = [
        SupplierResponse.model_validate(supplier).model_dump() for supplier in result["items"]
    ]
    return api_ok(result)


@router.get("/by-name/{name}")
def get_supplier_by_name_endpoint(
    name: str,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    # Declared before /{supplier_id} — a numeric-looking name would still
    # need this route to win, and a non-numeric one would 422 on the other.
    supplier = get_supplier_by_supplier_name(db, name)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())


@router.get("/{supplier_id}")
def get_supplier_endpoint(
    supplier_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    supplier = get_supplier(db, supplier_id)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())


@router.post("", status_code=201)
def create_supplier_endpoint(
    data: SupplierCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    supplier = create_supplier_record(db, data, current_user.id)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())


@router.put("/{supplier_id}")
def update_supplier_endpoint(
    supplier_id: int,
    data: SupplierUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    supplier = update_supplier_record(db, supplier_id, data, current_user.id)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())


@router.patch("/{supplier_id}/status")
def update_supplier_status_endpoint(
    supplier_id: int,
    data: SupplierStatusUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    supplier = update_supplier_status(db, supplier_id, data.status, current_user.id)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())


@router.post("/{supplier_id}/rating/recalculate")
def recalculate_supplier_rating_endpoint(
    supplier_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    """Doc: "Supplier rating calculation" (Module 5.9) — derives `rating`
    from this supplier's Asset outcomes (certified vs. disposed) instead of
    the caller having to type a number. 409 if there's no certified/disposed
    asset yet to calculate from. See supplier_service.calculate_supplier_rating.
    """
    supplier = recalculate_supplier_rating(db, supplier_id, current_user.id)
    return api_ok(SupplierResponse.model_validate(supplier).model_dump())
