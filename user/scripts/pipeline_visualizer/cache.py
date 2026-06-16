"""cache — a read-through TTL cache with a double-checked threading.Lock.

One heavy probe runs at most once per TTL window regardless of how many
concurrent requests arrive (SPEC Validation "Cache debounces probe"). The clock
is injectable so tests assert debounce with a fake clock instead of real sleeps.

TTL is a single named constant (DEFAULT_TTL_SECONDS = 2.0) so Phase 2's UI poll
interval (2.5s) can stay strictly greater, per Decision 12.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

DEFAULT_TTL_SECONDS = 2.0


class TtlCache:
    """A read-through cache that holds one value for `ttl` seconds.

    Usage:
        cache = TtlCache(ttl=2.0)
        value = cache.get(producer)   # producer() called at most once / ttl

    Thread-safety: the producer is invoked under a lock with a double-checked
    freshness test, so concurrent `get()` calls within one TTL window trigger
    exactly one producer invocation.
    """

    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._value = None
        self._expires_at = float("-inf")  # nothing cached yet → always stale

    def _is_fresh(self) -> bool:
        return self._clock() < self._expires_at

    def get(self, producer: Callable[[], object]):
        """Return the cached value, invoking `producer` iff the cache is stale.

        Double-checked locking: the fast path returns a fresh value without the
        lock; only a stale read takes the lock, re-checks freshness (a peer may
        have refreshed while we waited), and produces if still stale.
        """
        # Fast path — no lock when fresh.
        if self._is_fresh():
            return self._value
        with self._lock:
            # Re-check under the lock: a peer may have refreshed it.
            if self._is_fresh():
                return self._value
            self._value = producer()
            self._expires_at = self._clock() + self.ttl
            return self._value

    def invalidate(self) -> None:
        """Force the next get() to re-invoke the producer."""
        with self._lock:
            self._expires_at = float("-inf")
