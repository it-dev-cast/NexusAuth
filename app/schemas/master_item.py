import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _clean_name(value: str) -> str:
    value = " ".join((value or "").split())
    if not value:
        raise ValueError("name must not be empty.")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("name must not contain control characters.")
    return value


def _clean_code(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _CODE_RE.match(value):
        raise ValueError("code may contain only letters, digits, '.', '_' and '-'.")
    return value.upper()


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class MasterItemCreateRequest(BaseModel):
    name: str = Field(max_length=150)
    code: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_name(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return _clean_code(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _clean_description(value)


class MasterItemUpdateRequest(BaseModel):
    """Only the fields sent are changed (model_fields_set); sending
    `code: null`, `description: null` or `parent_id: null` clears them."""

    name: str | None = Field(default=None, max_length=150)
    code: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=500)
    parent_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return None if value is None else _clean_name(value)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str | None) -> str | None:
        return _clean_code(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _clean_description(value)


class MasterItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    master_type: str
    name: str
    code: str | None = None
    description: str | None = None
    parent_id: int | None = None
    # Filled in by the service: the parent's name, and the full chain
    # ("Springfield, Illinois, United States") for hierarchical lists.
    parent_name: str | None = None
    path: str | None = None
    is_active: bool
    # Records currently using this value by name (employees, assets,
    # suppliers) and child items (e.g. states under a country).
    usage_count: int = 0
    children_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
