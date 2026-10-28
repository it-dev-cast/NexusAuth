from contextvars import ContextVar
from urllib.parse import parse_qsl, urlencode

# Path and query string of the request being served (set by
# SafeAccessLogMiddleware), used to build next/previous page links.
current_request_target: ContextVar[tuple[str, str] | None] = ContextVar("current_request_target", default=None)


def _page_link(offset: int, limit: int) -> str | None:
    target = current_request_target.get()
    if target is None:
        return None
    path, query = target
    params = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k not in ("offset", "limit")]
    params += [("limit", str(limit)), ("offset", str(offset))]
    return f"{path}?{urlencode(params)}"


def paginated(items: list, total: int, limit: int, offset: int) -> dict:
    """Module 9 (API Standards) §Pagination — one shared response shape for
    every list endpoint: {items, total, limit, offset, has_more}. Every
    list service previously built this dict by hand at each call site with
    an identical {items, total, limit, offset} shape and no has_more, so a
    client had to derive "is there a next page?" itself from
    offset/limit/total arithmetic. Centralizing it here means that shape
    (and the has_more rule) only has one definition, not five duplicated
    ones — and getting a next page is just offset + limit.
    """
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
        # Relative links to the neighbouring pages (same filters and sort),
        # or null at either end.
        "next": _page_link(offset + limit, limit) if offset + len(items) < total else None,
        "previous": _page_link(max(offset - limit, 0), limit) if offset > 0 else None,
    }
