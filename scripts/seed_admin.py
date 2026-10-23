from sqlalchemy import text

from app.core.password_service import hash_password
from app.database.database import SessionLocal
from app.models.user import User
# Bug fix: this script previously referenced settings.company_id, which
# has never existed on Settings (app/core/config.py) — running it raised
# AttributeError before ever reaching db.add(). Reuse the same
# "find-or-create the internal Casterly company" helper auth_service.py's
# register_user/bootstrap_admin already use, instead of a nonexistent
# config field.
from app.services.auth_service import _default_company_id


def main() -> None:
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE revoked_tokens, auth_sessions, users RESTART IDENTITY CASCADE"))
        db.commit()
        db.add(
            User(
                email="admin@casterly.com",
                password_hash=hash_password("ExamplePasswordOnly"),
                full_name="Administrator",
                role="admin",
                company_id=_default_company_id(db),
                is_active=True,
                failed_login_attempts=0,
                login_count=0,
            )
        )
        db.commit()
        rows = db.execute(text("SELECT email, role FROM users")).fetchall()
        print("seeded", rows)
    finally:
        db.close()


if __name__ == "__main__":
    main()
