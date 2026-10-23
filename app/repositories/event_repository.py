from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.event import Event

# Deliberately no update_event / delete_event function exists in this file —
# same immutability model as audit_repository.py. The only way to interact
# with a written row is to read it.


def create_event(db: Session, event: Event) -> Event:
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _filtered(
    query,
    event_type: str | None,
    resource_type: str | None,
    resource_id: str | None,
    company_id: int | None,
    start_date: datetime | None,
    end_date: datetime | None,
):
    if event_type is not None:
        query = query.filter(Event.event_type == event_type)
    if resource_type is not None:
        query = query.filter(Event.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(Event.resource_id == resource_id)
    if company_id is not None:
        query = query.filter(Event.company_id == company_id)
    if start_date is not None:
        query = query.filter(Event.created_at >= start_date)
    if end_date is not None:
        query = query.filter(Event.created_at <= end_date)
    return query


def list_events(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    company_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[Event]:
    query = _filtered(
        db.query(Event), event_type, resource_type, resource_id, company_id, start_date, end_date
    )
    # Most recent first — same read order as the audit trail; a listener
    # catching up reads oldest-first instead (see list_events_after below).
    return query.order_by(Event.created_at.desc(), Event.id.desc()).limit(limit).offset(offset).all()


def count_events(
    db: Session,
    event_type: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    company_id: int | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    query = _filtered(
        db.query(func.count(Event.id)),
        event_type,
        resource_type,
        resource_id,
        company_id,
        start_date,
        end_date,
    )
    return query.scalar() or 0


def list_events_after(db: Session, after_id: int, limit: int = 100) -> list[Event]:
    """Oldest-first, id > after_id — the shape a real consumer (a future n8n
    poller, or anything else catching up on what it missed) needs: "give me
    everything since the last event I already processed", not the
    newest-first page a human browsing the admin list wants.
    """
    return (
        db.query(Event)
        .filter(Event.id > after_id)
        .order_by(Event.id.asc())
        .limit(limit)
        .all()
    )
