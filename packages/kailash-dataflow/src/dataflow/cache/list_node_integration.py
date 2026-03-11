"""
Cache Integration for ListNode

Integrates Redis caching with DataFlow ListNode operations
for automatic query result caching and cache invalidation.
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from .invalidation import CacheInvalidator, InvalidationPattern
from .key_generator import CacheKeyGenerator
from .redis_manager import RedisCacheManager

logger = logging.getLogger(__name__)


class ListNodeCacheIntegration:
    """Integrates caching with ListNode operations."""

    def __init__(
        self,
        cache_manager: RedisCacheManager,
        key_generator: CacheKeyGenerator,
        invalidator: CacheInvalidator,
    ):
        """
        Initialize cache integration.

        Args:
            cache_manager: Redis cache manager
            key_generator: Cache key generator
            invalidator: Cache invalidator
        """
        self.cache_manager = cache_manager
        self.key_generator = key_generator
        self.invalidator = invalidator
        self._setup_invalidation_patterns()

    async def execute_with_cache(
        self,
        model_name: str,
        query: str,
        params: List[Any],
        executor_func: callable,
        cache_enabled: bool = True,
        cache_ttl: Optional[int] = None,
        cache_key_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute query with caching support.

        Args:
            model_name: Name of the model
            query: SQL query string
            params: Query parameters
            executor_func: Function to execute query if cache miss
            cache_enabled: Whether to use cache
            cache_ttl: TTL for cache entry
            cache_key_override: Override cache key

        Returns:
            Query result with cache metadata
        """
        # Generate cache key
        if cache_key_override:
            cache_key = cache_key_override
        else:
            cache_key = self.key_generator.generate_key(model_name, query, params)

        # Check if caching is enabled and possible
        # FIX: Properly await async cache.can_cache() method
        if not cache_enabled or not await self.cache_manager.can_cache():
            # Execute directly without caching
            import asyncio

            if asyncio.iscoroutinefunction(executor_func):
                result = await executor_func()
            else:
                result = executor_func()
            return self._add_cache_metadata(
                result, cache_key, hit=False, source="direct"
            )

        # Try to get from cache first
        # FIX: Properly await async cache.get() method
        cached_result = await self.cache_manager.get(cache_key)
        if cached_result is not None:
            # Cache hit - return cached result with metadata
            logger.debug(f"Cache hit for key: {cache_key}")
            return self._add_cache_metadata(
                cached_result, cache_key, hit=True, source="cache"
            )

        # Cache miss - execute query
        logger.debug(f"Cache miss for key: {cache_key}")
        import asyncio

        if asyncio.iscoroutinefunction(executor_func):
            result = await executor_func()
        else:
            result = executor_func()

        # Cache the result
        # FIX: Properly await async cache.set() method
        if result is not None:
            cache_success = await self.cache_manager.set(cache_key, result, cache_ttl)
            if cache_success:
                logger.debug(f"Cached result for key: {cache_key}")
            else:
                logger.warning(f"Failed to cache result for key: {cache_key}")

        return self._add_cache_metadata(result, cache_key, hit=False, source="database")

    def invalidate_model_cache(
        self, model_name: str, operation: str, data: Dict[str, Any]
    ):
        """
        Invalidate cache for model operations.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        - Added can_cache() check to skip invalidation when caching is disabled
        - Provides defense in depth against async/sync issues

        Args:
            model_name: Name of the model
            operation: Operation performed (create, update, delete, etc.)
            data: Data involved in the operation
        """
        # FIX: CACHE_INVALIDATION_BUG_REPORT.md - Check if caching is enabled
        # Skip invalidation if cache_manager cannot cache (caching disabled)
        if hasattr(self.cache_manager, "can_cache"):
            import asyncio

            can_cache_result = self.cache_manager.can_cache()
            # Handle async can_cache() method
            if asyncio.iscoroutine(can_cache_result):
                # Don't block - close coroutine and assume cache check passed
                # The CacheInvalidator will handle the async case properly
                can_cache_result.close()
            elif not can_cache_result:
                logger.debug(
                    f"Cache invalidation skipped for {model_name}.{operation}: "
                    "caching is disabled"
                )
                return

        self.invalidator.invalidate(model_name, operation, data)

    def warmup_cache(
        self, model_name: str, common_queries: List[Tuple[str, List[Any]]]
    ):
        """
        Warmup cache with common queries.

        Args:
            model_name: Name of the model
            common_queries: List of (query, params) tuples
        """
        warmup_data = []
        for query, params in common_queries:
            cache_key = self.key_generator.generate_key(model_name, query, params)
            # This would typically be populated by running the queries
            # For now, we'll just generate the keys
            warmup_data.append((cache_key, None))

        if warmup_data:
            self.cache_manager.warmup(warmup_data)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self.cache_manager.get_stats()

    def _add_cache_metadata(
        self, result: Dict[str, Any], cache_key: str, hit: bool, source: str
    ) -> Dict[str, Any]:
        """
        Add cache metadata to result.

        Args:
            result: Original result
            cache_key: Cache key used
            hit: Whether this was a cache hit
            source: Source of the result (cache, database, direct)

        Returns:
            Result with cache metadata
        """
        if result is None:
            result = {}

        # Add cache metadata
        result["_cache"] = {
            "key": cache_key,
            "hit": hit,
            "source": source,
            "timestamp": time.time(),
        }

        return result

    def _setup_invalidation_patterns(self):
        """Setup default invalidation patterns for common operations."""
        # Create patterns for common CRUD operations
        create_pattern = InvalidationPattern(
            model="*",  # Apply to all models
            operation="create",
            invalidates=["{model}:list:*", "{model}:count:*"],
        )

        update_pattern = InvalidationPattern(
            model="*",
            operation="update",
            invalidates=["{model}:record:{id}", "{model}:list:*"],
        )

        delete_pattern = InvalidationPattern(
            model="*",
            operation="delete",
            invalidates=["{model}:record:{id}", "{model}:list:*", "{model}:count:*"],
        )

        bulk_create_pattern = InvalidationPattern(
            model="*",
            operation="bulk_create",
            invalidates=["{model}:list:*", "{model}:count:*"],
        )

        bulk_update_pattern = InvalidationPattern(
            model="*", operation="bulk_update", invalidates=["{model}:list:*"]
        )

        bulk_delete_pattern = InvalidationPattern(
            model="*",
            operation="bulk_delete",
            invalidates=["{model}:list:*", "{model}:count:*"],
        )

        # Register patterns
        patterns = [
            create_pattern,
            update_pattern,
            delete_pattern,
            bulk_create_pattern,
            bulk_update_pattern,
            bulk_delete_pattern,
        ]

        for pattern in patterns:
            self.invalidator.register_pattern(pattern)


class CacheableListNode:
    """Mixin class to add caching capabilities to ListNode."""

    def __init__(self, cache_integration: Optional[ListNodeCacheIntegration] = None):
        """
        Initialize cacheable list node.

        Args:
            cache_integration: Cache integration instance
        """
        self.cache_integration = cache_integration

    def execute_with_cache(
        self,
        model_name: str,
        query: str,
        params: List[Any],
        executor_func: callable,
        cache_enabled: bool = True,
        cache_ttl: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute query with caching if integration is available.

        Args:
            model_name: Name of the model
            query: SQL query string
            params: Query parameters
            executor_func: Function to execute query
            cache_enabled: Whether to use cache
            cache_ttl: TTL for cache entry

        Returns:
            Query result
        """
        if self.cache_integration and cache_enabled:
            return self.cache_integration.execute_with_cache(
                model_name, query, params, executor_func, cache_enabled, cache_ttl
            )
        else:
            # Execute directly without caching
            return executor_func()

    def invalidate_cache(self, model_name: str, operation: str, data: Dict[str, Any]):
        """
        Invalidate cache if integration is available.

        Args:
            model_name: Name of the model
            operation: Operation performed
            data: Data involved in the operation
        """
        if self.cache_integration:
            self.cache_integration.invalidate_model_cache(model_name, operation, data)


def create_cache_integration(
    cache_manager: RedisCacheManager,
    key_generator: CacheKeyGenerator,
    invalidator: CacheInvalidator,
) -> ListNodeCacheIntegration:
    """
    Create cache integration instance.

    Args:
        cache_manager: Redis cache manager
        key_generator: Cache key generator
        invalidator: Cache invalidator

    Returns:
        Cache integration instance
    """
    return ListNodeCacheIntegration(cache_manager, key_generator, invalidator)
