from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import api_ok
from app.database.database import get_db
from app.models.user import User
from app.schemas.report import ReportQuery
from app.services.report_service import (
    export_report_csv,
    get_filter_options,
    get_report_catalog,
    get_report_summary,
    run_report,
)

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Reports"],
)

# Unlike every other resource, there is no single `allowed_roles(...)` to
# gate this router with: each report is gated by the permission of the data
# it reports on (employee / company / asset / supplier / audit_log — see
# app/services/report_service.py). So these routes require a signed-in user,
# and the service decides, per report, what that user may see or run. The
# catalog, summary and filter-option endpoints only ever return what the
# caller is allowed to read.


def _query(
    search: str | None,
    company_id: int | None,
    department: str | None,
    job_role: str | None,
    status: str | None,
    company_type: str | None,
    manufacturer: str | None,
    model: str | None,
    category: str | None,
    action: str | None,
    resource_type: str | None,
    role: str | None,
    master: str | None,
    date_from: date | None,
    date_to: date | None,
    sort_by: str | None,
    sort_dir: str | None,
) -> ReportQuery:
    return ReportQuery(
        search=search,
        company_id=company_id,
        department=department,
        job_role=job_role,
        status=status,
        company_type=company_type,
        manufacturer=manufacturer,
        model=model,
        category=category,
        action=action,
        resource_type=resource_type,
        role=role,
        master=master,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@router.get("/catalog")
def report_catalog_endpoint(current_user: User = Depends(get_current_user)):
    return api_ok(get_report_catalog(current_user))


@router.get("/summary")
def report_summary_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(get_report_summary(db, current_user))


@router.get("/filter-options")
def report_filter_options_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(get_filter_options(db, current_user))


@router.get("/{report_key}")
def run_report_endpoint(
    report_key: str,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=200),
    company_id: int | None = Query(default=None, ge=1),
    department: str | None = Query(default=None, max_length=200),
    job_role: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=50),
    company_type: str | None = Query(default=None, max_length=50),
    manufacturer: str | None = Query(default=None, max_length=200),
    model: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=200),
    action: str | None = Query(default=None, max_length=50),
    resource_type: str | None = Query(default=None, max_length=50),
    role: str | None = Query(default=None, max_length=50),
    master: str | None = Query(default=None, max_length=50),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None, max_length=50),
    sort_dir: str | None = Query(default=None, pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _query(
        search, company_id, department, job_role, status, company_type, manufacturer, model,
        category, action, resource_type, role, master, date_from, date_to, sort_by, sort_dir,
    )
    return api_ok(run_report(db, current_user, report_key, query, limit, offset))


@router.get("/{report_key}/export")
def export_report_endpoint(
    report_key: str,
    search: str | None = Query(default=None, max_length=200),
    company_id: int | None = Query(default=None, ge=1),
    department: str | None = Query(default=None, max_length=200),
    job_role: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=50),
    company_type: str | None = Query(default=None, max_length=50),
    manufacturer: str | None = Query(default=None, max_length=200),
    model: str | None = Query(default=None, max_length=200),
    category: str | None = Query(default=None, max_length=200),
    action: str | None = Query(default=None, max_length=50),
    resource_type: str | None = Query(default=None, max_length=50),
    role: str | None = Query(default=None, max_length=50),
    master: str | None = Query(default=None, max_length=50),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None, max_length=50),
    sort_dir: str | None = Query(default=None, pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = _query(
        search, company_id, department, job_role, status, company_type, manufacturer, model,
        category, action, resource_type, role, master, date_from, date_to, sort_by, sort_dir,
    )
    text, filename, row_count = export_report_csv(db, current_user, report_key, query)
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Report-Row-Count": str(row_count),
            "Cache-Control": "no-store",
        },
    )
