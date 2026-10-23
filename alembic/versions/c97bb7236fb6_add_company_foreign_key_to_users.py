"""add company foreign key to users

Revision ID: c97bb7236fb6
Revises: 283d5f43314b
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c97bb7236fb6"
down_revision: Union[str, Sequence[str], None] = "283d5f43314b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Every existing user currently has a placeholder string company_id (usually
    # empty). Back them all onto one real "Casterly" company row so the new
    # foreign key has something valid to point at.
    existing = bind.execute(
        sa.text("SELECT id FROM companies WHERE name = 'Casterly'")
    ).fetchone()
    if existing:
        default_company_id = existing[0]
    else:
        result = bind.execute(
            sa.text(
                "INSERT INTO companies (name, company_type, is_active, created_at, updated_at) "
                "VALUES ('Casterly', 'internal', true, now(), now()) RETURNING id"
            )
        )
        default_company_id = result.fetchone()[0]

    op.add_column("users", sa.Column("company_id_fk", sa.Integer(), nullable=True))
    bind.execute(
        sa.text("UPDATE users SET company_id_fk = :cid").bindparams(cid=default_company_id)
    )

    op.drop_column("users", "company_id")
    op.alter_column("users", "company_id_fk", new_column_name="company_id")
    op.create_foreign_key(
        "fk_users_company_id_companies",
        "users",
        "companies",
        ["company_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_company_id_companies", "users", type_="foreignkey")
    op.alter_column("users", "company_id", new_column_name="company_id_fk")
    op.add_column("users", sa.Column("company_id", sa.String(length=100), nullable=True))
    op.drop_column("users", "company_id_fk")
