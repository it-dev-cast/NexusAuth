"""add master_items table and master-backed columns

Revision ID: d9f3a7c5b182
Revises: 7a3c9e5d1b42
Create Date: 2026-10-27 00:00:00.000000

Adds the generic `master_items` table (app/models/master_item.py) behind the
new Master Data screens, and the five nullable text columns that hold a
chosen value by name:

    employees.employment_type
    assets.category, assets.condition, assets.location
    suppliers.supplier_type

Purely additive: no existing column or row is changed. Existing records keep
NULL in the new columns.

Seeds starter values so the new dropdowns aren't empty:
  * Employment Type, Asset Category, Asset Condition, Supplier Type — a small
    common set an admin can edit.
  * Supplier Category and Payment Terms — the exact options the Supplier form
    used to hardcode, PLUS every distinct category/terms value already saved
    on a supplier, so nothing a supplier currently carries is missing from
    the lists (case-insensitive duplicates are collapsed; values longer than
    a master name allows stay on the supplier and are simply not seeded).
Country, State, City and Location are NOT seeded — those are your own data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9f3a7c5b182"
down_revision: Union[str, Sequence[str], None] = "7a3c9e5d1b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NAME_MAX = 150

_SEEDS = {
    "employment_type": ["Full-time", "Part-time", "Contract", "Temporary", "Intern", "Consultant"],
    "asset_category": [
        "Laptop",
        "Desktop",
        "Monitor",
        "Mobile Phone",
        "Tablet",
        "Printer",
        "Networking Equipment",
        "Peripherals",
        "Furniture",
    ],
    "asset_condition": ["New", "Good", "Fair", "Poor", "Damaged"],
    "supplier_type": ["Manufacturer", "Distributor", "Reseller", "Service Provider", "Contractor"],
    # The options the Supplier form hardcoded before this migration.
    "supplier_category": [
        "Hardware",
        "Software",
        "Office Supplies",
        "Logistics",
        "Facilities",
        "Maintenance & Support",
        "Consulting",
        "Raw Materials",
    ],
    "payment_terms": [
        "Due on Receipt",
        "Net 15",
        "Net 30",
        "Net 45",
        "Net 60",
        "Net 90",
        "COD",
        "Advance Payment",
        "50% Advance, 50% on Delivery",
    ],
}


def upgrade() -> None:
    master_items = op.create_table(
        "master_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("master_type", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=_NAME_MAX), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "parent_id",
            sa.Integer(),
            sa.ForeignKey("master_items.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_master_items_id", "master_items", ["id"])
    op.create_index("ix_master_items_master_type", "master_items", ["master_type"])
    op.create_index("ix_master_items_parent_id", "master_items", ["parent_id"])
    # Duplicate prevention in the database itself (the service checks first
    # to give a friendly message; this is the backstop against a race).
    op.execute(
        "CREATE UNIQUE INDEX uq_master_items_type_name_parent "
        "ON master_items (master_type, lower(name), coalesce(parent_id, 0))"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_master_items_type_code "
        "ON master_items (master_type, lower(code)) WHERE code IS NOT NULL"
    )

    op.add_column("employees", sa.Column("employment_type", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("condition", sa.String(length=100), nullable=True))
    op.add_column("assets", sa.Column("location", sa.String(length=150), nullable=True))
    op.add_column("suppliers", sa.Column("supplier_type", sa.String(length=100), nullable=True))

    bind = op.get_bind()

    def existing(column: str) -> list[str]:
        rows = bind.execute(
            sa.text(
                f"SELECT DISTINCT btrim({column}) FROM suppliers "
                f"WHERE {column} IS NOT NULL AND btrim({column}) <> '' ORDER BY 1"
            )
        ).fetchall()
        return [r[0] for r in rows if len(r[0]) <= _NAME_MAX]

    seeds = {key: list(values) for key, values in _SEEDS.items()}
    # Fold in what suppliers already carry, so no saved value is missing.
    seeds["supplier_category"] += existing("category")
    seeds["payment_terms"] += existing("terms")

    rows = []
    for master_type, names in seeds.items():
        seen: set[str] = set()
        for name in names:
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            rows.append({"master_type": master_type, "name": name, "is_active": True})
    op.bulk_insert(master_items, rows)


def downgrade() -> None:
    op.drop_column("suppliers", "supplier_type")
    op.drop_column("assets", "location")
    op.drop_column("assets", "condition")
    op.drop_column("assets", "category")
    op.drop_column("employees", "employment_type")
    op.drop_table("master_items")
