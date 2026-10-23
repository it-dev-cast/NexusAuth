from datetime import datetime

from sqlalchemy.orm import Session

from app.core.audit import serialize_snapshot
from app.core.pagination import paginated
from app.models.event import Event
from app.repositories import count_events, create_event, list_events


def publish_event(
    db: Session,
    resource_type: str,
    action: str,
    resource_id: str | int | None,
    payload: dict | None,
    company_id: int | None = None,
) -> Event:
    """Foundation Core Phase 2: "Event emission infrastructure"
    (NEXUS_ONE_ARCHITECTURE_PLAN §2.6, §9). Called from exactly one place —
    app/services/audit_service.record_audit_event — not scattered across
    every module's create/update path. Every audited state change already
    carries the same (actor, action, resource_type, resource_id, snapshot)
    shape an event needs, so deriving one from the other here means a
    future module's audit call automatically gets event emission for free,
    with no separate call to remember to add.

    event_type is "<resource_type>.<action>" (e.g. "company.create",
    "asset.status_transition") — lowercase and dotted, matching the plan's
    own §2.6 example ("Company.created, Asset.created, ...") rather than
    the differently-cased PascalCase names used in the plan's Phase 3 prose
    example ("AssetQCCompleted") — one convention had to be picked; this
    codebase uses this one everywhere an event_type is built.

    payload reuses serialize_snapshot (app/core/audit.py) — the exact same
    PII-masking already applied to audit snapshots, since this is the same
    underlying data. Not wrapped in try/except, same reasoning as
    record_audit_event: a failure here is a real problem, not one to
    silently swallow.
    """
    event = Event(
        event_type=f"{resource_type}.{action}",
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        company_id=company_id,
        payload=serialize_snapshot(payload),
    )
    return create_event(db, event)


def list_platform_events(
    db: Session,
    limit: int,
    offset: int,
    event_type: str | None,
    resource_type: str | None,
    resource_id: str | None,
    company_id: int | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> dict:
    items = list_events(
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
    total = count_events(
        db,
        event_type=event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        company_id=company_id,
        start_date=start_date,
        end_date=end_date,
    )
    return paginated(items, total, limit, offset)
