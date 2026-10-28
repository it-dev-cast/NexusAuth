from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.database import Base


class RateLimitCounter(Base):
    """One fixed-window request counter per (endpoint, caller) key. Written by
    app/core/rate_limit.py with a single atomic upsert, never through the ORM;
    the model exists so the table is part of the migrated schema."""

    __tablename__ = "rate_limit_counters"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    window_start: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
