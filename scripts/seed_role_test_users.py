"""Create (or reset) one operator and one read-only login for trying the
role-based screens — see applyRoleUi() in frontend/app.js.

Usage:
    python scripts/seed_role_test_users.py

Writes to whatever DATABASE_URL points at; run it against a test/dev
database, not production. Safe to re-run: existing accounts get their role,
password and lockout reset instead of being duplicated. Unlike
seed_admin.py, it never truncates anything.

    rbac.operator@casterly.com / ExamplePasswordOnly   (role: operator)
    rbac.readonly@casterly.com / ExamplePasswordOnly   (role: read_only)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.core.password_service import hash_password  # noqa: E402
from app.core.roles import Role  # noqa: E402
from app.database.database import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.auth_service import _default_company_id  # noqa: E402

PASSWORD = "ExamplePasswordOnly"
ACCOUNTS = [
    ("rbac.operator@casterly.com", "Test Operator", Role.OPERATOR),
    ("rbac.readonly@casterly.com", "Test Read-Only", Role.READ_ONLY),
]


def main() -> None:
    db = SessionLocal()
    try:
        company_id = _default_company_id(db)
        for email, full_name, role in ACCOUNTS:
            user = db.query(User).filter(User.email == email).first()
            if user is None:
                user = User(email=email, login_count=0, company_id=company_id)
                db.add(user)
            user.full_name = full_name
            user.role = role
            user.password_hash = hash_password(PASSWORD)
            user.is_active = True
            user.failed_login_attempts = 0
            user.locked_until = None
        db.commit()
        for email, _, role in ACCOUNTS:
            print(f"{email:28} {role}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
