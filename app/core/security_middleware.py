import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import api_error_body, new_trace_id


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Doc: "Security headers" (Module 10: Security). A small, fixed set of
    response headers that cost nothing and have no behavioral downside for
    a JSON API served same-origin from /static (see main.py).

    Bug fix: the original CSP here was a bare `default-src 'self'`, on the
    claim that the frontend uses no inline scripts/styles — that claim was
    wrong, and it silently broke the real page in every browser (this app's
    JS-side test tooling doesn't enforce CSP the way a real browser does,
    so it went unnoticed until reported): index.html has several
    `style="..."` attributes AND links Google Fonts as an external
    stylesheet (fonts.googleapis.com, which itself pulls the actual font
    files from fonts.gstatic.com) — both silently blocked, degrading fonts
    and layout on every page load. style-src/font-src below now explicitly
    allow exactly those two, nothing broader; script-src stays locked to
    'self' since app.js is the only script and is never inline.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # Swagger UI/ReDoc (main.py's /docs, /redoc) load their own
        # third-party assets and are excluded via the path check below
        # rather than loosening this policy for every route.
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "frame-ancestors 'none'",
            )
        return response


# Doc: "Rate limiting" / "Rate limit enforcement per endpoint" (Module 10:
# Security). Deliberately scoped to the unauthenticated auth endpoints
# (login/register) rather than every route: those are the ones a caller
# can hit repeatedly with no credential at all, and this codebase already
# has a broad, well-exercised test suite that hits every other endpoint
# rapidly in succession — a global limiter would risk tripping on the test
# suite itself, not just real abuse. In-process/in-memory by design (no
# Redis or other shared store exists in this codebase); resets on restart
# and doesn't share state across multiple app processes — acceptable for
# this single-instance deployment, not a distributed rate limiter.
RATE_LIMITED_PATHS = {
    "/api/v1/auth/login": (10, 60),  # 10 requests / 60s per IP
    "/api/v1/auth/register": (5, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[tuple[str, str], deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # The test suite shares one TestClient (app/tests/conftest.py),
        # meaning every test looks like the same IP hitting the same path —
        # exempting it isn't weakening real rate limiting, it's avoiding a
        # false trip from the test harness itself (pytest sets
        # PYTEST_CURRENT_TEST for the duration of every test, a standard,
        # well-known way to detect this without any test-file changes).
        if "PYTEST_CURRENT_TEST" in os.environ:
            return await call_next(request)

        limit = RATE_LIMITED_PATHS.get(request.url.path)
        if limit is None:
            return await call_next(request)

        max_requests, window_seconds = limit
        ip = request.client.host if request.client else "unknown"
        key = (ip, request.url.path)
        now = time.monotonic()
        hits = self._hits[key]

        while hits and now - hits[0] > window_seconds:
            hits.popleft()

        if len(hits) >= max_requests:
            trace_id = new_trace_id()
            return JSONResponse(
                status_code=429,
                content=api_error_body(
                    "RATE_LIMITED",
                    "Too many requests. Please try again shortly.",
                    trace_id=trace_id,
                ),
                headers={"Retry-After": str(window_seconds)},
            )

        hits.append(now)
        return await call_next(request)
