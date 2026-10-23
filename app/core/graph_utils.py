"""Circular dependency detection (Foundation Core Module 7).

Nothing in the current schema is hierarchical — Company -> Employee -> User
is a strict tree, not a graph that can cycle. This utility exists as
ready-to-use infrastructure for the day a self-referencing relationship
shows up (e.g. an Employee.manager_id "reports to" chain in a future HR
module), so that relationship doesn't ship without a cycle guard from day
one.

Usage once such a relationship exists:

    parent_of = {emp.id: emp.manager_id for emp in all_employees}
    if creates_cycle(parent_of, employee_id, new_manager_id):
        raise ...  # reject the assignment
"""


def creates_cycle(
    parent_of: dict[int, int | None],
    node_id: int,
    proposed_parent_id: int | None,
) -> bool:
    """Would setting node_id's parent to proposed_parent_id create a cycle?

    `parent_of` maps every node to its current parent (None = no parent).
    Walks up from the proposed parent; if it ever reaches node_id, applying
    that assignment would create a loop.
    """
    if proposed_parent_id is None:
        return False
    if proposed_parent_id == node_id:
        return True

    seen: set[int] = set()
    current = proposed_parent_id
    while current is not None:
        if current == node_id:
            return True
        if current in seen:
            # Already-corrupt data upstream — treat as a cycle rather than
            # loop forever.
            return True
        seen.add(current)
        current = parent_of.get(current)

    return False
