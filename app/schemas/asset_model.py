from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetModelCreateRequest(BaseModel):
    name: str = Field(max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class AssetModelUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class AssetModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    # Current count of non-disposed assets whose Asset.model matches this
    # entry's name — see app/repositories/asset_repository.py's
    # count_assets_by_model.
    asset_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AssetModelListResponse(BaseModel):
    items: list[AssetModelResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
