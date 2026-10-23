from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobRoleCreateRequest(BaseModel):
    name: str = Field(max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class JobRoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value


class JobRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    is_active: bool
    # Current headcount (non-exited employees whose Employee.job_role
    # matches this job role's name) — see
    # app/repositories/employee_repository.py's count_employees_by_job_role.
    employee_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobRoleListResponse(BaseModel):
    items: list[JobRoleResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
