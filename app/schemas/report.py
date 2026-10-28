from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportQuery:
    """Everything a caller can ask of a report, as received from the query
    string. All filters are optional; which ones a given report actually
    supports is declared in app/services/report_service.py's catalog and
    enforced there (an unsupported filter is rejected, never silently
    ignored — otherwise a caller would think a filter had been applied when
    it hadn't)."""

    search: str | None = None
    company_id: int | None = None
    department: str | None = None
    job_role: str | None = None
    status: str | None = None
    company_type: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    category: str | None = None
    action: str | None = None
    resource_type: str | None = None
    role: str | None = None
    master: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort_by: str | None = None
    sort_dir: str | None = None

    FILTER_NAMES = (
        "search",
        "company_id",
        "department",
        "job_role",
        "status",
        "company_type",
        "manufacturer",
        "model",
        "category",
        "action",
        "resource_type",
        "role",
        "master",
        "date_from",
        "date_to",
    )

    def provided_filters(self) -> dict:
        return {
            name: getattr(self, name)
            for name in self.FILTER_NAMES
            if getattr(self, name) is not None and getattr(self, name) != ""
        }
