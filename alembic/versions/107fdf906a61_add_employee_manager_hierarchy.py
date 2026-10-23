"""add employee manager hierarchy

Revision ID: 107fdf906a61
Revises: a4e7c3701650
Create Date: 2026-08-24 14:57:35.774859

Foundation Core Module 7 ("Circular dependency detection") had a correct,
tested utility (app/core/graph_utils.py) sitting unused because nothing in
the schema was hierarchical yet. This adds the first such relationship —
an Employee's manager, self-referencing employees.id — so that utility has
something real to protect. Cycle validation on assignment lives in
app/services/employee_service.py (_validate_manager_assignment), not here.

ON DELETE SET NULL, same reasoning as Employee.user_id: exiting/removing a
manager should unlink their reports, not cascade-delete or block on them.
Nullable and additive — no existing row is affected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '107fdf906a61'
down_revision: Union[str, Sequence[str], None] = 'a4e7c3701650'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("manager_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_employees_manager_id"), "employees", ["manager_id"], unique=False
    )
    op.create_foreign_key(
        "fk_employees_manager_id_employees",
        "employees",
        "employees",
        ["manager_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_employees_manager_id_employees", "employees", type_="foreignkey"
    )
    op.drop_index(op.f("ix_employees_manager_id"), table_name="employees")
    op.drop_column("employees", "manager_id")
