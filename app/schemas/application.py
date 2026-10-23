from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    return value or None


class ApplicationCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    category: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        return _normalize_category(value)


class ApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        return _normalize_category(value)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str | None = None
    is_active: bool
    # Current headcount (employees whose application_ids includes this
    # one) — see app/repositories/application_repository.py's
    # count_employees_by_application.
    employee_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationListResponse(BaseModel):
    items: list[ApplicationResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
