"""declare explicit fk cascade rules

Revision ID: 95090c9e1221
Revises: 344981c901cf
Create Date: 2026-08-20 00:00:00.000000

Entity Relationships & Constraints (Foundation Core Module 7): makes the
cascade behaviour of every existing foreign key explicit instead of relying
on Postgres's implicit default (NO ACTION).

- users.company_id -> companies.id     : RESTRICT (can't delete a company
  while users still reference it — companies are soft-deleted, never
  hard-deleted, so this is a safety net, not a normal code path)
- employees.company_id -> companies.id : RESTRICT (same reasoning)
- employees.user_id -> users.id        : SET NULL (if a user account is ever
  hard-deleted, the employee record survives, just unlinked — an employee
  existing without system login access is a normal state, not an error)
"""
from typing import Sequence, Union

from alembic import op


revision: str = "95090c9e1221"
down_revision: Union[str, Sequence[str], None] = "344981c901cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_users_company_id_companies", "users", type_="foreignkey")
    op.create_foreign_key(
        "fk_users_company_id_companies",
        "users",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("employees_company_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_company_id_fkey",
        "employees",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("employees_user_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_user_id_fkey",
        "employees",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("employees_user_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_user_id_fkey", "employees", "users", ["user_id"], ["id"]
    )

    op.drop_constraint("employees_company_id_fkey", "employees", type_="foreignkey")
    op.create_foreign_key(
        "employees_company_id_fkey", "employees", "companies", ["company_id"], ["id"]
    )

    op.drop_constraint("fk_users_company_id_companies", "users", type_="foreignkey")
    op.create_foreign_key(
        "fk_users_company_id_companies", "users", "companies", ["company_id"], ["id"]
    )
