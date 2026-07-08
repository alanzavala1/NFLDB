"""Fixed-window per-IP rate limiting, shared by the public write/billed routes.

In-process state is authoritative here because the deploy is a single worker
process (same reasoning as the DuckDB single-writer model). Not suitable as-is
for a multi-worker deploy — that would need shared state (e.g. Redis).
"""
import threading
import time


class RateLimiter:
    """At most `max_hits` per `window` seconds per key (typically client IP).

    Stale keys are evicted once the map grows past `max_keys`, so a public
    endpoint scanned by many one-off IPs can't grow memory without bound.
    """

    def __init__(self, max_hits: int, window: float = 60.0, max_keys: int = 1024):
        self.max_hits = max_hits
        self.window = window
        self.max_keys = max_keys
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def limited(self, key: str) -> bool:
        now = time.time()
        cutoff = now - self.window
        with self._lock:
            if len(self._hits) > self.max_keys:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    del self._hits[k]
            q = self._hits.setdefault(key, [])
            q[:] = [t for t in q if t > cutoff]
            if len(q) >= self.max_hits:
                return True
            q.append(now)
            return False
