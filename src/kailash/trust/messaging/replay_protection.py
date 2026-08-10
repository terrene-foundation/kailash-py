# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Replay Protection - Prevent message replay attacks.

This module provides replay protection to detect and prevent
the reuse of previously seen messages (replay attacks).

Key Components:
- ReplayProtection: Abstract interface
- InMemoryReplayProtection: In-memory implementation for development
- Future: RedisReplayProtection for distributed production use
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict

logger = logging.getLogger(__name__)


class ReplayProtection(ABC):
    """
    Abstract interface for replay protection.

    Replay protection detects attempts to reuse previously seen
    messages by tracking message nonces. Once a nonce is recorded,
    any future message with the same nonce is rejected as a replay.

    Implementations should:
    - Track nonces with their timestamps
    - Automatically expire old nonces
    - Be thread-safe for concurrent checks
    - Scale appropriately (in-memory vs distributed)
    """

    @abstractmethod
    async def check_nonce(
        self,
        message_id: str,
        nonce: str,
        timestamp: datetime,
    ) -> bool:
        """
        Check if a nonce has been seen before and record it.

        This method performs two operations atomically:
        1. Checks if the nonce has been seen before
        2. Records the nonce to prevent future replays

        Args:
            message_id: The message's unique identifier.
            nonce: The message's cryptographic nonce.
            timestamp: When the message was created.

        Returns:
            True if the nonce is new (NOT replayed).
            False if the nonce was seen before (IS a replay).
        """
        pass

    @abstractmethod
    async def cleanup_expired_nonces(self, ttl_seconds: int = 3600) -> int:
        """
        Remove nonces older than the TTL.

        This method should be called periodically to prevent
        unbounded memory growth. Nonces older than ttl_seconds
        are removed.

        Args:
            ttl_seconds: Time-to-live for nonces. Nonces older
                than this are removed. Default is 1 hour.

        Returns:
            Number of nonces removed.
        """
        pass


class InMemoryReplayProtection(ReplayProtection):
    """
    In-memory replay protection for development and testing.

    This implementation stores nonces in a dictionary and is
    suitable for single-process deployments. For production
    multi-process deployments, use RedisReplayProtection.

    Features:
    - Fast (< 1ms operations)
    - Thread-safe with asyncio.Lock
    - Automatic cleanup support
    - Nonce counting for diagnostics

    Limitations:
    - Not distributed (single process only)
    - Memory-limited (requires cleanup)
    - Lost on process restart

    Example:
        >>> protection = InMemoryReplayProtection()
        >>> nonce = secrets.token_hex(32)
        >>> # First check - should pass
        >>> is_new = await protection.check_nonce("msg-1", nonce, datetime.now(timezone.utc))
        >>> assert is_new is True
        >>> # Second check - should fail (replay)
        >>> is_new = await protection.check_nonce("msg-1", nonce, datetime.now(timezone.utc))
        >>> assert is_new is False
    """

    def __init__(self, max_nonces: int = 1_000_000):
        """Initialize in-memory replay protection.

        Args:
            max_nonces: Hard cap on stored nonces to prevent memory exhaustion.
                       When exceeded, expired nonces are cleaned up automatically.
        """
        self._seen_nonces: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._max_nonces = max_nonces

    async def check_nonce(
        self,
        message_id: str,
        nonce: str,
        timestamp: datetime,
    ) -> bool:
        """
        Check if a nonce has been seen before and record it.

        Args:
            message_id: The message's unique identifier.
            nonce: The message's cryptographic nonce.
            timestamp: When the message was created.

        Returns:
            True if the nonce is new (NOT replayed).
            False if the nonce was seen before (IS a replay).
        """
        async with self._lock:
            if nonce in self._seen_nonces:
                logger.warning(
                    f"Replay detected: message {message_id} with nonce {nonce[:16]}..."
                )
                return False

            # Record nonce
            self._seen_nonces[nonce] = timestamp

            # Auto-cleanup if nonce count exceeds hard cap
            if len(self._seen_nonces) > self._max_nonces:
                await self.cleanup_expired_nonces()
                # If still over cap after cleanup, evict oldest entries
                if len(self._seen_nonces) > self._max_nonces:
                    sorted_nonces = sorted(
                        self._seen_nonces.items(), key=lambda x: x[1]
                    )
                    excess = len(self._seen_nonces) - self._max_nonces
                    for old_nonce, _ in sorted_nonces[:excess]:
                        del self._seen_nonces[old_nonce]

            logger.debug(f"Recorded nonce for message {message_id}")
            return True

    async def cleanup_expired_nonces(self, ttl_seconds: int = 3600) -> int:
        """
        Remove nonces older than the TTL.

        Args:
            ttl_seconds: Time-to-live for nonces.

        Returns:
            Number of nonces removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)

        async with self._lock:
            expired = [nonce for nonce, ts in self._seen_nonces.items() if ts < cutoff]

            for nonce in expired:
                del self._seen_nonces[nonce]

            if expired:
                logger.info(f"Cleaned up {len(expired)} expired nonces")

            return len(expired)

    def get_nonce_count(self) -> int:
        """
        Get the current count of tracked nonces.

        Returns:
            Number of nonces currently tracked.
        """
        return len(self._seen_nonces)

    async def clear(self) -> None:
        """Clear all tracked nonces (for testing)."""
        async with self._lock:
            self._seen_nonces.clear()
