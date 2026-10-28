"""Generic filter operators, multi-field sorting and unknown-parameter
rejection for list endpoints (gaps #23-#25).

A list endpoint opts in with `Depends(list_query(Model))`. On top of its
existing parameters, a caller can then send:

  <field>[<op>]=<value>   eq, contains, in, gt, lt, gte, lte, range
                           e.g. created_at[gte]=2026-01-01, status[in]=approved,suspended,
                           rating[range]=3,5, name[contains]=dell
  sort=<field>,-<field>   up to 3 fields, "-" for descending; overrides sort_by/sort_dir

Any query parameter the endpoint doesn't declare, an unknown field, or an
operator that doesn't fit the field's type is a 422. Only plain columns of the
model can be used: PII, credentials and encrypted columns are never filterable
or sortable. Values are bound parameters; no SQL is built from input text.

The parsed query travels to the repository through a context variable, set
here per request and read by apply_list_filters()/list_order() inside the
repository's existing filter/order code, so the services in between keep
their signatures.
"""
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import inspect as sa_inspect

from app.core.audit import PII_FIELDS, SECRET_FIELDS
from app.database.encrypted_types import EncryptedString

MAX_SORT_FIELDS = 3
MAX_IN_VALUES = 100
_FILTER_KEY = re.compile(r"([a-z_][a-z0-9_]*)\[([a-z]+)\]")
_OPERATORS = {
    str: ("eq", "contains", "in"),
    int: ("eq", "in", "gt", "lt", "gte", "lte", "range"),
    float: ("eq", "gt", "lt", "gte", "lte", "range"),
    Decimal: ("eq", "gt", "lt", "gte", "lte", "range"),
    datetime: ("gt", "lt", "gte", "lte", "range"),
    date: ("eq", "gt", "lt", "gte", "lte", "range"),
    bool: ("eq",),
}


# Shown on every list endpoint in /docs.
LIST_QUERY_HELP = (
    "Besides the parameters below: filter with `field[op]=value` "
    "(ops: eq, contains, in, gt, lt, gte, lte, range — e.g. `created_at[gte]=2026-01-01`, "
    "`status[in]=approved,suspended`, `id[range]=10,20`) and sort with "
    "`sort=-created_at,name` (up to 3 fields, `-` = descending). Unknown parameters, "
    "fields or operators return 422. Pages include `next`/`previous` links."
)


@dataclass
class ListQuery:
    model: type
    filters: list = field(default_factory=list)
    order_by: list = field(default_factory=list)


current_list_query: ContextVar[ListQuery | None] = ContextVar("current_list_query", default=None)


def filterable_columns(model) -> dict:
    """Plain columns of `model` usable in filters and sorts."""
    columns = {}
    for column in sa_inspect(model).columns:
        if column.key in PII_FIELDS or column.key in SECRET_FIELDS or isinstance(column.type, EncryptedString):
            continue
        try:
            python_type = column.type.python_type
        except NotImplementedError:
            continue
        if python_type in _OPERATORS:
            columns[column.key] = (getattr(model, column.key), python_type)
    return columns


def _declared_query_params(request: Request) -> set[str]:
    route = request.scope.get("route")
    names: set[str] = set()
    pending = [route.dependant] if route is not None else []
    while pending:
        dependant = pending.pop()
        names.update(param.alias for param in dependant.query_params)
        pending.extend(dependant.dependencies)
    return names


def _parse(raw: str, python_type):
    raw = raw.strip()
    if python_type is bool:
        if raw.lower() in ("true", "1"):
            return True
        if raw.lower() in ("false", "0"):
            return False
        raise ValueError("expected true or false")
    if python_type is datetime:
        return datetime.fromisoformat(raw)
    if python_type is date:
        return date.fromisoformat(raw)
    if python_type is Decimal:
        try:
            return Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError("expected a number") from exc
    if python_type is int and not re.fullmatch(r"-?\d{1,18}", raw):
        raise ValueError("expected an integer")
    return python_type(raw)


def _condition(column, python_type, op: str, raw: str):
    if op == "contains":
        escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return column.ilike(f"%{escaped}%", escape="\\")
    if op == "in":
        values = [part for part in raw.split(",") if part.strip()]
        if not values or len(values) > MAX_IN_VALUES:
            raise ValueError(f"give 1 to {MAX_IN_VALUES} comma-separated values")
        return column.in_([_parse(v, python_type) for v in values])
    if op == "range":
        parts = raw.split(",")
        if len(parts) != 2:
            raise ValueError("give two comma-separated values: from,to")
        low, high = (_parse(p, python_type) for p in parts)
        return column.between(low, high)
    value = _parse(raw, python_type)
    return {
        "eq": column == value,
        "gt": column > value,
        "lt": column < value,
        "gte": column >= value,
        "lte": column <= value,
    }[op]


def list_query(model):
    """Dependency for a list endpoint over `model`. Must stay `async`: it has
    to set the context variable in the request's own context, not in a
    worker thread's copy."""
    columns = filterable_columns(model)

    async def dependency(request: Request) -> None:
        declared = _declared_query_params(request)
        query = ListQuery(model)
        errors = []

        def reject(key: str, message: str, value: str) -> None:
            errors.append({"type": "value_error", "loc": ("query", key), "msg": message, "input": value})

        for key, raw in request.query_params.multi_items():
            match = _FILTER_KEY.fullmatch(key)
            if match:
                name, op = match.groups()
                if name not in columns:
                    reject(key, f"'{name}' can't be filtered. Filterable fields: {', '.join(sorted(columns))}.", raw)
                    continue
                column, python_type = columns[name]
                if op not in _OPERATORS[python_type]:
                    reject(key, f"'{op}' isn't supported for '{name}'. Use one of: {', '.join(_OPERATORS[python_type])}.", raw)
                    continue
                try:
                    query.filters.append(_condition(column, python_type, op, raw))
                except (ValueError, TypeError) as exc:
                    reject(key, f"Invalid value for {name}[{op}]: {exc}.", raw)
            elif key == "sort":
                fields_ = [part.strip() for part in raw.split(",") if part.strip()]
                if not fields_ or len(fields_) > MAX_SORT_FIELDS:
                    reject(key, f"Sort by 1 to {MAX_SORT_FIELDS} fields, e.g. sort=-created_at,name.", raw)
                    continue
                for part in fields_:
                    name = part.lstrip("-")
                    if name not in columns:
                        reject(key, f"'{name}' can't be sorted on. Sortable fields: {', '.join(sorted(columns))}.", raw)
                        continue
                    column = columns[name][0]
                    query.order_by.append(column.desc() if part.startswith("-") else column.asc())
            elif key not in declared:
                reject(key, f"Unknown query parameter '{key}'.", raw)

        if errors:
            raise RequestValidationError(errors)
        if query.order_by:
            # A stable tie-breaker so pages never overlap or skip rows.
            query.order_by.append(sa_inspect(model).primary_key[0].asc())
        current_list_query.set(query)

    return dependency


def _active(model) -> ListQuery | None:
    query = current_list_query.get()
    return query if query is not None and query.model is model else None


def apply_list_filters(query, model):
    active = _active(model)
    return query.filter(*active.filters) if active and active.filters else query


def list_order(model, *default) -> list:
    """The caller's `sort=` order if given, else the endpoint's default."""
    active = _active(model)
    return active.order_by if active and active.order_by else list(default)
