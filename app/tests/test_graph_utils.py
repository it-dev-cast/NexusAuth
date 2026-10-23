from app.core.graph_utils import creates_cycle


def test_no_parent_is_never_a_cycle():
    assert creates_cycle({}, node_id=1, proposed_parent_id=None) is False


def test_self_parent_is_a_cycle():
    assert creates_cycle({}, node_id=1, proposed_parent_id=1) is True


def test_simple_chain_is_not_a_cycle():
    # 3 -> 2 -> 1 (parent_of[child] = parent). Assigning 1's parent to 3 is fine.
    parent_of = {2: 1, 3: 2}
    assert creates_cycle(parent_of, node_id=4, proposed_parent_id=3) is False


def test_assignment_that_would_close_a_loop_is_a_cycle():
    # 2 -> 1, 3 -> 2. Proposing 1's parent = 3 would close 1 -> 3 -> 2 -> 1.
    parent_of = {2: 1, 3: 2}
    assert creates_cycle(parent_of, node_id=1, proposed_parent_id=3) is True


def test_corrupt_existing_data_is_treated_as_a_cycle_not_infinite_loop():
    # Pre-existing bad data: 1 -> 2 -> 1. Must terminate, not loop forever.
    parent_of = {1: 2, 2: 1}
    assert creates_cycle(parent_of, node_id=5, proposed_parent_id=1) is True
