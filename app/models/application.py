from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base

# Many-to-many join table between Employee and Application — an employee
# can be granted access to any number of applications/modules (Dashboard,
# Refurbishment, HR Module, ...), and one application applies to many
# employees. A plain association table (no extra columns of its own) is
# enough here — see Employee.applications in app/models/employee.py for
# the ORM side; Application itself deliberately has no back-reference
# relationship, since nothing in this app needs "every employee with
# access to X" loaded as ORM objects (application_repository's
# count_employees_by_application answers the one place that needs a
# count, via a plain join, not a loaded relationship).
#
# granted_at / granted_by_user_id stamp when and by whom a grant was made.
# They are filled by the access endpoints (app/services/application_access_
# service.py); a grant made through the employee form still gets granted_at
# from the column default, with no grantor. Rows from before the columns
# existed keep NULL for both. Revoking removes the row — the grant/revoke
# history is the audit log (actions grant_access / revoke_access).
employee_applications = Table(
    "employee_applications",
    Base.metadata,
    Column("employee_id", ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True),
    Column("application_id", ForeignKey("applications.id", ondelete="CASCADE"), primary_key=True),
    Column("granted_at", DateTime(timezone=True), server_default=func.now(), nullable=True),
    Column("granted_by_user_id", ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
)


class Application(Base):
    """Master list of application/module names an employee can be granted
    access to (e.g. "Dashboard", "Refurbishment", "HR Module") — shown as a
    multi-select checkbox group on the Employee form, the same way
    Department/JobRole back their own dropdown fields (see those models'
    docstrings). Unlike Department/JobRole, which are free-text fields on
    Employee that merely happen to be *populated from* their master list
    (with an "Other" escape hatch), Application access is a real
    many-to-many relationship — there's no free-text equivalent of
    "checking a box for an app that doesn't exist yet". Global, not
    company-scoped: every company grants access from the same shared list.
    """

    __tablename__ = "applications"
    __table_args__ = (Index("uq_applications_code", "code", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Short, unique, upper-case identifier (HR_MODULE) — normalised by
    # ApplicationCreateRequest/UpdateRequest; unique across the master.
    code: Mapped[str] = mapped_column(String(40), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional http(s) address of the application. Informational only: this
    # master records who is meant to have access, it does not log anyone in to
    # (or provision accounts in) the application itself.
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Free-text grouping label (e.g. "Core", "People", "Assets",
    # "Operations", "Administration") — purely presentational, groups the
    # Employee form's checkbox grid into headed sections instead of one
    # flat list of 20+ boxes. Nullable: an application without a category
    # still works, it just renders under an "Other" bucket in the grid.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

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
