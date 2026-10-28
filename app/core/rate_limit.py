"""Fixed-window request counters for the rate limiter in
app/core/security_middleware.py.

Two backends, same interface — hit(key, window_seconds) -> (count, retry_after):

* DatabaseRateLimiter keeps the counters in PostgreSQL (table
  rate_limit_counters), so every worker process and every container sees the
  same numbers. One atomic INSERT .. ON CONFLICT statement per request, timed
  by the database clock so workers with drifting clocks still agree.
* MemoryRateLimiter keeps them in this process only. Fine for a single
  development server; behind several workers each would allow the full limit.
"""
import logging
import random
import threading
import time

from sqlalchemy import text

from app.core.config import get_settings

logger = logging.getLogger("nexus_auth.rate_limit")

_UPSERT = text(
    """
    INSERT INTO rate_limit_counters AS c (key, window_start, hits)
    VALUES (:key, now(), 1)
    ON CONFLICT (key) DO UPDATE SET
        hits = CASE WHEN c.window_start <= now() - make_interval(secs => CAST(:window AS double precision))
                    THEN 1 ELSE c.hits + 1 END,
        window_start = CASE WHEN c.window_start <= now() - make_interval(secs => CAST(:window AS double precision))
                            THEN now() ELSE c.window_start END
    RETURNING hits,
        CAST(CEIL(GREATEST(0, CAST(:window AS double precision) - EXTRACT(EPOCH FROM (now() - window_start)))) AS integer)
            AS retry_after
    """
)
_PRUNE = text("DELETE FROM rate_limit_counters WHERE window_start < now() - interval '1 day'")


class MemoryRateLimiter:
    def __init__(self):
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            start, hits = self._windows.get(key, (now, 0))
            if now - start >= window_seconds:
                start, hits = now, 0
            hits += 1
            self._windows[key] = (start, hits)
            if len(self._windows) > 10_000:
                self._windows = {k: v for k, v in self._windows.items() if now - v[0] < window_seconds}
            return hits, max(1, int(window_seconds - (now - start)) + 1)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()


class DatabaseRateLimiter:
    def __init__(self, engine, fallback: MemoryRateLimiter):
        self._engine = engine
        self._fallback = fallback

    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        try:
            with self._engine.begin() as connection:
                hits, retry_after = connection.execute(_UPSERT, {"key": key, "window": window_seconds}).one()
                # Old windows are harmless but would pile up; sweep now and then.
                if random.random() < 0.01:
                    connection.execute(_PRUNE)
            return hits, max(1, retry_after)
        except Exception:
            # The limiter must not take login down with it. Degrade to this
            # process's own counter (weaker, but still a limit) and say so.
            logger.warning("Rate limit store unavailable; using the in-process counter", exc_info=True)
            return self._fallback.hit(key, window_seconds)


_memory = MemoryRateLimiter()


def get_limiter():
    if get_settings().rate_limit_backend == "memory":
        return _memory
    from app.database.database import engine

    return DatabaseRateLimiter(engine, _memory)
