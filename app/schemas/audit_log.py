import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    old_value: dict | None = None
    new_value: dict | None = None
    created_at: datetime | None = None

    @field_validator("old_value", "new_value", mode="before")
    @classmethod
    def parse_json_text(cls, value):
        # Stored as a JSON text column (already PII-masked at write time —
        # see app/core/audit.py) — deserialize it back to an object for the
        # API response instead of returning a raw JSON string.
        if value is None or isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {"raw": value}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
