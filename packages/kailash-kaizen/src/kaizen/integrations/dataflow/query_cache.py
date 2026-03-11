"""
Query result caching for improved performance.

Provides LRU cache with TTL for database query results,
reducing redundant database operations and improving
response times for repeated queries.

Features:
- TTL (time-to-live) expiration
- Automatic cache invalidation
- Memory-efficient LRU eviction
- Thread-safe operations
- Query key generation from parameters
"""

import hashlib
import json
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


class QueryCache:
    """
    LRU cache for database query results with TTL.

    Implements least-recently-used eviction policy with automatic
    expiration based on time-to-live. Thread-safe for concurrent
    access from multiple agents.

    Args:
        max_size: Maximum number of entries in cache (default: 100)
        ttl_seconds: Time-to-live in seconds (default: 300 = 5 minutes)

    Example:
        >>> cache = QueryCache(max_size=100, ttl_seconds=300)
        >>> key = cache.create_key("users", {"active": True})
        >>> cache.set(key, query_results)
        >>> cached = cache.get(key)  # Fast retrieval
    """

    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        """
        Initialize query cache.

        Args:
            max_size: Maximum cache entries before LRU eviction
            ttl_seconds: Entry expiration time in seconds
        """
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []  # For LRU tracking
        self._lock = threading.RLock()  # Thread-safe operations
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def get(self, query_key: str) -> Optional[Any]:
        """
        Retrieve cached result if valid.

        Checks TTL expiration and updates LRU access order.

        Args:
            query_key: Cache key from create_key()

        Returns:
            Cached result if valid, None if miss/expired

        Example:
            >>> result = cache.get(key)
            >>> if result is None:
            >>>     result = execute_query()
            >>>     cache.set(key, result)
        """
        with self._lock:
            if query_key not in self._cache:
                self._stats["misses"] += 1
                return None

            entry = self._cache[query_key]

            # Check TTL expiration
            if datetime.now() - entry["timestamp"] > self.ttl:
                del self._cache[query_key]
                self._access_order.remove(query_key)
                self._stats["expirations"] += 1
                self._stats["misses"] += 1
                return None

            # Update LRU access order
            if query_key in self._access_order:
                self._access_order.remove(query_key)
            self._access_order.append(query_key)

            self._stats["hits"] += 1
            return entry["result"]

    def set(self, query_key: str, result: Any):
        """
        Cache query result with TTL.

        Implements LRU eviction if cache is full.

        Args:
            query_key: Cache key from create_key()
            result: Query result to cache

        Example:
            >>> key = cache.create_key("users", {"id": 123})
            >>> cache.set(key, {"id": 123, "name": "Alice"})
        """
        with self._lock:
            # Evict LRU entry if cache full
            if len(self._cache) >= self.max_size and query_key not in self._cache:
                self._evict_lru()

            # Store entry with timestamp
            self._cache[query_key] = {"result": result, "timestamp": datetime.now()}

            # Update access order
            if query_key in self._access_order:
                self._access_order.remove(query_key)
            self._access_order.append(query_key)

    def _evict_lru(self):
        """
        Evict least-recently-used entry.

        Called automatically when cache reaches max_size.
        """
        if not self._access_order:
            return

        # LRU entry is first in access order
        lru_key = self._access_order[0]

        if lru_key in self._cache:
            del self._cache[lru_key]
            self._access_order.remove(lru_key)
            self._stats["evictions"] += 1

    def invalidate(self, query_key: str = None, pattern: str = None):
        """
        Invalidate cache entries.

        Args:
            query_key: Specific key to invalidate (optional)
            pattern: Pattern to match keys for batch invalidation (optional)

        Example:
            >>> cache.invalidate(query_key=specific_key)  # Invalidate one
            >>> cache.invalidate(pattern="users_")  # Invalidate all user queries
        """
        with self._lock:
            if query_key:
                # Invalidate specific entry
                if query_key in self._cache:
                    del self._cache[query_key]
                    if query_key in self._access_order:
                        self._access_order.remove(query_key)

            elif pattern:
                # Invalidate by pattern
                keys_to_remove = [key for key in self._cache.keys() if pattern in key]
                for key in keys_to_remove:
                    del self._cache[key]
                    if key in self._access_order:
                        self._access_order.remove(key)

    def clear(self):
        """
        Clear entire cache.

        Removes all cached entries and resets statistics.

        Example:
            >>> cache.clear()  # Fresh start
        """
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics:
            - size: Current number of entries
            - max_size: Maximum cache size
            - hits: Cache hit count
            - misses: Cache miss count
            - hit_rate: Hit rate percentage
            - evictions: Number of LRU evictions
            - expirations: Number of TTL expirations

        Example:
            >>> stats = cache.get_stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.2f}%")
        """
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (
                (self._stats["hits"] / total_requests * 100)
                if total_requests > 0
                else 0.0
            )

            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": hit_rate,
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"],
            }

    @staticmethod
    def create_key(table: str, filter: dict, projection: list = None, **kwargs) -> str:
        """
        Create cache key from query parameters.

        Generates deterministic hash from query parameters for
        consistent cache key generation.

        Args:
            table: Table name
            filter: Query filter dictionary
            projection: Column projection list (optional)
            **kwargs: Additional query parameters

        Returns:
            SHA-256 hash of query parameters

        Example:
            >>> key = QueryCache.create_key("users", {"active": True}, ["id", "name"])
            >>> result = cache.get(key)
        """
        key_data = {
            "table": table,
            "filter": filter or {},
            "projection": projection or [],
            "kwargs": kwargs,
        }

        # Create deterministic JSON string
        key_str = json.dumps(key_data, sort_keys=True)

        # Generate hash
        return hashlib.sha256(key_str.encode()).hexdigest()
