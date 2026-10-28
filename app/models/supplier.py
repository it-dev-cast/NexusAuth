from datetime import datetime

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Unlike Employee, a Supplier is not scoped to a Company — the doc lists
    # no company_id for this module. Suppliers are one flat, Casterly-wide
    # vendor list that any company's Assets can reference.
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Payment terms, e.g. "Net 30", "COD".
    terms: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Free-form grouping, e.g. "Hardware", "Logistics".
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Added by migration d9f3a7c5b182 (master-backed fields); mapped here so
    # autogenerate doesn't read it as a dropped column. Not exposed by the API yet.
    supplier_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Supplier lifecycle: onboarded -> approved -> suspended (and back).
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="onboarded")

    # 0.00-5.00. NOT a computed/derived score today — an Operator/Admin
    # types this number directly (see SupplierUpdateRequest.rating). The
    # doc's "rating calculation" logic would derive this from order/QC
    # history, but no Refurbishment/Inventory module exists yet to source
    # that history from, so there is nothing to calculate it from. Kept as
    # a manually-entered field rather than left unimplemented, but callers
    # should not assume it reflects any actual performance data — see the
    # `description` on the Pydantic fields for the same caveat in /docs.
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
