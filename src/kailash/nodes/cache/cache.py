"""Cache node for high-performance data caching and retrieval.

This module provides comprehensive caching capabilities supporting multiple
backends including Redis, in-memory LRU, and file-based caching with
advanced features like TTL, compression, and serialization.
"""

import asyncio
import gzip
import hashlib
import json
import pickle
import time
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class CacheBackend(Enum):
    """Supported cache backend types."""

    MEMORY = "memory"
    REDIS = "redis"
    FILE = "file"
    HYBRID = "hybrid"  # Memory + Redis fallback


class SerializationFormat(Enum):
    """Data serialization formats."""

    JSON = "json"
    PICKLE = "pickle"
    STRING = "string"
    BYTES = "bytes"


class EvictionPolicy(Enum):
    """Cache eviction policies."""

    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    TTL = "ttl"  # Time To Live only
    FIFO = "fifo"  # First In, First Out


@register_node()
class CacheNode(AsyncNode):
    """Node for high-performance data caching and retrieval.

    This node provides comprehensive caching capabilities including:
    - Multiple backend support (Redis, in-memory, file-based, hybrid)
    - Configurable TTL (Time To Live) with automatic expiration
    - Multiple serialization formats (JSON, Pickle, String, Bytes)
    - Data compression for large values
    - Eviction policies (LRU, LFU, TTL, FIFO)
    - Atomic operations and transactions
    - Cache statistics and monitoring
    - Distributed caching with Redis
    - Fallback strategies for high availability

    Design Purpose:
    - Improve application performance through intelligent caching
    - Reduce database and API load
    - Provide configurable caching strategies
    - Support both simple and complex caching scenarios

    Examples:
        >>> # Simple key-value caching
        >>> cache = CacheNode()
        >>> result = await cache.execute(
        ...     operation="set",
        ...     key="user:123",
        ...     value={"name": "John", "email": "john@example.com"},
        ...     ttl=3600  # 1 hour
        ... )

        >>> # Batch operations with pattern matching
        >>> result = await cache.execute(
        ...     operation="get_pattern",
        ...     pattern="user:*",
        ...     limit=100
        ... )

        >>> # Cache with compression and custom serialization
        >>> result = await cache.execute(
        ...     operation="set",
        ...     key="large_data",
        ...     value=large_dataset,
        ...     compression=True,
        ...     serialization="pickle",
        ...     ttl=86400  # 24 hours
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the cache node."""
        super().__init__(**kwargs)
        self._memory_cache = {}
        self._access_times = {}
        self._access_counts = {}
        self._redis_client = None
        self._cache_stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "evictions": 0,
        }
        self.logger.info(f"Initialized CacheNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Cache operation (get, set, delete, exists, clear, stats, get_pattern)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Cache key for single operations",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Value to cache (for set operations)",
            ),
            "keys": NodeParameter(
                name="keys",
                type=list,
                required=False,
                description="Multiple keys for batch operations",
            ),
            "values": NodeParameter(
                name="values",
                type=dict,
                required=False,
                description="Key-value pairs for batch set operations",
            ),
            "pattern": NodeParameter(
                name="pattern",
                type=str,
                required=False,
                description="Pattern for pattern-based operations (supports wildcards)",
            ),
            "ttl": NodeParameter(
                name="ttl",
                type=int,
                required=False,
                default=3600,
                description="Time to live in seconds (0 = no expiration)",
            ),
            "backend": NodeParameter(
                name="backend",
                type=str,
                required=False,
                default="memory",
                description="Cache backend (memory, redis, file, hybrid)",
            ),
            "redis_url": NodeParameter(
                name="redis_url",
                type=str,
                required=False,
                default="redis://localhost:6379",
                description="Redis connection URL",
            ),
            "serialization": NodeParameter(
                name="serialization",
                type=str,
                required=False,
                default="json",
                description="Serialization format (json, pickle, string, bytes)",
            ),
            "compression": NodeParameter(
                name="compression",
                type=bool,
                required=False,
                default=False,
                description="Enable gzip compression for large values",
            ),
            "compression_threshold": NodeParameter(
                name="compression_threshold",
                type=int,
                required=False,
                default=1024,
                description="Minimum size in bytes to trigger compression",
            ),
            "eviction_policy": NodeParameter(
                name="eviction_policy",
                type=str,
                required=False,
                default="lru",
                description="Eviction policy (lru, lfu, ttl, fifo)",
            ),
            "max_memory_items": NodeParameter(
                name="max_memory_items",
                type=int,
                required=False,
                default=10000,
                description="Maximum items in memory cache",
            ),
            "namespace": NodeParameter(
                name="namespace",
                type=str,
                required=False,
                default="",
                description="Key namespace prefix",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "success": NodeParameter(
                name="success",
                type=bool,
                description="Whether the operation succeeded",
            ),
            "value": NodeParameter(
                name="value",
                type=Any,
                required=False,
                description="Retrieved value (for get operations)",
            ),
            "values": NodeParameter(
                name="values",
                type=dict,
                required=False,
                description="Multiple values (for batch operations)",
            ),
            "hit": NodeParameter(
                name="hit",
                type=bool,
                required=False,
                description="Cache hit status (for get operations)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="The cache key used",
            ),
            "ttl_remaining": NodeParameter(
                name="ttl_remaining",
                type=int,
                required=False,
                description="Remaining TTL in seconds",
            ),
            "backend_used": NodeParameter(
                name="backend_used",
                type=str,
                description="Backend that handled the operation",
            ),
            "operation_time": NodeParameter(
                name="operation_time",
                type=float,
                description="Time taken for the operation",
            ),
            "stats": NodeParameter(
                name="stats",
                type=dict,
                required=False,
                description="Cache statistics (for stats operation)",
            ),
            "compressed": NodeParameter(
                name="compressed",
                type=bool,
                required=False,
                description="Whether the value was compressed",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute cache operations."""
        operation = kwargs["operation"].lower()
        backend = CacheBackend(kwargs.get("backend", "memory"))

        start_time = time.time()

        try:
            # Initialize backend if needed
            await self._ensure_backend(backend, kwargs)

            # Execute operation
            if operation == "get":
                result = await self._get(kwargs)
            elif operation == "set":
                result = await self._set(kwargs)
            elif operation == "delete":
                result = await self._delete(kwargs)
            elif operation == "exists":
                result = await self._exists(kwargs)
            elif operation == "clear":
                result = await self._clear(kwargs)
            elif operation == "stats":
                result = await self._get_stats(kwargs)
            elif operation == "get_pattern":
                result = await self._get_pattern(kwargs)
            elif operation == "mget":
                result = await self._mget(kwargs)
            elif operation == "mset":
                result = await self._mset(kwargs)
            else:
                raise ValueError(f"Unsupported operation: {operation}")

            operation_time = time.time() - start_time
            result["operation_time"] = operation_time
            result["backend_used"] = backend.value

            return result

        except Exception as e:
            self.logger.error(f"Cache operation failed: {str(e)}")
            raise NodeExecutionError(f"Cache operation '{operation}' failed: {str(e)}")

        finally:
            # Clean up Redis connection after operation
            if self._redis_client:
                try:
                    await self._redis_client.aclose()
                except Exception:
                    pass  # Ignore cleanup errors
                self._redis_client = None

    async def _ensure_backend(self, backend: CacheBackend, kwargs: Dict[str, Any]):
        """Ensure the cache backend is initialized with proper connection management."""
        if backend in [CacheBackend.REDIS, CacheBackend.HYBRID]:
            if not REDIS_AVAILABLE:
                if backend == CacheBackend.REDIS:
                    raise NodeExecutionError(
                        "Redis is not available. Install with: pip install redis"
                    )
                else:
                    # Fall back to memory for hybrid mode
                    self.logger.warning("Redis not available, using memory cache only")
                    return

            # Create fresh Redis client for each operation to avoid event loop issues
            redis_url = kwargs.get("redis_url", "redis://localhost:6379")
            try:
                # Create a new client for this operation
                redis_client = redis.from_url(redis_url, decode_responses=False)
                # Test connection
                await redis_client.ping()

                # Store the client for this operation
                self._redis_client = redis_client

            except Exception as e:
                if backend == CacheBackend.REDIS:
                    raise NodeExecutionError(f"Failed to connect to Redis: {str(e)}")
                else:
                    # Fall back to memory for hybrid mode
                    self.logger.warning(
                        f"Redis connection failed, using memory cache: {str(e)}"
                    )
                    self._redis_client = None

    async def _close_redis_connection(self):
        """Close Redis connection if it exists."""
        if self._redis_client:
            try:
                await self._redis_client.aclose()
            except Exception:
                pass  # Ignore errors during cleanup
            self._redis_client = None

    def _build_key(self, key: str, namespace: str = "") -> str:
        """Build a namespaced cache key."""
        if namespace:
            return f"{namespace}:{key}"
        return key

    async def _get(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get a value from cache."""
        key = kwargs["key"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))
        serialization = SerializationFormat(kwargs.get("serialization", "json"))

        full_key = self._build_key(key, namespace)

        try:
            if backend == CacheBackend.REDIS and self._redis_client:
                value, hit = await self._redis_get(full_key, serialization, kwargs)
            elif backend == CacheBackend.HYBRID:
                # Try memory first, then Redis
                value, hit = await self._memory_get(full_key, serialization, kwargs)
                if hit and self._redis_client:
                    # Check if key still exists in Redis (might have been invalidated)
                    redis_exists = await self._redis_client.exists(full_key)
                    if not redis_exists:
                        # Key was invalidated in Redis, remove from memory cache
                        self._memory_cache.pop(full_key, None)
                        self._access_times.pop(full_key, None)
                        self._access_counts.pop(full_key, None)
                        value, hit = None, False
                elif not hit and self._redis_client:
                    value, hit = await self._redis_get(full_key, serialization, kwargs)
                    # Cache in memory for next access
                    if hit:
                        await self._memory_set(full_key, value, kwargs)
            else:
                value, hit = await self._memory_get(full_key, serialization, kwargs)

            if hit:
                self._cache_stats["hits"] += 1
            else:
                self._cache_stats["misses"] += 1

            return {
                "success": True,
                "value": value,
                "hit": hit,
                "key": full_key,
            }

        except Exception as e:
            self.logger.error(f"Cache get failed for key '{full_key}': {str(e)}")
            return {
                "success": False,
                "value": None,
                "hit": False,
                "key": full_key,
                "error": str(e),
            }

    async def _set(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Set a value in cache."""
        key = kwargs["key"]
        value = kwargs["value"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))
        ttl = kwargs.get("ttl", 3600)

        full_key = self._build_key(key, namespace)

        try:
            if backend == CacheBackend.REDIS and self._redis_client:
                success = await self._redis_set(full_key, value, ttl, kwargs)
            elif backend == CacheBackend.HYBRID:
                # Set in both memory and Redis
                success1 = await self._memory_set(full_key, value, kwargs)
                success2 = True
                if self._redis_client:
                    success2 = await self._redis_set(full_key, value, ttl, kwargs)
                success = success1 and success2
            else:
                success = await self._memory_set(full_key, value, kwargs)

            if success:
                self._cache_stats["sets"] += 1

            return {
                "success": success,
                "key": full_key,
                "ttl_remaining": ttl if ttl > 0 else -1,
            }

        except Exception as e:
            self.logger.error(f"Cache set failed for key '{full_key}': {str(e)}")
            return {
                "success": False,
                "key": full_key,
                "error": str(e),
            }

    async def _delete(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a value from cache."""
        key = kwargs["key"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))

        full_key = self._build_key(key, namespace)

        try:
            deleted = False

            if backend == CacheBackend.REDIS and self._redis_client:
                deleted = bool(await self._redis_client.delete(full_key))
            elif backend == CacheBackend.HYBRID:
                # Delete from both
                mem_deleted = full_key in self._memory_cache
                if mem_deleted:
                    del self._memory_cache[full_key]
                    del self._access_times[full_key]
                    self._access_counts.pop(full_key, None)

                redis_deleted = False
                if self._redis_client:
                    redis_deleted = bool(await self._redis_client.delete(full_key))

                deleted = mem_deleted or redis_deleted
            else:
                if full_key in self._memory_cache:
                    del self._memory_cache[full_key]
                    del self._access_times[full_key]
                    self._access_counts.pop(full_key, None)
                    deleted = True

            if deleted:
                self._cache_stats["deletes"] += 1

            return {
                "success": True,
                "deleted": deleted,
                "key": full_key,
            }

        except Exception as e:
            self.logger.error(f"Cache delete failed for key '{full_key}': {str(e)}")
            return {
                "success": False,
                "deleted": False,
                "key": full_key,
                "error": str(e),
            }

    async def _exists(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Check if a key exists in cache."""
        key = kwargs["key"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))

        full_key = self._build_key(key, namespace)

        try:
            exists = False

            if backend == CacheBackend.REDIS and self._redis_client:
                exists = bool(await self._redis_client.exists(full_key))
            elif backend == CacheBackend.HYBRID:
                exists = full_key in self._memory_cache or (
                    self._redis_client
                    and bool(await self._redis_client.exists(full_key))
                )
            else:
                exists = full_key in self._memory_cache

            return {
                "success": True,
                "exists": exists,
                "key": full_key,
            }

        except Exception as e:
            self.logger.error(
                f"Cache exists check failed for key '{full_key}': {str(e)}"
            )
            return {
                "success": False,
                "exists": False,
                "key": full_key,
                "error": str(e),
            }

    async def _clear(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Clear all cache entries."""
        backend = CacheBackend(kwargs.get("backend", "memory"))
        namespace = kwargs.get("namespace", "")

        try:
            cleared_count = 0

            if backend == CacheBackend.REDIS and self._redis_client:
                if namespace:
                    # Clear only namespaced keys
                    pattern = f"{namespace}:*"
                    keys = await self._redis_client.keys(pattern)
                    if keys:
                        cleared_count = await self._redis_client.delete(*keys)
                else:
                    # Clear all
                    await self._redis_client.flushdb()
                    cleared_count = -1  # Unknown count

            elif backend == CacheBackend.HYBRID:
                # Clear memory
                if namespace:
                    mem_keys = [
                        k
                        for k in self._memory_cache.keys()
                        if k.startswith(f"{namespace}:")
                    ]
                    for k in mem_keys:
                        del self._memory_cache[k]
                        del self._access_times[k]
                        self._access_counts.pop(k, None)
                    cleared_count += len(mem_keys)
                else:
                    cleared_count += len(self._memory_cache)
                    self._memory_cache.clear()
                    self._access_times.clear()
                    self._access_counts.clear()

                # Clear Redis
                if self._redis_client:
                    if namespace:
                        pattern = f"{namespace}:*"
                        keys = await self._redis_client.keys(pattern)
                        if keys:
                            cleared_count += await self._redis_client.delete(*keys)
                    else:
                        await self._redis_client.flushdb()

            else:
                # Memory cache
                if namespace:
                    mem_keys = [
                        k
                        for k in self._memory_cache.keys()
                        if k.startswith(f"{namespace}:")
                    ]
                    for k in mem_keys:
                        del self._memory_cache[k]
                        del self._access_times[k]
                        self._access_counts.pop(k, None)
                    cleared_count = len(mem_keys)
                else:
                    cleared_count = len(self._memory_cache)
                    self._memory_cache.clear()
                    self._access_times.clear()
                    self._access_counts.clear()

            return {
                "success": True,
                "cleared_count": cleared_count,
            }

        except Exception as e:
            self.logger.error(f"Cache clear failed: {str(e)}")
            return {
                "success": False,
                "cleared_count": 0,
                "error": str(e),
            }

    async def _get_stats(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get cache statistics."""
        backend = CacheBackend(kwargs.get("backend", "memory"))

        try:
            stats = dict(self._cache_stats)

            if backend == CacheBackend.MEMORY or backend == CacheBackend.HYBRID:
                stats["memory_items"] = len(self._memory_cache)
                stats["memory_size_bytes"] = sum(
                    len(str(v).encode()) for v in self._memory_cache.values()
                )

            if (
                backend == CacheBackend.REDIS or backend == CacheBackend.HYBRID
            ) and self._redis_client:
                redis_info = await self._redis_client.info()
                stats["redis_connected"] = True
                stats["redis_memory"] = redis_info.get("used_memory", 0)
                stats["redis_keys"] = redis_info.get("db0", {}).get("keys", 0)
            else:
                stats["redis_connected"] = False

            # Calculate hit rate
            total_reads = stats["hits"] + stats["misses"]
            stats["hit_rate"] = stats["hits"] / total_reads if total_reads > 0 else 0

            return {
                "success": True,
                "stats": stats,
            }

        except Exception as e:
            self.logger.error(f"Failed to get cache stats: {str(e)}")
            return {
                "success": False,
                "stats": {},
                "error": str(e),
            }

    async def _get_pattern(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get values matching a pattern."""
        pattern = kwargs["pattern"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))
        limit = kwargs.get("limit", 1000)

        if namespace:
            pattern = f"{namespace}:{pattern}"

        try:
            values = {}

            if backend == CacheBackend.REDIS and self._redis_client:
                keys = await self._redis_client.keys(pattern)
                if keys:
                    keys = keys[:limit]  # Limit results
                    raw_values = await self._redis_client.mget(keys)
                    for key, raw_value in zip(keys, raw_values):
                        if raw_value:
                            try:
                                values[
                                    key.decode() if isinstance(key, bytes) else key
                                ] = json.loads(raw_value)
                            except json.JSONDecodeError:
                                values[
                                    key.decode() if isinstance(key, bytes) else key
                                ] = (
                                    raw_value.decode()
                                    if isinstance(raw_value, bytes)
                                    else raw_value
                                )

            elif backend == CacheBackend.HYBRID:
                # Get from memory
                import fnmatch

                mem_keys = [
                    k for k in self._memory_cache.keys() if fnmatch.fnmatch(k, pattern)
                ]
                for key in mem_keys[:limit]:
                    values[key] = self._memory_cache[key]

                # Get from Redis if not enough results
                if len(values) < limit and self._redis_client:
                    remaining_limit = limit - len(values)
                    redis_keys = await self._redis_client.keys(pattern)
                    redis_keys = [k for k in redis_keys if k not in values][
                        :remaining_limit
                    ]
                    if redis_keys:
                        raw_values = await self._redis_client.mget(redis_keys)
                        for key, raw_value in zip(redis_keys, raw_values):
                            if raw_value:
                                try:
                                    values[
                                        key.decode() if isinstance(key, bytes) else key
                                    ] = json.loads(raw_value)
                                except json.JSONDecodeError:
                                    values[
                                        key.decode() if isinstance(key, bytes) else key
                                    ] = (
                                        raw_value.decode()
                                        if isinstance(raw_value, bytes)
                                        else raw_value
                                    )

            else:
                # Memory cache with fnmatch
                import fnmatch

                mem_keys = [
                    k for k in self._memory_cache.keys() if fnmatch.fnmatch(k, pattern)
                ]
                for key in mem_keys[:limit]:
                    values[key] = self._memory_cache[key]

            return {
                "success": True,
                "values": values,
                "count": len(values),
                "pattern": pattern,
            }

        except Exception as e:
            self.logger.error(f"Pattern get failed for pattern '{pattern}': {str(e)}")
            return {
                "success": False,
                "values": {},
                "count": 0,
                "pattern": pattern,
                "error": str(e),
            }

    async def _mget(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get multiple values by keys."""
        keys = kwargs["keys"]
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))

        full_keys = [self._build_key(key, namespace) for key in keys]

        try:
            values = {}
            hits = 0

            if backend == CacheBackend.REDIS and self._redis_client:
                raw_values = await self._redis_client.mget(full_keys)
                for key, raw_value in zip(full_keys, raw_values):
                    if raw_value:
                        try:
                            values[key] = json.loads(raw_value)
                            hits += 1
                        except json.JSONDecodeError:
                            values[key] = (
                                raw_value.decode()
                                if isinstance(raw_value, bytes)
                                else raw_value
                            )
                            hits += 1

            elif backend == CacheBackend.HYBRID:
                # Try memory first
                for key in full_keys:
                    if key in self._memory_cache:
                        values[key] = self._memory_cache[key]
                        hits += 1

                # Get missing keys from Redis
                missing_keys = [k for k in full_keys if k not in values]
                if missing_keys and self._redis_client:
                    raw_values = await self._redis_client.mget(missing_keys)
                    for key, raw_value in zip(missing_keys, raw_values):
                        if raw_value:
                            try:
                                value = json.loads(raw_value)
                                values[key] = value
                                # Cache in memory
                                self._memory_cache[key] = value
                                self._access_times[key] = time.time()
                                hits += 1
                            except json.JSONDecodeError:
                                value = (
                                    raw_value.decode()
                                    if isinstance(raw_value, bytes)
                                    else raw_value
                                )
                                values[key] = value
                                self._memory_cache[key] = value
                                self._access_times[key] = time.time()
                                hits += 1

            else:
                # Memory cache
                for key in full_keys:
                    if key in self._memory_cache:
                        values[key] = self._memory_cache[key]
                        hits += 1

            self._cache_stats["hits"] += hits
            self._cache_stats["misses"] += len(full_keys) - hits

            return {
                "success": True,
                "values": values,
                "hits": hits,
                "total_keys": len(full_keys),
            }

        except Exception as e:
            self.logger.error(f"Batch get failed: {str(e)}")
            return {
                "success": False,
                "values": {},
                "hits": 0,
                "total_keys": len(full_keys),
                "error": str(e),
            }

    async def _mset(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Set multiple key-value pairs."""
        values_dict = kwargs.get("values", {})
        namespace = kwargs.get("namespace", "")
        backend = CacheBackend(kwargs.get("backend", "memory"))
        ttl = kwargs.get("ttl", 3600)

        if not values_dict:
            return {"success": False, "error": "No values provided"}

        full_values = {
            self._build_key(key, namespace): value for key, value in values_dict.items()
        }

        try:
            success_count = 0

            if backend == CacheBackend.REDIS and self._redis_client:
                # Use Redis pipeline for efficiency
                pipe = self._redis_client.pipeline()
                for key, value in full_values.items():
                    serialized = (
                        json.dumps(value) if not isinstance(value, str) else value
                    )
                    if ttl > 0:
                        pipe.setex(key, ttl, serialized)
                    else:
                        pipe.set(key, serialized)

                results = await pipe.execute()
                success_count = sum(1 for r in results if r)

            elif backend == CacheBackend.HYBRID:
                # Set in memory
                for key, value in full_values.items():
                    self._memory_cache[key] = value
                    self._access_times[key] = time.time()
                    success_count += 1

                # Set in Redis
                if self._redis_client:
                    pipe = self._redis_client.pipeline()
                    for key, value in full_values.items():
                        serialized = (
                            json.dumps(value) if not isinstance(value, str) else value
                        )
                        if ttl > 0:
                            pipe.setex(key, ttl, serialized)
                        else:
                            pipe.set(key, serialized)
                    await pipe.execute()

            else:
                # Memory cache
                for key, value in full_values.items():
                    self._memory_cache[key] = value
                    self._access_times[key] = time.time()
                    success_count += 1

            self._cache_stats["sets"] += success_count

            return {
                "success": True,
                "set_count": success_count,
                "total_keys": len(full_values),
            }

        except Exception as e:
            self.logger.error(f"Batch set failed: {str(e)}")
            return {
                "success": False,
                "set_count": 0,
                "total_keys": len(full_values),
                "error": str(e),
            }

    async def _memory_get(
        self, key: str, serialization: SerializationFormat, kwargs: Dict[str, Any]
    ) -> tuple[Any, bool]:
        """Get value from memory cache."""
        if key not in self._memory_cache:
            return None, False

        # Check TTL if stored with timestamp
        value_data = self._memory_cache[key]
        if isinstance(value_data, dict) and "_cache_timestamp" in value_data:
            timestamp = value_data["_cache_timestamp"]
            ttl = value_data.get("_cache_ttl", 0)
            if ttl > 0 and time.time() - timestamp > ttl:
                # Expired
                del self._memory_cache[key]
                del self._access_times[key]
                self._access_counts.pop(key, None)
                return None, False
            value = value_data["_cache_value"]
        else:
            value = value_data

        # Update access statistics
        self._access_times[key] = time.time()
        self._access_counts[key] = self._access_counts.get(key, 0) + 1

        # Handle decompression if needed
        if kwargs.get("compression", False) and isinstance(value, bytes):
            try:
                value = gzip.decompress(value)
                if serialization == SerializationFormat.JSON:
                    value = json.loads(value.decode())
                elif serialization == SerializationFormat.PICKLE:
                    value = pickle.loads(value)
            except Exception:
                pass  # Use value as-is if decompression fails

        return value, True

    async def _memory_set(self, key: str, value: Any, kwargs: Dict[str, Any]) -> bool:
        """Set value in memory cache."""
        try:
            ttl = kwargs.get("ttl", 0)
            compression = kwargs.get("compression", False)
            compression_threshold = kwargs.get("compression_threshold", 1024)
            max_items = kwargs.get("max_memory_items", 10000)

            # Handle eviction if needed
            if len(self._memory_cache) >= max_items:
                await self._evict_memory_items(kwargs)

            # Prepare value for storage
            stored_value = value
            compressed = False

            # Apply compression if needed
            if compression:
                serialized = (
                    json.dumps(value) if not isinstance(value, (str, bytes)) else value
                )
                if isinstance(serialized, str):
                    serialized = serialized.encode()

                if len(serialized) >= compression_threshold:
                    stored_value = gzip.compress(serialized)
                    compressed = True

            # Store with TTL if specified
            if ttl > 0:
                self._memory_cache[key] = {
                    "_cache_value": stored_value,
                    "_cache_timestamp": time.time(),
                    "_cache_ttl": ttl,
                    "_cache_compressed": compressed,
                }
            else:
                self._memory_cache[key] = stored_value

            self._access_times[key] = time.time()
            return True

        except Exception as e:
            self.logger.error(f"Memory cache set failed: {str(e)}")
            return False

    async def _redis_get(
        self, key: str, serialization: SerializationFormat, kwargs: Dict[str, Any]
    ) -> tuple[Any, bool]:
        """Get value from Redis cache."""
        try:
            raw_value = await self._redis_client.get(key)
            if raw_value is None:
                return None, False

            # Handle decompression
            if kwargs.get("compression", False):
                try:
                    raw_value = gzip.decompress(raw_value)
                except Exception:
                    pass  # Not compressed or failed decompression

            # Deserialize based on format
            if serialization == SerializationFormat.JSON:
                value = json.loads(raw_value)
            elif serialization == SerializationFormat.PICKLE:
                value = pickle.loads(raw_value)
            elif serialization == SerializationFormat.STRING:
                value = (
                    raw_value.decode() if isinstance(raw_value, bytes) else raw_value
                )
            else:  # BYTES
                value = raw_value

            return value, True

        except Exception as e:
            self.logger.error(f"Redis get failed: {str(e)}")
            return None, False

    async def _redis_set(
        self, key: str, value: Any, ttl: int, kwargs: Dict[str, Any]
    ) -> bool:
        """Set value in Redis cache."""
        try:
            serialization = SerializationFormat(kwargs.get("serialization", "json"))
            compression = kwargs.get("compression", False)
            compression_threshold = kwargs.get("compression_threshold", 1024)

            # Serialize value
            if serialization == SerializationFormat.JSON:
                serialized = json.dumps(value)
            elif serialization == SerializationFormat.PICKLE:
                serialized = pickle.dumps(value)
            elif serialization == SerializationFormat.STRING:
                serialized = str(value)
            else:  # BYTES
                serialized = value if isinstance(value, bytes) else str(value).encode()

            # Apply compression if needed
            if compression and len(serialized) >= compression_threshold:
                if isinstance(serialized, str):
                    serialized = serialized.encode()
                serialized = gzip.compress(serialized)

            # Store in Redis
            if ttl > 0:
                await self._redis_client.setex(key, ttl, serialized)
            else:
                await self._redis_client.set(key, serialized)

            return True

        except Exception as e:
            self.logger.error(f"Redis set failed: {str(e)}")
            return False

    async def _evict_memory_items(self, kwargs: Dict[str, Any]):
        """Evict items from memory cache based on policy."""
        eviction_policy = EvictionPolicy(kwargs.get("eviction_policy", "lru"))
        max_items = kwargs.get("max_memory_items", 10000)

        # Remove 10% of items to make room
        evict_count = max(1, len(self._memory_cache) // 10)

        if eviction_policy == EvictionPolicy.LRU:
            # Remove least recently used
            sorted_by_access = sorted(self._access_times.items(), key=lambda x: x[1])
            for key, _ in sorted_by_access[:evict_count]:
                del self._memory_cache[key]
                del self._access_times[key]
                self._access_counts.pop(key, None)
                self._cache_stats["evictions"] += 1

        elif eviction_policy == EvictionPolicy.LFU:
            # Remove least frequently used
            sorted_by_frequency = sorted(
                self._access_counts.items(), key=lambda x: x[1]
            )
            for key, _ in sorted_by_frequency[:evict_count]:
                del self._memory_cache[key]
                del self._access_times[key]
                del self._access_counts[key]
                self._cache_stats["evictions"] += 1

        elif eviction_policy == EvictionPolicy.TTL:
            # Remove expired items first
            now = time.time()
            expired_keys = []
            for key, value_data in self._memory_cache.items():
                if isinstance(value_data, dict) and "_cache_timestamp" in value_data:
                    timestamp = value_data["_cache_timestamp"]
                    ttl = value_data.get("_cache_ttl", 0)
                    if ttl > 0 and now - timestamp > ttl:
                        expired_keys.append(key)

            for key in expired_keys:
                del self._memory_cache[key]
                del self._access_times[key]
                self._access_counts.pop(key, None)
                self._cache_stats["evictions"] += 1

        elif eviction_policy == EvictionPolicy.FIFO:
            # Remove oldest inserted items
            sorted_keys = list(self._memory_cache.keys())[:evict_count]
            for key in sorted_keys:
                del self._memory_cache[key]
                del self._access_times[key]
                self._access_counts.pop(key, None)
                self._cache_stats["evictions"] += 1

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self.async_run(**kwargs))
        else:
            # Event loop is running, create a task
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.async_run(**kwargs))
                return future.result()
