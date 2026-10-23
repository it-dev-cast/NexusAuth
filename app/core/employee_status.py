class EmployeeStatus:
    ONBOARDED = "onboarded"
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    EXITED = "exited"


ALL_STATUSES = {
    EmployeeStatus.ONBOARDED,
    EmployeeStatus.ACTIVE,
    EmployeeStatus.ON_LEAVE,
    EmployeeStatus.EXITED,
}

# Which status an employee may move to from their current one. EXITED is
# terminal — once someone has exited, they don't transition back.
VALID_TRANSITIONS: dict[str, set[str]] = {
    EmployeeStatus.ONBOARDED: {EmployeeStatus.ACTIVE, EmployeeStatus.EXITED},
    EmployeeStatus.ACTIVE: {EmployeeStatus.ON_LEAVE, EmployeeStatus.EXITED},
    EmployeeStatus.ON_LEAVE: {EmployeeStatus.ACTIVE, EmployeeStatus.EXITED},
    EmployeeStatus.EXITED: set(),
}


def is_valid_transition(current: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(current, set())
