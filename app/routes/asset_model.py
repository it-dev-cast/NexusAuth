from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.core.list_query import LIST_QUERY_HELP, list_query
from app.models.asset_model import AssetModel
from app.models.user import User
from app.schemas.asset_model import (
    AssetModelCreateRequest,
    AssetModelResponse,
    AssetModelUpdateRequest,
)
from app.services.asset_model_service import (
    create_asset_model_record,
    deactivate_asset_model,
    get_asset_model,
    list_asset_model_records,
    reactivate_asset_model,
    update_asset_model_record,
)


router = APIRouter(
    prefix="/api/v1/asset-models",
    tags=["Asset Models"],
)

# Who can do what to an AssetModel lives in one place: app/core/permissions.py.
require_reader = require_roles(*allowed_roles("asset_model", "read"))
require_writer = require_roles(*allowed_roles("asset_model", "write"))
require_deleter = require_roles(*allowed_roles("asset_model", "delete"))


@router.get("", dependencies=[Depends(list_query(AssetModel))], description=LIST_QUERY_HELP)
def list_asset_models_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    search: str | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_asset_model_records(
        db, limit=limit, offset=offset, include_inactive=include_inactive, search=search
    )
    result["items"] = [
        AssetModelResponse.model_validate(asset_model).model_dump() for asset_model in result["items"]
    ]
    return api_ok(result)


@router.get("/{asset_model_id}")
def get_asset_model_endpoint(
    asset_model_id: int,
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    asset_model = get_asset_model(db, asset_model_id)
    return api_ok(AssetModelResponse.model_validate(asset_model).model_dump())


@router.post("", status_code=201)
def create_asset_model_endpoint(
    data: AssetModelCreateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset_model = create_asset_model_record(db, data, current_user.id)
    return api_ok(AssetModelResponse.model_validate(asset_model).model_dump())


@router.put("/{asset_model_id}")
def update_asset_model_endpoint(
    asset_model_id: int,
    data: AssetModelUpdateRequest,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset_model = update_asset_model_record(db, asset_model_id, data, current_user.id)
    return api_ok(AssetModelResponse.model_validate(asset_model).model_dump())


@router.delete("/{asset_model_id}")
def delete_asset_model_endpoint(
    asset_model_id: int,
    current_user: User = Depends(require_deleter),
    db: Session = Depends(get_db),
):
    asset_model = deactivate_asset_model(db, asset_model_id, current_user.id)
    return api_ok(AssetModelResponse.model_validate(asset_model).model_dump())


@router.patch("/{asset_model_id}/reactivate")
def reactivate_asset_model_endpoint(
    asset_model_id: int,
    current_user: User = Depends(require_writer),
    db: Session = Depends(get_db),
):
    asset_model = reactivate_asset_model(db, asset_model_id, current_user.id)
    return api_ok(AssetModelResponse.model_validate(asset_model).model_dump())
