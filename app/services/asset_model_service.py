from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.asset_model import AssetModel
from app.repositories import (
    count_asset_models,
    count_assets_by_model,
    create_asset_model,
    get_asset_model_by_id,
    get_asset_model_by_name,
    list_asset_models,
    soft_delete_asset_model,
)
from app.schemas.asset_model import (
    AssetModelCreateRequest,
    AssetModelResponse,
    AssetModelUpdateRequest,
)
from app.services.audit_service import record_audit_event


def _asset_model_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(asset_model: AssetModel) -> dict:
    return AssetModelResponse.model_validate(asset_model).model_dump(mode="json")


def _attach_asset_counts(db: Session, asset_models: list[AssetModel]) -> list[AssetModel]:
    if not asset_models:
        return asset_models
    counts = count_assets_by_model(db)
    for asset_model in asset_models:
        asset_model.asset_count = counts.get(asset_model.name, 0)
    return asset_models


def create_asset_model_record(
    db: Session, data: AssetModelCreateRequest, actor_id: int | None
) -> AssetModel:
    if get_asset_model_by_name(db, data.name):
        raise _asset_model_error("ASSET_MODEL_ALREADY_EXISTS", "A model with this name already exists.")

    asset_model = create_asset_model(db, AssetModel(name=data.name, is_active=True))
    asset_model.asset_count = 0  # brand new, nothing registered against it yet
    record_audit_event(
        db, actor_id, "create", "asset_model", asset_model.id, old_value=None, new_value=_snapshot(asset_model)
    )
    return asset_model


def get_asset_model(db: Session, asset_model_id: int) -> AssetModel:
    asset_model = get_asset_model_by_id(db, asset_model_id)
    if not asset_model:
        raise _asset_model_error("ASSET_MODEL_NOT_FOUND", "Model not found.", status_code=404)
    _attach_asset_counts(db, [asset_model])
    return asset_model


def list_asset_model_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    search: str | None = None,
) -> dict:
    items = list_asset_models(db, limit=limit, offset=offset, include_inactive=include_inactive, search=search)
    total = count_asset_models(db, include_inactive=include_inactive, search=search)
    _attach_asset_counts(db, items)
    return paginated(items, total, limit, offset)


def update_asset_model_record(
    db: Session, asset_model_id: int, data: AssetModelUpdateRequest, actor_id: int | None
) -> AssetModel:
    asset_model = get_asset_model(db, asset_model_id)
    old_snapshot = _snapshot(asset_model)

    if data.name is not None:
        existing = get_asset_model_by_name(db, data.name)
        if existing and existing.id != asset_model.id:
            raise _asset_model_error("ASSET_MODEL_ALREADY_EXISTS", "A model with this name already exists.")
        asset_model.name = data.name

    db.commit()
    db.refresh(asset_model)
    record_audit_event(
        db, actor_id, "update", "asset_model", asset_model.id, old_value=old_snapshot, new_value=_snapshot(asset_model)
    )
    return asset_model


def deactivate_asset_model(db: Session, asset_model_id: int, actor_id: int | None) -> AssetModel:
    asset_model = get_asset_model(db, asset_model_id)
    if not asset_model.is_active:
        return asset_model
    old_snapshot = _snapshot(asset_model)
    asset_model = soft_delete_asset_model(db, asset_model)
    record_audit_event(
        db, actor_id, "delete", "asset_model", asset_model.id, old_value=old_snapshot, new_value=_snapshot(asset_model)
    )
    return asset_model


def reactivate_asset_model(db: Session, asset_model_id: int, actor_id: int | None) -> AssetModel:
    """Counterpart to deactivate_asset_model — see
    department_service.reactivate_department's docstring for why this is
    needed (AssetModelUpdateRequest only carries `name`, no is_active)."""
    asset_model = get_asset_model(db, asset_model_id)
    if asset_model.is_active:
        return asset_model
    old_snapshot = _snapshot(asset_model)
    asset_model.is_active = True
    db.commit()
    db.refresh(asset_model)
    _attach_asset_counts(db, [asset_model])
    record_audit_event(
        db, actor_id, "update", "asset_model", asset_model.id, old_value=old_snapshot, new_value=_snapshot(asset_model)
    )
    return asset_model
