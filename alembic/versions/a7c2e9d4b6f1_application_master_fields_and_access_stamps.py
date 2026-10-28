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

    bind = op.get_bind()

    inspector = sa.inspect(bind)
 
    # ---------------------------------------------------------

    # applications

    # Production DB may already contain fields from the earlier

    # manual NexusAuth hardening.

    # ---------------------------------------------------------

    app_columns = {

        col["name"]: col

        for col in inspector.get_columns("applications")

    }
 
    # Existing production DB already has code VARCHAR(100).

    # Do not recreate it or overwrite existing codes.

    if "code" not in app_columns:

        op.add_column(

            "applications",

            sa.Column("code", sa.String(length=_CODE_MAX), nullable=True),

        )
 
        rows = bind.execute(

            sa.text("SELECT id, name FROM applications ORDER BY id")

        ).fetchall()
 
        taken: set[str] = set()
 
        for app_id, name in rows:

            code = _code_from_name(name)
 
            if code in taken:

                suffix = f"_{app_id}"

                code = code[: _CODE_MAX - len(suffix)] + suffix
 
            taken.add(code)
 
            bind.execute(

                sa.text(

                    "UPDATE applications SET code = :code WHERE id = :id"

                ),

                {"code": code, "id": app_id},

            )
 
        op.alter_column(

            "applications",

            "code",

            nullable=False,

        )
 
    # Existing production DB already has description.

    if "description" not in app_columns:

        op.add_column(

            "applications",

            sa.Column("description", sa.Text(), nullable=True),

        )
 
    # New application code expects "url".

    # Older production schema uses "base_url".

    if "url" not in app_columns:

        op.add_column(

            "applications",

            sa.Column("url", sa.String(length=500), nullable=True),

        )
 
        if "base_url" in app_columns:

            bind.execute(

                sa.text(

                    """

                    UPDATE applications

                    SET url = base_url

                    WHERE url IS NULL

                      AND base_url IS NOT NULL

                    """

                )

            )
 
    # Create unique code index only if not already present.

    inspector = sa.inspect(bind)
 
    has_code_unique = False
 
    for idx in inspector.get_indexes("applications"):

        if (

            idx.get("unique")

            and idx.get("column_names") == ["code"]

        ):

            has_code_unique = True

            break
 
    if not has_code_unique:

        for constraint in inspector.get_unique_constraints("applications"):

            if constraint.get("column_names") == ["code"]:

                has_code_unique = True

                break
 
    if not has_code_unique:

        op.create_index(

            "uq_applications_code",

            "applications",

            ["code"],

            unique=True,

        )
 
    # ---------------------------------------------------------

    # employee_applications

    # ---------------------------------------------------------

    inspector = sa.inspect(bind)
 
    grant_columns = {

        col["name"]: col

        for col in inspector.get_columns("employee_applications")

    }
 
    # Already exists in the hardened DB.

    if "granted_at" not in grant_columns:

        op.add_column(

            "employee_applications",

            sa.Column(

                "granted_at",

                sa.DateTime(timezone=True),

                nullable=True,

            ),

        )
 
        op.execute(

            "ALTER TABLE employee_applications "

            "ALTER COLUMN granted_at SET DEFAULT now()"

        )
 
    # New code uses granted_by_user_id.

    # Old hardened schema uses granted_by.

    if "granted_by_user_id" not in grant_columns:

        op.add_column(

            "employee_applications",

            sa.Column(

                "granted_by_user_id",

                sa.Integer(),

                nullable=True,

            ),

        )
 
        if "granted_by" in grant_columns:

            bind.execute(

                sa.text(

                    """

                    UPDATE employee_applications

                    SET granted_by_user_id = granted_by

                    WHERE granted_by_user_id IS NULL

                      AND granted_by IS NOT NULL

                    """

                )

            )
 
    # Add FK only if it does not already exist.

    inspector = sa.inspect(bind)
 
    fk_exists = False
 
    for fk in inspector.get_foreign_keys("employee_applications"):

        if (

            fk.get("constrained_columns") == ["granted_by_user_id"]

            and fk.get("referred_table") == "users"

        ):

            fk_exists = True

            break
 
    if not fk_exists:

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
