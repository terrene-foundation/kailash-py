"""
Async Redis Cache Adapter

Provides an async wrapper for the synchronous RedisCacheManager, enabling
a unified async cache interface across all cache backends (InMemoryCache and Redis).

This adapter uses asyncio.run_in_executor() to run sync Redis operations in a
thread pool, preventing event loop blocking in async applications.

Design Decision:
- InMemoryCache: Native async (uses asyncio.Lock)
- RedisCacheManager: Sync (redis-py library limitation)
- AsyncRedisCacheAdapter: Async wrapper for RedisCacheManager

This allows ListNodeCacheIntegration to use a consistent async interface
with both cache backends.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from .redis_manager import RedisCacheManager

logger = logging.getLogger(__name__)


class AsyncRedisCacheAdapter:
    """
    Async wrapper for synchronous RedisCacheManager.

    Provides async interface compatible with InMemoryCache, allowing
    ListNodeCacheIntegration to use `await` with both cache backends.

    Thread Safety:
    - Uses asyncio.run_in_executor() to run sync operations in thread pool
    - Safe for concurrent async operations
    - Prevents event loop blocking

    Performance:
    - Minimal overhead (~1-2ms per operation for thread pool dispatch)
    - Same Redis performance as sync RedisCacheManager
    - No blocking of async event loop

    Example:
        >>> from dataflow.cache.redis_manager import RedisCacheManager, CacheConfig
        >>> from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter
        >>>
        >>> config = CacheConfig(host="localhost", port=6379)
        >>> redis_manager = RedisCacheManager(config)
        >>> adapter = AsyncRedisCacheAdapter(redis_manager)
        >>>
        >>> # Use async interface
        >>> value = await adapter.get("key1")
        >>> success = await adapter.set("key1", {"data": "value"})
    """

    def __init__(
        self,
        redis_manager: RedisCacheManager,
        max_workers: Optional[int] = None,
    ):
        """
        Initialize async Redis adapter.

        Args:
            redis_manager: Synchronous RedisCacheManager instance
            max_workers: Max threads in executor pool (None = default)
        """
        self.redis_manager = redis_manager
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.debug(
            f"AsyncRedisCacheAdapter initialized with max_workers={max_workers}"
        )

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from Redis cache (async).

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found

        Example:
            >>> value = await adapter.get("user:123")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.redis_manager.get, key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in Redis cache (async).

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None = use default)

        Returns:
            True if successful

        Example:
            >>> success = await adapter.set("user:123", {"name": "Alice"}, ttl=300)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.set, key, value, ttl
        )

    async def delete(self, key: str) -> int:
        """
        Delete key from Redis cache (async).

        Args:
            key: Cache key

        Returns:
            Number of keys deleted (0 or 1)

        Example:
            >>> deleted = await adapter.delete("user:123")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.delete, key
        )

    async def delete_many(self, keys: List[str]) -> int:
        """
        Delete multiple keys from Redis cache (async).

        Args:
            keys: List of cache keys

        Returns:
            Number of keys deleted

        Example:
            >>> deleted = await adapter.delete_many(["user:123", "user:456"])
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.delete_many, keys
        )

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis cache (async).

        Args:
            key: Cache key

        Returns:
            True if key exists

        Example:
            >>> exists = await adapter.exists("user:123")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.exists, key
        )

    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching pattern (async).

        Args:
            pattern: Key pattern (e.g., "cache:User:*")

        Returns:
            Number of keys deleted

        Example:
            >>> deleted = await adapter.clear_pattern("user:*")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.clear_pattern, pattern
        )

    async def can_cache(self) -> bool:
        """
        Check if caching is possible (async).

        Returns:
            True if caching is available

        Example:
            >>> can_cache = await adapter.can_cache()
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.redis_manager.can_cache)

    async def ping(self) -> bool:
        """
        Test Redis connection (async).

        Returns:
            True if Redis is reachable

        Example:
            >>> is_alive = await adapter.ping()
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.redis_manager.ping)

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics (async).

        Returns:
            Dictionary with cache statistics

        Example:
            >>> stats = await adapter.get_stats()
            >>> print(f"Hit rate: {stats['hit_rate']}")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self.redis_manager.get_stats)

    async def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for key (async).

        Args:
            key: Cache key

        Returns:
            Remaining TTL in seconds (-1 if no TTL, -2 if key doesn't exist)

        Example:
            >>> ttl = await adapter.get_ttl("user:123")
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.get_ttl, key
        )

    async def extend_ttl(self, key: str, ttl: int) -> bool:
        """
        Extend TTL for key (async).

        Args:
            key: Cache key
            ttl: New TTL in seconds

        Returns:
            True if successful

        Example:
            >>> success = await adapter.extend_ttl("user:123", 600)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.extend_ttl, key, ttl
        )

    async def set_many(self, items: List[Tuple[str, Any, Optional[int]]]) -> bool:
        """
        Set multiple items using pipeline (async).

        Args:
            items: List of (key, value, ttl) tuples

        Returns:
            True if all successful

        Example:
            >>> items = [("user:123", {"name": "Alice"}, 300)]
            >>> success = await adapter.set_many(items)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.set_many, items
        )

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values (async).

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs

        Example:
            >>> values = await adapter.get_many(["user:123", "user:456"])
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.get_many, keys
        )

    async def warmup(self, data: List[Tuple[str, Any]]) -> bool:
        """
        Warmup cache with data (async).

        Args:
            data: List of (key, value) tuples

        Returns:
            True if successful

        Example:
            >>> data = [("user:123", {"name": "Alice"})]
            >>> success = await adapter.warmup(data)
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor, self.redis_manager.warmup, data
        )

    async def get_metrics(self) -> Dict[str, Any]:
        """
        Get cache metrics (async). Normalizes Redis stats to match InMemoryCache interface.

        Returns:
            Dictionary with cache metrics (hits, misses, hit_rate, evictions)

        Example:
            >>> metrics = await adapter.get_metrics()
            >>> print(f"Hit rate: {metrics['hit_rate']}")
        """
        stats = await self.get_stats()

        # Normalize Redis stats to match InMemoryCache interface
        # Redis uses "keyspace_hits/keyspace_misses", InMemoryCache uses "hits/misses"
        return {
            "status": stats.get("status", "unknown"),
            "hits": stats.get("keyspace_hits", 0),
            "misses": stats.get("keyspace_misses", 0),
            "hit_rate": stats.get("hit_rate", 0.0),
            "evictions": 0,  # Redis doesn't track evictions in the same way
            "cached_entries": 0,  # Would require DBSIZE call (expensive)
            "memory_usage_mb": stats.get("memory_usage_mb", 0),
        }

    async def invalidate_model(self, model_name: str) -> int:
        """
        Invalidate all cache entries for a model (async).

        Args:
            model_name: Name of the model

        Returns:
            Number of keys invalidated

        Example:
            >>> deleted = await adapter.invalidate_model("User")
        """
        pattern = f"dataflow:{model_name}:*"
        return await self.clear_pattern(pattern)

    def __del__(self):
        """Cleanup executor on deletion."""
        if hasattr(self, "_executor"):
            self._executor.shutdown(wait=False)
            logger.debug("AsyncRedisCacheAdapter executor shut down")
