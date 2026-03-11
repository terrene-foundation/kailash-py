"""
Performance benchmarks for DataFlow Schema Cache (ADR-001)

Tests performance improvements from schema cache implementation:
- Cache hit vs cache miss latency
- Multi-operation workflow speedup
- Cache overhead measurements
- Scalability with different cache sizes

These tests use real infrastructure (NO MOCKING per Tier 3 policy).
"""

import time

import pytest
from dataflow import DataFlow


@pytest.fixture
def db_with_cache():
    """DataFlow instance with schema cache enabled."""
    db = DataFlow(":memory:")  # SQLite in-memory for speed
    return db


@pytest.fixture
def db_without_cache():
    """DataFlow instance with schema cache disabled."""
    db = DataFlow(":memory:")
    # Disable cache by setting enabled=False
    db._schema_cache.enabled = False
    return db


class TestCacheHitPerformance:
    """Benchmark cache hit vs cache miss latency."""

    def test_cache_miss_latency(self, db_with_cache, benchmark):
        """Measure latency of cache MISS (first check)."""

        @db_with_cache.model
        class User:
            name: str
            email: str

        # Clear cache to force miss
        db_with_cache._schema_cache.clear()

        def check_table():
            return db_with_cache._schema_cache.is_table_ensured("User", ":memory:")

        # Benchmark: should be False (cache miss)
        result = benchmark(check_table)
        assert result is False

    def test_cache_hit_latency(self, db_with_cache, benchmark):
        """Measure latency of cache HIT (subsequent checks)."""

        @db_with_cache.model
        class User:
            name: str
            email: str

        # Warm up cache
        db_with_cache._schema_cache.mark_table_ensured("User", ":memory:")

        def check_table():
            return db_with_cache._schema_cache.is_table_ensured("User", ":memory:")

        # Benchmark: should be True (cache hit)
        result = benchmark(check_table)
        assert result is True

    def test_cache_speedup_ratio(self, db_with_cache):
        """Measure speedup ratio: cache hit vs cache miss."""

        @db_with_cache.model
        class User:
            name: str
            email: str

        # Measure cache MISS (first check)
        db_with_cache._schema_cache.clear()
        miss_start = time.perf_counter()
        for _ in range(100):
            db_with_cache._schema_cache.is_table_ensured("User", ":memory:")
        miss_time = time.perf_counter() - miss_start

        # Measure cache HIT (subsequent checks)
        db_with_cache._schema_cache.mark_table_ensured("User", ":memory:")
        hit_start = time.perf_counter()
        for _ in range(100):
            db_with_cache._schema_cache.is_table_ensured("User", ":memory:")
        hit_time = time.perf_counter() - hit_start

        # Calculate speedup
        speedup = miss_time / hit_time if hit_time > 0 else 0

        print("\\nCache Performance:")
        print(f"  Miss time (100 ops): {miss_time*1000:.2f}ms")
        print(f"  Hit time (100 ops): {hit_time*1000:.2f}ms")
        print(f"  Speedup ratio: {speedup:.1f}x")

        # Cache hits should be significantly faster
        assert speedup > 10, f"Expected >10x speedup, got {speedup:.1f}x"


class TestMultiOperationWorkflow:
    """Benchmark real-world multi-operation workflow speedup."""

    def test_workflow_without_cache(self, db_without_cache, benchmark):
        """Measure workflow performance WITHOUT cache."""

        @db_without_cache.model
        class Product:
            name: str
            price: float

        def run_operations():
            # Simulate 10 operations on same table
            for i in range(10):
                # Each operation would trigger table check
                db_without_cache._schema_cache.is_table_ensured("Product", ":memory:")

        benchmark(run_operations)

    def test_workflow_with_cache(self, db_with_cache, benchmark):
        """Measure workflow performance WITH cache."""

        @db_with_cache.model
        class Product:
            name: str
            price: float

        # Pre-warm cache
        db_with_cache._schema_cache.mark_table_ensured("Product", ":memory:")

        def run_operations():
            # Simulate 10 operations on same table
            for i in range(10):
                # Each operation hits cache
                db_with_cache._schema_cache.is_table_ensured("Product", ":memory:")

        benchmark(run_operations)

    def test_workflow_speedup_comparison(self, db_with_cache, db_without_cache):
        """Compare workflow execution time: cache ON vs cache OFF."""

        # Setup models
        @db_with_cache.model
        class Order:
            customer_name: str
            total: float

        @db_without_cache.model
        class Order:
            customer_name: str
            total: float

        # Warm up cache for cached version
        db_with_cache._schema_cache.mark_table_ensured("Order", ":memory:")

        # Measure WITHOUT cache (10 operations)
        no_cache_start = time.perf_counter()
        for _ in range(10):
            db_without_cache._schema_cache.is_table_ensured("Order", ":memory:")
        no_cache_time = time.perf_counter() - no_cache_start

        # Measure WITH cache (10 operations)
        cache_start = time.perf_counter()
        for _ in range(10):
            db_with_cache._schema_cache.is_table_ensured("Order", ":memory:")
        cache_time = time.perf_counter() - cache_start

        # Calculate improvement
        improvement = (
            ((no_cache_time - cache_time) / no_cache_time * 100)
            if no_cache_time > 0
            else 0
        )

        print("\\nWorkflow Performance (10 operations):")
        print(f"  Without cache: {no_cache_time*1000:.2f}ms")
        print(f"  With cache: {cache_time*1000:.2f}ms")
        print(f"  Improvement: {improvement:.1f}%")

        # Should see significant improvement
        assert improvement > 50, f"Expected >50% improvement, got {improvement:.1f}%"


class TestCacheOverhead:
    """Measure cache overhead and memory usage."""

    def test_cache_memory_overhead(self, db_with_cache):
        """Measure memory overhead of cached entries."""
        import sys

        cache = db_with_cache._schema_cache

        # Measure empty cache
        empty_size = sys.getsizeof(cache._cache)

        # Add 100 entries
        for i in range(100):
            cache.mark_table_ensured(f"Model{i}", ":memory:")

        # Measure cache with 100 entries
        full_size = sys.getsizeof(cache._cache)

        overhead_per_entry = (full_size - empty_size) / 100

        print("\\nCache Memory Overhead:")
        print(f"  Empty cache: {empty_size} bytes")
        print(f"  Cache with 100 entries: {full_size} bytes")
        print(f"  Overhead per entry: ~{overhead_per_entry:.1f} bytes")

        # Overhead should be reasonable (<1KB per entry)
        assert (
            overhead_per_entry < 1024
        ), f"Overhead too high: {overhead_per_entry} bytes"

    def test_cache_operation_overhead(self, db_with_cache, benchmark):
        """Measure overhead of cache operations."""

        cache = db_with_cache._schema_cache

        # Pre-populate cache
        for i in range(100):
            cache.mark_table_ensured(f"Model{i}", ":memory:")

        def cache_lookup():
            # Lookup in populated cache
            return cache.is_table_ensured("Model50", ":memory:")

        # Benchmark: should be sub-millisecond
        result = benchmark(cache_lookup)
        assert result is True


class TestCacheScalability:
    """Test cache performance with different sizes."""

    @pytest.mark.parametrize("cache_size", [10, 100, 1000])
    def test_scalability_with_size(self, db_with_cache, cache_size):
        """Measure cache performance degradation with size."""

        cache = db_with_cache._schema_cache

        # Populate cache to specified size
        for i in range(cache_size):
            cache.mark_table_ensured(f"Model{i}", ":memory:")

        # Measure lookup time
        start = time.perf_counter()
        for _ in range(100):
            # Lookup middle entry
            cache.is_table_ensured(f"Model{cache_size//2}", ":memory:")
        elapsed = time.perf_counter() - start

        print(f"\\nCache size {cache_size}: {elapsed*1000:.2f}ms for 100 lookups")

        # Lookups should remain fast even with large cache
        assert elapsed < 0.01, f"Lookups too slow: {elapsed*1000:.2f}ms"

    def test_lru_eviction_performance(self, db_with_cache):
        """Measure performance of LRU eviction."""

        cache = db_with_cache._schema_cache
        cache.max_cache_size = 100  # Set limit

        # Fill cache to limit
        for i in range(100):
            cache.mark_table_ensured(f"Model{i}", ":memory:")

        # Measure eviction (add 11 more to trigger eviction)
        start = time.perf_counter()
        for i in range(100, 111):
            cache.mark_table_ensured(f"Model{i}", ":memory:")
        eviction_time = time.perf_counter() - start

        print(f"\\nLRU Eviction Time (11 entries): {eviction_time*1000:.2f}ms")

        # Eviction should be fast (<10ms)
        assert eviction_time < 0.01, f"Eviction too slow: {eviction_time*1000:.2f}ms"


class TestConcurrentAccess:
    """Benchmark concurrent cache access (thread safety)."""

    def test_concurrent_reads(self, db_with_cache):
        """Measure performance of concurrent cache reads."""
        import concurrent.futures

        cache = db_with_cache._schema_cache

        # Pre-populate cache
        for i in range(10):
            cache.mark_table_ensured(f"Model{i}", ":memory:")

        def read_cache():
            for _ in range(100):
                cache.is_table_ensured("Model5", ":memory:")

        # Measure concurrent reads (10 threads)
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_cache) for _ in range(10)]
            concurrent.futures.wait(futures)
        elapsed = time.perf_counter() - start

        print(f"\\nConcurrent Reads (10 threads × 100 ops): {elapsed*1000:.2f}ms")

        # Should handle concurrent access efficiently
        assert elapsed < 0.1, f"Concurrent access too slow: {elapsed*1000:.2f}ms"


# Performance benchmark summary
def test_performance_summary(db_with_cache):
    """
    Generate performance summary report.

    Expected improvements from cache (per ADR-001):
    - First operation: ~1500ms (migration check)
    - Subsequent operations: ~1ms (cache hit)
    - Improvement: 91-99% faster for multi-operation workflows
    """
    cache = db_with_cache._schema_cache

    # Test scenario: 10 operations on same model
    @db_with_cache.model
    class TestModel:
        field1: str
        field2: int

    # Clear metrics
    cache._hits = 0
    cache._misses = 0

    # Warm cache
    cache.mark_table_ensured("TestModel", ":memory:")

    # Simulate 10 operations
    for _ in range(10):
        cache.is_table_ensured("TestModel", ":memory:")

    # Get metrics
    metrics = cache.get_metrics()

    print("\\n" + "=" * 60)
    print("SCHEMA CACHE PERFORMANCE SUMMARY (ADR-001)")
    print("=" * 60)
    print(f"Cache Status: {'Enabled' if metrics['enabled'] else 'Disabled'}")
    print(f"Cache Size: {metrics['cache_size']} tables")
    print(f"Hit Rate: {metrics['hit_rate_percent']}%")
    print(f"Total Hits: {metrics['hits']}")
    print(f"Total Misses: {metrics['misses']}")
    print("=" * 60)

    # Validate performance expectations
    assert (
        metrics["hit_rate_percent"] > 90
    ), "Hit rate should be >90% for repeated operations"
    assert metrics["hits"] >= 10, "Should have at least 10 cache hits"
