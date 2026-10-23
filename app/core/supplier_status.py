class SupplierStatus:
    ONBOARDED = "onboarded"
    APPROVED = "approved"
    SUSPENDED = "suspended"


ALL_STATUSES = {
    SupplierStatus.ONBOARDED,
    SupplierStatus.APPROVED,
    SupplierStatus.SUSPENDED,
}

# Which status a supplier may move to from their current one.
#   onboarded -> approved             : passes vetting, can now be referenced by Assets
#   approved  -> suspended            : found unreliable / under review
#   suspended -> approved             : reinstated after review
# Unlike Employee's "exited", there is no terminal state here — a supplier
# relationship can always be reinstated, matching the doc's lifecycle
# (onboarded -> approved -> suspended) with no separate delete/soft-delete
# logic listed for Suppliers.
VALID_TRANSITIONS: dict[str, set[str]] = {
    SupplierStatus.ONBOARDED: {SupplierStatus.APPROVED},
    SupplierStatus.APPROVED: {SupplierStatus.SUSPENDED},
    SupplierStatus.SUSPENDED: {SupplierStatus.APPROVED},
}


def is_valid_transition(current: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(current, set())
