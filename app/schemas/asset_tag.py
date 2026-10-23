from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetTagCreateRequest(BaseModel):
    tag: str = Field(max_length=50)

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if not value:
            raise ValueError("tag must not be empty.")
        return value


class AssetTagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    tag: str
    created_at: datetime | None = None
