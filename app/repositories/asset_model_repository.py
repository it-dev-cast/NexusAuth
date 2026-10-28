from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset_model import AssetModel
from app.core.list_query import apply_list_filters, list_order


def get_asset_model_by_id(db: Session, asset_model_id: int) -> AssetModel | None:
    return db.query(AssetModel).filter(AssetModel.id == asset_model_id).first()


def get_asset_model_by_name(db: Session, name: str) -> AssetModel | None:
    return db.query(AssetModel).filter(AssetModel.name == name).first()


def create_asset_model(db: Session, asset_model: AssetModel) -> AssetModel:
    db.add(asset_model)
    db.commit()
    db.refresh(asset_model)
    return asset_model


def _filtered(query, include_inactive: bool, search: str | None):
    if not include_inactive:
        query = query.filter(AssetModel.is_active == True)  # noqa: E712
    if search:
        query = query.filter(AssetModel.name.ilike(f"%{search}%"))
    # Extra field[op]=value filters from the request, if any (app/core/list_query.py).
    return apply_list_filters(query, AssetModel)


def list_asset_models(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    include_inactive: bool = False,
    search: str | None = None,
) -> list[AssetModel]:
    query = _filtered(db.query(AssetModel), include_inactive, search)
    return query.order_by(*list_order(AssetModel, AssetModel.name.asc())).limit(limit).offset(offset).all()


def count_asset_models(db: Session, include_inactive: bool = False, search: str | None = None) -> int:
    query = _filtered(db.query(func.count(AssetModel.id)), include_inactive, search)
    return query.scalar() or 0


def soft_delete_asset_model(db: Session, asset_model: AssetModel) -> AssetModel:
    asset_model.is_active = False
    db.commit()
    db.refresh(asset_model)
    return asset_model
