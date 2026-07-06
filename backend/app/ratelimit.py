"""Per-IP fixed-window rate limiter for the expensive POST /api/query endpoint.

Each query runs two LLM calls, so a public demo needs a guard against bursts and bots that
would otherwise burn the OpenAI budget. This is in-memory and single-instance — fine for one
free-tier web service; a multi-instance deployment would move the counter to Redis (see the
README's future-work). Gated by `RATE_LIMIT_ENABLED` so local dev and tests are unaffected.
"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request

from .config import settings


class FixedWindowLimiter:
    """Count requests per key within a rolling fixed window; deny past `limit`."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}

    def allow(self, key: str, limit: int, now: float) -> bool:
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self.window_seconds:  # window elapsed -> reset
            self._hits[key] = (now, 1)
            return True
        if count >= limit:
            return False
        self._hits[key] = (start, count + 1)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = FixedWindowLimiter()


def client_ip(request: Request) -> str:
    """Real client IP, honoring the proxy's X-Forwarded-For (Render/most PaaS set it)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 when a client exceeds the per-minute quota (no-op when disabled)."""
    if not settings.rate_limit_enabled:
        return
    if not limiter.allow(client_ip(request), settings.rate_limit_per_minute, time.monotonic()):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded — please wait a minute and try again.",
        )
