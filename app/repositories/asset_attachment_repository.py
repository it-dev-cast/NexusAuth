from sqlalchemy.orm import Session

from app.models.asset_attachment import AssetAttachment


def create_asset_attachment(db: Session, attachment: AssetAttachment) -> AssetAttachment:
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def list_attachments_for_asset(db: Session, asset_id: int) -> list[AssetAttachment]:
    return (
        db.query(AssetAttachment)
        .filter(AssetAttachment.asset_id == asset_id)
        .order_by(AssetAttachment.created_at.desc(), AssetAttachment.id.desc())
        .all()
    )
