"""
Cache Invalidation

Automatic cache invalidation patterns for DataFlow.

FIX: CACHE_INVALIDATION_BUG_REPORT.md
- Added async/sync detection for cache operations
- Added _enabled flag to skip invalidation when caching is disabled
- Handles both sync RedisCacheManager and async AsyncRedisCacheAdapter
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set

from dataflow.core.async_utils import async_safe_run  # Phase 6: Async-safe execution

from .redis_manager import RedisCacheManager

logger = logging.getLogger(__name__)


@dataclass
class InvalidationPattern:
    """Cache invalidation pattern definition."""

    model: str
    operation: str
    invalidates: List[str] = None
    invalidate_groups: List[str] = None
    condition: Optional[Callable[[Dict, Dict], bool]] = None
    use_ttl: bool = False
    ttl: Optional[int] = None

    def __post_init__(self):
        if self.invalidates is None:
            self.invalidates = []
        if self.invalidate_groups is None:
            self.invalidate_groups = []


class CacheInvalidator:
    """Manages cache invalidation patterns."""

    def __init__(self, cache_manager: RedisCacheManager, enabled: bool = True):
        """
        Initialize cache invalidator.

        Args:
            cache_manager: Redis cache manager instance
            enabled: Whether cache invalidation is enabled (default True)
                     FIX: CACHE_INVALIDATION_BUG_REPORT.md - Added to skip invalidation
                     when caching is disabled.
        """
        self.cache_manager = cache_manager
        self._enabled = enabled
        self.patterns: List[InvalidationPattern] = []
        self.groups: Dict[str, List[str]] = {}
        self._pre_hooks: List[Callable] = []
        self._post_hooks: List[Callable] = []
        self._metrics_enabled = False
        self._metrics: Dict[str, Any] = {
            "total_invalidations": 0,
            "by_model": {},
            "by_operation": {},
        }
        self._batch_mode = False
        self._batch_keys: Set[str] = set()
        self._current_model: Optional[str] = None

        # FIX: CACHE_INVALIDATION_BUG_REPORT.md - Detect if cache_manager is async
        # AsyncRedisCacheAdapter has async delete() and clear_pattern() methods
        self._is_async_cache = self._detect_async_cache()

    def _detect_async_cache(self) -> bool:
        """
        Detect if the cache manager uses async methods.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        AsyncRedisCacheAdapter has async delete() and clear_pattern() methods,
        which must be handled differently from sync RedisCacheManager.

        Returns:
            True if cache_manager has async methods
        """
        if self.cache_manager is None:
            return False

        # Check if delete or clear_pattern are coroutine functions
        delete_method = getattr(self.cache_manager, "delete", None)
        clear_pattern_method = getattr(self.cache_manager, "clear_pattern", None)

        is_async = False
        if delete_method is not None:
            is_async = asyncio.iscoroutinefunction(delete_method)
        if not is_async and clear_pattern_method is not None:
            is_async = asyncio.iscoroutinefunction(clear_pattern_method)

        if is_async:
            logger.debug(
                "CacheInvalidator: Detected async cache manager, "
                "will handle async methods properly"
            )
        return is_async

    def is_enabled(self) -> bool:
        """
        Check if cache invalidation is enabled.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        Returns False if caching is disabled, preventing unnecessary
        invalidation attempts.

        Returns:
            True if invalidation is enabled
        """
        if not self._enabled:
            return False

        # Also check if cache_manager can cache
        if hasattr(self.cache_manager, "can_cache"):
            can_cache = self.cache_manager.can_cache()
            # Handle async can_cache (shouldn't block since this is sync)
            if asyncio.iscoroutine(can_cache):
                # Don't await in sync context - assume enabled
                can_cache.close()  # Close the coroutine to avoid warnings
                return True
            return can_cache

        return True

    def register_pattern(self, pattern: InvalidationPattern):
        """
        Register an invalidation pattern.

        Args:
            pattern: Invalidation pattern to register
        """
        self.patterns.append(pattern)
        logger.info(
            f"Registered invalidation pattern for {pattern.model}.{pattern.operation}"
        )

    def define_group(self, group_name: str, patterns: List[str]):
        """
        Define an invalidation group.

        Args:
            group_name: Name of the group
            patterns: List of cache key patterns in the group
        """
        self.groups[group_name] = patterns
        logger.info(
            f"Defined invalidation group '{group_name}' with {len(patterns)} patterns"
        )

    def invalidate(
        self,
        model: str,
        operation: str,
        data: Dict[str, Any],
        old_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Invalidate caches based on model operation.

        Args:
            model: Model name
            operation: Operation performed (create, update, delete, etc.)
            data: New data
            old_data: Previous data (for updates)

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        - Added early exit when caching is disabled
        - Prevents "coroutine was never awaited" warnings
        """
        # FIX: CACHE_INVALIDATION_BUG_REPORT.md - Early exit if invalidation is disabled
        if not self.is_enabled():
            logger.debug(
                f"Cache invalidation skipped for {model}.{operation}: caching is disabled"
            )
            return

        # Set current model for pattern expansion
        self._current_model = model

        # Call pre-hooks
        for hook in self._pre_hooks:
            try:
                hook(model, operation, data)
            except Exception as e:
                logger.error(f"Pre-hook error: {e}")

        # Collect keys to invalidate
        keys_to_invalidate = set()
        patterns_to_clear = set()

        # Find matching patterns
        matching_patterns = self._find_matching_patterns(model, operation)

        for pattern in matching_patterns:
            # Check condition if present
            if pattern.condition and not pattern.condition(old_data or {}, data):
                continue

            # Don't invalidate if using TTL expiration
            if pattern.use_ttl:
                continue

            # Process direct invalidation patterns
            for invalidate_pattern in pattern.invalidates:
                expanded = self._expand_pattern(invalidate_pattern, data)
                if "*" in expanded:
                    patterns_to_clear.add(expanded)
                else:
                    keys_to_invalidate.add(expanded)

            # Process invalidation groups
            for group_name in pattern.invalidate_groups:
                if group_name in self.groups:
                    for group_pattern in self.groups[group_name]:
                        expanded = self._expand_pattern(group_pattern, data)
                        if "*" in expanded:
                            patterns_to_clear.add(expanded)
                        else:
                            keys_to_invalidate.add(expanded)

        # Perform invalidation
        if self._batch_mode:
            # In batch mode, collect keys
            self._batch_keys.update(keys_to_invalidate)
            self._batch_keys.update(patterns_to_clear)
        else:
            # Immediate invalidation
            cleared_count = self._perform_invalidation(
                keys_to_invalidate, patterns_to_clear
            )

            # Update metrics
            if self._metrics_enabled:
                self._update_metrics(model, operation, cleared_count)

            # Call post-hooks
            for hook in self._post_hooks:
                try:
                    hook(model, operation, data, cleared_count)
                except Exception as e:
                    logger.error(f"Post-hook error: {e}")

        # Clear current model
        self._current_model = None

    def batch(self):
        """Context manager for batch invalidation."""

        class BatchContext:
            def __init__(self, invalidator):
                self.invalidator = invalidator

            def __enter__(self):
                self.invalidator._batch_mode = True
                self.invalidator._batch_keys.clear()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.invalidator._batch_mode = False
                # Perform batch invalidation
                keys = [k for k in self.invalidator._batch_keys if "*" not in k]
                patterns = [p for p in self.invalidator._batch_keys if "*" in p]
                self.invalidator._perform_invalidation(set(keys), set(patterns))
                self.invalidator._batch_keys.clear()

        return BatchContext(self)

    def add_pre_hook(self, hook: Callable):
        """Add pre-invalidation hook."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable):
        """Add post-invalidation hook."""
        self._post_hooks.append(hook)

    def enable_metrics(self):
        """Enable metrics collection."""
        self._metrics_enabled = True

    def get_metrics(self) -> Dict[str, Any]:
        """Get invalidation metrics."""
        return self._metrics.copy()

    def invalidate_key(self, key: str) -> bool:
        """
        Invalidate a specific cache key.

        Args:
            key: Cache key to invalidate

        Returns:
            True if successful
        """
        try:
            result = self.cache_manager.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to invalidate key {key}: {e}")
            return False

    def invalidate_keys(self, keys: List[str]) -> int:
        """
        Invalidate multiple cache keys.

        Args:
            keys: List of cache keys to invalidate

        Returns:
            Number of keys actually deleted
        """
        try:
            return self.cache_manager.delete_many(keys)
        except Exception as e:
            logger.error(f"Failed to invalidate keys {keys}: {e}")
            return 0

    def key_exists(self, key: str) -> bool:
        """
        Check if a cache key exists.

        Args:
            key: Cache key to check

        Returns:
            True if key exists
        """
        try:
            return self.cache_manager.exists(key)
        except Exception as e:
            logger.error(f"Failed to check key existence {key}: {e}")
            return False

    def _find_matching_patterns(
        self, model: str, operation: str
    ) -> List[InvalidationPattern]:
        """Find patterns matching the model and operation."""
        matching = []

        for pattern in self.patterns:
            # Check model match (support wildcards)
            if pattern.model == "*" or pattern.model == model:
                # Check operation match (support wildcards)
                if pattern.operation == "*" or pattern.operation.endswith("*"):
                    # Wildcard operation
                    prefix = pattern.operation.rstrip("*")
                    if operation.startswith(prefix):
                        matching.append(pattern)
                elif pattern.operation == operation:
                    matching.append(pattern)

        return matching

    def _expand_pattern(self, pattern: str, data: Dict[str, Any]) -> str:
        """
        Expand pattern with data values.

        Args:
            pattern: Pattern with placeholders (e.g., "User:record:{id}")
            data: Data to use for expansion

        Returns:
            Expanded pattern
        """
        result = pattern

        # Replace placeholders
        for key, value in data.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        # Handle model placeholder
        if "{model}" in result:
            # Use the current model being invalidated
            model_name = getattr(self, "_current_model", "Unknown")
            result = result.replace("{model}", model_name)

        return result

    def _perform_invalidation(self, keys: Set[str], patterns: Set[str]) -> int:
        """
        Perform actual cache invalidation.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        - Handles both sync and async cache managers
        - Properly awaits async methods or runs them in event loop
        - Prevents "coroutine was never awaited" warnings

        Args:
            keys: Individual keys to delete
            patterns: Patterns to clear

        Returns:
            Total number of keys cleared
        """
        cleared = 0

        # FIX: If cache manager is async, use async invalidation
        if self._is_async_cache:
            return self._perform_invalidation_async_safe(keys, patterns)

        # Delete individual keys (sync path)
        if keys:
            keys_list = list(keys)
            # Call delete for each key individually to match test expectations
            for key in keys_list:
                try:
                    result = self.cache_manager.delete(key)
                    # FIX: Handle coroutine results (defensive)
                    if asyncio.iscoroutine(result):
                        result.close()  # Close unawaited coroutine to avoid warnings
                        logger.warning(
                            f"Async cache method returned from sync context for key {key}"
                        )
                        continue
                    cleared += result if isinstance(result, int) else 1
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {e}")

        # Clear patterns (sync path)
        for pattern in patterns:
            try:
                result = self.cache_manager.clear_pattern(pattern)
                # FIX: Handle coroutine results (defensive)
                if asyncio.iscoroutine(result):
                    result.close()  # Close unawaited coroutine to avoid warnings
                    logger.warning(
                        f"Async cache method returned from sync context for pattern {pattern}"
                    )
                    continue
                cleared += result if isinstance(result, int) else 1
            except Exception as e:
                logger.error(f"Failed to clear pattern {pattern}: {e}")

        logger.info(f"Invalidated {cleared} cache keys")
        return cleared

    def _perform_invalidation_async_safe(
        self, keys: Set[str], patterns: Set[str]
    ) -> int:
        """
        Perform cache invalidation with async-safe handling.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        This method handles async cache managers (like AsyncRedisCacheAdapter)
        by scheduling async operations in the event loop without blocking
        the sync context.

        Args:
            keys: Individual keys to delete
            patterns: Patterns to clear

        Returns:
            Total number of keys cleared (estimated - async ops may complete later)
        """
        # Phase 6: Use async_safe_run for proper event loop handling
        # This works in both sync and async contexts transparently
        try:
            return async_safe_run(self._perform_invalidation_async(keys, patterns))
        except Exception as e:
            # Log warning but don't fail the operation
            logger.warning(f"Cache invalidation failed: {e}. Operation will continue.")
            return 0

    async def _perform_invalidation_async(
        self, keys: Set[str], patterns: Set[str]
    ) -> int:
        """
        Perform cache invalidation asynchronously.

        FIX: CACHE_INVALIDATION_BUG_REPORT.md
        This async method properly awaits async cache operations.

        Args:
            keys: Individual keys to delete
            patterns: Patterns to clear

        Returns:
            Total number of keys cleared
        """
        cleared = 0

        # Delete individual keys
        if keys:
            for key in keys:
                try:
                    result = self.cache_manager.delete(key)
                    if asyncio.iscoroutine(result):
                        result = await result
                    cleared += result if isinstance(result, int) else 1
                except Exception as e:
                    logger.error(f"Failed to delete key {key}: {e}")

        # Clear patterns
        for pattern in patterns:
            try:
                result = self.cache_manager.clear_pattern(pattern)
                if asyncio.iscoroutine(result):
                    result = await result
                cleared += result if isinstance(result, int) else 1
            except Exception as e:
                logger.error(f"Failed to clear pattern {pattern}: {e}")

        logger.info(f"Async invalidated {cleared} cache keys")
        return cleared

    def _update_metrics(self, model: str, operation: str, cleared_count: int):
        """Update invalidation metrics."""
        self._metrics["total_invalidations"] += 1

        # By model
        if model not in self._metrics["by_model"]:
            self._metrics["by_model"][model] = 0
        self._metrics["by_model"][model] += 1

        # By operation
        if operation not in self._metrics["by_operation"]:
            self._metrics["by_operation"][operation] = 0
        self._metrics["by_operation"][operation] += 1
