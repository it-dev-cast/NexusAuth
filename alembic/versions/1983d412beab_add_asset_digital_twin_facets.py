"""add asset digital twin facets

Revision ID: 1983d412beab
Revises: 498b79eb7443
Create Date: 2026-09-08 00:00:00.000000

Foundation Core Phase 2 deliverable: "Asset Digital Twin facet architecture"
(NEXUS_ONE_ARCHITECTURE_PLAN §2.7, §9 Phase 2). §2.7 describes twelve
facets for a single, centrally-modeled Asset: Identity, State, Timeline,
Relationships, Documents, Media, Financials, AI Memory, Audit, Search
Metadata, Tags, Attachments.

Where each facet actually lands, and why some add nothing here:

- Identity / State / Relationships / Audit — already covered by the
  existing assets table + supplier_id FK + audit_logs, untouched.
- Timeline — no new table. Derived from the events table (see
  app/services/event_service.py) filtered by resource_type="asset",
  resource_id — the plan's own §2.6 already produces exactly this history
  as a side effect of every audited asset action, so a second, duplicate
  history table would violate its own "add facets they own, not duplicate
  fields" rule.
- Financials — three new nullable columns on assets, below.
- Tags / Search Metadata — the new asset_tags table below; search
  (app/repositories/asset_repository.py) is extended to match against it.
- Documents / Media / Attachments — one shared asset_attachments table
  below (they are the same underlying concept — a reference to something
  external — not three separate ones). Same "field preparation, no
  storage infrastructure" precedent as assets.barcode_value: `reference`
  is a plain string (a URL/path), not an uploaded file; there is no file
  storage backend in this codebase to receive one.
- AI Memory — explicitly not built. There is no AI/LLM integration
  anywhere in this codebase yet (the plan's own §1 tech stack lists
  OpenRouter as external and not yet wired up) — nothing to attach memory
  to or generate it from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1983d412beab"
down_revision: Union[str, Sequence[str], None] = "498b79eb7443"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("purchase_cost", sa.Numeric(12, 2), nullable=True))
    op.add_column("assets", sa.Column("current_value", sa.Numeric(12, 2), nullable=True))
    op.add_column("assets", sa.Column("currency", sa.String(length=3), nullable=True))

    op.create_table(
        "asset_tags",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tag", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("asset_id", "tag", name="uq_asset_tags_asset_id_tag"),
    )
    op.create_index("ix_asset_tags_tag", "asset_tags", ["tag"])

    op.create_table(
        "asset_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "asset_id",
            sa.Integer(),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # "document" | "photo" | "other" — validated in
        # app/schemas/asset_attachment.py, not a DB enum, same convention
        # as assets.status.
        sa.Column("attachment_type", sa.String(length=20), nullable=False),
        # A URL/path reference, not an uploaded file — see module docstring.
        sa.Column("reference", sa.String(length=500), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("asset_attachments")
    op.drop_index("ix_asset_tags_tag", table_name="asset_tags")
    op.drop_table("asset_tags")
    op.drop_column("assets", "currency")
    op.drop_column("assets", "current_value")
    op.drop_column("assets", "purchase_cost")
