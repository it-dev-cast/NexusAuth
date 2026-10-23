"""create events table

Revision ID: 498b79eb7443
Revises: c2e7a1f9d4b6
Create Date: 2026-09-07 00:00:00.000000

Foundation Core Phase 2 deliverable: "Event emission infrastructure"
(NEXUS_ONE_ARCHITECTURE_PLAN §2.6, §9 Phase 2). Every state change already
flowing through app/services/audit_service.record_audit_event now also
publishes a row here (see app/services/event_service.publish_event) —
company/employee/supplier/asset creates/updates/status-transitions, and
every other module's audit-logged action, all get event emission for free
going forward, with no per-call-site wiring required.

Immutable by the same DB-level mechanism as audit_logs (see
6f52078ce90f_enforce_audit_log_immutability_at_db_.py) — a BEFORE
UPDATE OR DELETE trigger that raises unconditionally. A row here may
already have been read and acted on by a future consumer (n8n, or
anything else polling this table); nothing should ever be allowed to
change what it said after the fact.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "498b79eb7443"
down_revision: Union[str, Sequence[str], None] = "c2e7a1f9d4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("event_type", sa.String(length=150), nullable=False, index=True),
        sa.Column("resource_type", sa.String(length=50), nullable=False, index=True),
        sa.Column("resource_id", sa.String(length=100), nullable=True, index=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_event_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'events rows are immutable: % is not permitted on row id %',
                TG_OP, OLD.id;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER events_immutable
        BEFORE UPDATE OR DELETE ON events
        FOR EACH ROW EXECUTE FUNCTION prevent_event_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS events_immutable ON events;")
    op.execute("DROP FUNCTION IF EXISTS prevent_event_mutation();")
    op.drop_table("events")
