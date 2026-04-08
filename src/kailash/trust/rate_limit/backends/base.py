"""Abstract base class for rate limit backends.

Defines the interface that all rate limit backends must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Tuple


class RateLimitBackend(ABC):
    """Abstract interface for rate limit backends.

    All backends must implement check_and_record(), check(), record(), reset(),
    and close() methods. Prefer check_and_record() for atomic operations.
    Backends should be thread-safe for sync usage and async-safe for async usage.
    """

    @abstractmethod
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
            - allowed: True if request is within limit
            - remaining: Requests remaining in current window
            - reset_at: When the rate limit window resets
        """
        pass

    @abstractmethod
    async def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> Tuple[bool, int, datetime]:
        """Check if request is within rate limit.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 60)

        Returns:
            Tuple of (allowed, remaining, reset_at)
            - allowed: True if request is within limit
            - remaining: Requests remaining in current window
            - reset_at: When the rate limit window resets
        """
        pass

    @abstractmethod
    async def record(self, identifier: str) -> None:
        """Record a request for the identifier.

        Called after request is processed to update counters.

        Args:
            identifier: Unique identifier (user_id, IP, API key)
        """
        pass

    @abstractmethod
    async def reset(self, identifier: str) -> None:
        """Reset rate limit for an identifier (admin override).

        Args:
            identifier: Unique identifier to reset
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (connection pools, etc.)."""
        pass
