from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.asset_status import ALL_STATUSES


class AssetCreateRequest(BaseModel):
    # max_length matches the DB column width (app/models/asset.py) — see
    # the matching note in app/schemas/company.py.
    asset_tag: str = Field(max_length=100)
    manufacturer: str = Field(max_length=255)
    model: str = Field(max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    supplier_id: int
    barcode_value: str | None = Field(default=None, max_length=255)
    # Digital Twin "Financials" facet (§2.7) — all optional; intake often
    # happens before a price is finalized.
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    current_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None

    @field_validator("asset_tag")
    @classmethod
    def validate_asset_tag(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("asset_tag must not be empty.")
        return value

    @field_validator("manufacturer")
    @classmethod
    def validate_manufacturer(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("manufacturer must not be empty.")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("model must not be empty.")
        return value


class AssetUpdateRequest(BaseModel):
    # Deliberately excludes asset_tag (immutable), supplier_id (source
    # supplier doesn't change after intake), and status (has its own
    # dedicated PATCH .../status endpoint with transition validation).
    manufacturer: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)
    barcode_value: str | None = Field(default=None, max_length=255)
    purchase_cost: Decimal | None = Field(default=None, ge=0)
    current_value: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None


class AssetStatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ALL_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALL_STATUSES))}.")
        return value


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_tag: str
    manufacturer: str
    model: str
    serial_number: str | None = None
    supplier_id: int
    status: str
    barcode_value: str | None = None
    purchase_cost: Decimal | None = None
    current_value: Decimal | None = None
    currency: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
