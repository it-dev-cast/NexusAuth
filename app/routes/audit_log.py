from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.errors import api_ok
from app.core.permissions import allowed_roles
from app.database.database import get_db
from app.models.user import User
from app.schemas.audit_log import AuditLogResponse
from app.services.audit_service import list_audit_records


router = APIRouter(
    prefix="/api/v1/audit-logs",
    tags=["Audit"],
)

# No require_writer/require_deleter here on purpose — there is no write or
# delete action for this resource. See app/core/permissions.py.
require_reader = require_roles(*allowed_roles("audit_log", "read"))


@router.get("")
def list_audit_logs_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    current_user: User = Depends(require_reader),
    db: Session = Depends(get_db),
):
    result = list_audit_records(
        db,
        limit=limit,
        offset=offset,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )
    result["items"] = [
        AuditLogResponse.model_validate(log).model_dump() for log in result["items"]
    ]
    return api_ok(result)
