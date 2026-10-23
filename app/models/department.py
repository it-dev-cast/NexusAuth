from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Department(Base):
    """Master list of departments (e.g. "Engineering", "Finance") offered
    on the Employee form's Department dropdown — see
    app/services/employee_service.py's role-inheritance fallback and
    frontend/app.js's department select. Global, not company-scoped: every
    company picks from the same shared list, matching how the dropdown
    already behaved before this master table existed (a fixed option
    list).
    """

    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free text, not a FK to employees.id: this table is global/shared
    # across every company (see class docstring), so a single "Engineering"
    # row can't point at one company's Employee as its manager without
    # being wrong for every other company using the same shared row.
    manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Self-referencing hierarchy (e.g. "Support" under "Customer Success").
    # Same pattern as Employee.manager_id — cycle validation lives in
    # app/services/department_service.py via app.core.graph_utils.creates_cycle,
    # not here.
    parent_department_id: Mapped[int | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )

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
