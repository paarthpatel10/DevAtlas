"""In-process sliding-window rate limiting for expensive AI endpoints (spec section 13)."""

import threading
import time
from collections import deque
from collections.abc import Callable

from app.core.errors import AppError


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str = "Too many AI requests. Try again in a minute.") -> None:
        super().__init__(message)


class SlidingWindowLimiter:
    def __init__(
        self, limit: int, window_s: float = 60.0, now: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window_s = window_s
        self._now = now
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events.setdefault(key, deque())
        while events and now - events[0] >= self.window_s:
            events.popleft()
        return events

    def check(self, key: str) -> None:
        """Record one request for `key`, or raise RateLimitedError when over the limit."""
        with self._lock:
            now = self._now()
            events = self._prune(key, now)
            if len(events) >= self.limit:
                raise RateLimitedError()
            events.append(now)

    def wait_time(self, key: str) -> float:
        """Seconds until one more request for `key` would be allowed (for batch jobs)."""
        with self._lock:
            now = self._now()
            events = self._prune(key, now)
            if len(events) < self.limit:
                return 0.0
            return self.window_s - (now - events[0])
