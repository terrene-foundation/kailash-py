"""
Performance optimization for connection validation.

Provides advanced caching, lazy evaluation, batch validation,
and performance benchmarking for the validation system.
"""

import asyncio
import logging
import time
import weakref
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.workflow.type_inference import (
    ConnectionInferenceResult,
    TypeCompatibilityResult,
)

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for validation operations."""

    total_validations: int = 0
    total_time_ms: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_validation_time_ms: float = 0.0
    max_validation_time_ms: float = 0.0
    min_validation_time_ms: float = float("inf")

    # Cache performance
    cache_hit_ratio: float = 0.0
    cache_size: int = 0
    cache_memory_kb: float = 0.0

    # Bottlenecks
    slow_validations: List[Tuple[str, float]] = field(default_factory=list)
    expensive_connections: List[Tuple[str, str, float]] = field(default_factory=list)

    def update_validation_time(self, time_ms: float, operation: str = "unknown"):
        """Update validation timing statistics."""
        self.total_validations += 1
        self.total_time_ms += time_ms
        self.avg_validation_time_ms = self.total_time_ms / self.total_validations

        if time_ms > self.max_validation_time_ms:
            self.max_validation_time_ms = time_ms

        if time_ms < self.min_validation_time_ms:
            self.min_validation_time_ms = time_ms

        # Track slow validations (>50ms)
        if time_ms > 50.0:
            self.slow_validations.append((operation, time_ms))
            # Keep only recent slow validations
            if len(self.slow_validations) > 100:
                self.slow_validations = self.slow_validations[-100:]

    def update_cache_stats(self, hits: int, misses: int, size: int, memory_kb: float):
        """Update cache performance statistics."""
        self.cache_hits = hits
        self.cache_misses = misses
        self.cache_size = size
        self.cache_memory_kb = memory_kb

        total_requests = hits + misses
        self.cache_hit_ratio = hits / total_requests if total_requests > 0 else 0.0


class LRUCache:
    """Thread-safe LRU cache with memory management."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """Initialize LRU cache.

        Args:
            max_size: Maximum number of items to cache
            ttl_seconds: Time-to-live for cache entries
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict = OrderedDict()
        self._timestamps: Dict[Any, datetime] = {}
        self._lock = RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: Any) -> Optional[Any]:
        """Get item from cache."""
        with self._lock:
            # Check if key exists and is not expired
            if key in self._cache:
                timestamp = self._timestamps[key]
                if datetime.now(UTC) - timestamp < timedelta(seconds=self.ttl_seconds):
                    # Move to end (most recently used)
                    self._cache.move_to_end(key)
                    self._hits += 1
                    return self._cache[key]
                else:
                    # Expired, remove
                    del self._cache[key]
                    del self._timestamps[key]

            self._misses += 1
            return None

    def put(self, key: Any, value: Any) -> None:
        """Put item in cache."""
        with self._lock:
            # Update existing item
            if key in self._cache:
                self._cache[key] = value
                self._cache.move_to_end(key)
                self._timestamps[key] = datetime.now(UTC)
                return

            # Add new item
            self._cache[key] = value
            self._timestamps[key] = datetime.now(UTC)

            # Remove oldest if over capacity
            if len(self._cache) > self.max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                del self._timestamps[oldest_key]

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            self._hits = 0
            self._misses = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_ratio": self._hits / total_requests if total_requests > 0 else 0.0,
                "memory_estimate_kb": len(self._cache) * 0.1,  # Rough estimate
            }


class ValidationCache:
    """High-performance validation result cache."""

    def __init__(self, max_size: int = 5000, ttl_seconds: int = 3600):
        """Initialize validation cache.

        Args:
            max_size: Maximum cache entries
            ttl_seconds: Time-to-live for entries
        """
        self._compatibility_cache = LRUCache(max_size, ttl_seconds)
        self._connection_cache = LRUCache(max_size, ttl_seconds)
        self._schema_cache = LRUCache(
            max_size // 2, ttl_seconds * 2
        )  # Schemas change less often

    def get_compatibility_result(
        self, source_type: type, target_type: type, allow_coercion: bool
    ) -> Optional[TypeCompatibilityResult]:
        """Get cached compatibility result."""
        key = (source_type, target_type, allow_coercion)
        return self._compatibility_cache.get(key)

    def cache_compatibility_result(
        self,
        source_type: type,
        target_type: type,
        allow_coercion: bool,
        result: TypeCompatibilityResult,
    ) -> None:
        """Cache compatibility result."""
        key = (source_type, target_type, allow_coercion)
        self._compatibility_cache.put(key, result)

    def get_connection_result(
        self, source_node: str, target_node: str, mapping: Dict[str, str]
    ) -> Optional[ConnectionInferenceResult]:
        """Get cached connection validation result."""
        # Create hashable key from mapping
        mapping_key = tuple(sorted(mapping.items())) if mapping else ()
        key = (source_node, target_node, mapping_key)
        return self._connection_cache.get(key)

    def cache_connection_result(
        self,
        source_node: str,
        target_node: str,
        mapping: Dict[str, str],
        result: ConnectionInferenceResult,
    ) -> None:
        """Cache connection validation result."""
        mapping_key = tuple(sorted(mapping.items())) if mapping else ()
        key = (source_node, target_node, mapping_key)
        self._connection_cache.put(key, result)

    def get_schema_validation(self, schema_hash: str, data_hash: str) -> Optional[bool]:
        """Get cached schema validation result."""
        key = (schema_hash, data_hash)
        return self._schema_cache.get(key)

    def cache_schema_validation(
        self, schema_hash: str, data_hash: str, is_valid: bool
    ) -> None:
        """Cache schema validation result."""
        key = (schema_hash, data_hash)
        self._schema_cache.put(key, is_valid)

    def clear_all(self) -> None:
        """Clear all caches."""
        self._compatibility_cache.clear()
        self._connection_cache.clear()
        self._schema_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        compatibility_stats = self._compatibility_cache.get_stats()
        connection_stats = self._connection_cache.get_stats()
        schema_stats = self._schema_cache.get_stats()

        return {
            "compatibility_cache": compatibility_stats,
            "connection_cache": connection_stats,
            "schema_cache": schema_stats,
            "total_size": compatibility_stats["size"]
            + connection_stats["size"]
            + schema_stats["size"],
            "total_memory_kb": (
                compatibility_stats["memory_estimate_kb"]
                + connection_stats["memory_estimate_kb"]
                + schema_stats["memory_estimate_kb"]
            ),
        }


class LazyValidator:
    """Lazy evaluation for validation operations."""

    def __init__(self, cache: ValidationCache):
        """Initialize lazy validator.

        Args:
            cache: Validation cache instance
        """
        self.cache = cache
        self._pending_validations: Dict[str, Any] = {}
        self._validation_futures: Dict[str, asyncio.Future] = {}

    def defer_validation(
        self, validation_id: str, validation_func, *args, **kwargs
    ) -> str:
        """Defer validation until actually needed.

        Args:
            validation_id: Unique identifier for validation
            validation_func: Function to call for validation
            *args, **kwargs: Arguments for validation function

        Returns:
            Validation ID for later retrieval
        """
        self._pending_validations[validation_id] = {
            "func": validation_func,
            "args": args,
            "kwargs": kwargs,
            "created_at": time.time(),
        }
        return validation_id

    def get_validation_result(self, validation_id: str) -> Any:
        """Get validation result, executing if needed.

        Args:
            validation_id: Validation identifier

        Returns:
            Validation result
        """
        if validation_id not in self._pending_validations:
            raise ValueError(f"Unknown validation ID: {validation_id}")

        validation = self._pending_validations[validation_id]

        # Execute validation
        start_time = time.time()
        try:
            result = validation["func"](*validation["args"], **validation["kwargs"])
            execution_time = (time.time() - start_time) * 1000

            logger.debug(
                f"Lazy validation {validation_id} completed in {execution_time:.2f}ms"
            )
            return result
        finally:
            # Clean up
            del self._pending_validations[validation_id]

    def cleanup_expired(self, max_age_seconds: int = 300) -> int:
        """Clean up expired pending validations.

        Args:
            max_age_seconds: Maximum age for pending validations

        Returns:
            Number of cleaned up validations
        """
        current_time = time.time()
        expired_ids = [
            validation_id
            for validation_id, validation in self._pending_validations.items()
            if current_time - validation["created_at"] > max_age_seconds
        ]

        for validation_id in expired_ids:
            del self._pending_validations[validation_id]

        return len(expired_ids)


class BatchValidator:
    """Batch validation for improved performance."""

    def __init__(self, cache: ValidationCache, batch_size: int = 50):
        """Initialize batch validator.

        Args:
            cache: Validation cache instance
            batch_size: Number of validations to batch together
        """
        self.cache = cache
        self.batch_size = batch_size
        self._batch_queue: List[Dict[str, Any]] = []
        self._batch_results: Dict[str, Any] = {}

    def add_validation(
        self, validation_id: str, validation_type: str, **params
    ) -> None:
        """Add validation to batch queue.

        Args:
            validation_id: Unique identifier
            validation_type: Type of validation (compatibility, connection, schema)
            **params: Validation parameters
        """
        self._batch_queue.append(
            {
                "id": validation_id,
                "type": validation_type,
                "params": params,
                "added_at": time.time(),
            }
        )

        # Process batch if full
        if len(self._batch_queue) >= self.batch_size:
            self.process_batch()

    def process_batch(self) -> Dict[str, Any]:
        """Process all queued validations as a batch.

        Returns:
            Dictionary of validation results by ID
        """
        if not self._batch_queue:
            return {}

        start_time = time.time()
        batch = self._batch_queue.copy()
        self._batch_queue.clear()

        # Group by validation type for optimized processing
        by_type = defaultdict(list)
        for validation in batch:
            by_type[validation["type"]].append(validation)

        results = {}

        # Process each type in batch
        for validation_type, validations in by_type.items():
            if validation_type == "compatibility":
                results.update(self._process_compatibility_batch(validations))
            elif validation_type == "connection":
                results.update(self._process_connection_batch(validations))
            elif validation_type == "schema":
                results.update(self._process_schema_batch(validations))

        processing_time = (time.time() - start_time) * 1000
        logger.debug(
            f"Processed batch of {len(batch)} validations in {processing_time:.2f}ms"
        )

        self._batch_results.update(results)
        return results

    def _process_compatibility_batch(
        self, validations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process compatibility validations in batch."""
        results = {}

        # Check cache first for all validations
        for validation in validations:
            params = validation["params"]
            cached_result = self.cache.get_compatibility_result(
                params["source_type"], params["target_type"], params["allow_coercion"]
            )

            if cached_result:
                results[validation["id"]] = cached_result
            else:
                # Would need actual validation logic here
                # For now, indicate cache miss
                results[validation["id"]] = None

        return results

    def _process_connection_batch(
        self, validations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process connection validations in batch."""
        results = {}

        for validation in validations:
            params = validation["params"]
            cached_result = self.cache.get_connection_result(
                params["source_node"], params["target_node"], params["mapping"]
            )

            results[validation["id"]] = cached_result

        return results

    def _process_schema_batch(
        self, validations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Process schema validations in batch."""
        results = {}

        for validation in validations:
            params = validation["params"]
            cached_result = self.cache.get_schema_validation(
                params["schema_hash"], params["data_hash"]
            )

            results[validation["id"]] = cached_result

        return results

    def get_result(self, validation_id: str) -> Optional[Any]:
        """Get result for a specific validation."""
        return self._batch_results.get(validation_id)

    def flush(self) -> Dict[str, Any]:
        """Force process any remaining validations in queue."""
        return self.process_batch()


class PerformanceOptimizer:
    """Main performance optimization coordinator."""

    def __init__(self, cache_size: int = 5000, batch_size: int = 50):
        """Initialize performance optimizer.

        Args:
            cache_size: Size of validation cache
            batch_size: Batch size for validation operations
        """
        self.cache = ValidationCache(cache_size)
        self.lazy_validator = LazyValidator(self.cache)
        self.batch_validator = BatchValidator(self.cache, batch_size)
        self.metrics = PerformanceMetrics()

        # Optimization settings
        self.enable_caching = True
        self.enable_lazy_evaluation = True
        self.enable_batch_processing = True
        self.cache_cleanup_interval = 300  # 5 minutes

    def optimize_validation_pipeline(
        self, workflow_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Optimize validation pipeline for a workflow.

        Args:
            workflow_data: Workflow configuration

        Returns:
            Optimization recommendations
        """
        recommendations = {
            "cache_configuration": {},
            "batch_settings": {},
            "lazy_evaluation": {},
            "performance_warnings": [],
        }

        # Analyze workflow complexity
        node_count = len(workflow_data.get("nodes", []))
        connection_count = len(workflow_data.get("connections", []))

        # Cache size recommendations
        if connection_count > 100:
            recommendations["cache_configuration"]["size"] = min(
                10000, connection_count * 10
            )
            recommendations["cache_configuration"][
                "ttl"
            ] = 7200  # 2 hours for complex workflows
        else:
            recommendations["cache_configuration"]["size"] = 1000
            recommendations["cache_configuration"]["ttl"] = 3600  # 1 hour

        # Batch size recommendations
        if connection_count > 50:
            recommendations["batch_settings"]["size"] = min(100, connection_count // 2)
            recommendations["batch_settings"]["enable"] = True
        else:
            recommendations["batch_settings"]["size"] = 10
            recommendations["batch_settings"]["enable"] = False

        # Lazy evaluation recommendations
        recommendations["lazy_evaluation"]["enable"] = connection_count > 20

        # Performance warnings
        if connection_count > 200:
            recommendations["performance_warnings"].append(
                "Large number of connections detected. Consider workflow splitting."
            )

        if node_count > 50:
            recommendations["performance_warnings"].append(
                "Complex workflow detected. Enable all performance optimizations."
            )

        return recommendations

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report."""
        cache_stats = self.cache.get_stats()

        return {
            "validation_metrics": {
                "total_validations": self.metrics.total_validations,
                "avg_time_ms": self.metrics.avg_validation_time_ms,
                "max_time_ms": self.metrics.max_validation_time_ms,
                "min_time_ms": (
                    self.metrics.min_validation_time_ms
                    if self.metrics.min_validation_time_ms != float("inf")
                    else 0
                ),
            },
            "cache_performance": {
                "hit_ratio": self.metrics.cache_hit_ratio,
                "total_size": cache_stats["total_size"],
                "memory_usage_kb": cache_stats["total_memory_kb"],
            },
            "bottlenecks": {
                "slow_validations": self.metrics.slow_validations[-10:],  # Last 10
                "expensive_connections": self.metrics.expensive_connections[-10:],
            },
            "optimization_status": {
                "caching_enabled": self.enable_caching,
                "lazy_evaluation_enabled": self.enable_lazy_evaluation,
                "batch_processing_enabled": self.enable_batch_processing,
            },
        }

    def cleanup_resources(self) -> Dict[str, int]:
        """Clean up resources and return statistics."""
        cleanup_stats = {
            "expired_lazy_validations": self.lazy_validator.cleanup_expired(),
            "cache_entries_before": self.cache.get_stats()["total_size"],
        }

        # Optional: Clear old cache entries (could be more sophisticated)
        # For now, we rely on TTL in the cache implementation

        cleanup_stats["cache_entries_after"] = self.cache.get_stats()["total_size"]
        cleanup_stats["cache_entries_cleaned"] = (
            cleanup_stats["cache_entries_before"] - cleanup_stats["cache_entries_after"]
        )

        return cleanup_stats


# Global performance optimizer instance
_global_optimizer = None


def get_performance_optimizer() -> PerformanceOptimizer:
    """Get global performance optimizer instance."""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = PerformanceOptimizer()
    return _global_optimizer


def reset_performance_optimizer() -> None:
    """Reset global performance optimizer (for testing)."""
    global _global_optimizer
    _global_optimizer = None
