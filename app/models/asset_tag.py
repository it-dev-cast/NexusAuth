from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class AssetTag(Base):
    """Digital Twin "Tags" facet (NEXUS_ONE_ARCHITECTURE_PLAN §2.7) — also
    backs the "Search Metadata" facet: app/repositories/asset_repository.py's
    search matches against these alongside asset_tag/manufacturer/model.

    Free-form, per-asset labels an operator assigns (e.g. "fragile",
    "warranty-active") — not a shared master list like Manufacturer/Model,
    so this is a plain child table, not one of the global master-data
    modules (Department/Job Role/Application/Manufacturer/Asset Model).
    CASCADE on asset delete: a tag has no meaning once its asset is gone
    (unlike audit/event rows, which deliberately outlive their resource).
    """

    __tablename__ = "asset_tags"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tag: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("asset_id", "tag", name="uq_asset_tags_asset_id_tag"),)
