"""add revoked tokens and access jti

Revision ID: d2e8f6c1a044
Revises: b7c4e91a2d10
Create Date: 2026-08-14 12:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e8f6c1a044"
down_revision: Union[str, Sequence[str], None] = "b7c4e91a2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    session_columns = {
        column["name"] for column in inspector.get_columns("auth_sessions")
    }
    if "access_token_jti" not in session_columns:
        op.add_column(
            "auth_sessions",
            sa.Column("access_token_jti", sa.String(length=255), nullable=True),
        )
        op.create_index(
            "ix_auth_sessions_access_token_jti",
            "auth_sessions",
            ["access_token_jti"],
        )

    if "revoked_tokens" not in inspector.get_table_names():
        op.create_table(
            "revoked_tokens",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("jti", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("token_type", sa.String(length=50), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.String(length=100), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("jti"),
        )
        op.create_index("ix_revoked_tokens_id", "revoked_tokens", ["id"])
        op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"], unique=True)
        op.create_index("ix_revoked_tokens_user_id", "revoked_tokens", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "revoked_tokens" in inspector.get_table_names():
        op.drop_index("ix_revoked_tokens_user_id", table_name="revoked_tokens")
        op.drop_index("ix_revoked_tokens_jti", table_name="revoked_tokens")
        op.drop_index("ix_revoked_tokens_id", table_name="revoked_tokens")
        op.drop_table("revoked_tokens")

    session_columns = {
        column["name"] for column in inspector.get_columns("auth_sessions")
    }
    if "access_token_jti" in session_columns:
        op.drop_index(
            "ix_auth_sessions_access_token_jti",
            table_name="auth_sessions",
        )
        op.drop_column("auth_sessions", "access_token_jti")
