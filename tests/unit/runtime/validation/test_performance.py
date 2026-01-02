"""
Unit tests for validation performance optimization.

Tests Task 4.3: Performance Optimization
- Validation caching with LRU and TTL
- Lazy evaluation for deferred validation
- Batch processing for multiple validations
- Performance monitoring and metrics
- Resource cleanup and optimization
"""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from kailash.runtime.validation.performance import (
    BatchValidator,
    LazyValidator,
    LRUCache,
    PerformanceMetrics,
    PerformanceOptimizer,
    ValidationCache,
    get_performance_optimizer,
    reset_performance_optimizer,
)
from kailash.workflow.type_inference import CoercionRule, TypeCompatibilityResult


class TestPerformanceMetrics:
    """Test performance metrics tracking."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = PerformanceMetrics()

        assert metrics.total_validations == 0
        assert metrics.total_time_ms == 0.0
        assert metrics.cache_hits == 0
        assert metrics.cache_misses == 0
        assert metrics.avg_validation_time_ms == 0.0
        assert metrics.max_validation_time_ms == 0.0
        assert metrics.min_validation_time_ms == float("inf")

    def test_update_validation_time(self):
        """Test validation time tracking."""
        metrics = PerformanceMetrics()

        # Add some validation times
        metrics.update_validation_time(10.0, "test_validation_1")
        metrics.update_validation_time(20.0, "test_validation_2")
        metrics.update_validation_time(5.0, "test_validation_3")

        assert metrics.total_validations == 3
        assert metrics.total_time_ms == 35.0
        assert metrics.avg_validation_time_ms == 35.0 / 3
        assert metrics.max_validation_time_ms == 20.0
        assert metrics.min_validation_time_ms == 5.0

    def test_slow_validation_tracking(self):
        """Test tracking of slow validations."""
        metrics = PerformanceMetrics()

        # Add normal validation
        metrics.update_validation_time(10.0, "normal_validation")
        assert len(metrics.slow_validations) == 0

        # Add slow validation (>50ms)
        metrics.update_validation_time(75.0, "slow_validation")
        assert len(metrics.slow_validations) == 1
        assert metrics.slow_validations[0] == ("slow_validation", 75.0)

    def test_cache_stats_update(self):
        """Test cache statistics updates."""
        metrics = PerformanceMetrics()

        metrics.update_cache_stats(hits=80, misses=20, size=100, memory_kb=5.5)

        assert metrics.cache_hits == 80
        assert metrics.cache_misses == 20
        assert metrics.cache_size == 100
        assert metrics.cache_memory_kb == 5.5
        assert metrics.cache_hit_ratio == 0.8


class TestLRUCache:
    """Test LRU cache implementation."""

    def test_cache_basic_operations(self):
        """Test basic cache operations."""
        cache = LRUCache(max_size=3)

        # Test put and get
        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") == "value2"
        assert cache.get("nonexistent") is None

    def test_cache_lru_eviction(self):
        """Test LRU eviction policy."""
        cache = LRUCache(max_size=2)

        # Fill cache
        cache.put("key1", "value1")
        cache.put("key2", "value2")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key3, should evict key2 (least recently used)
        cache.put("key3", "value3")

        assert cache.get("key1") == "value1"  # Still present
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Newly added

    def test_cache_ttl_expiration(self):
        """Test TTL-based expiration."""
        cache = LRUCache(max_size=10, ttl_seconds=0.1)  # Very short TTL for testing

        # Add item
        cache.put("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(0.15)  # Just over the TTL

        # Should be expired
        assert cache.get("key1") is None

    def test_cache_statistics(self):
        """Test cache statistics."""
        cache = LRUCache(max_size=10)

        # Test hits and misses
        cache.put("key1", "value1")

        cache.get("key1")  # Hit
        cache.get("key2")  # Miss
        cache.get("key1")  # Hit

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_ratio"] == 2 / 3
        assert stats["size"] == 1

    def test_cache_clear(self):
        """Test cache clearing."""
        cache = LRUCache(max_size=10)

        cache.put("key1", "value1")
        cache.put("key2", "value2")

        assert cache.get_stats()["size"] == 2

        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestValidationCache:
    """Test validation cache system."""

    def test_compatibility_caching(self):
        """Test compatibility result caching."""
        cache = ValidationCache(max_size=100)

        # Create mock result
        result = TypeCompatibilityResult(
            is_compatible=True, confidence=0.9, coercion_rule=CoercionRule.INT_TO_FLOAT
        )

        # Cache and retrieve
        cache.cache_compatibility_result(int, float, True, result)
        cached_result = cache.get_compatibility_result(int, float, True)

        assert cached_result is not None
        assert cached_result.is_compatible is True
        assert cached_result.confidence == 0.9
        assert cached_result.coercion_rule == CoercionRule.INT_TO_FLOAT

        # Test cache miss
        missing_result = cache.get_compatibility_result(str, int, False)
        assert missing_result is None

    def test_connection_caching(self):
        """Test connection result caching."""
        cache = ValidationCache(max_size=100)

        # Mock connection result
        from kailash.workflow.type_inference import (
            ConnectionInferenceResult,
            TypeCompatibilityResult,
        )

        compatibility = TypeCompatibilityResult(is_compatible=True, confidence=1.0)
        result = ConnectionInferenceResult(
            source_type=str,
            target_type=str,
            compatibility=compatibility,
            suggested_fixes=[],
        )

        mapping = {"output": "input"}

        # Cache and retrieve
        cache.cache_connection_result("node1", "node2", mapping, result)
        cached_result = cache.get_connection_result("node1", "node2", mapping)

        assert cached_result is not None
        assert cached_result.is_compatible is True
        assert cached_result.source_type == str
        assert cached_result.target_type == str

    def test_schema_caching(self):
        """Test schema validation caching."""
        cache = ValidationCache(max_size=100)

        # Cache schema validation result
        cache.cache_schema_validation("schema_hash_123", "data_hash_456", True)

        # Retrieve
        result = cache.get_schema_validation("schema_hash_123", "data_hash_456")
        assert result is True

        # Test miss
        missing = cache.get_schema_validation("unknown", "unknown")
        assert missing is None

    def test_cache_statistics(self):
        """Test cache statistics aggregation."""
        cache = ValidationCache(max_size=100)

        # Add some entries
        result = TypeCompatibilityResult(is_compatible=True, confidence=1.0)
        cache.cache_compatibility_result(int, str, True, result)
        cache.cache_schema_validation("hash1", "hash2", True)

        stats = cache.get_stats()

        assert "compatibility_cache" in stats
        assert "connection_cache" in stats
        assert "schema_cache" in stats
        assert "total_size" in stats
        assert "total_memory_kb" in stats

        assert stats["total_size"] >= 2  # At least our 2 entries


class TestLazyValidator:
    """Test lazy validation system."""

    def test_defer_validation(self):
        """Test deferring validation."""
        cache = ValidationCache()
        lazy_validator = LazyValidator(cache)

        # Mock validation function
        def mock_validation(x, y):
            return x + y

        # Defer validation
        validation_id = lazy_validator.defer_validation(
            "test_validation", mock_validation, 5, 10
        )

        assert validation_id == "test_validation"
        assert validation_id in lazy_validator._pending_validations

    def test_get_validation_result(self):
        """Test getting deferred validation result."""
        cache = ValidationCache()
        lazy_validator = LazyValidator(cache)

        # Mock validation function
        def mock_validation(x, y):
            return x * y

        # Defer and execute
        lazy_validator.defer_validation("multiply", mock_validation, 3, 4)
        result = lazy_validator.get_validation_result("multiply")

        assert result == 12
        assert (
            "multiply" not in lazy_validator._pending_validations
        )  # Should be cleaned up

    def test_cleanup_expired(self):
        """Test cleanup of expired validations."""
        cache = ValidationCache()
        lazy_validator = LazyValidator(cache)

        # Add validation
        lazy_validator.defer_validation("test", lambda: None)

        # Manually set old timestamp
        lazy_validator._pending_validations["test"]["created_at"] = time.time() - 400

        # Cleanup
        cleaned = lazy_validator.cleanup_expired(max_age_seconds=300)

        assert cleaned == 1
        assert "test" not in lazy_validator._pending_validations


class TestBatchValidator:
    """Test batch validation system."""

    def test_add_validation(self):
        """Test adding validations to batch."""
        cache = ValidationCache()
        batch_validator = BatchValidator(cache, batch_size=3)

        # Add validations
        batch_validator.add_validation(
            "val1", "compatibility", source_type=str, target_type=int
        )
        batch_validator.add_validation(
            "val2", "connection", source_node="n1", target_node="n2", mapping={}
        )

        assert len(batch_validator._batch_queue) == 2

    def test_auto_batch_processing(self):
        """Test automatic batch processing when full."""
        cache = ValidationCache()
        batch_validator = BatchValidator(cache, batch_size=2)

        # Mock cache to return results
        mock_result = TypeCompatibilityResult(is_compatible=True, confidence=1.0)
        cache.cache_compatibility_result(str, int, True, mock_result)

        # Add validations (should trigger processing when batch_size reached)
        batch_validator.add_validation(
            "val1",
            "compatibility",
            source_type=str,
            target_type=int,
            allow_coercion=True,
        )
        batch_validator.add_validation(
            "val2",
            "compatibility",
            source_type=int,
            target_type=str,
            allow_coercion=True,
        )

        # Queue should be empty after auto-processing
        assert len(batch_validator._batch_queue) == 0

        # Results should be available
        result = batch_validator.get_result("val1")
        assert result is not None

    def test_manual_flush(self):
        """Test manual batch processing."""
        cache = ValidationCache()
        batch_validator = BatchValidator(cache, batch_size=10)  # Large batch size

        # Add validation
        batch_validator.add_validation(
            "val1",
            "compatibility",
            source_type=str,
            target_type=int,
            allow_coercion=True,
        )

        # Manually flush
        results = batch_validator.flush()

        assert len(batch_validator._batch_queue) == 0
        assert "val1" in results


class TestPerformanceOptimizer:
    """Test performance optimizer coordination."""

    def test_optimizer_initialization(self):
        """Test optimizer initialization."""
        optimizer = PerformanceOptimizer(cache_size=1000, batch_size=25)

        assert optimizer.cache is not None
        assert optimizer.lazy_validator is not None
        assert optimizer.batch_validator is not None
        assert optimizer.metrics is not None
        assert optimizer.enable_caching is True

    def test_workflow_optimization_recommendations(self):
        """Test workflow optimization recommendations."""
        optimizer = PerformanceOptimizer()

        # Simple workflow
        simple_workflow = {
            "nodes": [{"id": "n1"}, {"id": "n2"}],
            "connections": [{"from": "n1", "to": "n2"}],
        }

        recommendations = optimizer.optimize_validation_pipeline(simple_workflow)

        assert "cache_configuration" in recommendations
        assert "batch_settings" in recommendations
        assert "lazy_evaluation" in recommendations
        assert "performance_warnings" in recommendations

        # Complex workflow
        complex_workflow = {
            "nodes": [{"id": f"n{i}"} for i in range(60)],
            "connections": [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(59)],
        }

        complex_recommendations = optimizer.optimize_validation_pipeline(
            complex_workflow
        )

        # Should have different recommendations for complex workflow
        assert len(complex_recommendations["performance_warnings"]) > 0
        assert complex_recommendations["batch_settings"]["enable"] is True

    def test_performance_report(self):
        """Test performance report generation."""
        optimizer = PerformanceOptimizer()

        # Add some metrics
        optimizer.metrics.update_validation_time(15.0, "test_validation")
        optimizer.metrics.update_cache_stats(100, 20, 50, 2.5)

        report = optimizer.get_performance_report()

        assert "validation_metrics" in report
        assert "cache_performance" in report
        assert "bottlenecks" in report
        assert "optimization_status" in report

        # Check specific values
        assert report["validation_metrics"]["total_validations"] == 1
        assert report["validation_metrics"]["avg_time_ms"] == 15.0
        assert report["cache_performance"]["hit_ratio"] == 100 / 120

    def test_resource_cleanup(self):
        """Test resource cleanup."""
        optimizer = PerformanceOptimizer()

        # Add some resources to clean up
        optimizer.lazy_validator.defer_validation("old_validation", lambda: None)

        # Manually age the validation
        optimizer.lazy_validator._pending_validations["old_validation"][
            "created_at"
        ] = (time.time() - 400)

        # Cleanup
        cleanup_stats = optimizer.cleanup_resources()

        assert "expired_lazy_validations" in cleanup_stats
        assert "cache_entries_before" in cleanup_stats
        assert "cache_entries_after" in cleanup_stats
        assert cleanup_stats["expired_lazy_validations"] == 1


class TestGlobalOptimizer:
    """Test global optimizer instance management."""

    def teardown_method(self):
        """Reset global optimizer after each test."""
        reset_performance_optimizer()

    def test_global_optimizer_singleton(self):
        """Test global optimizer singleton pattern."""
        optimizer1 = get_performance_optimizer()
        optimizer2 = get_performance_optimizer()

        assert optimizer1 is optimizer2
        assert isinstance(optimizer1, PerformanceOptimizer)

    def test_global_optimizer_reset(self):
        """Test global optimizer reset."""
        optimizer1 = get_performance_optimizer()

        reset_performance_optimizer()

        optimizer2 = get_performance_optimizer()

        assert optimizer1 is not optimizer2


class TestPerformanceIntegration:
    """Test integration of performance features."""

    def test_end_to_end_performance_optimization(self):
        """Test complete performance optimization flow."""
        optimizer = PerformanceOptimizer(cache_size=100, batch_size=5)

        # Simulate validation workload
        start_time = time.time()

        # Add some compatibility validations to batch
        for i in range(10):
            optimizer.batch_validator.add_validation(
                f"val_{i}",
                "compatibility",
                source_type=str if i % 2 == 0 else int,
                target_type=int if i % 2 == 0 else str,
                allow_coercion=True,
            )

        # Process remaining batch
        optimizer.batch_validator.flush()

        # Update metrics
        processing_time = (time.time() - start_time) * 1000
        optimizer.metrics.update_validation_time(processing_time, "batch_processing")

        # Generate report
        report = optimizer.get_performance_report()

        assert report["validation_metrics"]["total_validations"] == 1
        assert report["optimization_status"]["batch_processing_enabled"] is True

    def test_performance_under_load(self):
        """Test performance optimization under load."""
        optimizer = PerformanceOptimizer(cache_size=1000, batch_size=20)

        # Simulate high load
        validation_times = []

        for i in range(100):
            start = time.time()

            # Cache some results
            result = TypeCompatibilityResult(is_compatible=True, confidence=1.0)
            optimizer.cache.cache_compatibility_result(
                type(f"Type{i % 10}"), type(f"Type{(i+1) % 10}"), True, result
            )

            # Retrieve (should hit cache)
            cached = optimizer.cache.get_compatibility_result(
                type(f"Type{i % 10}"), type(f"Type{(i+1) % 10}"), True
            )

            validation_times.append((time.time() - start) * 1000)

        # Update metrics
        for validation_time in validation_times:
            optimizer.metrics.update_validation_time(validation_time, "load_test")

        # Check performance
        report = optimizer.get_performance_report()
        avg_time = report["validation_metrics"]["avg_time_ms"]

        # Should be fast due to caching
        assert avg_time < 50.0  # Less than 50ms average
