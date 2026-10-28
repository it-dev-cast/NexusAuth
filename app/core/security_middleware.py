from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.client_ip import client_ip, rate_limit_identity
from app.core.config import get_settings
from app.core.errors import api_error_body, new_trace_id
from app.core.rate_limit import get_limiter


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
        # The API version that served this response, matching the URL prefix.
        if request.url.path.startswith("/api/v1/"):
            response.headers.setdefault("X-API-Version", "v1")
        # Token-bearing responses must never be cached by a browser or proxy.
        if request.url.path.startswith("/api/v1/auth/"):
            response.headers.setdefault("Cache-Control", "no-store")
            response.headers.setdefault("Pragma", "no-cache")
        # Opt-in (HSTS_MAX_AGE_SECONDS): only meaningful once HTTPS is
        # terminated in front of this app; harmless to browsers over HTTP.
        hsts = get_settings().hsts_max_age_seconds
        if hsts > 0:
            response.headers.setdefault("Strict-Transport-Security", f"max-age={hsts}; includeSubDomains")
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
# Security). Scoped to the unauthenticated auth endpoints (login/register):
# those are the ones a caller can hit repeatedly with no credential at all.
#
# Counters live in PostgreSQL by default (app/core/rate_limit.py), so the
# limit is shared by every worker process and container; RATE_LIMIT_BACKEND=
# memory keeps them per process for a single dev server. The caller is the
# real client address: behind a reverse proxy set TRUSTED_PROXIES so
# X-Forwarded-For is believed from it (and only from it) — see
# app/core/client_ip.py. The limit is never skipped for tests: the suite
# turns it off through RATE_LIMIT_ENABLED like any deployment could, and the
# tests of the limiter itself turn it back on.
RATE_LIMIT_WINDOW_SECONDS = 60


def rate_limited_paths(settings) -> dict[str, int]:
    """Endpoint -> requests allowed per window, per caller."""
    return {
        "/api/v1/auth/login": settings.rate_limit_login_per_minute,
        "/api/v1/auth/register": settings.rate_limit_register_per_minute,
    }


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if not settings.rate_limit_enabled or request.method != "POST":
            return await call_next(request)

        max_requests = rate_limited_paths(settings).get(request.url.path)
        if max_requests is None:
            return await call_next(request)

        key = f"{request.url.path}|{rate_limit_identity(client_ip(request))}"
        limiter = get_limiter()
        hits, retry_after = await run_in_threadpool(limiter.hit, key, RATE_LIMIT_WINDOW_SECONDS)

        if hits > max_requests:
            return JSONResponse(
                status_code=429,
                content=api_error_body(
                    "RATE_LIMITED",
                    "Too many requests. Please try again shortly.",
                    trace_id=new_trace_id(),
                ),
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
