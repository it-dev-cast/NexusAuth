"""create companies table

Revision ID: 283d5f43314b
Revises: f5c3d0e1a177
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "283d5f43314b"
down_revision: Union[str, Sequence[str], None] = "f5c3d0e1a177"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("company_type", sa.String(length=20), nullable=False, server_default="external"),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("config_defaults", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("companies")
