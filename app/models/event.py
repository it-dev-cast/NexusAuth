from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Event(Base):
    """Foundation Core Phase 2 deliverable: "Event emission infrastructure"
    (NEXUS_ONE_ARCHITECTURE_PLAN §2.6, §9 Phase 2). This is the durable
    record of every "something meaningful happened" announcement Foundation
    Core makes — the plan's example is "Asset registered, Work Order
    closed, Employee status changed" triggering other modules via n8n.

    n8n itself is not integrated yet (a separate, not-yet-started Phase 2
    deliverable) — there is no message broker in this codebase. This table
    is the durable, poll-able "outbox": anything that will eventually listen
    (n8n, or any future module) can read new rows here in event_type/id
    order instead of the platform needing a live broker connection today.
    Nothing currently reads this table but the admin-facing list endpoint —
    that's expected for this stage; the point of this deliverable is that
    events now exist and are captured, ready for a real consumer later.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # "<resource_type>.<action>", e.g. "company.create", "asset.status_transition".
    # See app/services/event_service.py for exactly how this is built.
    event_type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)

    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # String, not FK — same reasoning as AuditLog.resource_id: an event must
    # outlive the record it describes, and some events (auth ones) have no
    # single numeric resource id at all.
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Populated for the resources that actually carry a company_id —
    # Company, Employee, and User/auth events (see the company_id= argument
    # at each record_audit_event call site in company_service.py,
    # employee_service.py, and auth_service.py). Stays null for Asset,
    # Supplier, and every master-data list (Department/Job Role/Application/
    # Manufacturer/Asset Model): those resources have no company_id column
    # at all — they're flat, company-wide catalogs by design (see
    # app/core/tenancy.py's docstring) — so there is nothing to propagate
    # for them, not a gap to fill later.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # JSON text, PII-masked before it's ever written — reuses the exact same
    # app/core/audit.py masking already applied to audit snapshots, since
    # this is the same underlying data (see record_audit_event).
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    # No updated_at column, no update/delete repository function — an event
    # is written once and never touched again, same immutability model as
    # AuditLog (see the matching DB-level trigger in this table's migration).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
