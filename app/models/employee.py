from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database.database import Base
from app.database.encrypted_types import EncryptedString
from app.models.application import Application, employee_applications


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        # Doc requirement: "Email uniqueness per Company" — not globally unique,
        # since two different companies may each have their own person at the
        # same email in shared/contractor scenarios.
        UniqueConstraint("company_id", "email", name="uq_employees_company_email"),
        # Same reasoning as email above — an employee_code is a company's own
        # internal HR numbering (e.g. "EMP-0001"), not a global registry, so
        # two different companies may each have their own "EMP-0001". NULL
        # is allowed and never collides with itself (Postgres treats every
        # NULL as distinct for a unique constraint) — the field is optional.
        UniqueConstraint(
            "company_id", "employee_code", name="uq_employees_company_employee_code"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Nullable: an employee record can exist before they're given system
    # login access. One employee <-> at most one user account. ON DELETE
    # SET NULL: if the user account is ever removed, the employee record
    # survives, just unlinked.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True
    )

    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Company's own internal HR numbering (e.g. "EMP-0001") — free text, not
    # auto-generated; optional, since not every company using this system
    # necessarily has one yet. See __table_args__ above for the
    # per-company uniqueness rule.
    employee_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Job title shown on a business card/org chart (e.g. "Senior Software
    # Engineer") — distinct from job_role below, which is the broader
    # functional category (e.g. "Engineering") used for the Job role
    # dropdown/reporting. Two employees can share a job_role but have
    # different designations, and vice versa.
    designation: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Job/functional role (e.g. "Technician", "Manager") — distinct from the
    # RBAC Role (admin/operator/read_only) on the linked User account.
    job_role: Mapped[str] = mapped_column(String(100), nullable=False, default="Employee")

    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Added by migration d9f3a7c5b182 (master-backed fields); mapped here so
    # autogenerate doesn't read it as a dropped column. Not exposed by the API yet.
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Self-referencing "reports to" hierarchy (Module 7: the schema's first
    # actual hierarchical relationship — see app/core/graph_utils.py, which
    # was built for exactly this and, until now, had nothing to protect).
    # ON DELETE SET NULL: removing/exiting a manager shouldn't cascade into
    # orphaning their reports' records, just unlink them. Cycle validation
    # (an employee can't end up, directly or transitively, their own
    # manager) lives in employee_service, not here — see
    # _validate_manager_assignment.
    manager_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="onboarded")

    # --- Sensitive PII fields -------------------------------------------
    # Encrypted at rest via EncryptedString when PII_ENCRYPTION_KEY is set
    # (see app/database/encrypted_types.py, app/core/pii_crypto.py) — stored
    # as TEXT ciphertext, transparently decrypted back to plain text on
    # read. Attribute access from Python (including API responses) always
    # sees plain text; only the DB column itself holds ciphertext.
    # SECURITY_CHECKLIST.md: existing rows written before encryption was
    # enabled are NOT retroactively re-encrypted by this change — a
    # one-time backfill script is documented remaining work.
    bank_account_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    pan_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    aadhaar_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # These store a reference (filename/URL), not the file itself — no file
    # upload/storage infrastructure exists yet.
    residence_proof_reference: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # "Photo" on the Employee form/page — a reference (filename/URL), same
    # "no file upload infra yet" caveat as residence_proof_reference above.
    photo_reference: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # Contact PII, same treatment as bank/PAN/Aadhaar above.
    phone_number: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # Postal/office address, same contact-PII treatment as phone_number.
    address: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    # ---------------------------------------------------------------------

    # A public professional profile URL — not encrypted like the fields
    # above: it's meant to be shared/clicked, the opposite of private PII.
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Application/module access (Dashboard, Refurbishment, HR Module, ...) —
    # a real many-to-many, not a free-text field like job_role/department
    # above (see app/models/application.py's docstring for why). lazy=
    # "selectin" batches this into one extra query per list_employees()
    # call instead of one query per employee — the same N+1 shape as
    # dashboard_overview's count_active_sessions_by_user fix, applied here
    # up front rather than after the fact.
    applications: Mapped[list["Application"]] = relationship(
        secondary=employee_applications, lazy="selectin", order_by="Application.name"
    )

    @property
    def full_name(self) -> str:
        """Read-only, derived from first_name/last_name (the actual stored
        columns) — kept so every existing consumer that displays or sorts
        by "the employee's name" (audit snapshots, search suggestions,
        CSV export, the Employees table) doesn't need its own first+last
        concatenation logic. There is no full_name column and no setter —
        editing a name always means setting first_name/last_name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def application_ids(self) -> list[int]:
        return [a.id for a in self.applications]

    @property
    def application_names(self) -> list[str]:
        return [a.name for a in self.applications]
