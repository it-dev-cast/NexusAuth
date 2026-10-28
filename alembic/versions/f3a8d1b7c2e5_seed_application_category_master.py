"""seed the application_category master list

Revision ID: f3a8d1b7c2e5
Revises: e1b6c4a92f07
Create Date: 2026-10-27 00:00:00.000000

The Application form's Category dropdown used to be a hardcoded list
(Core, People, Assets, Operations, Administration). It is now filled from the
`application_category` list in `master_items` (shown on the Master Management
page), so those values — plus every category already saved on an application —
are inserted here. Data-only and idempotent: matched case-insensitively, an
existing item is left exactly as it is, and no application row is changed.

Downgrade removes only the `application_category` rows.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8d1b7c2e5"
down_revision: Union[str, Sequence[str], None] = "e1b6c4a92f07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FORMER_OPTIONS = ["Core", "People", "Assets", "Operations", "Administration"]
_NAME_MAX = 150


def upgrade() -> None:
    bind = op.get_bind()
    existing = {
        row[0].lower()
        for row in bind.execute(
            sa.text("SELECT name FROM master_items WHERE master_type = 'application_category'")
        ).fetchall()
    }
    saved = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT DISTINCT btrim(category) FROM applications "
                "WHERE category IS NOT NULL AND btrim(category) <> '' ORDER BY 1"
            )
        ).fetchall()
        if len(row[0]) <= _NAME_MAX
    ]
    for name in _FORMER_OPTIONS + saved:
        if name.lower() in existing:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO master_items (master_type, name, is_active) "
                "VALUES ('application_category', :name, true)"
            ),
            {"name": name},
        )
        existing.add(name.lower())


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM master_items WHERE master_type = 'application_category'"))
