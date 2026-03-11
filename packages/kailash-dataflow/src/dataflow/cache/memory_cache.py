"""
In-Memory Cache Implementation

Provides a lightweight LRU cache with TTL expiration for development
and non-Redis environments. Thread-safe with asyncio support.

Features:
- LRU (Least Recently Used) eviction
- TTL (Time To Live) expiration
- Thread-safe with asyncio locks
- Metrics tracking (hits, misses, evictions)
- Model-based invalidation
"""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InMemoryCache:
    """
    Thread-safe in-memory LRU cache with TTL expiration.

    This cache provides automatic memory management through:
    - LRU eviction when max_size is reached
    - TTL-based expiration for stale entries
    - Automatic cleanup on access

    Thread Safety:
    - Uses asyncio.Lock for async safety
    - Safe for concurrent read/write operations
    - Suitable for FastAPI/async applications
    """

    def __init__(self, max_size: int = 1000, ttl: int = 300):
        """
        Initialize in-memory cache.

        Args:
            max_size: Maximum number of entries (LRU eviction)
            ttl: Time to live in seconds (default: 300s = 5min)
        """
        self.cache: OrderedDict[str, tuple[Any, float, int]] = (
            OrderedDict()
        )  # (value, timestamp, ttl)
        self.max_size = max_size
        self.ttl = ttl
        self.lock = asyncio.Lock()

        # Metrics tracking
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._invalidations = 0

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        async with self.lock:
            if key in self.cache:
                value, timestamp, entry_ttl = self.cache[key]

                # Check TTL (use entry-specific TTL)
                if time.time() - timestamp < entry_ttl:
                    # Move to end (mark as recently used)
                    self.cache.move_to_end(key)
                    self._hits += 1
                    return value
                else:
                    # Expired - remove from cache
                    del self.cache[key]
                    self._misses += 1
                    return None

            self._misses += 1
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override (uses default if not specified)

        Returns:
            True if successful
        """
        async with self.lock:
            # LRU eviction if at capacity
            if key not in self.cache and len(self.cache) >= self.max_size:
                # Remove oldest entry (first item)
                self.cache.popitem(last=False)
                self._evictions += 1

            # Use custom TTL or default
            entry_ttl = ttl if ttl is not None else self.ttl

            # Store with timestamp and TTL
            self.cache[key] = (value, time.time(), entry_ttl)

            # Move to end if updating existing key
            if key in self.cache:
                self.cache.move_to_end(key)

            return True

    async def delete(self, key: str) -> int:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            Number of keys deleted (0 or 1)
        """
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                return 1
            return 0

    async def delete_many(self, keys: List[str]) -> int:
        """
        Delete multiple keys.

        Args:
            keys: List of cache keys

        Returns:
            Number of keys deleted
        """
        async with self.lock:
            deleted = 0
            for key in keys:
                if key in self.cache:
                    del self.cache[key]
                    deleted += 1
            return deleted

    async def exists(self, key: str) -> bool:
        """
        Check if key exists and is not expired.

        Args:
            key: Cache key

        Returns:
            True if key exists and is not expired
        """
        async with self.lock:
            if key in self.cache:
                value, timestamp, entry_ttl = self.cache[key]
                # Check TTL (use entry-specific TTL)
                if time.time() - timestamp < entry_ttl:
                    return True
                else:
                    # Expired - remove
                    del self.cache[key]
            return False

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self.lock:
            self.cache.clear()

    async def invalidate_model(self, model_name: str) -> int:
        """
        Invalidate all entries for a model.

        Args:
            model_name: Name of the model

        Returns:
            Number of keys invalidated
        """
        async with self.lock:
            # Find all keys for this model
            pattern = f"dataflow:{model_name}:"
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]

            # Remove them
            for key in keys_to_remove:
                del self.cache[key]

            self._invalidations += len(keys_to_remove)
            logger.info(
                f"Invalidated {len(keys_to_remove)} cache entries for model {model_name}"
            )
            return len(keys_to_remove)

    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching pattern.

        Args:
            pattern: Key pattern (supports wildcards with 'in' check)

        Returns:
            Number of keys deleted
        """
        async with self.lock:
            # Convert wildcard pattern to substring match
            search_pattern = pattern.replace("*", "")

            # Find matching keys
            keys_to_remove = [k for k in self.cache.keys() if search_pattern in k]

            # Remove them
            for key in keys_to_remove:
                del self.cache[key]

            return len(keys_to_remove)

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get cache metrics.

        Returns:
            Dictionary with metrics (hits, misses, hit_rate, etc.)
        """
        async with self.lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                "status": "in_memory",
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "evictions": self._evictions,
                "invalidations": self._invalidations,
                "cached_entries": len(self.cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
            }

    async def ping(self) -> bool:
        """Test cache availability."""
        return True

    async def can_cache(self) -> bool:
        """Check if caching is possible (always True for in-memory)."""
        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics (sync version for compatibility).

        Returns:
            Dictionary with cache statistics
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "status": "in_memory",
            "memory_usage_mb": 0,  # Not tracked for in-memory
            "cached_entries": len(self.cache),
            "hit_rate": hit_rate,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "invalidations": self._invalidations,
        }
