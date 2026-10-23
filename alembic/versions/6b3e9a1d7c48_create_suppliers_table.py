"""create suppliers table

Revision ID: 6b3e9a1d7c48
Revises: 95090c9e1221
Create Date: 2026-08-21 00:00:00.000000

Foundation Core Module 5: Supplier Management. Suppliers are not scoped to
a Company (the doc lists no company_id for this module) — one flat,
Casterly-wide vendor list that Assets (Module 6) will reference by id.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b3e9a1d7c48"
down_revision: Union[str, Sequence[str], None] = "95090c9e1221"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("terms", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="onboarded"),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("suppliers")
