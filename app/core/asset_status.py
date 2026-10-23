class AssetStatus:
    REGISTERED = "registered"
    IN_REPAIR = "in_repair"
    CERTIFIED = "certified"
    DISPOSED = "disposed"


ALL_STATUSES = {
    AssetStatus.REGISTERED,
    AssetStatus.IN_REPAIR,
    AssetStatus.CERTIFIED,
    AssetStatus.DISPOSED,
}

# Doc: "Asset status field (registered, in_repair, certified, etc.)" — the
# "etc." is Refurbishment's QC workflow (Module 6 App layer) adding more
# granular states later. Foundation Core only needs to own the field and a
# minimal, honest state machine for it:
#   registered -> in_repair   : work order opened on it
#   in_repair  -> certified   : QC passed
#   certified  -> in_repair   : QC/warranty issue found, sent back for rework
#   any        -> disposed    : soft-delete (see DISPOSED note below)
# DISPOSED is terminal, same pattern as Employee's "exited" and reached the
# same way — soft_delete_asset() routes through this same transition path.
VALID_TRANSITIONS: dict[str, set[str]] = {
    AssetStatus.REGISTERED: {AssetStatus.IN_REPAIR, AssetStatus.DISPOSED},
    AssetStatus.IN_REPAIR: {AssetStatus.CERTIFIED, AssetStatus.DISPOSED},
    AssetStatus.CERTIFIED: {AssetStatus.IN_REPAIR, AssetStatus.DISPOSED},
    AssetStatus.DISPOSED: set(),
}


def is_valid_transition(current: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(current, set())
