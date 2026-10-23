"""fix users.role column default

Revision ID: a4e7c3701650
Revises: c50668c12e48
Create Date: 2026-08-24 00:00:00.000000

`users.role` had a DB-level `server_default` of 'user' (set when the
column was first added in b7c4e91a2d10), but 'user' has never been a
valid role — see app/core/roles.py's ALL_ROLES ({admin, operator,
read_only}). Every application code path that creates a User
(register_user, bootstrap_admin) already sets role explicitly, so this
default was never actually exercised in practice, but a row inserted
without an explicit role (a raw INSERT, a future script) would silently
get an invalid role that fails every require_roles()/get_admin_user()
check.

Metadata-only change: updates the column's DEFAULT clause for future
inserts. Does not touch any existing row's stored role value — no data
migration, nothing destructive.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4e7c3701650"
down_revision: Union[str, Sequence[str], None] = "c50668c12e48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=50),
        server_default="read_only",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=50),
        server_default="user",
        existing_nullable=False,
    )
