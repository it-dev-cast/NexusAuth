from sqlalchemy.orm import Session

from app.core.errors import AuthError
from app.core.master_data import (
    GROUP_ORDER,
    LINKED_MASTERS,
    MASTER_TYPES,
    MasterType,
    get_master_type,
)
from app.core.pagination import paginated
from app.models.master_item import MasterItem
from app.repositories import master_item_repository as repo
from app.schemas.master_item import (
    MasterItemCreateRequest,
    MasterItemResponse,
    MasterItemUpdateRequest,
)
from app.services.audit_service import record_audit_event

OPTIONS_LIMIT = 1000  # a dropdown never needs more; keeps the payload bounded
ALLOWED_STATUS = {"active", "inactive", "all"}
ALLOWED_SORTS = {"name", "code", "created_at"}


def _a(label: str) -> str:
    """"a city" / "an employment type" — for readable messages."""
    return f"{'An' if label[:1].lower() in 'aeiou' else 'A'} {label.lower()}"


def _error(code: str, message: str, status_code: int = 400) -> AuthError:
    return AuthError(status_code=status_code, error_code=code, message=message)


def require_master_type(raw: str) -> MasterType:
    master_type = get_master_type(raw)
    if master_type is None:
        raise _error("MASTER_TYPE_NOT_FOUND", "Unknown master data list.", status_code=404)
    return master_type


# ---------------------------------------------------------------------------
# Response building
# ---------------------------------------------------------------------------
def _decorate(db: Session, items: list[MasterItem]) -> list[MasterItem]:
    """Attach parent_name / path / usage_count / children_count to rows for
    the response (batched, so a page of 100 rows is a handful of queries)."""
    if not items:
        return items

    # Walk the parent chain level by level (at most 3 deep: location -> city
    # -> state -> country), loading each level in one query.
    known: dict[int, MasterItem] = {i.id: i for i in items}
    frontier = {i.parent_id for i in items if i.parent_id and i.parent_id not in known}
    for _ in range(4):
        if not frontier:
            break
        loaded = repo.get_items_by_ids(db, list(frontier))
        known.update(loaded)
        frontier = {p.parent_id for p in loaded.values() if p.parent_id and p.parent_id not in known}

    def chain(item: MasterItem) -> list[str]:
        names, seen, current = [], set(), item.parent_id
        while current and current not in seen and current in known:
            seen.add(current)
            names.append(known[current].name)
            current = known[current].parent_id
        return names

    children = repo.children_counts(db, [i.id for i in items])
    by_type: dict[str, list[MasterItem]] = {}
    for i in items:
        by_type.setdefault(i.master_type, []).append(i)
    usage: dict[tuple[str, str], int] = {}
    for master_type, group in by_type.items():
        for name, n in repo.usage_counts(db, master_type, [i.name for i in group]).items():
            usage[(master_type, name)] = n

    for i in items:
        ancestors = chain(i)
        i.parent_name = ancestors[0] if ancestors else None
        i.path = ", ".join([i.name, *ancestors]) if ancestors else i.name
        i.usage_count = usage.get((i.master_type, i.name), 0)
        i.children_count = children.get(i.id, 0)
    return items


def _snapshot(db: Session, item: MasterItem) -> dict:
    _decorate(db, [item])
    return MasterItemResponse.model_validate(item).model_dump(mode="json")


def to_response(db: Session, item: MasterItem) -> dict:
    _decorate(db, [item])
    return MasterItemResponse.model_validate(item).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_parent(db: Session, master_type: MasterType, parent_id: int | None) -> None:
    if master_type.parent_type is None:
        if parent_id is not None:
            raise _error(
                "MASTER_ITEM_PARENT_NOT_ALLOWED",
                f"{master_type.label} items don't have a parent.",
            )
        return
    parent_label = MASTER_TYPES[master_type.parent_type].label
    if parent_id is None:
        if master_type.parent_required:
            raise _error("MASTER_ITEM_PARENT_REQUIRED", f"A {master_type.label.lower()} must belong to a {parent_label.lower()}.")
        return
    parent = repo.get_item_by_id(db, parent_id)
    if parent is None or parent.master_type != master_type.parent_type:
        raise _error("MASTER_ITEM_PARENT_INVALID", f"The parent must be an existing {parent_label.lower()}.")
    if not parent.is_active:
        raise _error("MASTER_ITEM_PARENT_INACTIVE", f"The {parent_label.lower()} '{parent.name}' is inactive.")


def _check_duplicates(
    db: Session,
    master_type: MasterType,
    name: str,
    code: str | None,
    parent_id: int | None,
    exclude_id: int | None = None,
) -> None:
    existing = repo.find_item_by_name(db, master_type.key, name, parent_id)
    if existing and existing.id != exclude_id:
        raise _error(
            "MASTER_ITEM_ALREADY_EXISTS",
            f"{_a(master_type.label)} named '{existing.name}' already exists"
            + (" in this parent." if parent_id is not None else "."),
        )
    if code:
        same_code = repo.find_item_by_code(db, master_type.key, code)
        if same_code and same_code.id != exclude_id:
            raise _error(
                "MASTER_ITEM_CODE_ALREADY_EXISTS",
                f"The code '{code}' is already used by '{same_code.name}'.",
            )


def _require_item(db: Session, master_type: MasterType, item_id: int) -> MasterItem:
    item = repo.get_item_by_id(db, item_id)
    # An id from a different list is "not found" here, so one list's screen
    # can't read or edit another list's rows by guessing ids.
    if item is None or item.master_type != master_type.key:
        raise _error("MASTER_ITEM_NOT_FOUND", f"{master_type.label} not found.", status_code=404)
    return item


# ---------------------------------------------------------------------------
# Public operations
# ---------------------------------------------------------------------------
def create_master_item(db: Session, raw_type: str, data: MasterItemCreateRequest, actor_id: int | None) -> MasterItem:
    master_type = require_master_type(raw_type)
    code = data.code if master_type.has_code else None
    if data.code and not master_type.has_code:
        raise _error("MASTER_ITEM_CODE_NOT_SUPPORTED", f"{master_type.plural} don't use a code.")
    _validate_parent(db, master_type, data.parent_id)
    _check_duplicates(db, master_type, data.name, code, data.parent_id)

    item = repo.create_item(
        db,
        MasterItem(
            master_type=master_type.key,
            name=data.name,
            code=code,
            description=data.description,
            parent_id=data.parent_id,
            is_active=True,
        ),
    )
    record_audit_event(db, actor_id, "create", "master_item", item.id, old_value=None, new_value=_snapshot(db, item))
    return item


def get_master_item(db: Session, raw_type: str, item_id: int) -> MasterItem:
    master_type = require_master_type(raw_type)
    item = _require_item(db, master_type, item_id)
    _decorate(db, [item])
    return item


def list_master_items(
    db: Session,
    raw_type: str,
    limit: int,
    offset: int,
    status: str,
    search: str | None,
    parent_id: int | None,
    sort_by: str,
    sort_dir: str,
) -> dict:
    master_type = require_master_type(raw_type)
    if status not in ALLOWED_STATUS:
        raise _error("MASTER_INVALID_FILTER", "status must be one of: active, inactive, all.")
    if sort_by not in ALLOWED_SORTS:
        raise _error("MASTER_INVALID_SORT", f"sort_by must be one of: {', '.join(sorted(ALLOWED_SORTS))}.")
    if sort_dir not in ("asc", "desc"):
        raise _error("MASTER_INVALID_SORT", "sort_dir must be asc or desc.")
    items = repo.list_items(db, master_type.key, limit, offset, status, search, parent_id, sort_by, sort_dir)
    total = repo.count_items(db, master_type.key, status, search, parent_id)
    _decorate(db, items)
    return paginated(items, total, limit, offset)


def list_master_options(db: Session, raw_type: str, parent_id: int | None) -> list[dict]:
    """Every ACTIVE item of a list, for filling dropdowns — unpaginated (up
    to OPTIONS_LIMIT) and without usage counts, so it stays cheap."""
    master_type = require_master_type(raw_type)
    items = repo.list_option_items(db, master_type.key, parent_id, OPTIONS_LIMIT)
    return [
        {"id": i.id, "name": i.name, "code": i.code, "parent_id": i.parent_id}
        for i in items
    ]


def update_master_item(
    db: Session, raw_type: str, item_id: int, data: MasterItemUpdateRequest, actor_id: int | None
) -> MasterItem:
    master_type = require_master_type(raw_type)
    item = _require_item(db, master_type, item_id)
    old_snapshot = _snapshot(db, item)
    fields = data.model_fields_set

    new_name = data.name if "name" in fields and data.name is not None else item.name
    new_code = item.code
    if "code" in fields:
        if data.code and not master_type.has_code:
            raise _error("MASTER_ITEM_CODE_NOT_SUPPORTED", f"{master_type.plural} don't use a code.")
        new_code = data.code
    new_parent = data.parent_id if "parent_id" in fields else item.parent_id

    if new_name != item.name and new_name.lower() != item.name.lower():
        # Entities store a value's name as text, so renaming one that is in
        # use would silently detach those records from it. Deactivate the
        # old value and add a new one instead.
        if old_snapshot["usage_count"] > 0:
            raise _error(
                "MASTER_ITEM_IN_USE",
                f"'{item.name}' is used by {old_snapshot['usage_count']} record(s), so it can't be renamed. "
                "Deactivate it and add a new value instead.",
            )
    if new_parent != item.parent_id:
        _validate_parent(db, master_type, new_parent)
    _check_duplicates(db, master_type, new_name, new_code, new_parent, exclude_id=item.id)

    item.name = new_name
    item.code = new_code
    if "description" in fields:
        item.description = data.description
    item.parent_id = new_parent
    db.commit()
    db.refresh(item)
    record_audit_event(
        db, actor_id, "update", "master_item", item.id, old_value=old_snapshot, new_value=_snapshot(db, item)
    )
    return item


def deactivate_master_item(db: Session, raw_type: str, item_id: int, actor_id: int | None) -> MasterItem:
    master_type = require_master_type(raw_type)
    item = _require_item(db, master_type, item_id)
    if not item.is_active:
        _decorate(db, [item])
        return item
    if repo.count_children(db, item.id, active_only=True) > 0:
        raise _error(
            "MASTER_ITEM_HAS_ACTIVE_CHILDREN",
            f"'{item.name}' still has active items under it. Deactivate those first.",
        )
    old_snapshot = _snapshot(db, item)
    # Records already using the value keep it (history is untouched); it just
    # stops being offered in dropdowns.
    item.is_active = False
    db.commit()
    db.refresh(item)
    record_audit_event(
        db, actor_id, "delete", "master_item", item.id, old_value=old_snapshot, new_value=_snapshot(db, item)
    )
    return item


def reactivate_master_item(db: Session, raw_type: str, item_id: int, actor_id: int | None) -> MasterItem:
    master_type = require_master_type(raw_type)
    item = _require_item(db, master_type, item_id)
    if item.is_active:
        _decorate(db, [item])
        return item
    if item.parent_id is not None:
        parent = repo.get_item_by_id(db, item.parent_id)
        if parent is not None and not parent.is_active:
            raise _error(
                "MASTER_ITEM_PARENT_INACTIVE",
                f"Reactivate '{parent.name}' first — it is the parent of '{item.name}' and is inactive.",
            )
    old_snapshot = _snapshot(db, item)
    item.is_active = True
    db.commit()
    db.refresh(item)
    record_audit_event(
        db, actor_id, "update", "master_item", item.id, old_value=old_snapshot, new_value=_snapshot(db, item)
    )
    return item


# ---------------------------------------------------------------------------
# Catalog (everything the Master Management dropdown offers)
# ---------------------------------------------------------------------------
def get_catalog(db: Session) -> dict:
    """Every master, in the order the Master Management dropdown lists them:
    by group, then the masters that have their own screens, then the list
    masters. `kind` says how the page shows one: "page" (its existing screen)
    or "list" (the generic list screen)."""
    totals = repo.type_totals(db)
    linked_counts = repo.linked_totals(db)
    entries = []
    for m in LINKED_MASTERS.values():
        active, total = linked_counts.get(m.key, (0, 0))
        entries.append(
            {
                "key": m.key,
                "slug": m.key.replace("_", "-"),
                "label": m.label,
                "plural": m.plural,
                "description": m.description,
                "group": m.group,
                "used_by": m.used_by,
                "kind": "page",
                "active_count": active,
                "total_count": total,
            }
        )
    for t in MASTER_TYPES.values():
        active, total = totals.get(t.key, (0, 0))
        entries.append(
            {
                "key": t.key,
                "slug": t.key.replace("_", "-"),
                "label": t.label,
                "plural": t.plural,
                "description": t.description,
                "group": t.group,
                "used_by": t.used_by,
                "kind": "list",
                "active_count": active,
                "total_count": total,
            }
        )
    rank = {"page": 0, "list": 1}
    entries.sort(key=lambda m: (GROUP_ORDER.index(m["group"]), rank[m["kind"]]))
    return {"groups": list(GROUP_ORDER), "masters": entries}
