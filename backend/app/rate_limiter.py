"""In-memory, per-process rate limiter guarding the shared Mistral workspace
quota. Mistral enforces limits per *workspace*, shared across every API key in
it (not per key) - so this app's local budget should be configured as roughly
this app's share of the real limit, since other live apps draw on the same
key. See `.env.example` for how to size it.

Deliberately simple per the "no Redis" requirement: a single fixed-window
request counter, global across all features (one shared workspace quota),
reset on process restart. This is a proxy for requests-per-second/minute, not
for token usage - only `run_chat` in `llm_client.py` reports token usage, and
Model Evaluation's LangChain call path doesn't go through `llm_client.py` at
all, so a token-based budget can't be applied uniformly at one chokepoint.

Feature code calls `reserve(n)` explicitly at the point(s) where it is about
to make n real calls to the model - see CLAUDE.md / the rate-limiting plan for
which call shapes reserve where. This module has no FastAPI import so it stays
usable from anywhere (services, background threads); translating
`RateLimitExceeded` into an HTTP 429 happens once, in `main.py`.
"""

import threading
import time

from app.config import get_settings


class RateLimitExceeded(Exception):
    """Raised by `reserve()` when the current window's budget is used up."""

    def __init__(self, retry_after: float, remaining: int):
        self.retry_after = retry_after
        self.remaining = remaining
        super().__init__(f"Rate limit reached — try again in {max(1, round(retry_after))}s")


class _FixedWindowLimiter:
    """Allow up to `max_requests` calls per `window_seconds`; once the window
    elapses, the count resets. Thread-safe: FastAPI runs sync endpoints in a
    threadpool, and LLM Quirks / Model Evaluation also run calls on their own
    background threads.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        self._max = max_requests
        self._window = window_seconds
        self._lock = threading.Lock()
        self._window_start = time.monotonic()
        self._count = 0

    def _reset_if_elapsed(self, now: float) -> None:
        if now - self._window_start >= self._window:
            self._window_start = now
            self._count = 0

    def reserve(self, n: int = 1) -> None:
        with self._lock:
            now = time.monotonic()
            self._reset_if_elapsed(now)
            if self._count + n > self._max:
                retry_after = self._window - (now - self._window_start)
                raise RateLimitExceeded(retry_after, remaining=max(0, self._max - self._count))
            self._count += n

    def status(self) -> tuple[int, float]:
        """Return (remaining, seconds_until_reset) without consuming budget -
        used for the read-only status endpoint that seeds the on-page badge.
        """
        with self._lock:
            now = time.monotonic()
            self._reset_if_elapsed(now)
            remaining = max(0, self._max - self._count)
            reset_in = self._window - (now - self._window_start)
            return remaining, reset_in


_limiter: _FixedWindowLimiter | None = None
_limiter_lock = threading.Lock()


def _get_limiter() -> _FixedWindowLimiter:
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                settings = get_settings()
                _limiter = _FixedWindowLimiter(
                    settings.rate_limit_max_requests, settings.rate_limit_window_seconds
                )
    return _limiter


def reserve(n: int = 1) -> None:
    """Reserve n calls' worth of budget in the current window, or raise
    `RateLimitExceeded` if that would exceed it. Call this right before
    making n real calls to the model - see module docstring for placement
    rules per call shape.
    """
    _get_limiter().reserve(n)


def status() -> tuple[int, float]:
    """Read-only (remaining, seconds_until_reset), for the status endpoint."""
    return _get_limiter().status()
