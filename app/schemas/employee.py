import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.employee_status import ALL_STATUSES

# Standard Indian PAN format: 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).
_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# Aadhaar: 12 digits. Accepts an optionally space/hyphen-grouped input
# (a common way it's presented/typed, e.g. "1234 5678 9012") and validates
# the format after stripping those separators — but does NOT re-derive
# Aadhaar's real checksum (Verhoeff algorithm), since that's beyond what a
# prototype's format check needs.
_AADHAAR_PATTERN = re.compile(r"^\d{12}$")
# Loose on purpose — international formats vary widely (spaces, hyphens,
# parens, a leading +country code); this only rejects obvious junk, the way
# Company/Supplier's contact_phone fields also don't strictly validate.
_PHONE_PATTERN = re.compile(r"^[+0-9][0-9\s\-()]{6,19}$")


def _validate_pan(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not _PAN_PATTERN.match(value.strip().upper()):
        raise ValueError("pan_number must match the format AAAAA9999A (5 letters, 4 digits, 1 letter).")
    return value


def _validate_aadhaar(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    digits_only = re.sub(r"[\s-]", "", value)
    if not _AADHAAR_PATTERN.match(digits_only):
        raise ValueError("aadhaar_number must be 12 digits (spaces/hyphens allowed as separators).")
    return value


def _validate_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    value = value.strip()
    if not _PHONE_PATTERN.match(value):
        raise ValueError(
            "phone_number must be 7-20 characters: digits, spaces, hyphens, "
            "parentheses, and an optional leading +."
        )
    return value


def _clean_address(value: str | None) -> str | None:
    # Trim each line and drop blank ones; an address that is only whitespace means "none".
    if value is None:
        return None
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return chr(10).join(lines) or None


def _validate_linkedin_url(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    value = value.strip()
    if not re.match(r"^https?://", value, re.IGNORECASE):
        raise ValueError("linkedin_url must start with http:// or https://.")
    return value


class EmployeeCreateRequest(BaseModel):
    company_id: int
    # max_length matches the DB column width (app/models/employee.py) —
    # see the matching note in app/schemas/company.py.
    first_name: str = Field(max_length=255)
    last_name: str = Field(max_length=255)
    email: EmailStr
    # Company's own internal HR numbering (e.g. "EMP-0001") — optional,
    # unique per company (app/models/employee.py's __table_args__).
    employee_code: str | None = Field(default=None, max_length=50)
    # Specific job title (e.g. "Senior Software Engineer") — distinct from
    # job_role below, which is the broader dropdown-backed category.
    designation: str | None = Field(default=None, max_length=150)
    phone_number: str | None = Field(default=None, max_length=20)
    linkedin_url: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=300)
    # None means "not specified" — the service falls back to the company's
    # config_defaults.default_job_role, then to "Employee" (role inheritance
    # from Company defaults). A hardcoded default here would make that
    # fallback unreachable.
    job_role: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    cost_center: str | None = Field(default=None, max_length=100)
    user_id: int | None = None
    # Must be an existing employee in the same company — validated in
    # employee_service.create_employee_record via the same
    # _validate_manager_assignment used on update. No cycle check needed
    # here: a brand-new employee can't already be part of one.
    manager_id: int | None = None
    # Application/module access (Dashboard, Refurbishment, HR Module, ...)
    # — a real FK list against the Application master, not free text like
    # job_role/department above. Every id must exist and be active;
    # validated in employee_service._validate_application_ids.
    application_ids: list[int] = Field(default_factory=list)

    # PROTOTYPE-ONLY sensitive fields — see app/models/employee.py note.
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    pan_number: str | None = None
    aadhaar_number: str | None = None
    residence_proof_reference: str | None = None
    photo_reference: str | None = None

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("first_name must not be empty.")
        return value

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("last_name must not be empty.")
        return value

    @field_validator("pan_number")
    @classmethod
    def validate_pan_number(cls, value: str | None) -> str | None:
        return _validate_pan(value)

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar_number(cls, value: str | None) -> str | None:
        return _validate_aadhaar(value)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        return _clean_address(value)

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, value: str | None) -> str | None:
        return _validate_linkedin_url(value)


class EmployeeUpdateRequest(BaseModel):
    # Admin-only corrective move (see app/services/employee_service.py) —
    # for fixing the wrong company picked at creation, not a general HR
    # transfer workflow. None (omitted) leaves the employee's company
    # unchanged, matching every other optional field here.
    company_id: int | None = None
    # None (omitted) leaves the name unchanged, same as every other optional
    # field here — but an explicitly-sent empty string still isn't allowed
    # (see the validators below), same rule as create.
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    # Nullable + model_fields_set (like department/cost_center below), so an
    # explicit null clears a previously-set code/designation/phone/URL
    # rather than being ignored as "not provided".
    employee_code: str | None = Field(default=None, max_length=50)
    designation: str | None = Field(default=None, max_length=150)
    phone_number: str | None = Field(default=None, max_length=20)
    linkedin_url: str | None = Field(default=None, max_length=500)
    address: str | None = Field(default=None, max_length=300)
    job_role: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=100)
    cost_center: str | None = Field(default=None, max_length=100)
    # "reports to" — see app/services/employee_service._validate_manager_assignment
    # for the same-company and no-cycle checks. Uses model_fields_set (like
    # department/cost_center clearing) so explicitly sending null unassigns
    # a manager rather than being ignored as "not provided".
    manager_id: int | None = None
    # None (omitted) = leave application access unchanged; an explicit list
    # (including []) replaces it entirely — same model_fields_set pattern
    # as department/cost_center, so saving other fields never silently
    # wipes out application access unless the caller actually sent this.
    application_ids: list[int] | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    pan_number: str | None = None
    aadhaar_number: str | None = None
    residence_proof_reference: str | None = None
    photo_reference: str | None = None

    @field_validator("first_name")
    @classmethod
    def validate_first_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("first_name must not be empty.")
        return value

    @field_validator("last_name")
    @classmethod
    def validate_last_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("last_name must not be empty.")
        return value

    @field_validator("pan_number")
    @classmethod
    def validate_pan_number(cls, value: str | None) -> str | None:
        return _validate_pan(value)

    @field_validator("aadhaar_number")
    @classmethod
    def validate_aadhaar_number(cls, value: str | None) -> str | None:
        return _validate_aadhaar(value)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        return _validate_phone(value)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str | None) -> str | None:
        return _clean_address(value)

    @field_validator("linkedin_url")
    @classmethod
    def validate_linkedin_url(cls, value: str | None) -> str | None:
        return _validate_linkedin_url(value)


class EmployeeStatusUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ALL_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(ALL_STATUSES))}.")
        return value


class EmployeeLinkUserRequest(BaseModel):
    user_id: int


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    user_id: int | None = None
    first_name: str
    last_name: str
    # Read-only, derived from first_name/last_name — see the property on
    # Employee (app/models/employee.py). Not settable via Create/Update;
    # kept here so existing consumers (search, CSV export, audit
    # snapshots) that display/sort "the employee's name" as one string
    # don't need their own concatenation logic.
    full_name: str
    email: str
    employee_code: str | None = None
    designation: str | None = None
    phone_number: str | None = None
    linkedin_url: str | None = None
    address: str | None = None
    job_role: str
    department: str | None = None
    cost_center: str | None = None
    manager_id: int | None = None
    # Backed by Employee.application_ids/application_names properties
    # (app/models/employee.py) — the real many-to-many, read off the
    # applications relationship, not a DB column of their own.
    application_ids: list[int] = Field(default_factory=list)
    application_names: list[str] = Field(default_factory=list)
    status: str
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    pan_number: str | None = None
    aadhaar_number: str | None = None
    residence_proof_reference: str | None = None
    photo_reference: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EmployeeListResponse(BaseModel):
    items: list[EmployeeResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
