"""create job_roles and departments tables

Revision ID: 8a1c4f7e2b93
Revises: 6f52078ce90f
Create Date: 2026-08-27 00:00:00.000000

Master-data lists for the Employee form's Job role / Department dropdowns
(frontend/app.js), previously a fixed, hardcoded option list. Admin-managed
via GET/POST/PUT/DELETE /api/v1/job-roles and /api/v1/departments. Both are
global, not company-scoped — every company picks from the same shared
list, matching how the fixed dropdown already behaved.

Seeds the same option set the hardcoded dropdown previously offered, so an
existing deployment's Employee form keeps working with no visible change
until an admin edits the lists — this migration doesn't invent new default
values, it just moves the existing ones into a table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8a1c4f7e2b93"
down_revision: Union[str, Sequence[str], None] = "6f52078ce90f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_JOB_ROLES = [
    "Software Engineer",
    "Product Manager",
    "Sales Executive",
    "Marketing Executive",
    "HR Manager",
    "Accountant",
    "Operations Manager",
    "Customer Support",
    "Field Technician",
    "Administrator",
    "Intern",
]

_DEPARTMENTS = [
    "Engineering",
    "Sales",
    "Marketing",
    "Human Resources",
    "Finance",
    "Operations",
    "Customer Support",
    "IT",
    "Legal",
    "Administration",
]


def upgrade() -> None:
    job_roles = op.create_table(
        "job_roles",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    departments = op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.bulk_insert(job_roles, [{"name": name, "is_active": True} for name in _JOB_ROLES])
    op.bulk_insert(departments, [{"name": name, "is_active": True} for name in _DEPARTMENTS])


def downgrade() -> None:
    op.drop_table("departments")
    op.drop_table("job_roles")
