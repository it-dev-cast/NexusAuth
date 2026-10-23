from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.application import ApplicationCreateRequest, ApplicationResponse, ApplicationUpdateRequest
from app.services.application_service import (
    create_application_record,
    deactivate_application,
    get_application,
    list_application_records,
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


@router.get("")
def list_applications_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_application_records(
        db, limit=limit, offset=offset, include_inactive=include_inactive, search=search
    )
    result["items"] = [
        ApplicationResponse.model_validate(application).model_dump() for application in result["items"]
    ]
    return api_ok(result)


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
