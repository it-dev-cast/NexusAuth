"""create assets table

Revision ID: 4d8f2b6c9a13
Revises: 6b3e9a1d7c48
Create Date: 2026-08-21 00:00:00.000000

Foundation Core Module 6: Asset Management (core fields only). Every asset
must reference a real Supplier — RESTRICT mirrors the same "safety net, not
a normal code path" reasoning used for companies.id / users.id, since
Suppliers are never hard-deleted either.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d8f2b6c9a13"
down_revision: Union[str, Sequence[str], None] = "6b3e9a1d7c48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("asset_tag", sa.String(length=100), nullable=False, unique=True, index=True),
        sa.Column("manufacturer", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("serial_number", sa.String(length=255), nullable=True, index=True),
        sa.Column(
            "supplier_id",
            sa.Integer(),
            sa.ForeignKey("suppliers.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="registered"),
        sa.Column("barcode_value", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("assets")
