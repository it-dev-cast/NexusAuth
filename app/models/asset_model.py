from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class AssetModel(Base):
    """Master list of asset models (e.g. "Latitude 5420", "MacBook Pro
    14") offered on the Asset form's Model dropdown — see
    app/services/asset_service.py and frontend/app.js's model select.
    Global, flat, and independent of Manufacturer (not a FK to it) — per
    the same "one shared list, not scoped to anything else" pattern as
    Job Role / Department (app/models/job_role.py), so picking a
    Manufacturer does not filter which Models are offered.
    """

    __tablename__ = "asset_models"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
