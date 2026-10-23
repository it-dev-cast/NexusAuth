from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # SET NULL, not RESTRICT: a user account being removed later must never
    # block-delete, and must never erase, the trail of what that user did.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # e.g. "create", "update", "status_transition", "delete", "link_user",
    # "login_success", "login_failure", "access_denied".
    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # e.g. "company", "employee", "supplier", "asset", "auth", "rbac".
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # String, not FK — audit rows must outlive the record they describe, and
    # some events (login attempts before a user is resolved) have no clean
    # numeric id at all.
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # JSON text, PII-masked before it's ever written (see app/core/audit.py).
    # No update/delete repository function exists for this table at all —
    # doc: "Audit record immutability" is enforced structurally, the same
    # way Asset's asset_tag immutability is: there's simply no code path.
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # No updated_at column — an audit row is written once and never touched
    # again.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
