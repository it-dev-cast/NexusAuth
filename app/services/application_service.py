from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.pagination import paginated
from app.models.application import Application
from app.repositories import (
    count_applications,
    count_employees_by_application,
    create_application,
    get_application_by_code,
    get_application_by_id,
    get_application_by_name,
    list_application_categories,
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


def _require_unique(db: Session, name: str | None, code: str | None, own_id: int | None) -> None:
    if name is not None:
        existing = get_application_by_name(db, name)
        if existing and existing.id != own_id:
            raise _application_error(
                "APPLICATION_ALREADY_EXISTS", "An application with this name already exists."
            )
    if code is not None:
        existing = get_application_by_code(db, code)
        if existing and existing.id != own_id:
            raise _application_error(
                "APPLICATION_CODE_ALREADY_EXISTS", "An application with this code already exists."
            )


def create_application_record(
    db: Session, data: ApplicationCreateRequest, actor_id: int | None
) -> Application:
    _require_unique(db, data.name, data.code, None)

    application = create_application(
        db,
        Application(
            name=data.name,
            code=data.code,
            description=data.description,
            category=data.category,
            url=data.url,
            is_active=data.is_active,
        ),
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
    status: str | None = None,
    category: str | None = None,
) -> dict:
    items = list_applications(
        db, limit=limit, offset=offset, include_inactive=include_inactive, search=search, status=status, category=category
    )
    total = count_applications(db, include_inactive=include_inactive, search=search, status=status, category=category)
    _attach_employee_counts(db, items)
    return paginated(items, total, limit, offset)


def list_categories_in_use(db: Session) -> list[str]:
    return list_application_categories(db)


def update_application_record(
    db: Session, application_id: int, data: ApplicationUpdateRequest, actor_id: int | None
) -> Application:
    application = get_application(db, application_id)
    old_snapshot = _snapshot(application)
    fields = data.model_fields_set

    _require_unique(db, data.name, data.code, application.id)
    if data.name is not None:
        application.name = data.name
    if data.code is not None:
        application.code = data.code
    if "description" in fields:
        application.description = data.description
    if "category" in fields:
        application.category = data.category
    if "url" in fields:
        application.url = data.url

    db.commit()
    db.refresh(application)
    _attach_employee_counts(db, [application])
    new_snapshot = _snapshot(application)
    if new_snapshot != old_snapshot:
        record_audit_event(
            db, actor_id, "update", "application", application.id, old_value=old_snapshot, new_value=new_snapshot
        )

    # Status goes through the same two functions as the Deactivate/Reactivate
    # buttons, so each change is audited as its own event.
    if data.is_active is not None and data.is_active != application.is_active:
        if data.is_active:
            application = reactivate_application(db, application_id, actor_id)
        else:
            application = deactivate_application(db, application_id, actor_id)
    return application


def deactivate_application(db: Session, application_id: int, actor_id: int | None) -> Application:
    """Takes the application out of use: it can no longer be given to anyone
    (see application_access_service.grant_application_access and the employee
    form's validation). Existing grants are deliberately kept, not deleted —
    they stay visible, flagged as belonging to an inactive application, can
    still be revoked, and come back into full effect on reactivation without
    anything being re-entered. The deactivation itself is audited."""
    application = get_application(db, application_id)
    if not application.is_active:
        return application
    old_snapshot = _snapshot(application)
    application = soft_delete_application(db, application)
    _attach_employee_counts(db, [application])
    record_audit_event(
        db, actor_id, "delete", "application", application.id, old_value=old_snapshot, new_value=_snapshot(application)
    )
    return application


def reactivate_application(db: Session, application_id: int, actor_id: int | None) -> Application:
    """Counterpart to deactivate_application — see
    department_service.reactivate_department's docstring for why this is
    needed (the plain PUT historically carried no is_active)."""
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
