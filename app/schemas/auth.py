from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

# bcrypt silently truncates the input to its first 72 BYTES — anything
# after that is ignored by hashpw/checkpw entirely. Without a cap, two
# different passwords that share the same first 72 bytes would hash (and
# then verify) identically, which is surprising and a real weakening of
# the password. Reject before it ever reaches bcrypt instead.
MAX_PASSWORD_BYTES = 72


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {MAX_PASSWORD_BYTES} bytes "
                "(bcrypt silently truncates anything longer)."
            )
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {}})

    refresh_token: str | None = None


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    role: str
    company_id: int | None = None
    is_active: bool
    login_count: int = 0
    failed_login_attempts: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class RoleUpdateRequest(BaseModel):
    role: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_must_fit_bcrypt(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"new_password must be at most {MAX_PASSWORD_BYTES} bytes "
                "(bcrypt silently truncates anything longer)."
            )
        return value


class SessionResponse(BaseModel):
    id: int
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    is_revoked: bool
    ip_address: str | None = None
    user_agent: str | None = None
