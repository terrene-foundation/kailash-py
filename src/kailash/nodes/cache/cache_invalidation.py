"""Cache invalidation node for intelligent cache management.

This module provides advanced cache invalidation strategies including
pattern-based invalidation, cascade invalidation, event-driven clearing,
and tag-based invalidation for complex cache hierarchies.
"""

import asyncio
import fnmatch
import re
import time
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

try:
    import redis.asyncio as redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class InvalidationStrategy(Enum):
    """Cache invalidation strategies."""

    IMMEDIATE = "immediate"  # Invalidate immediately
    LAZY = "lazy"  # Mark for lazy deletion
    TTL_REFRESH = "ttl_refresh"  # Reset TTL
    CASCADE = "cascade"  # Cascade to dependent keys
    TAG_BASED = "tag_based"  # Invalidate by tags


class InvalidationScope(Enum):
    """Scope of invalidation operation."""

    SINGLE = "single"  # Single key
    PATTERN = "pattern"  # Pattern matching
    TAG = "tag"  # Tag-based
    DEPENDENCY = "dependency"  # Dependency chain
    TIME_BASED = "time_based"  # Time-based expiration


class EventType(Enum):
    """Cache invalidation event types."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"
    EXPIRE = "expire"


@register_node()
class CacheInvalidationNode(AsyncNode):
    """Node for intelligent cache invalidation and management.

    This node provides comprehensive cache invalidation capabilities including:
    - Pattern-based invalidation with wildcard and regex support
    - Tag-based cache invalidation for complex hierarchies
    - Cascade invalidation for dependent cache entries
    - Event-driven invalidation based on data changes
    - Time-based invalidation strategies
    - Dependency tracking and management
    - Statistics and monitoring for invalidation operations
    - Support for multiple cache backends (Redis, memory, hybrid)

    Design Purpose:
    - Maintain cache consistency across complex applications
    - Provide flexible invalidation strategies
    - Support real-time and batch invalidation operations
    - Enable efficient cache management for microservices

    Examples:
        >>> # Pattern-based invalidation
        >>> invalidator = CacheInvalidationNode()
        >>> result = await invalidator.execute(
        ...     strategy="immediate",
        ...     scope="pattern",
        ...     pattern="user:*:profile",
        ...     reason="User profile updated"
        ... )

        >>> # Tag-based invalidation
        >>> result = await invalidator.execute(
        ...     strategy="cascade",
        ...     scope="tag",
        ...     tags=["user:123", "profile", "session"],
        ...     cascade_patterns=["session:*", "cache:user:123:*"]
        ... )

        >>> # Event-driven invalidation
        >>> result = await invalidator.execute(
        ...     strategy="immediate",
        ...     scope="dependency",
        ...     event_type="update",
        ...     source_key="user:123",
        ...     dependencies=["user:123:profile", "user:123:preferences"]
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the cache invalidation node."""
        super().__init__(**kwargs)
        self._redis_client = None
        self._memory_cache = {}
        self._tag_registry = {}  # tag -> set of keys
        self._dependency_graph = {}  # key -> set of dependent keys
        self._invalidation_log = []
        self._stats = {
            "invalidations": 0,
            "cascade_invalidations": 0,
            "pattern_matches": 0,
            "tag_matches": 0,
            "dependency_cascades": 0,
        }
        self.logger.info(f"Initialized CacheInvalidationNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "strategy": NodeParameter(
                name="strategy",
                type=str,
                required=True,
                description="Invalidation strategy (immediate, lazy, ttl_refresh, cascade, tag_based)",
            ),
            "scope": NodeParameter(
                name="scope",
                type=str,
                required=True,
                description="Invalidation scope (single, pattern, tag, dependency, time_based)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Single cache key to invalidate",
            ),
            "keys": NodeParameter(
                name="keys",
                type=list,
                required=False,
                description="Multiple cache keys to invalidate",
            ),
            "pattern": NodeParameter(
                name="pattern",
                type=str,
                required=False,
                description="Pattern for key matching (supports wildcards and regex)",
            ),
            "tags": NodeParameter(
                name="tags",
                type=list,
                required=False,
                description="Tags to invalidate",
            ),
            "dependencies": NodeParameter(
                name="dependencies",
                type=list,
                required=False,
                description="Dependent keys to invalidate",
            ),
            "cascade_patterns": NodeParameter(
                name="cascade_patterns",
                type=list,
                required=False,
                description="Patterns for cascade invalidation",
            ),
            "max_age": NodeParameter(
                name="max_age",
                type=int,
                required=False,
                description="Maximum age in seconds for time-based invalidation",
            ),
            "reason": NodeParameter(
                name="reason",
                type=str,
                required=False,
                default="Manual invalidation",
                description="Reason for invalidation (for logging)",
            ),
            "event_type": NodeParameter(
                name="event_type",
                type=str,
                required=False,
                description="Event type that triggered invalidation",
            ),
            "source_key": NodeParameter(
                name="source_key",
                type=str,
                required=False,
                description="Source key that triggered the invalidation",
            ),
            "backend": NodeParameter(
                name="backend",
                type=str,
                required=False,
                default="memory",
                description="Cache backend (memory, redis, hybrid)",
            ),
            "redis_url": NodeParameter(
                name="redis_url",
                type=str,
                required=False,
                default="redis://localhost:6379",
                description="Redis connection URL",
            ),
            "namespace": NodeParameter(
                name="namespace",
                type=str,
                required=False,
                default="",
                description="Key namespace prefix",
            ),
            "dry_run": NodeParameter(
                name="dry_run",
                type=bool,
                required=False,
                default=False,
                description="Simulate invalidation without executing",
            ),
            "batch_size": NodeParameter(
                name="batch_size",
                type=int,
                required=False,
                default=1000,
                description="Batch size for large invalidation operations",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "success": NodeParameter(
                name="success",
                type=bool,
                description="Whether the invalidation succeeded",
            ),
            "invalidated_count": NodeParameter(
                name="invalidated_count",
                type=int,
                description="Number of cache entries invalidated",
            ),
            "cascade_count": NodeParameter(
                name="cascade_count",
                type=int,
                description="Number of cascade invalidations performed",
            ),
            "invalidated_keys": NodeParameter(
                name="invalidated_keys",
                type=list,
                description="List of invalidated cache keys",
            ),
            "cascade_keys": NodeParameter(
                name="cascade_keys",
                type=list,
                description="List of cascade invalidated keys",
            ),
            "strategy_used": NodeParameter(
                name="strategy_used",
                type=str,
                description="Invalidation strategy that was applied",
            ),
            "scope_used": NodeParameter(
                name="scope_used",
                type=str,
                description="Invalidation scope that was applied",
            ),
            "execution_time": NodeParameter(
                name="execution_time",
                type=float,
                description="Time taken to execute invalidation",
            ),
            "stats": NodeParameter(
                name="stats",
                type=dict,
                description="Invalidation statistics",
            ),
            "dry_run": NodeParameter(
                name="dry_run",
                type=bool,
                description="Whether this was a dry run",
            ),
            "reason": NodeParameter(
                name="reason",
                type=str,
                description="Reason for invalidation",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=str,
                description="ISO timestamp of invalidation",
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute cache invalidation based on strategy and scope."""
        strategy = InvalidationStrategy(kwargs["strategy"])
        scope = InvalidationScope(kwargs["scope"])
        dry_run = kwargs.get("dry_run", False)
        reason = kwargs.get("reason", "Manual invalidation")

        start_time = time.time()

        try:
            # Initialize backend if needed
            await self._ensure_backend(kwargs)

            # Execute invalidation based on scope
            if scope == InvalidationScope.SINGLE:
                result = await self._invalidate_single(strategy, kwargs, dry_run)
            elif scope == InvalidationScope.PATTERN:
                result = await self._invalidate_pattern(strategy, kwargs, dry_run)
            elif scope == InvalidationScope.TAG:
                result = await self._invalidate_tag(strategy, kwargs, dry_run)
            elif scope == InvalidationScope.DEPENDENCY:
                result = await self._invalidate_dependency(strategy, kwargs, dry_run)
            elif scope == InvalidationScope.TIME_BASED:
                result = await self._invalidate_time_based(strategy, kwargs, dry_run)
            else:
                raise ValueError(f"Unsupported invalidation scope: {scope}")

            execution_time = time.time() - start_time

            # Log invalidation
            if not dry_run:
                self._log_invalidation(strategy, scope, result, reason, kwargs)

            # Update statistics
            self._update_stats(result)

            return {
                "success": True,
                "invalidated_count": result.get("invalidated_count", 0),
                "cascade_count": result.get("cascade_count", 0),
                "invalidated_keys": result.get("invalidated_keys", []),
                "cascade_keys": result.get("cascade_keys", []),
                "strategy_used": strategy.value,
                "scope_used": scope.value,
                "execution_time": execution_time,
                "stats": dict(self._stats),
                "dry_run": dry_run,
                "reason": reason,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Cache invalidation failed: {str(e)}")
            raise NodeExecutionError(f"Cache invalidation failed: {str(e)}")

    async def _ensure_backend(self, kwargs: Dict[str, Any]):
        """Ensure cache backend is initialized."""
        backend = kwargs.get("backend", "memory")

        if backend in ["redis", "hybrid"]:
            if not REDIS_AVAILABLE:
                if backend == "redis":
                    raise NodeExecutionError(
                        "Redis is not available. Install with: pip install redis"
                    )
                else:
                    self.logger.warning("Redis not available, using memory cache only")
                    return

            redis_url = kwargs.get("redis_url", "redis://localhost:6379")

            # Only recreate Redis client if the current one is problematic
            if self._redis_client:
                try:
                    # Test if current connection is still valid
                    await asyncio.wait_for(self._redis_client.ping(), timeout=1.0)
                    # Connection is good, reuse it
                    return
                except:
                    # Connection is bad, close and recreate
                    try:
                        await self._redis_client.aclose()
                    except:
                        pass  # Ignore errors when closing old client

            try:
                self._redis_client = redis.from_url(redis_url)
                # Test connection with proper error handling
                try:
                    await asyncio.wait_for(self._redis_client.ping(), timeout=2.0)
                    self.logger.debug(
                        f"Fresh Redis connection established to {redis_url}"
                    )
                except (asyncio.TimeoutError, RuntimeError) as e:
                    if "Event loop is closed" in str(e):
                        # Event loop issue - create new client without ping test
                        self._redis_client = redis.from_url(redis_url)
                        self.logger.debug(
                            "Created Redis client without ping test due to event loop issue"
                        )
                    else:
                        raise
            except Exception as e:
                if backend == "redis":
                    raise NodeExecutionError(f"Failed to connect to Redis: {str(e)}")
                else:
                    self.logger.warning(
                        f"Redis connection failed, using memory cache: {str(e)}"
                    )
                    self._redis_client = None

    def _build_key(self, key: str, namespace: str = "") -> str:
        """Build a namespaced cache key."""
        if namespace:
            return f"{namespace}:{key}"
        return key

    async def _invalidate_single(
        self, strategy: InvalidationStrategy, kwargs: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Invalidate a single cache key."""
        key = kwargs.get("key")
        keys = kwargs.get("keys", [])
        namespace = kwargs.get("namespace", "")

        if not key and not keys:
            raise ValueError(
                "Either 'key' or 'keys' must be provided for single invalidation"
            )

        target_keys = [key] if key else keys
        full_keys = [self._build_key(k, namespace) for k in target_keys]

        invalidated_keys = []
        cascade_keys = []

        for full_key in full_keys:
            if not dry_run:
                success = await self._execute_invalidation(strategy, full_key, kwargs)
                if success:
                    invalidated_keys.append(full_key)

                    # Handle cascade if strategy supports it
                    if strategy == InvalidationStrategy.CASCADE:
                        cascaded = await self._cascade_invalidate(full_key, kwargs)
                        cascade_keys.extend(cascaded)
            else:
                # Dry run - just collect what would be invalidated
                invalidated_keys.append(full_key)
                if strategy == InvalidationStrategy.CASCADE:
                    cascaded = await self._get_cascade_keys(full_key, kwargs)
                    cascade_keys.extend(cascaded)

        return {
            "invalidated_count": len(invalidated_keys),
            "cascade_count": len(cascade_keys),
            "invalidated_keys": invalidated_keys,
            "cascade_keys": cascade_keys,
        }

    async def _invalidate_pattern(
        self, strategy: InvalidationStrategy, kwargs: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Invalidate cache keys matching a pattern."""
        pattern = kwargs.get("pattern")
        namespace = kwargs.get("namespace", "")
        backend = kwargs.get("backend", "memory")
        batch_size = kwargs.get("batch_size", 1000)

        if not pattern:
            raise ValueError("Pattern must be provided for pattern invalidation")

        if namespace:
            pattern = f"{namespace}:{pattern}"

        # Find matching keys
        matching_keys = await self._find_matching_keys(pattern, backend)

        invalidated_keys = []
        cascade_keys = []

        # Process in batches
        for i in range(0, len(matching_keys), batch_size):
            batch = matching_keys[i : i + batch_size]

            for key in batch:
                if not dry_run:
                    success = await self._execute_invalidation(strategy, key, kwargs)
                    if success:
                        invalidated_keys.append(key)

                        if strategy == InvalidationStrategy.CASCADE:
                            cascaded = await self._cascade_invalidate(key, kwargs)
                            cascade_keys.extend(cascaded)
                else:
                    invalidated_keys.append(key)
                    if strategy == InvalidationStrategy.CASCADE:
                        cascaded = await self._get_cascade_keys(key, kwargs)
                        cascade_keys.extend(cascaded)

        return {
            "invalidated_count": len(invalidated_keys),
            "cascade_count": len(cascade_keys),
            "invalidated_keys": invalidated_keys,
            "cascade_keys": cascade_keys,
        }

    async def _invalidate_tag(
        self, strategy: InvalidationStrategy, kwargs: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Invalidate cache keys associated with specific tags."""
        tags = kwargs.get("tags", [])

        if not tags:
            raise ValueError("Tags must be provided for tag-based invalidation")

        invalidated_keys = []
        cascade_keys = []

        for tag in tags:
            # Get keys associated with this tag
            tag_keys = self._tag_registry.get(tag, set())

            for key in tag_keys:
                if not dry_run:
                    success = await self._execute_invalidation(strategy, key, kwargs)
                    if success:
                        invalidated_keys.append(key)

                        if strategy == InvalidationStrategy.CASCADE:
                            cascaded = await self._cascade_invalidate(key, kwargs)
                            cascade_keys.extend(cascaded)
                else:
                    invalidated_keys.append(key)
                    if strategy == InvalidationStrategy.CASCADE:
                        cascaded = await self._get_cascade_keys(key, kwargs)
                        cascade_keys.extend(cascaded)

        return {
            "invalidated_count": len(invalidated_keys),
            "cascade_count": len(cascade_keys),
            "invalidated_keys": invalidated_keys,
            "cascade_keys": cascade_keys,
        }

    async def _invalidate_dependency(
        self, strategy: InvalidationStrategy, kwargs: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Invalidate cache keys based on dependency relationships."""
        source_key = kwargs.get("source_key")
        dependencies = kwargs.get("dependencies", [])

        if not source_key and not dependencies:
            raise ValueError("Either source_key or dependencies must be provided")

        invalidated_keys = []
        cascade_keys = []

        # Get all dependent keys
        dependent_keys = set(dependencies) if dependencies else set()

        if source_key:
            # Add dependencies from dependency graph
            dependent_keys.update(self._dependency_graph.get(source_key, set()))

        for key in dependent_keys:
            if not dry_run:
                success = await self._execute_invalidation(strategy, key, kwargs)
                if success:
                    invalidated_keys.append(key)

                    if strategy == InvalidationStrategy.CASCADE:
                        cascaded = await self._cascade_invalidate(key, kwargs)
                        cascade_keys.extend(cascaded)
            else:
                invalidated_keys.append(key)
                if strategy == InvalidationStrategy.CASCADE:
                    cascaded = await self._get_cascade_keys(key, kwargs)
                    cascade_keys.extend(cascaded)

        return {
            "invalidated_count": len(invalidated_keys),
            "cascade_count": len(cascade_keys),
            "invalidated_keys": invalidated_keys,
            "cascade_keys": cascade_keys,
        }

    async def _invalidate_time_based(
        self, strategy: InvalidationStrategy, kwargs: Dict[str, Any], dry_run: bool
    ) -> Dict[str, Any]:
        """Invalidate cache keys based on age."""
        max_age = kwargs.get("max_age")
        backend = kwargs.get("backend", "memory")

        if not max_age:
            raise ValueError("max_age must be provided for time-based invalidation")

        cutoff_time = time.time() - max_age
        invalidated_keys = []
        cascade_keys = []

        # Find expired keys based on backend
        if backend == "redis" and self._redis_client:
            # Redis doesn't directly support age-based queries
            # We would need to store metadata or use Redis streams
            self.logger.warning(
                "Time-based invalidation not fully supported for Redis backend"
            )

        elif backend in ["memory", "hybrid"]:
            # Check memory cache for old entries
            expired_keys = []
            for key, value in self._memory_cache.items():
                if isinstance(value, dict) and "_cache_timestamp" in value:
                    if value["_cache_timestamp"] < cutoff_time:
                        expired_keys.append(key)

            for key in expired_keys:
                if not dry_run:
                    success = await self._execute_invalidation(strategy, key, kwargs)
                    if success:
                        invalidated_keys.append(key)

                        if strategy == InvalidationStrategy.CASCADE:
                            cascaded = await self._cascade_invalidate(key, kwargs)
                            cascade_keys.extend(cascaded)
                else:
                    invalidated_keys.append(key)
                    if strategy == InvalidationStrategy.CASCADE:
                        cascaded = await self._get_cascade_keys(key, kwargs)
                        cascade_keys.extend(cascaded)

        return {
            "invalidated_count": len(invalidated_keys),
            "cascade_count": len(cascade_keys),
            "invalidated_keys": invalidated_keys,
            "cascade_keys": cascade_keys,
        }

    async def _execute_invalidation(
        self, strategy: InvalidationStrategy, key: str, kwargs: Dict[str, Any]
    ) -> bool:
        """Execute the actual invalidation based on strategy."""
        backend = kwargs.get("backend", "memory")

        try:
            if strategy == InvalidationStrategy.IMMEDIATE:
                # Delete immediately
                if backend == "redis" and self._redis_client:
                    await self._redis_client.delete(key)
                elif backend in ["memory", "hybrid"]:
                    self._memory_cache.pop(key, None)
                    if backend == "hybrid" and self._redis_client:
                        await self._redis_client.delete(key)

            elif strategy == InvalidationStrategy.LAZY:
                # Mark for lazy deletion (could set a special flag)
                if backend == "redis" and self._redis_client:
                    await self._redis_client.set(f"{key}:_lazy_delete", "1", ex=1)
                elif backend in ["memory", "hybrid"]:
                    if key in self._memory_cache:
                        # Replace with lazy deletion marker
                        self._memory_cache[key] = {
                            "_lazy_delete": True,
                            "_timestamp": time.time(),
                        }

            elif strategy == InvalidationStrategy.TTL_REFRESH:
                # Reset TTL to expire soon
                new_ttl = kwargs.get("new_ttl", 1)  # 1 second
                if backend == "redis" and self._redis_client:
                    await self._redis_client.expire(key, new_ttl)
                elif backend in ["memory", "hybrid"]:
                    if key in self._memory_cache and isinstance(
                        self._memory_cache[key], dict
                    ):
                        self._memory_cache[key]["_cache_ttl"] = new_ttl
                        self._memory_cache[key]["_cache_timestamp"] = time.time()

            elif strategy == InvalidationStrategy.CASCADE:
                # CASCADE strategy should also immediately delete the key
                # The cascade dependencies will be handled separately
                if backend == "redis" and self._redis_client:
                    await self._redis_client.delete(key)
                elif backend in ["memory", "hybrid"]:
                    self._memory_cache.pop(key, None)
                    if backend == "hybrid" and self._redis_client:
                        await self._redis_client.delete(key)

            return True

        except Exception as e:
            self.logger.error(f"Failed to invalidate key '{key}': {str(e)}")
            return False

    async def _cascade_invalidate(self, key: str, kwargs: Dict[str, Any]) -> List[str]:
        """Perform cascade invalidation for dependent keys."""
        cascade_patterns = kwargs.get("cascade_patterns", [])
        cascaded_keys = []

        # Invalidate based on cascade patterns
        for pattern in cascade_patterns:
            # Replace placeholder with actual key
            resolved_pattern = pattern.replace("{key}", key)
            matching_keys = await self._find_matching_keys(
                resolved_pattern, kwargs.get("backend", "memory")
            )

            for match_key in matching_keys:
                success = await self._execute_invalidation(
                    InvalidationStrategy.IMMEDIATE, match_key, kwargs
                )
                if success:
                    cascaded_keys.append(match_key)

        # Invalidate dependencies from dependency graph
        dependent_keys = self._dependency_graph.get(key, set())
        for dep_key in dependent_keys:
            success = await self._execute_invalidation(
                InvalidationStrategy.IMMEDIATE, dep_key, kwargs
            )
            if success:
                cascaded_keys.append(dep_key)

        return cascaded_keys

    async def _get_cascade_keys(self, key: str, kwargs: Dict[str, Any]) -> List[str]:
        """Get keys that would be cascade invalidated (for dry run)."""
        cascade_patterns = kwargs.get("cascade_patterns", [])
        cascade_keys = []

        for pattern in cascade_patterns:
            resolved_pattern = pattern.replace("{key}", key)
            matching_keys = await self._find_matching_keys(
                resolved_pattern, kwargs.get("backend", "memory")
            )
            cascade_keys.extend(matching_keys)

        # Add dependencies
        cascade_keys.extend(self._dependency_graph.get(key, set()))

        return cascade_keys

    async def _find_matching_keys(self, pattern: str, backend: str) -> List[str]:
        """Find cache keys matching a pattern."""
        matching_keys = []

        try:
            if backend == "redis" and self._redis_client:
                # Use Redis KEYS command (note: this can be expensive)
                redis_keys = await self._redis_client.keys(pattern)
                matching_keys.extend(
                    [k.decode() if isinstance(k, bytes) else k for k in redis_keys]
                )

            elif backend in ["memory", "hybrid"]:
                # Use fnmatch for memory cache
                for key in self._memory_cache.keys():
                    if fnmatch.fnmatch(key, pattern):
                        matching_keys.append(key)

                # Also check Redis for hybrid
                if backend == "hybrid" and self._redis_client:
                    redis_keys = await self._redis_client.keys(pattern)
                    for k in redis_keys:
                        decoded_key = k.decode() if isinstance(k, bytes) else k
                        if decoded_key not in matching_keys:
                            matching_keys.append(decoded_key)

        except Exception as e:
            self.logger.error(
                f"Failed to find matching keys for pattern '{pattern}': {str(e)}"
            )

        return matching_keys

    def _log_invalidation(
        self,
        strategy: InvalidationStrategy,
        scope: InvalidationScope,
        result: Dict[str, Any],
        reason: str,
        kwargs: Dict[str, Any],
    ):
        """Log invalidation operation."""
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "strategy": strategy.value,
            "scope": scope.value,
            "reason": reason,
            "invalidated_count": result.get("invalidated_count", 0),
            "cascade_count": result.get("cascade_count", 0),
            "source_key": kwargs.get("source_key"),
            "pattern": kwargs.get("pattern"),
            "tags": kwargs.get("tags"),
        }

        self._invalidation_log.append(log_entry)

        # Keep only last 1000 log entries
        if len(self._invalidation_log) > 1000:
            self._invalidation_log = self._invalidation_log[-1000:]

    def _update_stats(self, result: Dict[str, Any]):
        """Update invalidation statistics."""
        self._stats["invalidations"] += result.get("invalidated_count", 0)
        self._stats["cascade_invalidations"] += result.get("cascade_count", 0)

        if result.get("invalidated_count", 0) > 0:
            self._stats["pattern_matches"] += 1

    def add_tag(self, key: str, tag: str):
        """Add a tag association for a cache key."""
        if tag not in self._tag_registry:
            self._tag_registry[tag] = set()
        self._tag_registry[tag].add(key)

    def remove_tag(self, key: str, tag: str):
        """Remove a tag association for a cache key."""
        if tag in self._tag_registry:
            self._tag_registry[tag].discard(key)
            if not self._tag_registry[tag]:
                del self._tag_registry[tag]

    def add_dependency(self, parent_key: str, dependent_key: str):
        """Add a dependency relationship."""
        if parent_key not in self._dependency_graph:
            self._dependency_graph[parent_key] = set()
        self._dependency_graph[parent_key].add(dependent_key)

    def remove_dependency(self, parent_key: str, dependent_key: str):
        """Remove a dependency relationship."""
        if parent_key in self._dependency_graph:
            self._dependency_graph[parent_key].discard(dependent_key)
            if not self._dependency_graph[parent_key]:
                del self._dependency_graph[parent_key]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        try:
            # Try to get current event loop
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return asyncio.run(self.async_run(**kwargs))
        else:
            # Event loop is running, schedule the coroutine
            import concurrent.futures
            import threading

            result_holder = {}
            exception_holder = {}

            def run_in_new_loop():
                try:
                    # Create a new event loop for this thread
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        result = new_loop.run_until_complete(self.async_run(**kwargs))
                        result_holder["result"] = result
                    finally:
                        new_loop.close()
                except Exception as e:
                    exception_holder["error"] = e

            thread = threading.Thread(target=run_in_new_loop)
            thread.start()
            thread.join()

            if "error" in exception_holder:
                raise exception_holder["error"]

            return result_holder["result"]
