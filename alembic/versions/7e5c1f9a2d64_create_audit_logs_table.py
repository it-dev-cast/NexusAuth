"""create audit_logs table

Revision ID: 7e5c1f9a2d64
Revises: 4d8f2b6c9a13
Create Date: 2026-08-21 00:00:00.000000

Foundation Core Module 8: Audit & Change Tracking. user_id uses SET NULL,
not RESTRICT, so a later user deletion can never be blocked by — or erase —
the audit trail of what that user did.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7e5c1f9a2d64"
down_revision: Union[str, Sequence[str], None] = "4d8f2b6c9a13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("action", sa.String(length=50), nullable=False, index=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
