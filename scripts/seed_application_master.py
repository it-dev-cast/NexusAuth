"""One-off seed for the Application master list, per the exact taxonomy
the user specified. Idempotent: re-running skips any name that already
exists rather than erroring on the unique-name constraint, so it's safe
to run again after adding "Dashboard" by hand (or anything else)."""

import re

from app.database.database import SessionLocal
from app.models.application import Application

CATALOG: dict[str, list[str]] = {
    "Core": ["Dashboard", "Notifications", "Reports & Analytics"],
    "People": [
        "HR / Employee Management",
        "Department Management",
        "User Management",
        "Role & Permission Management",
    ],
    "Assets": [
        "Asset Management",
        "Asset Allocation",
        "Asset Transfer",
        "Asset Return",
        "Refurbishing",
        "Maintenance",
    ],
    "Operations": [
        "Procurement",
        "Supplier Management",
        "Inventory Management",
        "Request Management",
        "Approval Management",
    ],
    "Administration": [
        "Company Management",
        "Branch / Location Management",
        "Application Master",
        "Audit & Logs",
        "Settings",
        "Configuration",
    ],
}


def _code_for(name: str, taken: set[str]) -> str:
    """HR / Employee Management -> HR_EMPLOYEE_MANAGEMENT (same rule the
    migration used for the existing rows); a clash gets a numeric suffix."""
    base = (re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "APP")[:36]
    code, n = base, 2
    while code in taken:
        code = f"{base}_{n}"
        n += 1
    return code


def main() -> None:
    db = SessionLocal()
    try:
        existing = {name for (name,) in db.query(Application.name).all()}
        taken_codes = {code for (code,) in db.query(Application.code).all()}
        created = 0
        for category, names in CATALOG.items():
            for name in names:
                if name in existing:
                    continue
                code = _code_for(name, taken_codes)
                taken_codes.add(code)
                db.add(Application(name=name, code=code, category=category, is_active=True))
                created += 1
        db.commit()
        print(f"created {created} application(s); {len(existing)} already existed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
