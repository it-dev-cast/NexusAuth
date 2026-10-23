from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_ATTACHMENT_TYPES = {"document", "photo", "other"}


class AssetAttachmentCreateRequest(BaseModel):
    attachment_type: str
    reference: str = Field(max_length=500)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("attachment_type")
    @classmethod
    def validate_attachment_type(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ALLOWED_ATTACHMENT_TYPES:
            raise ValueError(f"attachment_type must be one of: {', '.join(sorted(ALLOWED_ATTACHMENT_TYPES))}.")
        return value

    @field_validator("reference")
    @classmethod
    def validate_reference(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("reference must not be empty.")
        return value


class AssetAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    attachment_type: str
    reference: str
    description: str | None = None
    uploaded_by: int | None = None
    created_at: datetime | None = None
