"""add role to users

Revision ID: b7c4e91a2d10
Revises: 78348d455eac
Create Date: 2026-08-14 12:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7c4e91a2d10"
down_revision: Union[str, Sequence[str], None] = "78348d455eac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    if "role" not in columns:
        op.add_column(
            "users",
            sa.Column(
                "role",
                sa.String(),
                nullable=False,
                server_default="user",
            ),
        )


def downgrade() -> None:
    op.drop_column("users", "role")
