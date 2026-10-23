"""create manufacturers and asset_models tables

Revision ID: c2e7a1f9d4b6
Revises: ae1ba839a382
Create Date: 2026-09-04 00:00:00.000000

Master-data lists for the Asset form's Manufacturer / Model dropdowns
(frontend/app.js), previously plain free-text fields. Admin-managed via
GET/POST/PUT/DELETE /api/v1/manufacturers and /api/v1/asset-models — same
pattern as the Job Role / Department master lists
(8a1c4f7e2b93_create_job_roles_and_departments_tables.py): both global
(not company-scoped) and independent flat lists (Model is not a foreign
key to Manufacturer, so picking one does not filter the other).

Seeds a starter set of common manufacturers/models so the Asset form's
dropdowns aren't empty on a fresh install — an admin can add more via
each master list's own page.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2e7a1f9d4b6"
down_revision: Union[str, Sequence[str], None] = "ae1ba839a382"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MANUFACTURERS = [
    "Dell",
    "HP",
    "Lenovo",
    "Apple",
    "ASUS",
    "Acer",
    "Microsoft",
    "Samsung",
    "Cisco",
    "Logitech",
]

_ASSET_MODELS = [
    "Latitude 5420",
    "Inspiron 15",
    "OptiPlex 7090",
    "EliteBook 840",
    "ThinkPad T14",
    "MacBook Pro 14",
    "Surface Laptop 5",
    "ZenBook 14",
    "Aspire 5",
    "Galaxy Tab S8",
]


def upgrade() -> None:
    manufacturers = op.create_table(
        "manufacturers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    asset_models = op.create_table(
        "asset_models",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.bulk_insert(manufacturers, [{"name": name, "is_active": True} for name in _MANUFACTURERS])
    op.bulk_insert(asset_models, [{"name": name, "is_active": True} for name in _ASSET_MODELS])


def downgrade() -> None:
    op.drop_table("asset_models")
    op.drop_table("manufacturers")
