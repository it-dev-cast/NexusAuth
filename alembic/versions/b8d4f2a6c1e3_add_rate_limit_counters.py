"""add rate_limit_counters

Revision ID: b8d4f2a6c1e3
Revises: a7c2e9d4b6f1
Create Date: 2026-10-28 00:00:00.000000

Shared request counters for the login/register rate limiter, so the limit
holds across every worker process and container instead of per process.
One row per (endpoint, caller) key; purely additive, nothing existing is
touched. Downgrade drops only this table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b8d4f2a6c1e3"
down_revision: Union[str, Sequence[str], None] = "a7c2e9d4b6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("rate_limit_counters")
