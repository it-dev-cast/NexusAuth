from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # "internal" = Casterly itself, "external" = a customer/partner company.
    company_type: Mapped[str] = mapped_column(String(20), nullable=False, default="external")

    address: Mapped[str | None] = mapped_column(String(500), nullable=True)

    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Per-company defaults as free-form JSON-in-text for now — a real JSON
    # column can replace this once Postgres-specific types are wired in;
    # keeping it a plain string avoids a dialect-specific migration today.
    # Consumed today by Employee creation (app/services/employee_service.py's
    # _company_defaults) for role inheritance from Company defaults, reading
    # optional "default_job_role" / "default_department" keys.
    config_defaults: Mapped[str | None] = mapped_column(String(1000), nullable=True)

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
