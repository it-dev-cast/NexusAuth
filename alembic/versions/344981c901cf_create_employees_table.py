"""create employees table

Revision ID: 344981c901cf
Revises: c97bb7236fb6
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "344981c901cf"
down_revision: Union[str, Sequence[str], None] = "c97bb7236fb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False, index=True),
        sa.Column("job_role", sa.String(length=100), nullable=False, server_default="Employee"),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("cost_center", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="onboarded"),
        sa.Column("bank_account_number", sa.String(length=50), nullable=True),
        sa.Column("bank_ifsc", sa.String(length=20), nullable=True),
        sa.Column("pan_number", sa.String(length=20), nullable=True),
        sa.Column("aadhaar_number", sa.String(length=20), nullable=True),
        sa.Column("residence_proof_reference", sa.String(length=500), nullable=True),
        sa.Column("photo_reference", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "email", name="uq_employees_company_email"),
    )


def downgrade() -> None:
    op.drop_table("employees")
