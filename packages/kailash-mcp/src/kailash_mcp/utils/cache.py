"""
Caching utilities for MCP servers.

Provides LRU cache, TTL support, and decorators for method-level caching.
Based on patterns from production MCP server implementations.
"""

import asyncio
import functools
import hashlib
import json
import logging
import threading
import time
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, TypeVar

from kailash.utils.redis_validation import validate_redis_url

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

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache, evicting LRU items if necessary.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses instance default if None)
        """
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

        lru_key = min(self._access_order.keys(), key=self._access_order.get)  # type: ignore[reportCallIssue]
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


class UnifiedCache:
    """
    Unified cache interface that works with both Redis and in-memory LRU cache.

    This provides a consistent interface regardless of the backend.
    Includes cache stampede prevention using single-flight pattern.
    """

    def __init__(
        self,
        name: str,
        ttl: int = 300,
        redis_client=None,
        redis_prefix: str = "mcp:",
        lru_cache=None,
    ):
        """Initialize unified cache.

        Args:
            name: Cache name
            ttl: Default TTL
            redis_client: Redis client (if using Redis backend)
            redis_prefix: Redis key prefix
            lru_cache: LRU cache instance (if using memory backend)
        """
        self.name = name
        self.ttl = ttl
        self.redis_client = redis_client
        self.redis_prefix = redis_prefix
        self.lru_cache = lru_cache
        self.is_redis = redis_client is not None

        # Single-flight pattern for stampede prevention
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._flight_lock = asyncio.Lock()

        # One WARN per cache PER REASON when the sync surface degrades on
        # Redis, so a hot-path caller does not flood the log on every call.
        # Keyed by reason because the causes are distinct and an operator
        # needs to see each: a sync `get`/`set` can never reach Redis, while
        # a sync tool running INSIDE an event loop cannot use `asyncio.run`.
        self._sync_degradation_warned: set = set()

    def _make_key(self, key: str) -> str:
        """Make cache key with name prefix."""
        if self.is_redis:
            return f"{self.redis_prefix}{self.name}:{key}"
        return key

    def _warn_sync_on_redis_once(
        self, method: str, replacement: str, detail: Optional[str] = None
    ) -> None:
        """Emit ONE loud WARN per cache PER REASON when the sync surface degrades.

        A sync method cannot await, so ``get``/``set`` genuinely cannot reach
        Redis; the result is NO caching (slow but correct), not wrong data.
        Unlike :meth:`clear`, they do NOT raise: the sync half of the
        ``cached()`` decorator wraps a sync function and therefore has no async
        path to move to, so raising would make ``@cached`` unusable on Redis —
        a harder break than the degradation it reports. Silence is still
        BLOCKED (``zero-tolerance.md`` Rule 3), so the degradation is announced
        once per cache, per distinct cause, with the replacement named.

        De-duplication is keyed on ``method`` so a caller hitting two different
        causes sees both: one WARN would otherwise hide whichever fired second.
        """
        if method in self._sync_degradation_warned:
            return
        self._sync_degradation_warned.add(method)
        logger.warning(
            "cache.sync.degraded_on_redis name=%s method=%s replacement=%s "
            "detail=%s; this cache is serving NO cached values on that path",
            self.name,
            method,
            replacement,
            detail
            or (f"sync {method} cannot reach Redis (every Redis op here is awaited)"),
        )

    def get(self, key: str):
        """Get value from cache.

        On the Redis backend this always MISSES — a sync method cannot await —
        and says so once via :meth:`_warn_sync_on_redis_once`. Await
        :meth:`aget` for a working read.
        """
        if self.is_redis:
            self._warn_sync_on_redis_once("get", "aget")
            return None
        return self.lru_cache.get(key)  # type: ignore[reportOptionalMemberAccess]

    def set(self, key: str, value, ttl: Optional[int] = None):
        """Set value in cache.

        On the Redis backend this stores NOTHING — a sync method cannot await —
        and says so once. Await :meth:`aset` for a working write.
        """
        if self.is_redis:
            self._warn_sync_on_redis_once("set", "aset")
            return
        self.lru_cache.set(key, value, ttl or self.ttl)  # type: ignore[reportOptionalMemberAccess]

    async def aget(self, key: str):
        """Async get value from cache."""
        if self.is_redis:
            try:
                redis_key = self._make_key(key)
                value = await self.redis_client.get(redis_key)  # type: ignore[reportOptionalMemberAccess]
                return json.loads(value) if value else None
            except Exception as e:
                logger.error("cache.redis.get.error error=%s", e)
                return None
        else:
            return self.lru_cache.get(key)  # type: ignore[reportOptionalMemberAccess]

    async def aset(self, key: str, value, ttl: Optional[int] = None):
        """Async set value in cache."""
        if self.is_redis:
            try:
                redis_key = self._make_key(key)
                serialized_value = json.dumps(value)
                cache_ttl = ttl or self.ttl
                await self.redis_client.setex(redis_key, cache_ttl, serialized_value)  # type: ignore[reportOptionalMemberAccess]
                return True
            except Exception as e:
                logger.error("cache.redis.set.error error=%s", e)
                return False
        else:
            self.lru_cache.set(key, value, ttl or self.ttl)  # type: ignore[reportOptionalMemberAccess]
            return True

    async def get_or_compute(
        self,
        key: str,
        compute_func: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None,
    ) -> Any:
        """Get value from cache or compute it if not present (with stampede prevention).

        This method implements single-flight pattern to prevent cache stampede.
        If multiple requests come in for the same key while it's being computed,
        only one will actually execute the compute function.

        Args:
            key: Cache key
            compute_func: Async function to compute the value if not in cache
            ttl: TTL for cached value

        Returns:
            The cached or computed value
        """
        # First try to get from cache
        cached_value = await self.aget(key)
        if cached_value is not None:
            return cached_value

        # Check if computation is already in flight
        async with self._flight_lock:
            if key in self._in_flight:
                # Wait for the existing computation
                logger.debug("cache.get_or_compute.waiting key=%s", key)
                return await self._in_flight[key]

            # Start new computation
            future = asyncio.Future()
            self._in_flight[key] = future

        try:
            # Compute the value
            logger.debug("cache.get_or_compute.start key=%s", key)
            value = await compute_func()

            # Cache the result
            await self.aset(key, value, ttl)

            # Notify waiting requests
            future.set_result(value)
            return value

        except Exception as e:
            # Notify waiting requests of the error
            future.set_exception(e)
            raise
        finally:
            # Clean up in-flight tracking
            async with self._flight_lock:
                self._in_flight.pop(key, None)

    def _namespace_pattern(self) -> str:
        """Return the SCAN MATCH pattern covering exactly this cache's keys.

        Mirrors :meth:`_make_key` (``{prefix}{name}:{key}``) so the pattern can
        never drift from the keys actually written. Glob metacharacters in the
        prefix/name are ESCAPED: a cache named ``tools*`` would otherwise match
        ``mcp:tools-internal:...`` and delete a sibling cache's keys.
        """
        literal = f"{self.redis_prefix}{self.name}:"
        escaped = "".join("\\" + ch if ch in "*?[]\\" else ch for ch in literal)
        return f"{escaped}*"

    def clear(self):
        """Clear cache.

        The memory backend clears in place. The Redis backend CANNOT be cleared
        from a sync method — every Redis operation on this class is awaited — so
        this RAISES rather than silently doing nothing. It previously executed
        ``pass``, which left the cache fully populated while every caller (and
        ``MCPServer.clear_cache``'s "Cleared cache" log line) reported success;
        a cache that reports a successful invalidation and serves the stale
        entries indefinitely is worse than one that refuses. Await
        :meth:`aclear` instead.
        """
        if self.is_redis:
            raise RuntimeError(
                "UnifiedCache.clear() cannot clear a Redis-backed cache: every "
                "Redis operation on this class is async. Await aclear() instead "
                f"(cache name={self.name!r})."
            )
        self.lru_cache.clear()  # type: ignore[reportOptionalMemberAccess]

    async def aclear(self) -> int:
        """Delete every key owned by THIS cache. Returns the number deleted.

        Scoped to this cache's own namespace (``{prefix}{name}:*``) via
        SCAN + DELETE. ``FLUSHDB`` is deliberately NOT used: the Redis database
        is shared with every other :class:`UnifiedCache` instance and, in most
        deployments, with non-MCP consumers — flushing it to clear one cache
        would destroy their keys, a far worse defect than the no-op this
        replaces.

        A failure is logged AND re-raised rather than swallowed: a clear that
        silently fails leaves stale entries served indefinitely, which is the
        exact failure mode this method exists to close.
        """
        if not self.is_redis:
            self.lru_cache.clear()  # type: ignore[reportOptionalMemberAccess]
            return 0

        pattern = self._namespace_pattern()
        deleted = 0
        cursor: Any = 0
        try:
            while True:
                cursor, keys = await self.redis_client.scan(  # type: ignore[reportOptionalMemberAccess]
                    cursor=cursor, match=pattern, count=500
                )
                if keys:
                    await self.redis_client.delete(*keys)  # type: ignore[reportOptionalMemberAccess]
                    deleted += len(keys)
                # redis-py returns int 0 to end the sweep; some clients echo "0".
                if int(cursor) == 0:
                    break
        except Exception as e:
            logger.error(
                "cache.redis.clear.error name=%s pattern=%s deleted=%d error=%s",
                self.name,
                pattern,
                deleted,
                e,
            )
            raise
        logger.info("cache.redis.clear.ok name=%s deleted=%d", self.name, deleted)
        return deleted

    def stats(self):
        """Get cache statistics."""
        if self.is_redis:
            return {"backend": "redis", "name": self.name}
        else:
            return self.lru_cache.stats()  # type: ignore[reportOptionalMemberAccess]


class CacheManager:
    """
    High-level cache management with multiple caching strategies.

    Provides easy-to-use caching for MCP servers with different cache types
    for different use cases.
    """

    def __init__(
        self,
        enabled: bool = True,
        default_ttl: int = 300,
        backend: str = "memory",
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize cache manager.

        Args:
            enabled: Whether caching is enabled
            default_ttl: Default TTL for cache entries
            backend: Cache backend ("memory" or "redis")
            config: Backend-specific configuration
        """
        self.enabled = enabled
        self.default_ttl = default_ttl
        self.backend = backend
        self.config = config or {}
        self._caches: Dict[str, UnifiedCache] = {}

        # Initialize Redis if specified
        self._redis = None
        if backend == "redis" and enabled:
            self._init_redis()

    def get_cache(
        self, name: str, max_size: int = 128, ttl: Optional[int] = None
    ) -> UnifiedCache:
        """Get or create a named cache."""
        if name not in self._caches:
            cache_ttl = ttl if ttl is not None else self.default_ttl
            if self.backend == "redis" and self._redis:
                self._caches[name] = UnifiedCache(
                    name=name,
                    ttl=cache_ttl,
                    redis_client=self._redis,
                    redis_prefix=self.config.get("prefix", "mcp:"),
                )
            else:
                self._caches[name] = UnifiedCache(
                    name=name,
                    ttl=cache_ttl,
                    lru_cache=LRUCache(max_size=max_size, ttl=cache_ttl),
                )
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
                    logger.debug(
                        "cache.sync.hit func=%s key=%s",
                        func.__name__,
                        cache_key,
                    )
                    return result

                # Execute function and cache result
                logger.debug(
                    "cache.sync.miss func=%s key=%s",
                    func.__name__,
                    cache_key,
                )
                result = func(*args, **kwargs)
                cache.set(cache_key, result)
                return result

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Create cache key from function name and arguments
                cache_key = self._create_cache_key(func.__name__, args, kwargs)

                # AWAIT the async surface. This wrapper previously called the
                # SYNC `cache.get`/`cache.set`, which return None / store
                # nothing on the Redis backend — so every `@cached` async
                # function on a Redis-backed manager silently received NO
                # caching at all, despite being in a context that can await.
                # `aget`/`aset` fall through to the LRU on the memory backend,
                # so this is a pure gain, not a backend-conditional path.
                result = await cache.aget(cache_key)
                if result is not None:
                    logger.debug(
                        "cache.async.hit func=%s key=%s",
                        func.__name__,
                        cache_key,
                    )
                    return result

                # Execute function and cache result
                logger.debug(
                    "cache.async.miss func=%s key=%s",
                    func.__name__,
                    cache_key,
                )
                result = await func(*args, **kwargs)
                await cache.aset(cache_key, result)
                return result

            # Return appropriate wrapper based on function type
            if asyncio.iscoroutinefunction(func):
                return async_wrapper  # type: ignore[return-value]
            else:
                return sync_wrapper  # type: ignore[return-value]

        return decorator

    def _init_redis(self):
        """Initialize Redis connection."""
        try:
            import redis.asyncio as redis
            from urllib.parse import urlparse

            redis_url = self.config.get("redis_url", "redis://localhost:6379")
            # Validate Redis URL scheme to prevent SSRF (H4)
            validate_redis_url(redis_url)
            self._redis = redis.from_url(redis_url, decode_responses=True)
            # Mask credentials: log only scheme://host:port — never
            # the userinfo or query-string password. See security.md
            # § "No secrets in logs".
            _parsed = urlparse(redis_url)
            _safe_port = f":{_parsed.port}" if _parsed.port else ""
            logger.info(
                "Initialized Redis cache backend: %s://%s%s",
                _parsed.scheme,
                _parsed.hostname or "localhost",
                _safe_port,
            )
        except ImportError:
            logger.warning("Redis not available. Install with: pip install redis")
            self.enabled = False
        except Exception as e:
            logger.error("cache.redis.init.error error=%s", e)
            self.enabled = False

    async def get_redis(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        if not self._redis:
            return None
        try:
            value = await self._redis.get(self._make_redis_key(key))
            return json.loads(value) if value else None
        except Exception as e:
            logger.error("cache.redis.get.error error=%s", e)
            return None

    async def set_redis(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis cache."""
        if not self._redis:
            return False
        try:
            redis_key = self._make_redis_key(key)
            serialized_value = json.dumps(value)
            if ttl:
                await self._redis.setex(redis_key, ttl, serialized_value)
            else:
                await self._redis.set(redis_key, serialized_value)
            return True
        except Exception as e:
            logger.error("cache.redis.set.error error=%s", e)
            return False

    def _make_redis_key(self, key: str) -> str:
        """Create Redis key with prefix."""
        prefix = self.config.get("prefix", "mcp:")
        return f"{prefix}{key}"

    def _create_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Create a cache key from function name and arguments.

        The arguments are folded into a DIGEST rather than interpolated
        verbatim, because this string is not private: it is DEBUG-logged by
        ``UnifiedCache.get_or_compute`` and by the ``cached`` decorator, and it
        becomes a REDIS KEY NAME via ``UnifiedCache._make_key``. A verbatim key
        therefore reaches log lines, ``KEYS mcp:*``, ``MONITOR``, the slowlog,
        and RDB/AOF on disk.

        The MCP server strips a fixed set of transport-credential kwargs before
        reaching here, but that set is a fixed list of names and cannot be
        complete: a tool taking ``github_token``, or a deployment spelling its
        header ``x_api_key`` / ``auth_token`` / ``apikey``, still arrives with a
        secret in a business argument. Lengthening the name list cannot fix
        that — business arguments are exactly what the key must keep
        distinguishing. Hashing closes the log surface, the Redis key-name
        surface, and the unbounded-key-length surface at once, for every
        argument, without weakening that discrimination.

        ``func_name`` is kept as a readable prefix so a key remains
        attributable to its tool when debugging or scanning Redis. Callers that
        need per-principal partitioning pass an already-digested principal tag
        as part of ``func_name`` (see ``MCPServer._cache_key_scope``), so no
        raw identifier reaches the prefix either.
        """
        # Pre-image composition is unchanged from the verbatim form, so the same
        # inputs that used to collide still collide and no call that used to be
        # distinguished stops being distinguished.
        args_str = str(args) if args else ""
        kwargs_str = str(sorted(kwargs.items())) if kwargs else ""
        digest = hashlib.sha256(
            f"{func_name}:{args_str}:{kwargs_str}".encode("utf-8")
        ).hexdigest()
        return f"{func_name}:{digest}"

    def clear_all(self) -> None:
        """Clear all caches (memory backend).

        On a Redis-backed manager each :meth:`UnifiedCache.clear` raises, because
        Redis cannot be cleared synchronously — await :meth:`aclear_all` instead.
        The raise is deliberate: this method previously reported success while
        clearing nothing.
        """
        for cache in self._caches.values():
            cache.clear()

    async def aclear_all(self) -> int:
        """Clear all caches on either backend. Returns total Redis keys deleted."""
        deleted = 0
        for cache in self._caches.values():
            deleted += await cache.aclear()
        return deleted

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
    """Clear all caches in the global cache manager (memory backend).

    Raises on a Redis-backed manager — await :func:`aclear_all_caches` instead.
    """
    _global_cache_manager.clear_all()


async def aclear_all_caches() -> int:
    """Clear all caches in the global cache manager on either backend.

    Returns the number of Redis keys deleted (0 on the memory backend).
    """
    return await _global_cache_manager.aclear_all()
