"""In-memory token bucket rate limiter for development.

Uses token bucket algorithm with steady refill rate, burst allowance,
and thread-safe operations via threading.Lock.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

from nexus.auth.rate_limit.backends.base import RateLimitBackend


class InMemoryBackend(RateLimitBackend):
    """In-memory token bucket rate limiter for development.

    Uses token bucket algorithm with the following characteristics:
    - Tokens refill at a steady rate (requests_per_minute / 60)
    - Burst allowance through bucket capacity
    - Thread-safe via threading.Lock
    - No persistence - resets on restart

    Performance: O(1) check and record operations
    Memory: O(n) where n is number of unique identifiers

    Example:
        >>> backend = InMemoryBackend()
        >>> allowed, remaining, reset_at = await backend.check("user-123", limit=100)
        >>> if allowed:
        ...     await backend.record("user-123")
    """

    # Maximum entries to prevent unbounded memory growth from spoofed identifiers
    DEFAULT_MAX_ENTRIES = 100_000

    def __init__(self, burst_multiplier: float = 1.0, max_entries: int = 0):
        """Initialize in-memory backend.

        Args:
            burst_multiplier: Multiplier for bucket capacity (default: 1.0)
            max_entries: Maximum number of tracked identifiers (default: 100,000).
                         When exceeded, oldest entries are evicted.
                         Set to 0 to use DEFAULT_MAX_ENTRIES.
        """
        self._buckets: Dict[str, Tuple[float, datetime]] = {}
        self._lock = threading.Lock()
        self._burst_multiplier = burst_multiplier
        self._max_entries = max_entries if max_entries > 0 else self.DEFAULT_MAX_ENTRIES

    def _evict_if_needed(self) -> None:
        """Evict oldest entries if max_entries exceeded.

        SECURITY: Prevents unbounded memory growth from spoofed identifiers
        (e.g., forged X-Forwarded-For headers creating unique keys).
        Must be called while holding self._lock.
        """
        if len(self._buckets) <= self._max_entries:
            return

        # Evict oldest 10% of entries (sorted by last_update time)
        evict_count = max(1, len(self._buckets) // 10)
        sorted_keys = sorted(
            self._buckets.keys(),
            key=lambda k: self._buckets[k][1],  # Sort by last_update time
        )
        for key in sorted_keys[:evict_count]:
            del self._buckets[key]

        logger.warning(
            "Rate limit memory eviction: removed %d oldest entries "
            "(max_entries=%d, current=%d)",
            evict_count,
            self._max_entries,
            len(self._buckets),
        )

    async def check_and_record(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Atomically check rate limit and record request if allowed.

        This is the preferred method - combines check and record in a single
        atomic operation to prevent TOCTOU race conditions.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
        """
        with self._lock:
            self._evict_if_needed()
            now = datetime.now(timezone.utc)

            if identifier not in self._buckets:
                # New identifier starts with full bucket
                tokens = float(limit) * self._burst_multiplier
            else:
                tokens, last_update = self._buckets[identifier]
                elapsed = (now - last_update).total_seconds()

                # Refill tokens based on elapsed time
                refill_rate = limit / window_seconds
                tokens = min(
                    limit * self._burst_multiplier,
                    tokens + (elapsed * refill_rate),
                )

            # Calculate reset time
            reset_at = now + timedelta(seconds=window_seconds)

            if tokens >= 1.0:
                # Atomically consume token and update state
                self._buckets[identifier] = (tokens - 1.0, now)
                return True, int(tokens) - 1, reset_at
            else:
                # Update state without consuming (no token available)
                self._buckets[identifier] = (tokens, now)
                return False, 0, reset_at

    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check rate limit using token bucket algorithm.

        DEPRECATED: Use check_and_record() instead for atomic operations.
        This method exists for backwards compatibility but has TOCTOU risk
        when used with separate record() call.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
        """
        with self._lock:
            now = datetime.now(timezone.utc)

            if identifier not in self._buckets:
                # New identifier starts with full bucket
                tokens = float(limit) * self._burst_multiplier
            else:
                tokens, last_update = self._buckets[identifier]
                elapsed = (now - last_update).total_seconds()

                # Refill tokens based on elapsed time
                refill_rate = limit / window_seconds
                tokens = min(
                    limit * self._burst_multiplier,
                    tokens + (elapsed * refill_rate),
                )

            # Update bucket state
            self._buckets[identifier] = (tokens, now)

            # Calculate reset time
            reset_at = now + timedelta(seconds=window_seconds)

            if tokens >= 1.0:
                return True, int(tokens) - 1, reset_at
            else:
                return False, 0, reset_at

    async def record(self, identifier: str) -> None:
        """Consume one token from the bucket.

        DEPRECATED: Use check_and_record() instead for atomic operations.

        Args:
            identifier: Unique identifier
        """
        with self._lock:
            tokens, last_update = self._buckets[identifier]
            if tokens >= 1.0:
                self._buckets[identifier] = (tokens - 1.0, last_update)

    async def reset(self, identifier: str) -> None:
        """Reset rate limit for identifier.

        Args:
            identifier: Unique identifier to reset
        """
        with self._lock:
            if identifier in self._buckets:
                del self._buckets[identifier]

    async def close(self) -> None:
        """No cleanup needed for in-memory backend."""
        pass
