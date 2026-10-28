from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Doc: "Asset immutability rules (asset_tag cannot be changed)". Enforced
    # structurally, not just by convention — AssetUpdateRequest (schemas/asset.py)
    # has no asset_tag field at all, so there is no code path that can change it.
    asset_tag: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    manufacturer: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # Added by migration d9f3a7c5b182 (master-backed fields); mapped here so
    # autogenerate doesn't read it as a dropped columns. Not exposed by the API yet.
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Suppliers are never hard-deleted (no delete endpoint exists for them,
    # only status transitions), so RESTRICT here is a safety net, matching
    # the same reasoning used for companies.id / users.id elsewhere.
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Asset lifecycle: registered -> in_repair -> certified (-> in_repair again
    # on rework), and disposed as the terminal soft-delete state.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="registered")

    # Doc: "Asset barcode/QR code field preparation" — just the field, no
    # scanning/generation infrastructure exists yet.
    barcode_value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Digital Twin "Financials" facet (NEXUS_ONE_ARCHITECTURE_PLAN §2.7).
    # What the supplier was paid, and what this asset is currently valued
    # at — separate columns, not one, since they diverge the moment
    # refurbishment/depreciation/market pricing exists (none of that logic
    # is implemented yet; current_value is a plain manually-set number for
    # now, same "field now, logic later" precedent as barcode_value above).
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    # ISO 4217 code (e.g. "INR", "USD") — a plain string, not a currency
    # master table; no multi-currency conversion logic exists in this
    # codebase, so nothing yet compares values across differing codes.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
