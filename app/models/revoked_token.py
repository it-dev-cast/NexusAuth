from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

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
