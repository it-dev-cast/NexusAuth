from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class AssetAttachment(Base):
    """Digital Twin "Documents" / "Media" / "Attachments" facets
    (NEXUS_ONE_ARCHITECTURE_PLAN §2.7) — one shared table, not three. The
    plan lists them as separate facets, but they're the same underlying
    concept here (a reference to something external attached to an
    asset); splitting them into three near-identical tables would be
    exactly the field duplication §2.7 itself warns against.

    `reference` is a plain URL/path string, not an uploaded file — same
    "field now, storage infrastructure later" precedent as
    Asset.barcode_value. There is no file storage backend (S3, local disk
    with upload handling, size/type limits) anywhere in this codebase to
    receive an actual upload.
    """

    __tablename__ = "asset_attachments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # "document" | "photo" | "other" — validated in
    # app/schemas/asset_attachment.py, not a DB enum, same convention as
    # Asset.status.
    attachment_type: Mapped[str] = mapped_column(String(20), nullable=False)

    reference: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # SET NULL, not RESTRICT — same reasoning as AuditLog.user_id: a user
    # account being removed later must never block-delete an attachment,
    # nor erase the record that it exists.
    uploaded_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
