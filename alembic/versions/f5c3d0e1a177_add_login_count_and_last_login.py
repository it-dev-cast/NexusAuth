"""add login count and last login

Revision ID: f5c3d0e1a177
Revises: e4a1b8c2d066
Create Date: 2026-08-14 15:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5c3d0e1a177"
down_revision: Union[str, Sequence[str], None] = "e4a1b8c2d066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "login_count" not in columns:
        op.add_column(
            "users",
            sa.Column("login_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "last_login_at" not in columns:
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "last_login_at" in columns:
        op.drop_column("users", "last_login_at")
    if "login_count" in columns:
        op.drop_column("users", "login_count")
