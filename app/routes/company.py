from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.company import (
    CompanyCreateRequest,
    CompanyResponse,
    CompanyUpdateRequest,
)
from app.services.company_service import (
    create_company_record,
    deactivate_company,
    get_company_for_user,
    list_company_records,
    reactivate_company,
    update_company_record,
)


router = APIRouter(
    prefix="/api/v1/companies",
    tags=["Companies"],
)

# Who can do what to a Company lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("company", "read"))
require_writer = require_roles(*allowed_roles("company", "write"))
require_deleter = require_roles(*allowed_roles("company", "delete"))


@router.get("")
def list_companies_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Partial, case-insensitive match on name — see the matching comment in
    # app/routes/supplier.py.
    search: str | None = Query(default=None),
    # Doc: "invalid filter fields are rejected" — same reasoning as the
    # Supplier/Asset status filters: a real Literal, not a bare `str`, so
    # `?company_type=bogus` 422s instead of silently matching nothing.
    company_type: Literal["internal", "external"] | None = Query(default=None),
    sort_by: str = Query(default="id", pattern="^(id|created_at)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_company_records(
        db,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
        current_user=current_user,
        search=search,
        company_type=company_type,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    result["items"] = [
        CompanyResponse.model_validate(company).model_dump() for company in result["items"]
    ]
    return api_ok(result)


@router.get("/{company_id}")
def get_company_endpoint(
    company_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    company = get_company_for_user(db, company_id, current_user)
    return api_ok(CompanyResponse.model_validate(company).model_dump())


@router.post("", status_code=201)
def create_company_endpoint(
    data: CompanyCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    company = create_company_record(db, data, current_user.id)
    return api_ok(CompanyResponse.model_validate(company).model_dump())


@router.put("/{company_id}")
def update_company_endpoint(
    company_id: int,
    data: CompanyUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    company = update_company_record(db, company_id, data, current_user)
    return api_ok(CompanyResponse.model_validate(company).model_dump())


@router.delete("/{company_id}")
def delete_company_endpoint(
    company_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    company = deactivate_company(db, company_id, current_user)
    return api_ok(CompanyResponse.model_validate(company).model_dump())


@router.patch("/{company_id}/reactivate")
def reactivate_company_endpoint(
    company_id: int,
    # require_deleter, not require_writer: reactivate is the reverse of
    # deactivate, so it should take the same permission level as delete
    # (admin-only for Company), not write (which includes Operator here) —
    # otherwise an Operator could reactivate a company they aren't allowed
    # to deactivate in the first place.
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    company = reactivate_company(db, company_id, current_user)
    return api_ok(CompanyResponse.model_validate(company).model_dump())
