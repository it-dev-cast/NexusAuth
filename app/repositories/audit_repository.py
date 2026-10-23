from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

# Deliberately no update_audit_log / delete_audit_log function exists in this
# file. Doc: "Audit record immutability" — the only way to interact with a
# written row is to read it.


def create_audit_log(db: Session, audit_log: AuditLog) -> AuditLog:
    db.add(audit_log)
    db.commit()
    db.refresh(audit_log)
    return audit_log


def _filtered(
    query,
    resource_type: str | None,
    resource_id: str | None,
    user_id: int | None,
    action: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
):
    if resource_type is not None:
        query = query.filter(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(AuditLog.resource_id == resource_id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if start_date is not None:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date is not None:
        query = query.filter(AuditLog.created_at <= end_date)
    return query


def list_audit_logs(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    resource_type: str | None = None,
    resource_id: str | None = None,
    user_id: int | None = None,
    action: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[AuditLog]:
    query = _filtered(
        db.query(AuditLog), resource_type, resource_id, user_id, action, start_date, end_date
    )
    # Doc: "Audit record ordering" — most recent first, the standard trail read order.
    return query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset).all()


def count_audit_logs(
    db: Session,
    resource_type: str | None = None,
    resource_id: str | None = None,
    user_id: int | None = None,
    action: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    query = _filtered(
        db.query(func.count(AuditLog.id)),
        resource_type,
        resource_id,
        user_id,
        action,
        start_date,
        end_date,
    )
    return query.scalar() or 0
