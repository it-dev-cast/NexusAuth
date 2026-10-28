import base64
import hashlib
import ipaddress
import re
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, PrivateAttr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_EXAMPLE_ENV = Path(__file__).resolve().parents[2] / ".env.example"


def _example_env_secrets() -> set[str]:
    """JWT secret values written in the committed .env.example — public, so
    never acceptable as a real secret."""
    try:
        text = _EXAMPLE_ENV.read_text(encoding="utf-8")
    except OSError:
        return set()
    found = re.findall(r"^\s*JWT_SECRET(?:_KEY)?\s*=\s*(.+?)\s*$", text, re.M)
    return {v.strip("'\"") for v in found if v.strip("'\"")}


ENVIRONMENTS = ("development", "test", "staging", "production")


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _check_jwt_secret(value: str, name: str) -> str:
    weak = {
        "",
        "secret",
        "change-this",
        "development-secret-change-this",
    }
    if value.strip() in weak or len(value) < 32:
        raise ValueError(f"{name} is missing or too weak. Set a secret at least 32 characters long.")
    # Long but trivially guessable ("a" * 32) is just as forgeable.
    if len(set(value)) < 10:
        raise ValueError(
            f"{name} is too repetitive. Generate a random one: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    # The example file is committed to git, so its placeholder is public:
    # anyone could sign tokens with it. Never echo the value itself.
    if value in _example_env_secrets():
        raise ValueError(
            f"{name} is still the placeholder from .env.example, which is public. "
            'Generate your own: python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return value


JWT_ALGORITHMS = ("HS256", "RS256")
MIN_RSA_KEY_BITS = 2048


def _pem_text(value: str) -> str:
    """A PEM given in an environment variable usually has its newlines
    written as the two characters backslash-n; turn them back into real ones."""
    return value.replace("\\n", "\n").strip() + "\n"


def _read_pem_file(path: str, name: str) -> str:
    try:
        return Path(path).expanduser().read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"{name}: cannot read the key file {path!r}.") from exc


def _public_key_id(public_pem: str) -> str:
    """A stable id for a public key (first 16 chars of the url-safe SHA-256 of
    its DER encoding), used as the JWT `kid` header and the JWKS `kid`."""
    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.urlsafe_b64encode(hashlib.sha256(der).digest()).decode("ascii").rstrip("=")[:16]


def _load_rsa_public(pem: str, name: str):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    try:
        key = serialization.load_pem_public_key(pem.encode("utf-8"))
    except Exception as exc:
        raise ValueError(f"{name} is not a valid PEM public key.") from exc
    if not isinstance(key, rsa.RSAPublicKey):
        raise ValueError(f"{name} must be an RSA public key.")
    if key.key_size < MIN_RSA_KEY_BITS:
        raise ValueError(f"{name} must be at least {MIN_RSA_KEY_BITS} bits.")
    return key


def _load_rsa_private(pem: str, name: str):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    try:
        key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
    except Exception as exc:
        raise ValueError(f"{name} is not a valid unencrypted PEM private key.") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError(f"{name} must be an RSA private key.")
    if key.key_size < MIN_RSA_KEY_BITS:
        raise ValueError(f"{name} must be at least {MIN_RSA_KEY_BITS} bits.")
    return key


def _public_pem(key) -> str:
    from cryptography.hazmat.primitives import serialization

    return key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")


def _check_fernet_key(value: str, name: str) -> str:
    from cryptography.fernet import Fernet

    try:
        Fernet(value.encode("utf-8"))
    except Exception as exc:
        raise ValueError(
            f"{name} must be a valid Fernet key (32 url-safe base64-encoded "
            "bytes), e.g. Fernet.generate_key()."
        ) from exc
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        # A rejected setting is often a secret; keep its value out of the
        # startup error (and so out of logs).
        hide_input_in_errors=True,
    )

    # Required for HS256 (the shared signing secret). With RS256 it is unused,
    # except that it may stay set so tokens issued before the switch keep
    # verifying (see jwt_verifiers).
    jwt_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    # HS256 (shared secret, the default) or RS256 (RSA key pair: this service
    # signs with the private key; any other service verifies with the public
    # key from /.well-known/jwks.json and never holds a signing secret).
    # Anything else is refused at startup, as is an RS256 setup without a
    # usable key, so a bad value fails loudly here instead of on the first
    # login after a deploy.
    jwt_algorithm: str = "HS256"
    # RS256 keys: a file path (preferred) or PEM text with its newlines written
    # as backslash-n. The public key is derived from the private one when not
    # given. JWT_KEY_ID is optional; without it the key id is a hash of the
    # public key.
    jwt_private_key: str | None = None
    jwt_private_key_path: str | None = None
    jwt_public_key: str | None = None
    jwt_public_key_path: str | None = None
    jwt_key_id: str | None = None
    # RS256 key rotation: public-key files (comma-separated) of the keys being
    # rotated out. Tokens they signed keep verifying until they expire.
    jwt_previous_public_key_paths: str = ""
    # Key rotation: put the old JWT_SECRET_KEY here (comma-separated) when you
    # set a new one. Tokens it signed keep verifying until they expire, so a
    # rotation doesn't sign everyone out. Remove it after
    # REFRESH_TOKEN_EXPIRE_DAYS. Never put the .env.example placeholder here.
    jwt_previous_secret_keys: str = ""
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    # One of ENVIRONMENTS. "production" turns on the stricter checks in
    # production_rules below.
    environment: str = "development"
    # Strict-Transport-Security max-age, sent only when > 0. Turn on once the
    # site is served over HTTPS end to end (e.g. behind the TLS proxy);
    # browsers then refuse plain HTTP for this host for that long.
    hsts_max_age_seconds: int = 0
    # Password for the admin@casterly.com account created on an EMPTY users
    # table at first startup. Unset = no account is created (create one with
    # scripts/seed_admin.py instead); there is no built-in default password.
    bootstrap_admin_password: str | None = None

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
    # Startup only: how many times to try the first DB connection before
    # giving up (exponential backoff with jitter between tries).
    db_startup_connect_attempts: int = 5
    db_statement_timeout_ms: int = 30000

    # Doc: "Brute force protection (lock after 5 failed attempts)" /
    # "Account lockout duration" (NEXUS_ONE_ARCHITECTURE_PLAN §3, Module 10:
    # Security) — see auth_repository.increment_failed_logins /
    # auth_service.login_user. Configurable rather than hardcoded so a
    # deployment can tune sensitivity without a code change.
    max_failed_login_attempts: int = 5
    account_lockout_minutes: int = 15

    # Rate limiting of the unauthenticated auth endpoints (see
    # app/core/security_middleware.py). "database" keeps the counters in
    # PostgreSQL, so every worker and container shares them; "memory" is per
    # process and only suitable for a single-process development server.
    rate_limit_enabled: bool = True
    rate_limit_backend: str = "database"
    rate_limit_login_per_minute: int = 10
    rate_limit_register_per_minute: int = 5
    # Reverse proxies whose X-Forwarded-For header may be believed
    # (comma-separated IPs or CIDRs, e.g. "10.0.0.0/8,172.16.0.0/12"). Empty =
    # trust no header: the client is whoever opened the connection. Without
    # this, behind a proxy every caller looks like the proxy's own address.
    trusted_proxies: str = ""

    @field_validator("rate_limit_backend")
    @classmethod
    def rate_limit_backend_must_be_known(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ("database", "memory"):
            raise ValueError("RATE_LIMIT_BACKEND must be 'database' or 'memory'.")
        return value

    @field_validator("trusted_proxies")
    @classmethod
    def trusted_proxies_must_be_networks(cls, value: str) -> str:
        for entry in _split_csv(value):
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXIES: {entry!r} is not an IP address or CIDR range.") from exc
        return value

    @property
    def trusted_proxy_networks(self) -> list:
        return [ipaddress.ip_network(entry, strict=False) for entry in _split_csv(self.trusted_proxies)]

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
    # Key rotation for PII: old Fernet keys (comma-separated) still used to
    # DECRYPT existing values; everything new is encrypted with
    # PII_ENCRYPTION_KEY. Rows move to the new key as they are re-saved.
    pii_previous_encryption_keys: str = ""

    @field_validator("pii_encryption_key")
    @classmethod
    def pii_key_must_be_valid_fernet_key(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return _check_fernet_key(value, "PII_ENCRYPTION_KEY")

    @field_validator("jwt_algorithm")
    @classmethod
    def only_supported_algorithms(cls, value: str) -> str:
        value = (value or "").strip()
        if value not in JWT_ALGORITHMS:
            raise ValueError(
                f"JWT_ALGORITHM={value!r} is not supported — use one of: "
                f"{', '.join(JWT_ALGORITHMS)}."
            )
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def secret_must_be_strong(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return _check_jwt_secret(value, "JWT_SECRET_KEY")

    @field_validator("jwt_previous_secret_keys")
    @classmethod
    def previous_secrets_must_be_strong(cls, value: str) -> str:
        for key in _split_csv(value):
            _check_jwt_secret(key, "JWT_PREVIOUS_SECRET_KEYS")
        return value

    @field_validator("pii_previous_encryption_keys")
    @classmethod
    def previous_pii_keys_must_be_valid(cls, value: str) -> str:
        for key in _split_csv(value):
            _check_fernet_key(key, "PII_PREVIOUS_ENCRYPTION_KEYS")
        return value

    @field_validator("environment")
    @classmethod
    def environment_must_be_known(cls, value: str) -> str:
        value = (value or "").strip().lower()
        if value not in ENVIRONMENTS:
            raise ValueError(f"ENVIRONMENT must be one of: {', '.join(ENVIRONMENTS)}.")
        return value

    # Loaded and checked once at startup (see jwt_key_material).
    _signing_pem: str | None = PrivateAttr(default=None)
    _signing_kid: str | None = PrivateAttr(default=None)
    _verify_keys: list = PrivateAttr(default_factory=list)  # [(kid, public_pem)], current key first

    @model_validator(mode="after")
    def jwt_key_material(self):
        if self.jwt_algorithm == "HS256":
            if not self.jwt_secret_key:
                raise ValueError(
                    "JWT_SECRET_KEY is missing or too weak. Set a secret at least 32 characters long."
                )
            return self

        # RS256
        private_pem = None
        if self.jwt_private_key_path:
            private_pem = _read_pem_file(self.jwt_private_key_path, "JWT_PRIVATE_KEY_PATH")
        elif self.jwt_private_key:
            private_pem = _pem_text(self.jwt_private_key)
        if not private_pem:
            raise ValueError(
                "JWT_ALGORITHM=RS256 needs a private key: set JWT_PRIVATE_KEY_PATH "
                "(or JWT_PRIVATE_KEY). Generate a pair with scripts/generate_jwt_keys.py."
            )
        private_key = _load_rsa_private(private_pem, "The JWT private key")
        derived_public = _public_pem(private_key.public_key())

        given_public = None
        if self.jwt_public_key_path:
            given_public = _read_pem_file(self.jwt_public_key_path, "JWT_PUBLIC_KEY_PATH")
        elif self.jwt_public_key:
            given_public = _pem_text(self.jwt_public_key)
        if given_public:
            public_key = _load_rsa_public(given_public, "The JWT public key")
            if public_key.public_numbers() != private_key.public_key().public_numbers():
                raise ValueError("The JWT public key does not belong to the JWT private key.")

        kid = (self.jwt_key_id or "").strip() or _public_key_id(derived_public)
        verify_keys = [(kid, derived_public)]
        for path in _split_csv(self.jwt_previous_public_key_paths):
            pem = _read_pem_file(path, "JWT_PREVIOUS_PUBLIC_KEY_PATHS")
            previous = _public_pem(_load_rsa_public(pem, "A key in JWT_PREVIOUS_PUBLIC_KEY_PATHS"))
            verify_keys.append((_public_key_id(previous), previous))

        self._signing_pem = private_pem
        self._signing_kid = kid
        self._verify_keys = verify_keys
        return self

    @model_validator(mode="after")
    def production_rules(self):
        # Settings that are merely unwise in development are refused in
        # production, so a misconfigured deploy fails at startup instead of
        # running with PII in plaintext or a wide-open CORS policy.
        if self.environment != "production":
            return self
        problems = []
        if not self.pii_encryption_key:
            problems.append("PII_ENCRYPTION_KEY must be set")
        if "*" in self.cors_origins:
            problems.append("CORS_ALLOWED_ORIGINS must not contain '*'")
        if not self.rate_limit_enabled:
            problems.append("RATE_LIMIT_ENABLED must not be turned off")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems) + ".")
        return self

    @property
    def jwt_verification_keys(self) -> list[str]:
        """Keys a token may be signed with: the current one first, then the
        ones being rotated out. New tokens are only ever signed with the
        current key."""
        current = [self.jwt_secret_key] if self.jwt_secret_key else []
        return [*current, *_split_csv(self.jwt_previous_secret_keys)]

    @property
    def jwt_signing_key(self) -> str:
        """What new tokens are signed with: the shared secret (HS256) or the
        PEM private key (RS256)."""
        return self._signing_pem if self.jwt_algorithm == "RS256" else self.jwt_secret_key

    @property
    def jwt_signing_headers(self) -> dict | None:
        return {"kid": self._signing_kid} if self.jwt_algorithm == "RS256" else None

    @property
    def jwt_public_keys(self) -> list[tuple[str, str]]:
        """(kid, PEM) of every public key a token may verify against, the
        current one first. Empty under HS256."""
        return list(self._verify_keys)

    @property
    def jwt_verifiers(self) -> list[tuple[str | None, str, str]]:
        """(kid, key, algorithm) for every way a token may legitimately
        verify, current key first. Each key is only ever paired with its own
        algorithm, so a public key can never be presented as an HMAC secret.
        Under RS256, previous HMAC secrets stay valid for tokens issued before
        the switch."""
        hmac = [(None, key, "HS256") for key in self.jwt_verification_keys]
        if self.jwt_algorithm == "RS256":
            return [(kid, pem, "RS256") for kid, pem in self._verify_keys] + hmac
        return hmac

    @property
    def pii_decryption_keys(self) -> list[str]:
        keys = [self.pii_encryption_key] if self.pii_encryption_key else []
        return keys + _split_csv(self.pii_previous_encryption_keys)

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
