"""OpenAPI enrichment (gaps #27/#58). Routes return `api_ok(...)` dicts, so
FastAPI documents every response as an untyped object and every 422 in its
own `{detail}` shape, which is not what the API sends. This post-processes the
generated spec in one place, without touching the routes:

* the real error envelope as a schema, with an example, on 401/403/404/409/
  422/429/500 responses wherever they can occur;
* the roles each operation accepts (from its role dependency), in the
  description and as `x-required-roles`;
* typed `{data, meta}` success schemas for the main resources, using the
  existing *Response models (paginated shape for their list endpoints).
"""
from pydantic import BaseModel

from app.schemas.application import ApplicationResponse
from app.schemas.asset import AssetResponse
from app.schemas.asset_model import AssetModelResponse
from app.schemas.audit_log import AuditLogResponse
from app.schemas.auth import UserResponse
from app.schemas.company import CompanyResponse
from app.schemas.department import DepartmentResponse
from app.schemas.employee import EmployeeResponse
from app.schemas.event import EventResponse
from app.schemas.job_role import JobRoleResponse
from app.schemas.manufacturer import ManufacturerResponse
from app.schemas.supplier import SupplierResponse

REF = "#/components/schemas/"

# Collection path -> the model of one item.
RESOURCES: dict[str, type[BaseModel]] = {
    "/api/v1/companies": CompanyResponse,
    "/api/v1/employees": EmployeeResponse,
    "/api/v1/suppliers": SupplierResponse,
    "/api/v1/assets": AssetResponse,
    "/api/v1/departments": DepartmentResponse,
    "/api/v1/job-roles": JobRoleResponse,
    "/api/v1/applications": ApplicationResponse,
    "/api/v1/manufacturers": ManufacturerResponse,
    "/api/v1/asset-models": AssetModelResponse,
    "/api/v1/audit-logs": AuditLogResponse,
    "/api/v1/events": EventResponse,
}

ERROR_SCHEMA = {
    "type": "object",
    "required": ["error_code", "message", "trace_id"],
    "properties": {
        "error_code": {"type": "string", "description": "Stable machine-readable code, e.g. VALIDATION_ERROR, AUTH_FORBIDDEN, COMPANY_NOT_FOUND."},
        "message": {"type": "string", "description": "Human-readable explanation."},
        "details": {"description": "Optional. For VALIDATION_ERROR, one entry per invalid field (type, loc, msg)."},
        "trace_id": {"type": "string", "description": "Same value as the X-Request-Id response header."},
    },
    "example": {
        "error_code": "VALIDATION_ERROR",
        "message": "Request validation failed.",
        "details": [{"type": "missing", "loc": ["body", "name"], "msg": "Field required"}],
        "trace_id": "4f1c2b9e8d7a4c3b",
    },
}

ERROR_DESCRIPTIONS = {
    "401": "Missing, malformed, expired or revoked access token (AUTH_MALFORMED_HEADER, AUTH_INVALID_TOKEN, AUTH_TOKEN_EXPIRED, AUTH_TOKEN_REVOKED).",
    "403": "Signed in, but this role may not do this (AUTH_FORBIDDEN), or a rule forbids it (e.g. EMPLOYEE_LINK_FORBIDDEN).",
    "404": "The resource doesn't exist, or belongs to another company (<RESOURCE>_NOT_FOUND, NOT_FOUND).",
    "409": "Conflicts with existing data (RESOURCE_CONFLICT, ASSET_TAG_ALREADY_EXISTS, SUPPLIER_NOT_APPROVED, ...).",
    "422": "Invalid input: body, path or query (VALIDATION_ERROR). Values of personal-data and password fields are never echoed back.",
    "429": "Too many attempts from this address (RATE_LIMITED). Retry after the Retry-After header.",
    "500": "Unexpected server error (INTERNAL_ERROR). Quote trace_id when reporting it.",
}

GENERAL_HELP = """
**Responses.** Success: `{"data": ..., "meta": {"trace_id": ...}}`. Lists put
`{items, total, limit, offset, has_more, next, previous}` in `data`.
Errors: `{"error_code", "message", "details", "trace_id"}` (schema `ErrorResponse`).

**Authentication.** `Authorization: Bearer <access token>` from `POST /api/v1/auth/login`.
Each operation lists the roles it accepts. Operators and read-only users only
see their own company's companies and employees.

**Versioning.** Every `/api/v1` response carries `X-API-Version: v1`.
"""


def _iter_routes(routes, prefix: str = ""):
    """Every endpoint route with its full path. Newer FastAPI keeps included
    routers as wrapper objects instead of copying their routes up."""
    for route in routes:
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            yield from _iter_routes(included.routes, prefix + (getattr(context, "prefix", "") or ""))
        elif getattr(route, "dependant", None) is not None:
            yield prefix + route.path, route


def _role_map(app) -> dict[tuple[str, str], list[str]]:
    roles = {}
    for path, route in _iter_routes(app.routes):
        dependant = route.dependant
        if dependant is None:
            continue
        found = None
        pending = list(dependant.dependencies)
        while pending and found is None:
            dep = pending.pop(0)
            found = getattr(dep.call, "required_roles", None)
            pending.extend(dep.dependencies)
        if found:
            for method in route.methods:
                roles[(path, method.lower())] = found
    return roles


def _envelope(item_ref: dict, paginated: bool) -> dict:
    data = item_ref
    if paginated:
        data = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": item_ref},
                "total": {"type": "integer"},
                "limit": {"type": "integer"},
                "offset": {"type": "integer"},
                "has_more": {"type": "boolean"},
                "next": {"type": ["string", "null"], "example": "/api/v1/suppliers?limit=20&offset=20"},
                "previous": {"type": ["string", "null"]},
            },
        }
    return {
        "type": "object",
        "properties": {"data": data, "meta": {"type": "object", "properties": {"trace_id": {"type": "string"}}}},
    }


def enrich_openapi(schema: dict, app) -> dict:
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components["ErrorResponse"] = ERROR_SCHEMA
    for model in RESOURCES.values():
        model_schema = model.model_json_schema(ref_template=REF + "{model}")
        for name, nested in model_schema.pop("$defs", {}).items():
            components.setdefault(name, nested)
        components[model.__name__] = model_schema
    # FastAPI's own validation schemas describe a body this API never sends.
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)

    schema["info"]["description"] = (schema["info"].get("description") or "") + "\n" + GENERAL_HELP
    error_ref = {"$ref": REF + "ErrorResponse"}
    roles = _role_map(app)

    for path, operations in schema.get("paths", {}).items():
        for method, operation in operations.items():
            responses = operation.setdefault("responses", {})
            secured = bool(operation.get("security"))
            codes = ["422", "500"]
            if secured:
                codes += ["401", "403"]
            if "{" in path:
                codes.append("404")
            if method in ("post", "put", "patch"):
                codes.append("409")
            if path in ("/api/v1/auth/login", "/api/v1/auth/register"):
                codes.append("429")
            for code in codes:
                responses[code] = {
                    "description": ERROR_DESCRIPTIONS[code],
                    "content": {"application/json": {"schema": error_ref}},
                }

            allowed = roles.get((path, method))
            if allowed:
                operation["x-required-roles"] = allowed
                note = "**Roles:** " + ", ".join(allowed)
                operation["description"] = f"{note}\n\n{operation.get('description', '')}".strip()

            for collection, model in RESOURCES.items():
                item_ref = {"$ref": REF + model.__name__}
                ok = "201" if "201" in responses else "200"
                if path == collection and method == "get":
                    content = _envelope(item_ref, paginated=True)
                elif path.startswith(collection + "/{") and path.count("/") == collection.count("/") + 1:
                    content = _envelope(item_ref, paginated=False)
                elif path == collection and method == "post":
                    content = _envelope(item_ref, paginated=False)
                else:
                    continue
                responses.setdefault(ok, {"description": "Success"})["content"] = {"application/json": {"schema": content}}
                break
    return schema
