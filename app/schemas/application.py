import re
from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,39}$")


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    return value or None


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    return value or None


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return value
    value = value.strip()
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or " " in value:
        raise ValueError("url must be a full http:// or https:// address.")
    return value


def normalize_application_code(value: str) -> str:
    """The one definition of how a code is written down: trimmed, upper-case,
    inner whitespace turned into "_" — so "hr module" and "HR_MODULE" are the
    same code. Letters, digits, "_" and "-" only; 2-40 characters."""
    code = re.sub(r"\s+", "_", (value or "").strip()).upper()
    if not code:
        raise ValueError("code must not be empty.")
    if not CODE_PATTERN.match(code):
        raise ValueError(
            "code must be 2-40 characters: letters, digits, hyphen or underscore, starting with a letter or digit."
        )
    return code


class ApplicationCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    code: str = Field(max_length=60)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        return normalize_application_code(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        return _normalize_category(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_description(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _normalize_url(value)


class ApplicationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    code: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    url: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return normalize_application_code(value)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str | None) -> str | None:
        return _normalize_category(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _normalize_description(value)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        return _normalize_url(value)


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    description: str | None = None
    category: str | None = None
    url: str | None = None
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


class ApplicationAccessGrantRequest(BaseModel):
    employee_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("employee_ids")
    @classmethod
    def validate_employee_ids(cls, value: list[int]) -> list[int]:
        # keep the caller's order, drop repeats
        return list(dict.fromkeys(value))


class ApplicationAccessEmployee(BaseModel):
    """One row of "who has access to this application"."""

    employee_id: int
    employee_code: str | None = None
    full_name: str
    email: str
    company_id: int
    status: str
    granted_at: datetime | None = None
    granted_by: str | None = None


class EmployeeApplicationAccess(BaseModel):
    """One row of "which applications does this employee have"."""

    application_id: int
    name: str
    code: str
    category: str | None = None
    is_active: bool
    granted_at: datetime | None = None
