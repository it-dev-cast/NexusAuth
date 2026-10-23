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
    }
