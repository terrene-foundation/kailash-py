"""
Caching utilities for MCP servers.

Provides LRU cache, TTL support, and decorators for method-level caching.
Based on patterns from production MCP server implementations.
"""

import asyncio
import functools
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class LRUCache:
    """
    Thread-safe LRU cache with TTL (time-to-live) support.

    Features:
    - Configurable maximum size
    - TTL expiration for entries
    - Thread-safe operations
    - Performance statistics
    """

    def __init__(self, max_size: int = 128, ttl: int = 300):
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of entries to store
            ttl: Time-to-live in seconds (0 = no expiration)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: Dict[str, float] = {}
        self._lock = threading.RLock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            value, timestamp = self._cache[key]

            # Check TTL expiration
            if self.ttl > 0 and time.time() - timestamp > self.ttl:
                del self._cache[key]
                del self._access_order[key]
                self._misses += 1
                return None

            # Update access time for LRU
            self._access_order[key] = time.time()
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """Set value in cache, evicting LRU items if necessary."""
        with self._lock:
            current_time = time.time()

            # If key exists, update it
            if key in self._cache:
                self._cache[key] = (value, current_time)
                self._access_order[key] = current_time
                return

            # Check if we need to evict
            if len(self._cache) >= self.max_size:
                self._evict_lru()

            # Add new entry
            self._cache[key] = (value, current_time)
            self._access_order[key] = current_time

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._access_order:
            return

        lru_key = min(self._access_order.keys(), key=self._access_order.get)
        del self._cache[lru_key]
        del self._access_order[lru_key]
        self._evictions += 1

    def clear(self) -> None:
        """Clear all entries from cache."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()

    def stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl": self.ttl,
            }


class CacheManager:
    """
    High-level cache management with multiple caching strategies.

    Provides easy-to-use caching for MCP servers with different cache types
    for different use cases.
    """

    def __init__(self, enabled: bool = True, default_ttl: int = 300):
        """
        Initialize cache manager.

        Args:
            enabled: Whether caching is enabled
            default_ttl: Default TTL for cache entries
        """
        self.enabled = enabled
        self.default_ttl = default_ttl
        self._caches: Dict[str, LRUCache] = {}

    def get_cache(
        self, name: str, max_size: int = 128, ttl: Optional[int] = None
    ) -> LRUCache:
        """Get or create a named cache."""
        if name not in self._caches:
            cache_ttl = ttl if ttl is not None else self.default_ttl
            self._caches[name] = LRUCache(max_size=max_size, ttl=cache_ttl)
        return self._caches[name]

    def cached(self, cache_name: str = "default", ttl: Optional[int] = None):
        """
        Decorator to cache function results.

        Args:
            cache_name: Name of cache to use
            ttl: TTL for this specific cache

        Returns:
            Decorated function with caching
        """

        def decorator(func: F) -> F:
            if not self.enabled:
                return func

            cache = self.get_cache(cache_name, ttl=ttl)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                cache_key = self._create_cache_key(func.__name__, args, kwargs)

                # Try to get from cache
                result = cache.get(cache_key)
                if result is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return result

                # Execute function and cache result
                logger.debug(f"Cache miss for {func.__name__}: {cache_key}")
                result = func(*args, **kwargs)
                cache.set(cache_key, result)
                return result

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                cache_key = self._create_cache_key(func.__name__, args, kwargs)

                # Try to get from cache
                result = cache.get(cache_key)
                if result is not None:
                    logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                    return result

                # Execute function and cache result
                logger.debug(f"Cache miss for {func.__name__}: {cache_key}")
                result = await func(*args, **kwargs)
                cache.set(cache_key, result)
                return result

            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def _create_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Create a cache key from function name and arguments."""
        # Convert args and kwargs to string representation
        args_str = str(args) if args else ""
        kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
        return f"{func_name}:{args_str}:{kwargs_str}"

    def clear_all(self) -> None:
        """Clear all caches."""
        for cache in self._caches.values():
            cache.clear()

    def stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all caches."""
        return {name: cache.stats() for name, cache in self._caches.items()}


# Global cache manager instance
_global_cache_manager = CacheManager()


def cached_query(cache_name: str = "query", ttl: int = 300, enabled: bool = True):
    """
    Simple decorator for caching query results.

    This is a convenience decorator that uses the global cache manager.

    Args:
        cache_name: Name of cache to use
        ttl: Time-to-live for cache entries
        enabled: Whether caching is enabled

    Example:
        @cached_query("search", ttl=600)
        async def search_data(query: str) -> list:
            # Expensive search operation
            return results
    """

    def decorator(func: F) -> F:
        if not enabled:
            return func

        return _global_cache_manager.cached(cache_name, ttl=ttl)(func)

    return decorator


def get_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for the global cache manager."""
    return _global_cache_manager.stats()


def clear_all_caches() -> None:
    """Clear all caches in the global cache manager."""
    _global_cache_manager.clear_all()
