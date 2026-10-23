import json
import logging
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger("nexusauth.access")
rbac_logger = logging.getLogger("nexusauth.rbac")


class JsonFormatter(logging.Formatter):
    """Doc: "Structured logging (JSON format)" / "Log timestamp
    generation" / "Log level assignment" / "Context field inclusion"
    (NEXUS_ONE_ARCHITECTURE_PLAN §3, Module 10: Observability & Logging).

    Every log line this process emits becomes one JSON object with a fixed
    set of top-level fields, so a log aggregator (or a human piping
    through `jq`) can filter/query by field instead of regexing a plain
    string. Call sites attach request/error-specific fields via
    `extra={"context": {...}}` (see SafeAccessLogMiddleware, main.py's
    exception handlers, log_rbac_denied/log_role_change below) rather than
    baking them into the message text — `default=str` mirrors
    audit_service.serialize_snapshot's handling of non-JSON-native values
    (datetimes, etc.) so a bad context value degrades to its str() form
    instead of raising and losing the log line entirely.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if context:
            payload.update(context)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)

# Doc: "Trace ID propagation" (Module 10: Observability & Logging) — the
# header a caller/gateway may send to correlate its own request id with
# this service's logs and error responses. If absent, one is generated
# per request instead (see SafeAccessLogMiddleware below).
REQUEST_ID_HEADER = "X-Request-Id"

_BLOCKED = (
    "authorization",
    "password",
    "refresh_token",
    "access_token",
    "jwt_secret",
    "secret",
)


def _safe_path(request: Request) -> str:
    return request.url.path


class SafeAccessLogMiddleware(BaseHTTPMiddleware):
    """Doc: "API endpoint hit logging" (Module 8). Deliberately kept as a
    plain-text log line for every request here, NOT written into the
    audit_logs DB table (app/models/audit_log.py) — that table is a
    change/decision trail (create/update/status-transition/login/access-denied),
    and writing one row per GET request would bloat it with events nobody
    audits, for no real trail value. If per-request DB-queryable metrics are
    ever needed, that's a separate "request log" table, not audit_logs.
    """

    async def dispatch(self, request: Request, call_next):
        # Doc: "Request ID generation" / "Trace ID propagation" — reuse an
        # inbound X-Request-Id if the caller/gateway sent one (so their id
        # and ours correlate), otherwise mint one. Stashed on request.state
        # so route/error handlers (main.py's exception handlers) can reuse
        # the exact same id as this request's trace_id instead of minting
        # an unrelated second one.
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id

        # Doc: "Performance logging" — request duration, start to finish.
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers[REQUEST_ID_HEADER] = request_id
        path = _safe_path(request)
        line = f"{request.method} {path} -> {response.status_code} {duration_ms}ms request_id={request_id}"
        # assert_no_secrets is a canary against a future regression — e.g.
        # someone adding request/response headers or the raw query string
        # (request.url instead of request.url.path) to this log line
        # without noticing what's in them — not a filter; it fails loudly
        # in dev/tests rather than silently letting a secret through.
        #
        # The path itself is deliberately excluded from the scan: it's a
        # fixed, code-defined route template (see app/routes/*.py), never a
        # place a live secret VALUE can appear in this app's routing (no
        # route embeds a password/token as a path segment; query strings
        # are already excluded by _safe_path() returning .path, not .url).
        # A route can legitimately be *named* after a security concept —
        # e.g. POST /api/v1/auth/change-password — without that name ever
        # being a leaked secret; only the check on the rest of the line
        # (method/status/duration/request_id, all fully attacker/app
        # independent) still guards the real invariant.
        assert_no_secrets(f"{request.method} {response.status_code} {duration_ms}ms {request_id}")
        # extra={"context": {...}} — see JsonFormatter above. These become
        # real top-level fields in the emitted JSON (method, path,
        # status_code, duration_ms, request_id), not just baked into the
        # message string, so a log aggregator can filter/query on them
        # directly (e.g. "every 5xx", "p95 duration_ms per path").
        logger.info(
            "%s",
            line,
            extra={
                "context": {
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                }
            },
        )
        return response


def log_rbac_denied(user_id: int, email: str, role: str, endpoint: str) -> None:
    rbac_logger.warning(
        "RBAC_DENIED user_id=%s email=%s role=%s endpoint=%s",
        user_id,
        email,
        role,
        endpoint,
        extra={
            "context": {
                "event": "rbac_denied",
                "user_id": user_id,
                "email": email,
                "role": role,
                "endpoint": endpoint,
            }
        },
    )


def log_role_change(
    actor_id: int,
    actor_email: str,
    target_id: int,
    old_role: str,
    new_role: str,
) -> None:
    rbac_logger.info(
        "ROLE_CHANGED actor_id=%s actor_email=%s target_id=%s old_role=%s new_role=%s",
        actor_id,
        actor_email,
        target_id,
        old_role,
        new_role,
        extra={
            "context": {
                "event": "role_changed",
                "actor_id": actor_id,
                "actor_email": actor_email,
                "target_id": target_id,
                "old_role": old_role,
                "new_role": new_role,
            }
        },
    )


def assert_no_secrets(text: str) -> None:
    # Was previously `if item in lowered and item in ("authorization", "bearer ")`
    # — since no _BLOCKED entry ever equals "bearer ", that second clause
    # only ever let "authorization" through the check; password,
    # refresh_token, access_token, jwt_secret, and secret were silently
    # never checked at all. Fixed to check every _BLOCKED term.
    lowered = text.lower()
    for item in _BLOCKED:
        if item in lowered:
            raise AssertionError(f"Secret-like value found in logs: {item}")
