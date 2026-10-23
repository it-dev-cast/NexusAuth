from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.application import Application
from app.repositories import (
    count_applications,
    count_employees_by_application,
    create_application,
    get_application_by_id,
    get_application_by_name,
    list_applications,
    soft_delete_application,
)
from app.schemas.application import ApplicationCreateRequest, ApplicationResponse, ApplicationUpdateRequest
from app.services.audit_service import record_audit_event


def _application_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _snapshot(application: Application) -> dict:
    return ApplicationResponse.model_validate(application).model_dump(mode="json")


def _attach_employee_counts(db: Session, applications: list[Application]) -> list[Application]:
    if not applications:
        return applications
    counts = count_employees_by_application(db)
    for application in applications:
        application.employee_count = counts.get(application.id, 0)
    return applications


def create_application_record(
    db: Session, data: ApplicationCreateRequest, actor_id: int | None
) -> Application:
    if get_application_by_name(db, data.name):
        raise _application_error(
            "APPLICATION_ALREADY_EXISTS", "An application with this name already exists."
        )

    application = create_application(
        db, Application(name=data.name, category=data.category, is_active=True)
    )
    application.employee_count = 0  # brand new, nobody granted access yet
    record_audit_event(
        db, actor_id, "create", "application", application.id, old_value=None, new_value=_snapshot(application)
    )
    return application


def get_application(db: Session, application_id: int) -> Application:
    application = get_application_by_id(db, application_id)
    if not application:
        raise _application_error("APPLICATION_NOT_FOUND", "Application not found.", status_code=404)
    _attach_employee_counts(db, [application])
    return application


def list_application_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    search: str | None = None,
) -> dict:
    items = list_applications(db, limit=limit, offset=offset, include_inactive=include_inactive, search=search)
    total = count_applications(db, include_inactive=include_inactive, search=search)
    _attach_employee_counts(db, items)
    return paginated(items, total, limit, offset)


def update_application_record(
    db: Session, application_id: int, data: ApplicationUpdateRequest, actor_id: int | None
) -> Application:
    application = get_application(db, application_id)
    old_snapshot = _snapshot(application)

    if data.name is not None:
        existing = get_application_by_name(db, data.name)
        if existing and existing.id != application.id:
            raise _application_error(
                "APPLICATION_ALREADY_EXISTS", "An application with this name already exists."
            )
        application.name = data.name
    if "category" in data.model_fields_set:
        application.category = data.category

    db.commit()
    db.refresh(application)
    record_audit_event(
        db, actor_id, "update", "application", application.id, old_value=old_snapshot, new_value=_snapshot(application)
    )
    return application


def deactivate_application(db: Session, application_id: int, actor_id: int | None) -> Application:
    application = get_application(db, application_id)
    if not application.is_active:
        return application
    old_snapshot = _snapshot(application)
    application = soft_delete_application(db, application)
    record_audit_event(
        db, actor_id, "delete", "application", application.id, old_value=old_snapshot, new_value=_snapshot(application)
    )
    return application


def reactivate_application(db: Session, application_id: int, actor_id: int | None) -> Application:
    """Counterpart to deactivate_application — see
    department_service.reactivate_department's docstring for why this is
    needed (ApplicationUpdateRequest only carries `name`, no is_active)."""
    application = get_application(db, application_id)
    if application.is_active:
        return application
    old_snapshot = _snapshot(application)
    application.is_active = True
    db.commit()
    db.refresh(application)
    _attach_employee_counts(db, [application])
    record_audit_event(
        db, actor_id, "update", "application", application.id, old_value=old_snapshot, new_value=_snapshot(application)
    )
    return application
