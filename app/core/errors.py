import uuid
from contextvars import ContextVar

from fastapi import Request
from fastapi.responses import JSONResponse


class AuthError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details=None,
    ):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details


def new_trace_id() -> str:
    return str(uuid.uuid4())


# The current request's id (set by SafeAccessLogMiddleware), so a success
# body's meta.trace_id matches the X-Request-Id header and the access log,
# the same way error bodies already do.
current_request_id: ContextVar[str | None] = ContextVar("current_request_id", default=None)


def api_ok(data, trace_id: str | None = None) -> dict:
    return {
        "data": data,
        "meta": {"trace_id": trace_id or current_request_id.get() or new_trace_id()},
    }


def api_error_body(
    error_code: str,
    message: str,
    details=None,
    trace_id: str | None = None,
) -> dict:
    return {
        "error_code": error_code,
        "message": message,
        "details": details,
        "trace_id": trace_id or new_trace_id(),
    }


async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
    # Doc: "Trace ID propagation" — reuse this request's id (set by
    # SafeAccessLogMiddleware, see app/core/logging.py) as the error
    # envelope's trace_id when available, so a caller's own X-Request-Id
    # and the id in this error body are the same value.
    trace_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=api_error_body(
            exc.error_code,
            exc.message,
            exc.details,
            trace_id=trace_id,
        ),
        headers={"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None,
    )
