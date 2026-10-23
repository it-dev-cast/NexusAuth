import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

ALLOWED_COMPANY_TYPES = {"internal", "external"}


def _validate_config_defaults_json(value: str | None) -> str | None:
    # Doc: "Company-level configuration defaults" — config_defaults is
    # read back by employee_service._company_defaults() at employee-create
    # time (role/department inheritance). Before this validator, malformed
    # JSON here was silently swallowed to {} there with no error anywhere
    # — an admin could typo a company's defaults and never find out except
    # by noticing new employees quietly didn't inherit a role/department.
    # Reject it here instead, at the point where it's actually set.
    if value is None or value == "":
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("config_defaults must be valid JSON (or omitted).") from exc
    if not isinstance(parsed, dict):
        raise ValueError("config_defaults must be a JSON object (e.g. {\"default_job_role\": \"...\"}).")
    return value


class CompanyCreateRequest(BaseModel):
    # max_length on every string field matches its DB column width
    # (see app/models/company.py) — without this, an oversized value
    # sailed past validation and hit an unhandled DataError at the DB
    # layer (a generic 500) instead of a clean 422.
    name: str = Field(max_length=255)
    company_type: str = "external"
    # Mandatory alongside name — a company record isn't considered
    # complete without a way to reach it. contact_phone stays optional
    # (email already covers "a way to reach them").
    address: str = Field(max_length=500)
    contact_email: EmailStr
    contact_phone: str | None = Field(default=None, max_length=50)
    config_defaults: str | None = Field(default=None, max_length=1000)

    @field_validator("company_type")
    @classmethod
    def validate_company_type(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ALLOWED_COMPANY_TYPES:
            raise ValueError(
                f"company_type must be one of: {', '.join(sorted(ALLOWED_COMPANY_TYPES))}."
            )
        return value

    @field_validator("name", "address")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("This field must not be empty.")
        return value

    @field_validator("config_defaults")
    @classmethod
    def validate_config_defaults(cls, value: str | None) -> str | None:
        return _validate_config_defaults_json(value)


class CompanyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=50)
    config_defaults: str | None = Field(default=None, max_length=1000)

    # address/contact_email are mandatory on every company record (see
    # CompanyCreateRequest) — omitting them from an update leaves the
    # existing value untouched (model_fields_set in company_service), but
    # explicitly sending them as null/empty would clear a required field,
    # so that's rejected here rather than silently accepted. Skipped
    # automatically when the field is omitted (Pydantic doesn't run
    # validators against unset defaults), so "don't touch this field"
    # still works exactly as before.
    @field_validator("address")
    @classmethod
    def validate_address_not_cleared(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("address is required and cannot be cleared.")
        return value.strip()

    # name had no validator at all here before — an update could clear it
    # to empty/null with nothing rejecting that.
    @field_validator("name")
    @classmethod
    def validate_name_update(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            raise ValueError("name is required and cannot be cleared.")
        return value.strip()

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email_not_cleared(cls, value: EmailStr | None) -> EmailStr | None:
        if value is None:
            raise ValueError("contact_email is required and cannot be cleared.")
        return value

    @field_validator("config_defaults")
    @classmethod
    def validate_config_defaults(cls, value: str | None) -> str | None:
        return _validate_config_defaults_json(value)


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    company_type: str
    address: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    config_defaults: str | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
