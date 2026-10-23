from app.core.errors import AuthError
from app.core.pagination import paginated
from app.core.roles import Role
from app.core.tenancy import enforce_company_scope
from app.models.company import Company
from app.models.user import User
from app.repositories import (
    count_companies,
    create_company,
    get_company_by_id,
    get_company_by_name,
    list_companies,
    soft_delete_company,
)
from app.schemas.company import CompanyCreateRequest, CompanyResponse, CompanyUpdateRequest
from app.services.audit_service import record_audit_event
from sqlalchemy.orm import Session


def _company_error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def _not_found_error() -> AuthError:
    return _company_error("COMPANY_NOT_FOUND", "Company not found.", status_code=404)


def _snapshot(company: Company) -> dict:
    return CompanyResponse.model_validate(company).model_dump(mode="json")


def create_company_record(db: Session, data: CompanyCreateRequest, actor_id: int | None) -> Company:
    if get_company_by_name(db, data.name):
        raise _company_error(
            "COMPANY_ALREADY_EXISTS",
            "A company with this name already exists.",
        )

    company = Company(
        name=data.name,
        company_type=data.company_type,
        address=data.address,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        config_defaults=data.config_defaults,
        is_active=True,
    )
    company = create_company(db, company)
    record_audit_event(
        db, actor_id, "create", "company", company.id, old_value=None, new_value=_snapshot(company),
        company_id=company.id,
    )
    return company


def get_company(db: Session, company_id: int) -> Company:
    """Unscoped existence lookup — for internal cross-module references
    (e.g. employee_service checking a company exists/active before creating
    an employee under it), NOT for a user directly reading a Company
    resource. Routes must use get_company_for_user instead."""
    company = get_company_by_id(db, company_id)
    if not company:
        raise _not_found_error()
    return company


def get_company_for_user(db: Session, company_id: int, current_user: User) -> Company:
    """Company-scoped lookup for the `/companies/{id}` routes (Foundation
    Core company isolation). Admin is exempt (global/platform role, see
    app/core/tenancy.py); everyone else may only reach their own company —
    any other id, existing or not, comes back as COMPANY_NOT_FOUND."""
    company = get_company(db, company_id)
    enforce_company_scope(
        db, current_user, company.id, _not_found_error(), "company", company.id
    )
    return company


def list_company_records(
    db: Session,
    limit: int,
    offset: int,
    include_inactive: bool,
    current_user: User,
    search: str | None = None,
    company_type: str | None = None,
    sort_by: str = "id",
    sort_dir: str = "desc",
) -> dict:
    if current_user.role != Role.ADMIN:
        # Non-admins don't get a directory of every company in the system —
        # only their own shows up, same as if it were the only company that
        # existed for them. sort is meaningless over a single row, so it's
        # intentionally ignored on this branch; search/company_type still
        # apply (an unmatching filter correctly yields an empty list).
        own = (
            get_company_by_id(db, current_user.company_id)
            if current_user.company_id is not None
            else None
        )
        matches = (
            own
            and (include_inactive or own.is_active)
            and (not company_type or own.company_type == company_type)
            and (not search or search.lower() in own.name.lower())
        )
        items = [own] if matches else []
        return paginated(items, len(items), limit, offset)

    items = list_companies(
        db,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
        search=search,
        company_type=company_type,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total = count_companies(db, include_inactive=include_inactive, search=search, company_type=company_type)
    return paginated(items, total, limit, offset)


def update_company_record(
    db: Session,
    company_id: int,
    data: CompanyUpdateRequest,
    current_user: User,
) -> Company:
    actor_id = current_user.id
    company = get_company_for_user(db, company_id, current_user)
    old_snapshot = _snapshot(company)

    # name is NOT NULL — "provided" always means "set to this value";
    # there's no such thing as clearing a company's name, so it keeps the
    # plain not-None check rather than the explicit-null-out pattern below.
    if data.name is not None:
        existing = get_company_by_name(db, data.name)
        if existing and existing.id != company.id:
            raise _company_error(
                "COMPANY_ALREADY_EXISTS",
                "A company with this name already exists.",
            )
        company.name = data.name

    # address/contact_email/contact_phone/config_defaults are nullable —
    # distinguish "field omitted" (leave untouched) from "field explicitly
    # sent as null" (clear it) via model_fields_set, instead of collapsing
    # both to "value is None" and making it impossible to ever null one of
    # these back out once set.
    fields = data.model_fields_set
    if "address" in fields:
        company.address = data.address
    if "contact_email" in fields:
        company.contact_email = data.contact_email
    if "contact_phone" in fields:
        company.contact_phone = data.contact_phone
    if "config_defaults" in fields:
        company.config_defaults = data.config_defaults

    db.commit()
    db.refresh(company)
    record_audit_event(
        db, actor_id, "update", "company", company.id, old_value=old_snapshot, new_value=_snapshot(company),
        company_id=company.id,
    )
    return company


def deactivate_company(db: Session, company_id: int, current_user: User) -> Company:
    actor_id = current_user.id
    company = get_company_for_user(db, company_id, current_user)
    if not company.is_active:
        return company
    old_snapshot = _snapshot(company)
    company = soft_delete_company(db, company)
    record_audit_event(
        db, actor_id, "delete", "company", company.id, old_value=old_snapshot, new_value=_snapshot(company),
        company_id=company.id,
    )
    return company


def reactivate_company(db: Session, company_id: int, current_user: User) -> Company:
    """Counterpart to deactivate_company — without this, a deactivated
    company was a dead end: nothing in the API could ever set is_active
    back to True (CompanyUpdateRequest carries no such field)."""
    actor_id = current_user.id
    company = get_company_for_user(db, company_id, current_user)
    if company.is_active:
        return company
    old_snapshot = _snapshot(company)
    company.is_active = True
    db.commit()
    db.refresh(company)
    record_audit_event(
        db, actor_id, "update", "company", company.id, old_value=old_snapshot, new_value=_snapshot(company),
        company_id=company.id,
    )
    return company
