from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.event import EventResponse
from app.services.event_service import list_platform_events

router = APIRouter(
    prefix="/api/v1/events",
    tags=["Events"],
)

# No require_writer/require_deleter here on purpose — same reasoning as
# audit_log.py: events are only ever created as a side effect of
# record_audit_event (see app/services/audit_service.py), never through a
# public write endpoint. See app/core/permissions.py.
require_reader = require_roles(*allowed_roles("event", "read"))


@router.get("")
def list_events_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    company_id: int | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_platform_events(
        db,
        limit=limit,
        offset=offset,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )
    result["items"] = [
        EventResponse.model_validate(event).model_dump() for event in result["items"]
    ]
    return api_ok(result)
