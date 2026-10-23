from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Manufacturer(Base):
    """Master list of asset manufacturers (e.g. "Dell", "HP") offered on
    the Asset form's Manufacturer dropdown — see
    app/services/asset_service.py and frontend/app.js's manufacturer
    select. Global, not company-scoped: every company's assets pick from
    the same shared list, matching the Job Role / Department master
    lists this is modeled on (app/models/job_role.py).
    """

    __tablename__ = "manufacturers"

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
