from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.core.roles import Role
from app.database.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    # Default is a real role (see app/core/roles.py) — "user" was never a
    # valid value in ALL_ROLES/RBAC's permission matrix. Every actual code
    # path (register_user, bootstrap_admin) already sets role explicitly,
    # so this default was never exercised, but a User row inserted without
    # an explicit role (a raw INSERT, a future script) would otherwise get
    # a role that fails every require_roles()/get_admin_user() check —
    # locked out of the app entirely rather than merely low-privilege.
    role = Column(String(50), nullable=False, default=Role.READ_ONLY)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="RESTRICT"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    failed_login_attempts = Column(Integer, nullable=False, default=0)
    login_count = Column(Integer, nullable=False, default=0)
    last_login_at = Column(DateTime, nullable=True)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
