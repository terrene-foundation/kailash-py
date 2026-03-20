# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Bounded LRU client cache for BYOK (Bring Your Own Key) provider clients.

In multi-tenant scenarios each per-request API key creates a new provider
client. Without caching, every request incurs client construction overhead
(TLS handshake, connection pool init). This module provides a thread-safe
bounded cache with TTL eviction to reuse clients across requests sharing
the same credentials.

Usage:
    cache = BYOKClientCache(max_size=128, ttl_seconds=300)
    client = cache.get_or_create(
        api_key="sk-tenant-123",
        base_url="https://api.openai.com/v1",
        factory=lambda: openai.OpenAI(api_key="sk-tenant-123"),
    )
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

__all__ = ["BYOKClientCache"]


class _CacheEntry:
    """Internal cache entry with creation timestamp."""

    __slots__ = ("client", "created_at")

    def __init__(self, client: Any) -> None:
        self.client = client
        self.created_at = time.monotonic()


class BYOKClientCache:
    """Thread-safe bounded LRU cache for per-request provider clients.

    Keys are derived from SHA-256 of (api_key, base_url) so plaintext
    credentials are never stored as dict keys.

    Args:
        max_size: Maximum number of cached clients. Default 128.
        ttl_seconds: Time-to-live per entry in seconds. Default 300 (5 min).
    """

    def __init__(self, max_size: int = 128, ttl_seconds: float = 300.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(api_key: Optional[str], base_url: Optional[str]) -> str:
        """Create a SHA-256 cache key from credentials."""
        raw = f"{api_key or ''}|{base_url or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get_or_create(
        self,
        api_key: Optional[str],
        base_url: Optional[str],
        factory: Callable[[], Any],
    ) -> Any:
        """Get a cached client or create one via *factory*.

        Args:
            api_key: The API key (used for cache key derivation only).
            base_url: The base URL (used for cache key derivation only).
            factory: Zero-arg callable that returns a new client instance.

        Returns:
            A (possibly cached) client instance.
        """
        key = self._make_key(api_key, base_url)
        now = time.monotonic()

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None and (now - entry.created_at) < self._ttl:
                # Move to end (most recently used)
                self._cache.move_to_end(key)
                return entry.client

            # Evict expired entry if present
            if entry is not None:
                self._evict(key)

        # Create client outside lock to avoid holding lock during network ops
        client = factory()

        with self._lock:
            # Double-check another thread didn't create it
            entry = self._cache.get(key)
            if entry is not None and (now - entry.created_at) < self._ttl:
                # Another thread beat us; close our client and return theirs
                self._close_client(client)
                self._cache.move_to_end(key)
                return entry.client

            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                evicted_key, evicted_entry = self._cache.popitem(last=False)
                self._close_client(evicted_entry.client)
                logger.debug("Evicted client cache entry (LRU)")

            self._cache[key] = _CacheEntry(client)

        return client

    def clear(self) -> None:
        """Clear all cached clients, calling close() on each."""
        with self._lock:
            for entry in self._cache.values():
                self._close_client(entry.client)
            self._cache.clear()
        logger.debug("BYOK client cache cleared")

    def _evict(self, key: str) -> None:
        """Evict a single entry (must hold lock)."""
        entry = self._cache.pop(key, None)
        if entry is not None:
            self._close_client(entry.client)

    @staticmethod
    def _close_client(client: Any) -> None:
        """Best-effort close of a client."""
        if hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def __repr__(self) -> str:
        with self._lock:
            return f"BYOKClientCache({len(self._cache)}/{self._max_size} entries)"
