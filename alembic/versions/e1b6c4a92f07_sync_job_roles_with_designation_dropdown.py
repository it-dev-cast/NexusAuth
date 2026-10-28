"""sync job roles master with the Employee form's former designation list

Revision ID: e1b6c4a92f07
Revises: d9f3a7c5b182
Create Date: 2026-10-27 00:00:00.000000

The Employee form's Designation dropdown used to be a hardcoded list of 16
job titles. It is now filled from the Job Roles master, so every title that
was in that list must exist there or it would silently disappear from the
dropdown.

Data-only and idempotent: inserts each title that has no job role yet
(matched case-insensitively), and touches nothing else. A title that already
exists is left exactly as it is — including one an admin has deactivated
(that is a deliberate choice, so it is not re-activated here). No employee
row is changed.

Downgrade removes only the rows this migration added, and only if no
employee currently uses them (by job role or designation).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1b6c4a92f07"
down_revision: Union[str, Sequence[str], None] = "d9f3a7c5b182"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The exact options of the old hardcoded <select id="employee-designation-select">.
_FORMER_DESIGNATION_OPTIONS = [
    "Founder",
    "CEO",
    "CTO",
    "COO",
    "CFO",
    "Engineering Manager",
    "Product Manager",
    "Software Engineer",
    "Senior Software Engineer",
    "Designer",
    "Marketing Manager",
    "Sales Manager",
    "Account Executive",
    "Customer Support",
    "HR Manager",
    "Intern",
]

# Titles this migration actually inserted are not recorded anywhere, so the
# downgrade only considers the ones that are absent from the original seed
# (see 8a1c4f7e2b93) — never a title that was there before.
_ORIGINALLY_SEEDED = {
    "software engineer",
    "product manager",
    "sales executive",
    "marketing executive",
    "hr manager",
    "accountant",
    "operations manager",
    "customer support",
    "field technician",
    "administrator",
    "intern",
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = {
        row[0].lower() for row in bind.execute(sa.text("SELECT name FROM job_roles")).fetchall()
    }
    for name in _FORMER_DESIGNATION_OPTIONS:
        if name.lower() in existing:
            continue
        bind.execute(
            sa.text("INSERT INTO job_roles (name, is_active) VALUES (:name, true)"),
            {"name": name},
        )
        existing.add(name.lower())


def downgrade() -> None:
    bind = op.get_bind()
    for name in _FORMER_DESIGNATION_OPTIONS:
        if name.lower() in _ORIGINALLY_SEEDED:
            continue
        bind.execute(
            sa.text(
                "DELETE FROM job_roles WHERE lower(name) = lower(:name) "
                "AND NOT EXISTS (SELECT 1 FROM employees e "
                "WHERE lower(e.job_role) = lower(:name) OR lower(e.designation) = lower(:name))"
            ),
            {"name": name},
        )
