from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DepartmentCreateRequest(BaseModel):
    name: str = Field(max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    manager_name: str | None = Field(default=None, max_length=255)
    parent_department_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("description", "manager_name")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None


class DepartmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    manager_name: str | None = Field(default=None, max_length=255)
    # None is ambiguous here ("not provided" vs "explicitly clear the
    # parent") — the service reads model_fields_set to tell them apart,
    # same pattern as EmployeeUpdateRequest.department/cost_center.
    parent_department_id: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty.")
        return value

    @field_validator("description", "manager_name")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    manager_name: str | None = None
    parent_department_id: int | None = None
    is_active: bool
    # Current headcount (non-exited employees whose Employee.department
    # matches this department's name) — see
    # app/repositories/employee_repository.py's count_employees_by_department.
    employee_count: int = 0
    # Both computed by app/services/department_service.py's
    # _attach_hierarchy_info, batched (not per-row queried) — never
    # persisted columns.
    parent_department_name: str | None = None
    children_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DepartmentListResponse(BaseModel):
    items: list[DepartmentResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
