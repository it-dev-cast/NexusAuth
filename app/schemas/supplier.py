from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.supplier_status import ALL_STATUSES


class SupplierCreateRequest(BaseModel):
    # max_length matches the DB column width (app/models/supplier.py) —
    # see the matching note in app/schemas/company.py.
    name: str = Field(max_length=255)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    terms: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    rating: float | None = Field(
        default=None,
        ge=0,
        le=5,
        description=(
            "Manually entered by an Operator/Admin — not calculated from "
            "order or QC history (no such history exists yet in this "
            "codebase). Treat as a free-text score, not a derived metric."
        ),
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class SupplierUpdateRequest(BaseModel):
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    terms: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)
    rating: float | None = Field(
        default=None,
        ge=0,
        le=5,
        description=(
            "Manually entered by an Operator/Admin — not calculated from "
            "order or QC history (no such history exists yet in this "
            "codebase). Treat as a free-text score, not a derived metric."
        ),
    )


class SupplierStatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ALL_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALL_STATUSES))}.")
        return value


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_email: str | None = None
    contact_phone: str | None = None
    terms: str | None = None
    category: str | None = None
    status: str
    rating: float | None = Field(
        default=None,
        description="Manually entered — not a calculated/derived score.",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SupplierListResponse(BaseModel):
    items: list[SupplierResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
