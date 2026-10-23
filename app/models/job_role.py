from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class JobRole(Base):
    """Master list of job roles/titles (e.g. "Software Engineer",
    "Field Technician") offered on the Employee form's Job role dropdown —
    see app/services/employee_service.py's role-inheritance fallback and
    frontend/app.js's job-role select. Global, not company-scoped: every
    company picks from the same shared list, matching how the dropdown
    already behaved before this master table existed (a fixed option
    list). Distinct from the RBAC Role (admin/operator/read_only,
    app/core/roles.py) — this is a job title, not a permission level.
    """

    __tablename__ = "job_roles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

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
