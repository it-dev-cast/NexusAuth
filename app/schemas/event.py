import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    resource_type: str
    resource_id: str | None = None
    company_id: int | None = None
    payload: dict | None = None
    created_at: datetime | None = None

    @field_validator("payload", mode="before")
    @classmethod
    def parse_json_text(cls, value):
        # Stored as a JSON text column (already PII-masked at write time —
        # see app/core/audit.py, reused as-is by publish_event) — deserialize
        # it back to an object for the API response instead of a raw string.
        if value is None or isinstance(value, dict):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {"raw": value}


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
