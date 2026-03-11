# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Trust Chain Caching for EATP Week 11.

Provides high-performance caching for TrustLineageChain lookups with:
- LRU eviction policy to manage memory
- TTL-based expiration for freshness
- Thread-safe async operations
- O(1) lookup performance
- Comprehensive statistics tracking

Target: 100x speedup (cache hit <1ms vs database lookup ~100ms)

Example:
    >>> from eatp.cache import TrustChainCache
    >>> from eatp import PostgresTrustStore, TrustOperations
    >>>
    >>> # Initialize cache
    >>> cache = TrustChainCache(ttl_seconds=300, max_size=10000)
    >>>
    >>> # Try cache first, fallback to database
    >>> chain = await cache.get("agent-001")
    >>> if chain is None:
    ...     chain = await trust_store.get_chain("agent-001")
    ...     await cache.set("agent-001", chain)
    >>>
    >>> # Check performance
    >>> stats = cache.get_stats()
    >>> print(f"Hit rate: {stats.hit_rate:.2%}")
"""

import asyncio
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from eatp.chain import TrustLineageChain

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """
    Internal cache entry with metadata.

    Tracks the cached chain along with timing information
    for TTL and LRU eviction.

    Attributes:
        chain: The cached TrustLineageChain
        expires_at: When this entry expires (TTL)
        last_accessed: Last access time for LRU eviction
    """

    chain: TrustLineageChain
    expires_at: datetime
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        """Check if this entry has expired based on TTL."""
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class CacheStats:
    """
    Cache statistics for monitoring performance.

    Provides insights into cache effectiveness and helps
    identify optimization opportunities.

    Attributes:
        hits: Number of cache hits
        misses: Number of cache misses
        hit_rate: Hit rate as a percentage (0.0 to 1.0)
        size: Current number of entries in cache
        evictions: Number of LRU evictions performed
    """

    hits: int
    misses: int
    hit_rate: float
    size: int
    evictions: int


class TrustChainCache:
    """
    High-performance LRU cache for TrustLineageChain objects.

    Provides thread-safe caching with TTL expiration and LRU eviction
    to dramatically reduce database lookup times.

    Performance Characteristics:
    - Cache hit: <1ms (100x faster than database)
    - Cache miss: ~100ms (database lookup time)
    - Target hit rate: >90% in production

    Thread Safety:
    - All operations are protected by asyncio.Lock
    - Safe for concurrent access from multiple agents

    Eviction Policy:
    - TTL-based: Entries expire after ttl_seconds
    - LRU: When max_size reached, least recently accessed entries are removed

    Example:
        >>> cache = TrustChainCache(ttl_seconds=300, max_size=10000)
        >>>
        >>> # Check cache first
        >>> chain = await cache.get("agent-001")
        >>> if chain is None:
        ...     # Cache miss - fetch from database
        ...     chain = await trust_store.get_chain("agent-001")
        ...     await cache.set("agent-001", chain)
        >>>
        >>> # Monitor performance
        >>> stats = cache.get_stats()
        >>> print(f"Hit rate: {stats.hit_rate:.2%}, Size: {stats.size}")
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 10000,
        eviction_policy: str = "lru",
    ):
        """
        Initialize the Trust Chain Cache.

        Args:
            ttl_seconds: Time-to-live for cached entries (default: 300 seconds / 5 minutes)
            max_size: Maximum number of entries before LRU eviction (default: 10000)
            eviction_policy: Eviction policy to use (default: "lru")
                - "lru": Least Recently Used (only supported policy)

        Raises:
            ValueError: If eviction_policy is not "lru"
        """
        if eviction_policy != "lru":
            raise ValueError(
                f"Unsupported eviction policy: {eviction_policy}. Only 'lru' is supported."
            )

        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._eviction_policy = eviction_policy

        # OrderedDict provides O(1) access and maintains insertion order for LRU
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()

        # Thread safety lock
        self._lock = asyncio.Lock()

        # Statistics tracking
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        logger.info(
            f"Initialized TrustChainCache: ttl={ttl_seconds}s, max_size={max_size}, "
            f"policy={eviction_policy}"
        )

    async def get(self, agent_id: str) -> Optional[TrustLineageChain]:
        """
        Retrieve a cached trust chain.

        Performs O(1) lookup with automatic expiration checking
        and LRU tracking.

        Args:
            agent_id: The agent ID to lookup

        Returns:
            TrustLineageChain if found and not expired, None otherwise
        """
        async with self._lock:
            # Check if entry exists
            if agent_id not in self._cache:
                self._misses += 1
                logger.debug(f"Cache miss: {agent_id}")
                return None

            entry = self._cache[agent_id]

            # Check if expired
            if entry.is_expired():
                # Remove expired entry
                del self._cache[agent_id]
                self._misses += 1
                logger.debug(f"Cache miss (expired): {agent_id}")
                return None

            # Update LRU tracking
            entry.last_accessed = datetime.now(timezone.utc)
            # Move to end of OrderedDict (most recently used)
            self._cache.move_to_end(agent_id)

            self._hits += 1
            logger.debug(f"Cache hit: {agent_id}")
            return entry.chain

    async def set(self, agent_id: str, chain: TrustLineageChain) -> None:
        """
        Store a trust chain in the cache.

        Handles TTL expiration calculation and LRU eviction
        if max_size is exceeded.

        Args:
            agent_id: The agent ID to cache
            chain: The TrustLineageChain to store

        Note:
            If max_size is exceeded, the least recently accessed
            entry will be automatically evicted.
        """
        async with self._lock:
            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=self._ttl_seconds
            )

            # Create new entry
            entry = CacheEntry(
                chain=chain,
                expires_at=expires_at,
                last_accessed=datetime.now(timezone.utc),
            )

            # Check if we need to evict (before adding new entry)
            if agent_id not in self._cache and len(self._cache) >= self._max_size:
                # Evict least recently used (first item in OrderedDict)
                evicted_agent_id, _ = self._cache.popitem(last=False)
                self._evictions += 1
                logger.debug(
                    f"LRU eviction: {evicted_agent_id} (max_size={self._max_size})"
                )

            # Store entry (will update if exists)
            self._cache[agent_id] = entry
            # Ensure it's at the end (most recently used)
            self._cache.move_to_end(agent_id)

            logger.debug(f"Cached chain: {agent_id} (expires in {self._ttl_seconds}s)")

    async def invalidate(self, agent_id: str) -> None:
        """
        Remove a specific entry from the cache.

        Useful for invalidating cache after trust chain updates.

        Args:
            agent_id: The agent ID to invalidate
        """
        async with self._lock:
            if agent_id in self._cache:
                del self._cache[agent_id]
                logger.debug(f"Invalidated cache entry: {agent_id}")
            else:
                logger.debug(f"Invalidation skipped (not found): {agent_id}")

    async def invalidate_all(self) -> None:
        """
        Clear all entries from the cache.

        Useful for testing or when trust data changes globally.
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Invalidated all cache entries: {count} removed")

    def get_stats(self) -> CacheStats:
        """
        Get current cache statistics.

        Returns cache performance metrics without acquiring lock
        (safe for monitoring without blocking operations).

        Returns:
            CacheStats with current performance metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            hit_rate=hit_rate,
            size=len(self._cache),
            evictions=self._evictions,
        )

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        This is called automatically during get() operations,
        but can be called explicitly for batch cleanup.

        Returns:
            Number of expired entries removed
        """
        async with self._lock:
            expired_keys = [
                agent_id
                for agent_id, entry in self._cache.items()
                if entry.is_expired()
            ]

            for agent_id in expired_keys:
                del self._cache[agent_id]

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)

    def reset_stats(self) -> None:
        """
        Reset statistics counters.

        Useful for testing or periodic monitoring resets.
        Does not clear cached entries.
        """
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        logger.debug("Cache statistics reset")

    @property
    def ttl_seconds(self) -> int:
        """Get the TTL in seconds."""
        return self._ttl_seconds

    @property
    def max_size(self) -> int:
        """Get the maximum cache size."""
        return self._max_size

    @property
    def eviction_policy(self) -> str:
        """Get the eviction policy."""
        return self._eviction_policy
