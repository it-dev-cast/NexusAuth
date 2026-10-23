"""One-off seed for the Application master list, per the exact taxonomy
the user specified. Idempotent: re-running skips any name that already
exists rather than erroring on the unique-name constraint, so it's safe
to run again after adding "Dashboard" by hand (or anything else)."""

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


def main() -> None:
    db = SessionLocal()
    try:
        existing = {name for (name,) in db.query(Application.name).all()}
        created = 0
        for category, names in CATALOG.items():
            for name in names:
                if name in existing:
                    continue
                db.add(Application(name=name, category=category, is_active=True))
                created += 1
        db.commit()
        print(f"created {created} application(s); {len(existing)} already existed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
