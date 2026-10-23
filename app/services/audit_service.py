from datetime import datetime

from sqlalchemy.orm import Session

from app.core.audit import serialize_snapshot
from app.core.pagination import paginated
from app.models.audit_log import AuditLog
from app.repositories import count_audit_logs, create_audit_log, list_audit_logs
from app.services.event_service import publish_event


def record_audit_event(
    db: Session,
    user_id: int | None,
    action: str,
    resource_type: str,
    resource_id: str | int | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    company_id: int | None = None,
) -> AuditLog:
    """The one function every module's create/update/status-transition path
    calls. Doc requirements this satisfies in one place: audit record
    creation on create/update/delete, state-transition auditing, and
    PII-masked before/after snapshots.

    Deliberately NOT wrapped in try/except — if writing an audit row fails,
    that is a real problem the caller's transaction should surface, not one
    to silently swallow. This does mean an audit-table outage could reject
    otherwise-valid business writes; acceptable for this prototype's scope.

    Retention policy (doc: "Audit retention policy"): rows are kept
    indefinitely. No scheduled purge job exists in this project (there is no
    job runner/cron infrastructure at all yet) — a real retention window is
    future work, not implemented here.

    Also publishes a Foundation Core Phase 2 event (see
    app/services/event_service.py) for the same state change — every call
    site here already carries exactly the (action, resource_type,
    resource_id, snapshot) shape an event needs, so this is the one place
    that guarantees no future module can add audit logging without also
    getting event emission, rather than requiring a second call to remember
    at every site.

    company_id (Phase 2: "multi-tenant context propagation") is optional and
    None by default — this AuditLog table itself has no company_id column at
    all (it never has; see app/models/audit_log.py), so passing it does
    nothing here. It exists purely to forward on to publish_event, for the
    handful of callers (Company, Employee, User) whose resource actually
    carries a company_id. Callers for resources that don't (Asset, Supplier,
    and every master-data list — see app/core/tenancy.py's docstring for why)
    correctly omit it, and the resulting event's company_id stays null.
    """
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        old_value=serialize_snapshot(old_value),
        new_value=serialize_snapshot(new_value),
    )
    log = create_audit_log(db, log)
    publish_event(
        db,
        resource_type=resource_type,
        action=action,
        resource_id=resource_id,
        payload=new_value if new_value is not None else old_value,
        company_id=company_id,
    )
    return log


def list_audit_records(
    db: Session,
    limit: int,
    offset: int,
    resource_type: str | None,
    resource_id: str | None,
    user_id: int | None,
    action: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> dict:
    items = list_audit_logs(
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
    total = count_audit_logs(
        db,
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
        action=action,
        start_date=start_date,
        end_date=end_date,
    )
    return paginated(items, total, limit, offset)
