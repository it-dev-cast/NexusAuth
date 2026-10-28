from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"
    # Migration d2e8f6c1a044 created both a unique constraint and a unique
    # index on jti; declare both so autogenerate sees no difference.
    __table_args__ = (UniqueConstraint("jti", name="revoked_tokens_jti_key"),)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
    )
    jti: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    token_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    reason: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
