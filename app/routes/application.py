from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.application import (
    ApplicationAccessGrantRequest,
    ApplicationCreateRequest,
    ApplicationResponse,
    ApplicationUpdateRequest,
)
from app.services.application_access_service import (
    grant_application_access,
    list_access_for_application,
    list_candidates_for_application,
    revoke_application_access,
)
from app.services.application_service import (
    create_application_record,
    deactivate_application,
    get_application,
    list_application_records,
    list_categories_in_use,
    reactivate_application,
    update_application_record,
)


router = APIRouter(
    prefix="/api/v1/applications",
    tags=["Applications"],
)

# Who can do what to an Application lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("application", "read"))
require_writer = require_roles(*allowed_roles("application", "write"))
require_deleter = require_roles(*allowed_roles("application", "delete"))
# Granting/revoking access and listing who holds an application exposes
# employee records across companies, so it is its own (admin-only) permission.
require_access_reader = require_roles(*allowed_roles("application_access", "read"))
require_access_writer = require_roles(*allowed_roles("application_access", "write"))


@router.get("")
def list_applications_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    # Name or code, partial and case-insensitive.
    search: str | None = Query(default=None),
    # An explicit status wins over include_inactive.
    status: Literal["active", "inactive", "all"] | None = Query(default=None),
    category: str | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_application_records(
        db,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
        search=search,
        status=status,
        category=category,
    )
    result["items"] = [
        ApplicationResponse.model_validate(application).model_dump() for application in result["items"]
    ]
    return api_ok(result)


# Declared before /{application_id} so "categories" isn't parsed as an id.
@router.get("/categories")
def list_application_categories_endpoint(
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    return api_ok(list_categories_in_use(db))


@router.get("/{application_id}")
def get_application_endpoint(
    application_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    application = get_application(db, application_id)
    return api_ok(ApplicationResponse.model_validate(application).model_dump())


@router.post("", status_code=201)
def create_application_endpoint(
    data: ApplicationCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    application = create_application_record(db, data, current_user.id)
    return api_ok(ApplicationResponse.model_validate(application).model_dump())


@router.put("/{application_id}")
def update_application_endpoint(
    application_id: int,
    data: ApplicationUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    application = update_application_record(db, application_id, data, current_user.id)
    return api_ok(ApplicationResponse.model_validate(application).model_dump())


@router.delete("/{application_id}")
def delete_application_endpoint(
    application_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    application = deactivate_application(db, application_id, current_user.id)
    return api_ok(ApplicationResponse.model_validate(application).model_dump())


@router.patch("/{application_id}/reactivate")
def reactivate_application_endpoint(
    application_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    application = reactivate_application(db, application_id, current_user.id)
    return api_ok(ApplicationResponse.model_validate(application).model_dump())


# ---- Access management: which employees hold this application ----


@router.get("/{application_id}/access")
def list_application_access_endpoint(
    application_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    # Employee name, email or employee ID (employee code).
    search: str | None = Query(default=None),
    current_user: User = Depends(require_access_reader),
    db: Session = Depends(get_db),
):
    return api_ok(list_access_for_application(db, application_id, search, limit, offset))


@router.get("/{application_id}/access/candidates")
def list_application_access_candidates_endpoint(
    application_id: int,
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(require_access_reader),
    db: Session = Depends(get_db),
):
    """Employees who could be given this application: not exited and not
    already holding it."""
    return api_ok(list_candidates_for_application(db, application_id, search, limit))


@router.post("/{application_id}/access", status_code=201)
def grant_application_access_endpoint(
    application_id: int,
    data: ApplicationAccessGrantRequest,
    current_user: User = Depends(require_access_writer),
    db: Session = Depends(get_db),
):
    return api_ok(grant_application_access(db, application_id, data.employee_ids, current_user))


@router.delete("/{application_id}/access/{employee_id}")
def revoke_application_access_endpoint(
    application_id: int,
    employee_id: int,
    current_user: User = Depends(require_access_writer),
    db: Session = Depends(get_db),
):
    return api_ok(revoke_application_access(db, application_id, employee_id, current_user))
