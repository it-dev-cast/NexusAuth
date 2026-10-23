from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    jwt_secret_key: str = Field(
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    # Only HS256 is actually implemented: jwt_service.py signs/verifies with
    # a single shared secret (settings.jwt_secret_key) via jose's HMAC path.
    # There is no RSA keypair loading anywhere in this codebase, so setting
    # JWT_ALGORITHM to an asymmetric algorithm (RS256, ES256, ...) wouldn't
    # be "supported later" — jose would be handed a random string where it
    # expects a private key and fail. Previously nothing caught this until
    # the first login attempt after a deploy (health/readiness don't touch
    # JWT at all, so this could pass every startup check and only break on
    # a real user's first request). Validated here instead, so a bad value
    # fails loudly at startup, matching jwt_secret_key's existing pattern.
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    environment: str = "development"

    db_user: str | None = None
    db_password: str | None = None
    db_host: str = "localhost"
    db_port: str = "5432"
    db_name: str | None = None
    database_url: str | None = None

    # Doc: "Connection timeout handling" / "Query timeout enforcement"
    # (Module 10: Error Recovery & Resilience) — without these, a hung TCP
    # connect or a slow/runaway query blocks a worker indefinitely, since
    # pool_pre_ping (app/database/database.py) only discards already-dead
    # connections, it doesn't bound how long a new attempt or a query can
    # take. Applied via psycopg connect_args, not per-query — see
    # app/database/database.py.
    db_connect_timeout_seconds: int = 10
    db_statement_timeout_ms: int = 30000

    # Doc: "Brute force protection (lock after 5 failed attempts)" /
    # "Account lockout duration" (NEXUS_ONE_ARCHITECTURE_PLAN §3, Module 10:
    # Security) — see auth_repository.increment_failed_logins /
    # auth_service.login_user. Configurable rather than hardcoded so a
    # deployment can tune sensitivity without a code change.
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # File upload support (Employee photo). Relative to the project root
    # unless an absolute path is given; created at startup if missing (see
    # main.py). Kept out of the repo (.gitignore) and out of the DB —
    # app/models/employee.py's photo_reference column stores only the
    # returned URL, same "reference, not the file itself" shape every other
    # PII-adjacent file field in this codebase already uses.
    upload_dir: str = "uploads"
    upload_max_bytes: int = 5 * 1024 * 1024

    @field_validator("database_url", mode="after")
    @classmethod
    def db_config_must_be_complete(cls, value, info):
        # Doc: "Required configuration enforcement" — without this, a
        # deployment that forgets DATABASE_URL *and* the individual DB_*
        # vars passes startup validation silently, then only fails on the
        # first real query with a confusing driver error from a connection
        # string like "postgresql+psycopg://None:None@localhost:5432/None"
        # (sqlalchemy_url below). Fail loudly at startup instead, matching
        # jwt_secret_key's existing pattern.
        if value:
            return value
        data = info.data
        missing = [
            name
            for name in ("db_user", "db_password", "db_name")
            if not data.get(name)
        ]
        if missing:
            raise ValueError(
                "Database is not configured: set DATABASE_URL, or all of "
                f"DB_USER/DB_PASSWORD/DB_NAME (missing: {', '.join(missing)})."
            )
        return value

    # Doc: "Application version tracking" / "Build timestamp tracking" —
    # surfaced on GET /health (main.py) so a deploy pipeline or on-call
    # engineer can confirm which build is actually serving traffic. Both
    # optional: a deployment that doesn't set them just gets null back
    # rather than failing to start over metadata that isn't essential.
    build_timestamp: str | None = None
    git_sha: str | None = None

    # Doc: "CORS validation" — comma-separated explicit allow-list, empty
    # by default (no cross-origin access) rather than "*", since this
    # app's own frontend is served same-origin from /static (main.py) and
    # has no cross-origin need today. Set only if a separately-hosted
    # frontend is ever added. See cors_origins below and main.py's
    # CORSMiddleware registration.
    cors_allowed_origins: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    # Optional: enables field-level encryption at rest for Employee PII
    # (bank account, IFSC, PAN, Aadhaar, document references — see
    # app/database/encrypted_types.py). A Fernet key, e.g. the output of
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # Optional rather than required so existing deployments/tests that
    # haven't set it yet don't fail to start; see app/core/pii_crypto.py
    # for the loud startup warning that fires instead.
    pii_encryption_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PII_ENCRYPTION_KEY"),
    )

    @field_validator("pii_encryption_key")
    @classmethod
    def pii_key_must_be_valid_fernet_key(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        from cryptography.fernet import Fernet

        try:
            Fernet(value.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "PII_ENCRYPTION_KEY must be a valid Fernet key (32 url-safe "
                "base64-encoded bytes), e.g. Fernet.generate_key()."
            ) from exc
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def only_hs256_is_supported(cls, value: str) -> str:
        value = (value or "").strip()
        if value != "HS256":
            raise ValueError(
                f"JWT_ALGORITHM={value!r} is not supported — this codebase only "
                "implements HS256 (a shared-secret HMAC signature). Asymmetric "
                "algorithms like RS256 would need an RSA keypair this project "
                "doesn't load anywhere; set JWT_ALGORITHM=HS256."
            )
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def secret_must_be_strong(cls, value: str) -> str:
        weak = {
            "",
            "secret",
            "change-this",
            "development-secret-change-this",
        }
        if value.strip() in weak or len(value) < 32:
            raise ValueError(
                "JWT_SECRET_KEY is missing or too weak. "
                "Set a secret at least 32 characters long."
            )
        return value

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
