"""One database transaction per API request (gap #50).

get_db() (app/database/database.py) hands each request an AppSession whose
commit() only flushes. This middleware ends that transaction once the route
has produced its response and BEFORE the response is sent: committed when
the request succeeded, rolled back when it failed. A business change and the
audit row written after it therefore commit together or not at all.
"""
import logging

from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import api_error_body

logger = logging.getLogger("nexusauth.transaction")


class TransactionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            _rollback(request)
            raise
        session = getattr(request.state, "db_session", None)
        if session is None:
            return response
        if response.status_code >= 400:
            _rollback(request)
            return response
        try:
            session.commit_now()
        except Exception as exc:
            session.rollback()
            trace_id = getattr(request.state, "request_id", None)
            if isinstance(exc, IntegrityError):
                return JSONResponse(
                    status_code=409,
                    content=api_error_body("RESOURCE_CONFLICT", "This request conflicts with existing data.", trace_id=trace_id),
                )
            logger.exception("Commit failed on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=500,
                content=api_error_body("INTERNAL_ERROR", "An unexpected error occurred.", trace_id=trace_id),
            )
        return response


def _rollback(request: Request) -> None:
    session = getattr(request.state, "db_session", None)
    if session is not None:
        session.rollback()
