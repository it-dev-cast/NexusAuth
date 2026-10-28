"""application master fields + access grant stamps

Revision ID: a7c2e9d4b6f1
Revises: f3a8d1b7c2e5
Create Date: 2026-10-27 00:00:00.000000

Application Master:
  * applications.code        - short unique identifier (e.g. HR_MODULE). Existing
                               rows get a code derived from their name (upper-case,
                               non-alphanumerics -> "_"); a clash with an earlier
                               row gets the row id appended, so nothing is merged
                               or renamed. Then NOT NULL + a unique index.
  * applications.description - optional free text.
  * applications.url         - optional http(s) address of the application.

Access grants (employee_applications):
  * granted_at          - when the grant was made. Rows that existed before this
                          migration stay NULL (the real date was never recorded);
                          every new grant gets now() from the column default.
  * granted_by_user_id  - who made it (NULL for grants made through the employee
                          form and for rows that predate this migration).

Nothing is deleted or rewritten: existing applications, employees and grants are
untouched apart from the new columns. Downgrade drops only the new columns.
"""
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2e9d4b6f1"
down_revision: Union[str, Sequence[str], None] = "f3a8d1b7c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CODE_MAX = 40


def _code_from_name(name: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
    return (code or "APP")[:_CODE_MAX]


def upgrade() -> None:
    op.add_column("applications", sa.Column("code", sa.String(length=_CODE_MAX), nullable=True))
    op.add_column("applications", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("url", sa.String(length=500), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, name FROM applications ORDER BY id")).fetchall()
    taken: set[str] = set()
    for app_id, name in rows:
        code = _code_from_name(name)
        if code in taken:
            suffix = f"_{app_id}"
            code = code[: _CODE_MAX - len(suffix)] + suffix
        taken.add(code)
        bind.execute(
            sa.text("UPDATE applications SET code = :code WHERE id = :id"), {"code": code, "id": app_id}
        )

    op.alter_column("applications", "code", nullable=False)
    op.create_index("uq_applications_code", "applications", ["code"], unique=True)

    # Existing grants keep granted_at NULL (unknown); only new rows get now().
    op.add_column("employee_applications", sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TABLE employee_applications ALTER COLUMN granted_at SET DEFAULT now()")
    op.add_column("employee_applications", sa.Column("granted_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_employee_applications_granted_by_user",
        "employee_applications",
        "users",
        ["granted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_employee_applications_granted_by_user", "employee_applications", type_="foreignkey")
    op.drop_column("employee_applications", "granted_by_user_id")
    op.drop_column("employee_applications", "granted_at")
    op.drop_index("uq_applications_code", table_name="applications")
    op.drop_column("applications", "url")
    op.drop_column("applications", "description")
    op.drop_column("applications", "code")
