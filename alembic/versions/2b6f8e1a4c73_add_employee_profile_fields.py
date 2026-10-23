"""add employee profile fields (first/last name, employee_code, designation, phone, linkedin)

Revision ID: 2b6f8e1a4c73
Revises: 1983d412beab
Create Date: 2026-09-28 00:00:00.000000

Employee page fields requested: first name, last name, email (already
existed), job role (already existed), department (already existed),
employee id, designation, phone number, photo (already existed as
photo_reference), linkedin url.

full_name is split into first_name/last_name (both NOT NULL, backfilled
below) rather than kept alongside them — a single source of truth, not two
that could drift. Every existing read of "the employee's name" keeps
working unchanged via a new Employee.full_name Python property
(app/models/employee.py) computed from the two real columns; there is no
full_name column any more, so nothing can write to it directly.

employee_code and designation are plain nullable strings (employee_code
uniquely constrained per company, like email). phone_number joins the
existing EncryptedString PII columns (bank/PAN/Aadhaar/etc. — see
c50668c12e48) since it's the same class of contact PII. linkedin_url is a
plain, unencrypted String — a public profile link, not private PII.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2b6f8e1a4c73"
down_revision: Union[str, Sequence[str], None] = "1983d412beab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("first_name", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("last_name", sa.String(length=255), nullable=True))
    op.add_column("employees", sa.Column("employee_code", sa.String(length=50), nullable=True))
    op.add_column("employees", sa.Column("designation", sa.String(length=150), nullable=True))
    # Text, not a bounded VARCHAR — same reasoning as c50668c12e48's PII
    # columns: this goes through EncryptedString, and a Fernet token is
    # meaningfully longer than the phone number it wraps.
    op.add_column("employees", sa.Column("phone_number", sa.Text(), nullable=True))
    op.add_column("employees", sa.Column("linkedin_url", sa.String(length=500), nullable=True))

    op.create_index(
        "ix_employees_employee_code", "employees", ["employee_code"], unique=False
    )

    # Backfill: split each existing full_name on its first space.
    # "Priya Sharma" -> first_name="Priya", last_name="Sharma".
    # A single-word value (no space) becomes first_name=<value>,
    # last_name="" — a valid, non-null empty string, not a guess at a
    # surname that isn't there.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE employees SET
                first_name = split_part(full_name, ' ', 1),
                last_name = CASE
                    WHEN position(' ' in full_name) > 0
                    THEN trim(substring(full_name from position(' ' in full_name) + 1))
                    ELSE ''
                END
            """
        )
    )

    op.alter_column("employees", "first_name", existing_type=sa.String(length=255), nullable=False)
    op.alter_column("employees", "last_name", existing_type=sa.String(length=255), nullable=False)

    op.drop_column("employees", "full_name")

    op.create_unique_constraint(
        "uq_employees_company_employee_code", "employees", ["company_id", "employee_code"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_employees_company_employee_code", "employees", type_="unique")

    op.add_column("employees", sa.Column("full_name", sa.String(length=255), nullable=True))
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE employees SET full_name = trim(both ' ' from (first_name || ' ' || last_name))
            """
        )
    )
    op.alter_column("employees", "full_name", existing_type=sa.String(length=255), nullable=False)

    op.drop_index("ix_employees_employee_code", table_name="employees")
    op.drop_column("employees", "linkedin_url")
    op.drop_column("employees", "phone_number")
    op.drop_column("employees", "designation")
    op.drop_column("employees", "employee_code")
    op.drop_column("employees", "last_name")
    op.drop_column("employees", "first_name")
