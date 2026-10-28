from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func as sql_func

from app.database.database import Base


class MasterItem(Base):
    """One row of any admin-managed master list that has no behaviour of its
    own: Employment Type, Asset Category, Asset Condition, Supplier Category,
    Supplier Type, Payment Terms, Location, Country, State, City.

    (Re-created from the session transcript after a file-name clash in this
    backup folder; this is the original models/master_item.py.)
    """

    __tablename__ = "master_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    master_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("master_items.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sql_func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sql_func.now(),
        onupdate=sql_func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_master_items_type_name_parent",
            "master_type",
            text("lower(name)"),
            text("coalesce(parent_id, 0)"),
            unique=True,
        ),
        Index(
            "uq_master_items_type_code",
            "master_type",
            text("lower(code)"),
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
    )
