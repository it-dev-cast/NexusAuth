"""add department hierarchy and details

Revision ID: b2f9d4a6c815
Revises: 8a1c4f7e2b93
Create Date: 2026-08-28 11:15:00.000000

Phase 1 of the Departments feature build-out: adds a description, a
manager (free text — Department is a global, company-wide master list per
its own docstring, so linking to one specific Employee row would be wrong:
a shared "Engineering" department can't have a single company's employee
as its manager for every company that uses it), and a self-referencing
parent_department_id for a department hierarchy.

parent_department_id follows the exact same pattern as
107fdf906a61_add_employee_manager_hierarchy.py: nullable, ON DELETE SET
NULL (removing a parent should unlink its children, not cascade-delete or
block), cycle validation lives in app/services/department_service.py via
the same app/core/graph_utils.creates_cycle already used for Employee
managers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2f9d4a6c815"
down_revision: Union[str, Sequence[str], None] = "8a1c4f7e2b93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("departments")}

    if "description" not in columns:
        op.add_column("departments", sa.Column("description", sa.Text(), nullable=True))
    if "manager_name" not in columns:
        op.add_column("departments", sa.Column("manager_name", sa.String(length=255), nullable=True))
    if "parent_department_id" not in columns:
        op.add_column("departments", sa.Column("parent_department_id", sa.Integer(), nullable=True))
        op.create_index(
            op.f("ix_departments_parent_department_id"), "departments", ["parent_department_id"], unique=False
        )
        op.create_foreign_key(
            "fk_departments_parent_department_id_departments",
            "departments",
            "departments",
            ["parent_department_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("departments")}

    if "parent_department_id" in columns:
        op.drop_constraint(
            "fk_departments_parent_department_id_departments", "departments", type_="foreignkey"
        )
        op.drop_index(op.f("ix_departments_parent_department_id"), table_name="departments")
        op.drop_column("departments", "parent_department_id")
    if "manager_name" in columns:
        op.drop_column("departments", "manager_name")
    if "description" in columns:
        op.drop_column("departments", "description")
