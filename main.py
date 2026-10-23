import hashlib
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.dependencies import get_admin_user, get_current_user
from app.core.errors import AuthError, api_error_body, auth_error_handler, new_trace_id
from app.core.logging import JsonFormatter, SafeAccessLogMiddleware
from app.core.security_middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.database.database import SessionLocal, engine
from app.database.schema_check import SchemaNotReadyError, verify_schema_ready
from app.models.user import User
from app.routes.auth import router as auth_router
from app.routes.company import router as company_router
from app.routes.employee import router as employee_router
from app.routes.supplier import router as supplier_router
from app.routes.asset import router as asset_router
from app.routes.audit_log import router as audit_log_router
from app.routes.event import router as event_router
from app.routes.job_role import router as job_role_router
from app.routes.department import router as department_router
from app.routes.application import router as application_router
from app.routes.manufacturer import router as manufacturer_router
from app.routes.asset_model import router as asset_model_router
from app.routes.upload import router as upload_router
from app.services.auth_service import bootstrap_admin
import app.models  # noqa: F401
import logging

FRONTEND_DIR = Path(__file__).parent / "frontend"

logger = logging.getLogger("nexusauth.startup")

# Doc: "Structured logging (JSON format)" (NEXUS_ONE_ARCHITECTURE_PLAN §3,
# Module 10: Observability & Logging) — every line this process's own
# loggers emit (nexusauth.*) is one JSON object (see JsonFormatter),
# not the plain "%(levelname)s %(name)s %(message)s" text this used to be.
# A handler + JsonFormatter is used directly rather than basicConfig's
# format= string, since basicConfig only accepts a format template, not an
# arbitrary Formatter subclass.
_log_handler = logging.StreamHandler()
_log_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_log_handler])


# Schema architecture: Alembic migrations -> schema verification -> app
# startup. The app never creates or alters its own schema (no
# Base.metadata.create_all in the startup path) — see
# app/database/schema_check.py. If the DB isn't at the expected migration
# head, fail loudly here rather than quietly improvising a schema or letting
# every route hit confusing "column does not exist" errors later.
verify_schema_ready(engine)

_bootstrap_db = SessionLocal()
try:
    bootstrap_admin(_bootstrap_db)
finally:
    _bootstrap_db.close()


app = FastAPI(
    title="Nexus One Authentication Service",
    version="1.0.0",
    description="Intern prototype for Authentication & Token Management.",
    # Branding: docs/redoc are re-defined below as custom routes so the
    # Casterly logo can be injected into them. Disable FastAPI's built-in
    # ones here so there's no duplicate/unbranded route at the same path.
    docs_url=None,
    redoc_url=None,
)
app_settings = get_settings()

# Middleware execution order (outermost first, since Starlette makes the
# LAST add_middleware call the outermost layer): CORS -> SecurityHeaders ->
# RateLimit -> SafeAccessLog -> GZip. CORS needs to be outermost so a
# preflight OPTIONS request is handled before anything else runs.
#
# GZip is deliberately innermost — wrapping the route directly, not
# wrapped by any of the other (BaseHTTPMiddleware-based) layers. Every
# BaseHTTPMiddleware's call_next() reconstructs the downstream response as
# a stream; stacking SafeAccessLog/RateLimit/SecurityHeaders *outside*
# GZip made every response arrive at GZip already "streaming" (more_body
# semantics), which bypasses its minimum_size check entirely and
# compresses even a 70-byte /health response, growing it via gzip's
# framing overhead instead of shrinking it. With GZip innermost, it sees
# the route's real, atomic response first and minimum_size works as
# intended; the small/large decision then simply carries through the
# other middlewares' pass-through streaming untouched.
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(SafeAccessLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    # Doc: "CORS validation" — explicit allow-list (app_settings.cors_origins,
    # from CORS_ALLOWED_ORIGINS), empty by default. This app's own frontend
    # is served same-origin from /static (below), so no cross-origin access
    # is needed until a separately-hosted frontend exists; an empty
    # allow-list means CORSMiddleware simply never adds the "allow" headers,
    # which browsers treat as "cross-origin request denied" — the safe
    # default, not "*".
    allow_origins=app_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_exception_handler(AuthError, auth_error_handler)

BRANDING_DIR = FRONTEND_DIR / "branding"
CASTERLY_FAVICON_URL = "/static/branding/favicon.ico"

# ReDoc reads a logo straight from the OpenAPI document (the "x-logo"
# extension is ReDoc's own documented convention, not something Swagger UI
# understands) — so the branding for /redoc goes on the schema, once,
# rather than on the route.
_original_openapi = app.openapi


def _branded_openapi() -> dict:
    schema = _original_openapi()
    schema["info"]["x-logo"] = {
        "url": "/static/branding/casterly-logo-horizontal.png",
        "backgroundColor": "#1A0A37",
        "altText": "Casterly",
    }
    return schema


app.openapi = _branded_openapi


@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html() -> HTMLResponse:
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
        swagger_favicon_url=CASTERLY_FAVICON_URL,
    )
    # get_swagger_ui_html has no parameter for a logo, and FastAPI's template
    # renders with "layout": "BaseLayout" (not Swagger's own
    # StandaloneLayout), which doesn't even build a topbar element to
    # restyle — there's nothing in the DOM a `.topbar` CSS override could
    # attach to. Simplest reliable option: splice our own logo bar directly
    # into the static HTML, above Swagger UI's mount point, rather than
    # fighting the client-side layout for a topbar it doesn't render.
    branding_css = """
    <style>
        .casterly-topbar {
            background-color: #1A0A37;
            padding: 10px 20px;
        }
        .casterly-topbar img { height: 40px; display: block; }
    </style>
    """
    branding_bar = (
        '<div class="casterly-topbar">'
        '<img src="/static/branding/casterly-logo-horizontal.png" alt="Casterly">'
        "</div>"
    )
    body = response.body.decode("utf-8")
    body = body.replace("</head>", branding_css + "</head>")
    body = body.replace('<div id="swagger-ui">', branding_bar + '<div id="swagger-ui">')
    return HTMLResponse(content=body)


@app.get("/redoc", include_in_schema=False)
def custom_redoc_html() -> HTMLResponse:
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - ReDoc",
        redoc_favicon_url=CASTERLY_FAVICON_URL,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Module 9 (API Standards) §"Error Handling": every error response
    # shares one envelope — {error_code, message, details, trace_id}.
    # FastAPI/Pydantic validation failures (bad body, bad query param,
    # bad path param) previously bypassed that entirely and returned their
    # own bare {"detail": [...]} shape instead — the one error type in
    # this app that didn't follow its own documented error contract.
    trace_id = getattr(request.state, "request_id", None) or new_trace_id()
    logger.info(
        "Validation error on %s %s: %s",
        request.method,
        request.url.path,
        len(exc.errors()),
        extra={
            "context": {
                "event": "validation_error",
                "method": request.method,
                "path": request.url.path,
                "error_count": len(exc.errors()),
                "trace_id": trace_id,
            }
        },
    )
    return JSONResponse(
        status_code=422,
        content=api_error_body(
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=jsonable_encoder(exc.errors()),
            trace_id=trace_id,
        ),
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Doc: "integrity errors are translated into appropriate API responses."
    # Most create/update paths already pre-check uniqueness before writing,
    # but that check-then-insert has an inherent race under concurrency —
    # this is the backstop for that race, and for any FK/constraint
    # violation that isn't pre-checked. Never surface the raw SQL/constraint
    # text (table/column names, driver detail) to the client.
    trace_id = getattr(request.state, "request_id", None) or new_trace_id()
    logger.warning(
        "Integrity error on %s %s: %s",
        request.method,
        request.url.path,
        exc.__class__.__name__,
        extra={
            "context": {
                "event": "integrity_error",
                "method": request.method,
                "path": request.url.path,
                "exception_type": exc.__class__.__name__,
                "trace_id": trace_id,
            }
        },
    )
    return JSONResponse(
        status_code=409,
        content=api_error_body(
            "RESOURCE_CONFLICT",
            "This request conflicts with existing data.",
            trace_id=trace_id,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Last-resort handler. Doc: "unexpected exceptions do not leak stack
    # traces" / "no Python traceback, SQL queries, credentials, or
    # filesystem paths in error responses." The real exception is logged
    # server-side (with a trace_id to correlate) and never put in the body.
    trace_id = getattr(request.state, "request_id", None) or new_trace_id()
    logger.exception(
        "Unhandled error on %s %s (trace_id=%s)",
        request.method,
        request.url.path,
        trace_id,
        extra={
            "context": {
                "event": "unhandled_error",
                "method": request.method,
                "path": request.url.path,
                "trace_id": trace_id,
            }
        },
    )
    return JSONResponse(
        status_code=500,
        content=api_error_body(
            "INTERNAL_ERROR",
            "An unexpected error occurred.",
            trace_id=trace_id,
        ),
    )


@app.get("/")
def home():
    return {
        "message": "FastAPI is working!"
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(BRANDING_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/health")
def health():
    """Liveness — is the process itself up? No dependency checks, no auth:
    an orchestrator/load balancer must be able to call this even if the
    database is down, to tell "the process is wedged" apart from "a
    downstream dependency is unavailable" (that's /readiness).

    Doc: "Application version tracking" / "Build timestamp tracking"
    (Module 10: Metadata & System Information) — version/build_timestamp/
    git_sha let an on-call engineer or deploy pipeline confirm which build
    is actually serving traffic. build_timestamp/git_sha are null unless
    the deploy sets BUILD_TIMESTAMP/GIT_SHA — optional, since neither is
    essential to the process being alive.
    """
    return {
        "status": "ok",
        "version": app.version,
        "build_timestamp": app_settings.build_timestamp,
        "git_sha": app_settings.git_sha,
    }


@app.get("/readiness")
def readiness(response: Response):
    """Readiness — can this instance actually serve traffic? Checks the
    dependencies requests need, currently just PostgreSQL. Never includes
    the exception text, connection string, or credentials in the response —
    only a generic ok/unavailable per check."""
    checks: dict[str, str] = {}
    ready = True

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("Readiness check failed: database unavailable")
        checks["database"] = "unavailable"
        ready = False

    if not ready:
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}


@app.get("/db-test")
def database_test():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        value = result.scalar()

    return {
        "database": "connected",
        "result": value,
    }


app.include_router(auth_router)
app.include_router(company_router)
app.include_router(employee_router)
app.include_router(supplier_router)
app.include_router(asset_router)
app.include_router(audit_log_router)
app.include_router(event_router)
app.include_router(job_role_router)
app.include_router(department_router)
app.include_router(application_router)
app.include_router(manufacturer_router)
app.include_router(asset_model_router)
app.include_router(upload_router)


@app.get("/protected")
def protected_route(current_user: User = Depends(get_current_user)):
    return {
        "message": "You are authenticated",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role,
        },
    }


@app.get("/admin")
def admin_route(current_user: User = Depends(get_admin_user)):
    return {
        "message": "Admin access granted",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "role": current_user.role,
        },
    }


@app.get("/ui", include_in_schema=False)
def ui_page():
    # Cache-busting: browsers aggressively cache /static/* by URL, so an
    # edit to styles.css/app.js can silently keep serving the old file to
    # anyone who navigates normally (not a hard-refresh) — exactly what
    # happened testing the theme rollout. Stamping each asset URL with a
    # hash of its own current content means the URL itself changes the
    # instant the file does, so a plain reload always gets the current
    # version — no one has to remember Ctrl+Shift+R after every edit.
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
    css_hash = hashlib.md5((FRONTEND_DIR / "styles.css").read_bytes()).hexdigest()[:10]
    js_hash = hashlib.md5((FRONTEND_DIR / "app.js").read_bytes()).hexdigest()[:10]
    html = html.replace(
        '<link rel="stylesheet" href="/static/styles.css" />',
        f'<link rel="stylesheet" href="/static/styles.css?v={css_hash}" />',
    )
    html = html.replace(
        '<script src="/static/app.js"></script>',
        f'<script src="/static/app.js?v={js_hash}"></script>',
    )
    # The hash-busted asset URLs above only help if the browser actually
    # re-fetches *this* HTML document on every reload — without an
    # explicit no-store here, a plain reload (including the ones the app
    # fires after every Save/Edit/Delete) can be served straight from the
    # browser's own HTTP cache, silently keeping an old index.html frozen
    # in place (e.g. a version from before full-page-reload-after-save
    # existed), which reads exactly like "it only refreshed the list"
    # even though the current code does a real full reload. /ui is cheap
    # to regenerate, so never let it be cached.
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Employee photo uploads (app/core/uploads.py, app/routes/upload.py).
# StaticFiles requires the directory to already exist at mount time —
# created here, not committed to the repo (see .gitignore), same as the
# venv/pycache directories that already aren't.
_UPLOAD_DIR = Path(app_settings.upload_dir)
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_UPLOAD_DIR), name="uploads")
