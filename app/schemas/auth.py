from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# bcrypt silently truncates the input to its first 72 BYTES — anything
# after that is ignored by hashpw/checkpw entirely. Without a cap, two
# different passwords that share the same first 72 bytes would hash (and
# then verify) identically, which is surprising and a real weakening of
# the password. Reject before it ever reaches bcrypt instead.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def check_password_policy(value: str, field: str = "password") -> str:
    """The rule every new password must meet (register, change-password):
    8+ characters, at least one letter and one digit, and at most 72 bytes.
    Login deliberately doesn't apply it, so accounts created before the rule
    can still sign in and then change their password."""
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"{field} must be at most {MAX_PASSWORD_BYTES} bytes "
            "(bcrypt silently truncates anything longer)."
        )
    if len(value) < MIN_PASSWORD_LENGTH or not value.strip():
        raise ValueError(f"{field} must be at least {MIN_PASSWORD_LENGTH} characters.")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError(f"{field} must contain at least one letter and one digit.")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def email_is_lowercase(cls, value: str) -> str:
        # One account per mailbox, whatever capitals it was typed with —
        # see get_user_by_email.
        return value.lower()

    @field_validator("password")
    @classmethod
    def password_meets_policy(cls, value: str) -> str:
        return check_password_policy(value)


class LoginRequest(BaseModel):
    email: EmailStr
    # Deliberately not the 72-byte limit: a password over that is simply
    # wrong, and login answers "invalid credentials" for it like any other
    # wrong password (see password_service.verify_password). This only stops
    # absurdly large bodies.
    password: str = Field(min_length=1, max_length=1024)


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
    def new_password_meets_policy(cls, value: str) -> str:
        return check_password_policy(value, "new_password")


class SessionResponse(BaseModel):
    id: int
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    is_revoked: bool
    ip_address: str | None = None
    user_agent: str | None = None
