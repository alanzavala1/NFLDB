"""A process-wide daily ceiling for the billed /ask endpoint.

The per-IP rate limiter in `rate_limit.py` stops one caller hammering the
endpoint. It does nothing about cost, because it is per-key: rotating IPs walks
straight around it, and even a single well-behaved IP at 8 requests/minute is
~11,500 questions a day. On a public URL with no authentication, in front of a
metered model, that is an unbounded bill waiting to happen — and a billing alert
is a notification after the fact, not a brake.

This is the brake. One counter for the whole process, checked before the model
is called, tripping on either of two ceilings:

  * **requests** — the coarse bound. Cannot be bypassed by a code path that
    forgets to report its token usage, which matters because the streaming
    endpoint (the one the UI actually uses) did not track tokens at all.
  * **tokens** — the precise bound, recorded where the number is known.

Tripping on either means the request ceiling alone is a valid guarantee, and the
token ceiling tightens it when the data is available. Both are deliberately
generous against real traffic — the whole site serves a few hundred requests a
month — and stingy against abuse.

In-process state is authoritative for the same reason it is in `rate_limit.py`:
this deploys as a single worker. A multi-worker deploy would multiply these
ceilings by the worker count, which is a reason to keep the limits conservative
rather than a reason to reach for shared state at this scale.
"""
from __future__ import annotations

import os
import threading
import time

# Defaults sized against reality, not against what the endpoint could take: the
# entire site serves a few hundred requests a month across every route. A
# question costs roughly 18k tokens, so these two ceilings bound the day at a
# similar place and neither is reachable by honest use.
DEFAULT_MAX_REQUESTS = 200
DEFAULT_MAX_TOKENS = 3_000_000
WINDOW_SECONDS = 24 * 60 * 60


class SpendGuard:
    """Rolling-window ceilings on requests and tokens for one process.

    The window rolls rather than resetting at midnight: a fixed daily boundary
    hands an abuser a predictable moment to start again, and makes the endpoint
    fail for everyone until an arbitrary clock time.
    """

    def __init__(
        self,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        window: float = WINDOW_SECONDS,
    ):
        self.max_requests = max_requests
        self.max_tokens = max_tokens
        self.window = window
        self._requests: list[float] = []
        self._tokens: list[tuple[float, int]] = []
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        self._requests = [t for t in self._requests if t > cutoff]
        self._tokens = [(t, n) for t, n in self._tokens if t > cutoff]

    def exceeded(self) -> str | None:
        """The reason this request should be refused, or None to allow it.

        Returns a reason rather than a bool so the caller can log which ceiling
        tripped — the two mean different things when you come to investigate.
        """
        now = time.time()
        with self._lock:
            self._prune(now)
            if len(self._requests) >= self.max_requests:
                return f"request ceiling reached ({self.max_requests}/day)"
            spent = sum(n for _, n in self._tokens)
            if spent >= self.max_tokens:
                return f"token ceiling reached ({spent:,}/{self.max_tokens:,} per day)"
        return None

    def record_request(self) -> None:
        """Count a request we are about to let through."""
        now = time.time()
        with self._lock:
            self._prune(now)
            self._requests.append(now)

    def record_tokens(self, usage: dict | int | None) -> None:
        """Add the tokens a completed question actually cost.

        Accepts the `usage` dict llm.py builds (input/cache/output buckets) or a
        plain total. Never raises: a billing counter must not be able to fail a
        request that has already succeeded.
        """
        try:
            total = usage if isinstance(usage, int) else sum(
                int(v) for v in (usage or {}).values() if isinstance(v, (int, float))
            )
        except Exception:
            return
        if total <= 0:
            return
        now = time.time()
        with self._lock:
            self._prune(now)
            self._tokens.append((now, total))

    def snapshot(self) -> dict:
        """Current consumption, for logging and for an admin view."""
        now = time.time()
        with self._lock:
            self._prune(now)
            return {
                "requests": len(self._requests),
                "max_requests": self.max_requests,
                "tokens": sum(n for _, n in self._tokens),
                "max_tokens": self.max_tokens,
            }


def _from_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
        return value if value > 0 else default
    except ValueError:
        return default


# The singleton the app uses. Limits are env-tunable so they can be tightened
# without a deploy, but they default to safe rather than to unlimited.
guard = SpendGuard(
    max_requests=_from_env("ASK_DAILY_REQUESTS", DEFAULT_MAX_REQUESTS),
    max_tokens=_from_env("ASK_DAILY_TOKENS", DEFAULT_MAX_TOKENS),
)
