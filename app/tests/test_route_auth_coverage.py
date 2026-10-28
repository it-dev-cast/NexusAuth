"""Module 1 (Authentication & Token Management) #10: "Request authentication
middleware" is implemented as a per-route FastAPI dependency
(app.core.dependencies.get_current_user / get_admin_user / require_roles),
not a single global ASGI middleware — see the docstrings there. That's a
deliberate choice, but it means there's no single chokepoint that would
catch a future route added without an auth dependency; a route like that
would silently serve real data to anyone.

This test is the regression guard for that gap: it walks every route
FastAPI actually registered and, for anything not explicitly allow-listed
as intentionally public, asserts that calling it with NO Authorization
header never succeeds (2xx). It doesn't need real path/body data to prove
that — an auth dependency that's actually wired in rejects the call before
the route body (or Pydantic body validation) ever runs.
"""
from app.tests.conftest import client
from main import app

# Routes that are genuinely meant to be reachable without a token — auth
# entry points themselves, health/readiness probes, static assets, and
# docs. Anything not in here is assumed to require authentication.
PUBLIC_PATHS = {
    "/",
    "/health",
    "/readiness",
    "/favicon.ico",
    "/.well-known/jwks.json",  # public keys only
    "/openapi.json",
    "/docs",
    "/redoc",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
}
PUBLIC_PREFIXES = ("/static", "/ui")


def _is_public(path: str) -> bool:
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _dummy_path(path_template: str) -> str:
    # Fill in any {param} path segments with a harmless placeholder — the
    # exact value doesn't matter, since a wired-in auth dependency rejects
    # the call before any route logic that would use it ever runs.
    result = path_template
    while "{" in result:
        start = result.index("{")
        end = result.index("}", start) + 1
        result = result[:start] + "1" + result[end:]
    return result


def _iter_routes(routes):
    # This FastAPI version wraps app.include_router(...) lazily: entries in
    # app.routes for an included router show up as a fastapi.routing.
    # _IncludedRouter wrapper (path=None, methods=None), not flattened
    # APIRoute objects — its real routes live on .original_router.routes.
    # Recurse so nothing registered via include_router (i.e. every real
    # business route in this app) gets silently skipped.
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from _iter_routes(included.routes)
            continue
        yield route


def _protected_routes():
    routes = []
    for route in _iter_routes(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if _is_public(path):
            continue
        for method in methods:
            if method == "HEAD":
                continue
            routes.append((method, path))
    return routes


def test_every_non_public_route_rejects_requests_with_no_auth_header():
    routes = _protected_routes()
    # Sanity check on the test itself: if this list is empty, the walk
    # over app.routes broke silently and the test would pass for the
    # wrong reason (nothing checked).
    assert len(routes) > 10

    failures = []
    for method, path_template in routes:
        url = _dummy_path(path_template)
        response = client.request(method, url, json={} if method in ("POST", "PUT", "PATCH") else None)
        if response.status_code < 300:
            failures.append((method, path_template, response.status_code))

    assert not failures, (
        "These routes returned a 2xx with NO Authorization header — they "
        "are missing an auth dependency: " + str(failures)
    )
