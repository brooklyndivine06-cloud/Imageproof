"""Small in-process sliding-window rate limiter.

This is per-process. If you run several API workers or replicas, enforce the
limit at your gateway / reverse proxy as well (see README, "Deployment").
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from fastapi import Request


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 50_000,
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - self.window
        with self._lock:
            if len(self._hits) > self._max_keys:
                self._purge(cutoff)
            q = self._hits.setdefault(key, deque())
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry = max(1, int(q[0] + self.window - now) + 1)
                return RateLimitDecision(False, self.limit, 0, retry)
            q.append(now)
            return RateLimitDecision(True, self.limit, self.limit - len(q), 0)

    def _purge(self, cutoff: float) -> None:
        for key in [k for k, q in self._hits.items() if not q or q[-1] <= cutoff]:
            del self._hits[key]


def client_ip(request: Request, trusted_proxy_count: int) -> str:
    """Resolve the client address.

    Only the last ``trusted_proxy_count`` X-Forwarded-For entries are trusted,
    because those were appended by proxies we control. Anything a client
    prepends to the header is ignored.
    """
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy_count <= 0:
        return peer
    header = request.headers.get("x-forwarded-for")
    if not header:
        return peer
    parts = [p.strip() for p in header.split(",") if p.strip()]
    idx = len(parts) - trusted_proxy_count
    if 0 <= idx < len(parts):
        return parts[idx]
    return parts[0] if parts else peer
