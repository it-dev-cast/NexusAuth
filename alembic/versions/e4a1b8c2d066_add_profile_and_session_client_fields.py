"""add profile and session client fields

Revision ID: e4a1b8c2d066
Revises: d2e8f6c1a044
Create Date: 2026-08-14 14:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e4a1b8c2d066"
down_revision: Union[str, Sequence[str], None] = "d2e8f6c1a044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "full_name" not in user_columns:
        op.add_column("users", sa.Column("full_name", sa.String(length=255), nullable=True))
    if "company_id" not in user_columns:
        op.add_column("users", sa.Column("company_id", sa.String(length=100), nullable=True))

    session_columns = {
        column["name"] for column in inspector.get_columns("auth_sessions")
    }
    if "ip_address" not in session_columns:
        op.add_column(
            "auth_sessions",
            sa.Column("ip_address", sa.String(length=45), nullable=True),
        )
    if "user_agent" not in session_columns:
        op.add_column(
            "auth_sessions",
            sa.Column("user_agent", sa.String(length=512), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    session_columns = {
        column["name"] for column in inspector.get_columns("auth_sessions")
    }
    if "user_agent" in session_columns:
        op.drop_column("auth_sessions", "user_agent")
    if "ip_address" in session_columns:
        op.drop_column("auth_sessions", "ip_address")

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    if "company_id" in user_columns:
        op.drop_column("users", "company_id")
    if "full_name" in user_columns:
        op.drop_column("users", "full_name")
