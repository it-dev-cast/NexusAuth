from sqlalchemy.orm import Session

from app.models.asset_tag import AssetTag


def create_asset_tag(db: Session, asset_tag: AssetTag) -> AssetTag:
    db.add(asset_tag)
    db.commit()
    db.refresh(asset_tag)
    return asset_tag


def get_asset_tag(db: Session, asset_id: int, tag: str) -> AssetTag | None:
    return (
        db.query(AssetTag)
        .filter(AssetTag.asset_id == asset_id, AssetTag.tag == tag)
        .first()
    )


def list_tags_for_asset(db: Session, asset_id: int) -> list[AssetTag]:
    return (
        db.query(AssetTag)
        .filter(AssetTag.asset_id == asset_id)
        .order_by(AssetTag.tag.asc())
        .all()
    )


def delete_asset_tag(db: Session, asset_tag: AssetTag) -> None:
    db.delete(asset_tag)
    db.commit()
