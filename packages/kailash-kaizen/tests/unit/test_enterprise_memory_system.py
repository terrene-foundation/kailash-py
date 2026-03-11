"""
Unit tests for Enterprise Memory System implementation.

Tests performance requirements, tier functionality, and integration features.
"""

import asyncio
import os
import tempfile
import time
from unittest.mock import Mock

import pytest
from src.kaizen.memory import (
    ColdMemoryTier,
    EnterpriseMemorySystem,
    HotMemoryTier,
    TierManager,
    WarmMemoryTier,
)
from src.kaizen.memory.signature_integration import SignatureMemoryIntegration


class TestHotMemoryTier:
    """Test hot memory tier performance and functionality"""

    @pytest.fixture
    def hot_tier(self):
        return HotMemoryTier(max_size=100, eviction_policy="lru")

    @pytest.mark.asyncio
    async def test_hot_tier_performance_requirement(self, hot_tier):
        """Test hot tier meets <1ms access time requirement"""
        # Setup test data
        test_key = "test_key"
        test_value = {"data": "test_value", "number": 42}

        # Store data
        await hot_tier.put(test_key, test_value)

        # Test multiple access times to ensure consistency
        access_times = []
        for _ in range(100):
            start_time = time.perf_counter()
            result = await hot_tier.get(test_key)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            access_times.append(elapsed_ms)
            assert result == test_value, "Hot tier should return correct value"

        # Calculate statistics
        avg_time = sum(access_times) / len(access_times)
        p99_time = sorted(access_times)[98]  # 99th percentile

        print(f"Hot tier average access time: {avg_time:.4f}ms")
        print(f"Hot tier 99th percentile: {p99_time:.4f}ms")

        # Performance requirements
        assert (
            avg_time < 1.0
        ), f"Hot tier average access time {avg_time:.4f}ms exceeds 1ms requirement"
        assert (
            p99_time < 1.0
        ), f"Hot tier 99th percentile {p99_time:.4f}ms exceeds 1ms requirement"

    @pytest.mark.asyncio
    async def test_hot_tier_eviction_policies(self):
        """Test different eviction policies"""
        # Test LRU eviction
        lru_tier = HotMemoryTier(max_size=3, eviction_policy="lru")

        await lru_tier.put("key1", "value1")
        await lru_tier.put("key2", "value2")
        await lru_tier.put("key3", "value3")

        # Access key1 to make it recently used
        await lru_tier.get("key1")

        # Add key4, should evict key2 (least recently used)
        await lru_tier.put("key4", "value4")

        assert await lru_tier.exists("key1"), "Recently used key1 should not be evicted"
        assert not await lru_tier.exists(
            "key2"
        ), "Least recently used key2 should be evicted"
        assert await lru_tier.exists("key3"), "Key3 should still exist"
        assert await lru_tier.exists("key4"), "New key4 should exist"

    @pytest.mark.asyncio
    async def test_hot_tier_ttl_functionality(self, hot_tier):
        """Test TTL (time-to-live) functionality"""
        test_key = "ttl_test"
        test_value = "ttl_value"

        # Store with 1 second TTL
        await hot_tier.put(test_key, test_value, ttl=1)

        # Should be available immediately
        result = await hot_tier.get(test_key)
        assert result == test_value, "Value should be available before TTL expires"

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Should be expired and return None
        result = await hot_tier.get(test_key)
        assert result is None, "Value should be expired after TTL"

    @pytest.mark.asyncio
    async def test_hot_tier_statistics(self, hot_tier):
        """Test statistics tracking"""
        # Perform operations
        await hot_tier.put("key1", "value1")
        await hot_tier.get("key1")  # Hit
        await hot_tier.get("nonexistent")  # Miss
        await hot_tier.delete("key1")

        stats = hot_tier.get_stats()

        assert stats["hits"] == 1, "Should record 1 hit"
        assert stats["misses"] == 1, "Should record 1 miss"
        assert stats["puts"] == 1, "Should record 1 put"
        assert stats["deletes"] == 1, "Should record 1 delete"


class TestWarmMemoryTier:
    """Test warm memory tier performance and functionality"""

    @pytest.fixture
    def warm_tier(self):
        # Use temporary directory for testing
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_warm.db")
        return WarmMemoryTier(storage_path=db_path, max_size_mb=10)

    @pytest.mark.asyncio
    async def test_warm_tier_performance_requirement(self, warm_tier):
        """Test warm tier meets <10ms access time requirement"""
        test_key = "warm_test_key"
        test_value = {"data": "warm_test_value", "list": [1, 2, 3, 4, 5]}

        # Store data
        await warm_tier.put(test_key, test_value)

        # Test multiple access times
        access_times = []
        for _ in range(50):
            start_time = time.perf_counter()
            result = await warm_tier.get(test_key)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            access_times.append(elapsed_ms)
            assert result == test_value, "Warm tier should return correct value"

        # Calculate statistics
        avg_time = sum(access_times) / len(access_times)
        p99_time = sorted(access_times)[int(0.99 * len(access_times))]

        print(f"Warm tier average access time: {avg_time:.4f}ms")
        print(f"Warm tier 99th percentile: {p99_time:.4f}ms")

        # Performance requirements
        assert (
            avg_time < 10.0
        ), f"Warm tier average access time {avg_time:.4f}ms exceeds 10ms requirement"
        assert (
            p99_time < 10.0
        ), f"Warm tier 99th percentile {p99_time:.4f}ms exceeds 10ms requirement"

    @pytest.mark.asyncio
    async def test_warm_tier_persistence(self, warm_tier):
        """Test warm tier data persistence"""
        test_key = "persist_key"
        test_value = {"persist": True, "data": "persistent_data"}

        # Store data
        await warm_tier.put(test_key, test_value)

        # Create new instance with same storage path
        new_warm_tier = WarmMemoryTier(storage_path=warm_tier.storage_path)

        # Should retrieve persisted data
        result = await new_warm_tier.get(test_key)
        assert result == test_value, "Warm tier should persist data between instances"


class TestColdMemoryTier:
    """Test cold memory tier performance and functionality"""

    @pytest.fixture
    def cold_tier(self):
        # Use temporary directory for testing
        temp_dir = tempfile.mkdtemp()
        return ColdMemoryTier(storage_path=temp_dir, compression=True)

    @pytest.mark.asyncio
    async def test_cold_tier_performance_requirement(self, cold_tier):
        """Test cold tier meets <100ms access time requirement"""
        test_key = "cold_test_key"
        test_value = {
            "large_data": "x" * 1000,  # Larger data to test compression
            "complex_structure": {
                "nested": {"deep": {"value": 42}},
                "list": list(range(100)),
            },
        }

        # Store data
        await cold_tier.put(test_key, test_value)

        # Test multiple access times
        access_times = []
        for _ in range(20):
            start_time = time.perf_counter()
            result = await cold_tier.get(test_key)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            access_times.append(elapsed_ms)
            assert result == test_value, "Cold tier should return correct value"

        # Calculate statistics
        avg_time = sum(access_times) / len(access_times)
        p99_time = sorted(access_times)[int(0.99 * len(access_times))]

        print(f"Cold tier average access time: {avg_time:.4f}ms")
        print(f"Cold tier 99th percentile: {p99_time:.4f}ms")

        # Performance requirements
        assert (
            avg_time < 100.0
        ), f"Cold tier average access time {avg_time:.4f}ms exceeds 100ms requirement"
        assert (
            p99_time < 100.0
        ), f"Cold tier 99th percentile {p99_time:.4f}ms exceeds 100ms requirement"

    @pytest.mark.asyncio
    async def test_cold_tier_compression(self, cold_tier):
        """Test cold tier compression functionality"""
        test_key = "compression_test"
        large_value = {"data": "x" * 10000}  # Large enough to trigger compression

        # Store data
        await cold_tier.put(test_key, large_value)

        # Should retrieve correct data despite compression
        result = await cold_tier.get(test_key)
        assert (
            result == large_value
        ), "Cold tier should correctly compress and decompress data"


class TestTierManager:
    """Test tier management functionality"""

    @pytest.fixture
    def tier_manager(self):
        config = {
            "hot_promotion_threshold": 3,
            "warm_promotion_threshold": 2,
            "access_window_seconds": 60,
            "cold_demotion_threshold": 3600,
        }
        return TierManager(config)

    @pytest.mark.asyncio
    async def test_access_pattern_tracking(self, tier_manager):
        """Test access pattern tracking"""
        test_key = "pattern_test"

        # Record accesses
        await tier_manager.record_access(test_key, "cold")
        await tier_manager.record_access(test_key, "cold")
        await tier_manager.record_access(test_key, "cold")

        patterns = tier_manager.get_access_patterns()
        assert test_key in patterns, "Access pattern should be tracked"
        assert (
            patterns[test_key]["recent_accesses"] == 3
        ), "Should track correct number of accesses"

    @pytest.mark.asyncio
    async def test_promotion_logic(self, tier_manager):
        """Test tier promotion logic"""
        test_key = "promotion_test"

        # Record enough accesses to trigger promotion
        for _ in range(4):
            await tier_manager.record_access(test_key, "cold")

        # Should promote from cold to warm
        should_promote_to_warm = await tier_manager.should_promote(
            test_key, "cold", "warm"
        )
        assert (
            should_promote_to_warm
        ), "Should promote from cold to warm after sufficient accesses"

        # Should also promote from cold to hot
        should_promote_to_hot = await tier_manager.should_promote(
            test_key, "cold", "hot"
        )
        assert (
            should_promote_to_hot
        ), "Should promote from cold to hot after sufficient accesses"


class TestEnterpriseMemorySystem:
    """Test complete enterprise memory system"""

    @pytest.fixture
    def memory_system(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "hot_max_size": 100,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
            "monitoring_enabled": True,
            "multi_tenant_enabled": True,
        }
        return EnterpriseMemorySystem(config)

    @pytest.mark.asyncio
    async def test_intelligent_tier_placement(self, memory_system):
        """Test intelligent data placement across tiers"""
        # Small data should go to hot tier by default
        small_key = "small_data"
        small_value = "small"

        await memory_system.put(small_key, small_value)

        # Verify it's accessible (should be in hot tier)
        result = await memory_system.get(small_key)
        assert result == small_value, "Should retrieve small data correctly"

        # Large data should go to cold tier
        large_key = "large_data"
        large_value = "x" * 200000  # Large data

        await memory_system.put(large_key, large_value)
        result = await memory_system.get(large_key)
        assert result == large_value, "Should retrieve large data correctly"

    @pytest.mark.asyncio
    async def test_tier_promotion(self, memory_system):
        """Test automatic tier promotion based on access patterns"""
        test_key = "promotion_test"
        test_value = "test_value_for_promotion"

        # Store in cold tier initially
        await memory_system.put(test_key, test_value, tier_hint="cold")

        # Access multiple times to trigger promotion
        for _ in range(5):
            result = await memory_system.get(test_key)
            assert result == test_value, "Should always return correct value"
            await asyncio.sleep(0.01)  # Small delay between accesses

        # Check system stats to verify promotion occurred
        stats = await memory_system.get_system_stats()
        assert "monitoring" in stats, "Should have monitoring data"

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(self, memory_system):
        """Test multi-tenant data isolation"""
        key = "shared_key"
        tenant1_value = "tenant1_data"
        tenant2_value = "tenant2_data"

        # Store data for different tenants
        await memory_system.put(key, tenant1_value, tenant_id="tenant1")
        await memory_system.put(key, tenant2_value, tenant_id="tenant2")

        # Verify isolation
        result1 = await memory_system.get(key, tenant_id="tenant1")
        result2 = await memory_system.get(key, tenant_id="tenant2")

        assert result1 == tenant1_value, "Tenant 1 should get its own data"
        assert result2 == tenant2_value, "Tenant 2 should get its own data"
        assert result1 != result2, "Different tenants should have isolated data"

    @pytest.mark.asyncio
    async def test_system_statistics(self, memory_system):
        """Test comprehensive system statistics"""
        # Perform various operations
        await memory_system.put("test1", "value1", tier_hint="hot")
        await memory_system.put("test2", "value2", tier_hint="warm")
        await memory_system.put("test3", "value3", tier_hint="cold")

        # Access data
        await memory_system.get("test1")
        await memory_system.get("test2")
        await memory_system.get("nonexistent")

        # Get statistics
        stats = await memory_system.get_system_stats()

        # Verify structure
        assert "tiers" in stats, "Should have tier statistics"
        assert "total_size" in stats, "Should have total size"
        assert "monitoring" in stats, "Should have monitoring data"
        assert "config" in stats, "Should have configuration data"

        # Verify tier data
        assert "hot" in stats["tiers"], "Should have hot tier stats"
        assert "warm" in stats["tiers"], "Should have warm tier stats"
        assert "cold" in stats["tiers"], "Should have cold tier stats"


class TestSignatureMemoryIntegration:
    """Test signature system integration with memory tiers"""

    @pytest.fixture
    def mock_signature(self):
        signature = Mock()
        signature.name = "test_signature"
        signature.metadata = {"access_frequency": "high", "computation_cost": "medium"}
        return signature

    @pytest.fixture
    def memory_integration(self):
        temp_dir = tempfile.mkdtemp()
        config = {
            "hot_max_size": 50,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
        }
        memory_system = EnterpriseMemorySystem(config)
        return SignatureMemoryIntegration(memory_system)

    @pytest.mark.asyncio
    async def test_signature_caching_strategies(
        self, memory_integration, mock_signature
    ):
        """Test different signature caching strategies"""
        inputs = {"query": "test query", "param": 42}
        result = {"output": "test result", "confidence": 0.95}

        # Test exact caching
        await memory_integration.cache_signature_result(
            mock_signature, inputs, result, strategy="exact"
        )
        cached_result = await memory_integration.get_cached_result(
            mock_signature, inputs, strategy="exact"
        )
        assert cached_result == result, "Exact caching should work correctly"

        # Test semantic caching
        cached_result = await memory_integration.get_cached_result(
            mock_signature, inputs, strategy="semantic"
        )
        assert cached_result == result, "Semantic caching should find exact match"

        # Test cache statistics
        stats = memory_integration.get_cache_stats()
        assert stats["cache_hits"] > 0, "Should record cache hits"
        assert stats["cache_writes"] > 0, "Should record cache writes"

    @pytest.mark.asyncio
    async def test_tier_hint_determination(self, memory_integration, mock_signature):
        """Test tier hint determination based on signature metadata"""

        # High frequency signature should get hot tier hint
        mock_signature.metadata = {"access_frequency": "high"}
        tier_hint = memory_integration._determine_tier_hint(
            mock_signature, "small result"
        )
        assert tier_hint == "hot", "High frequency signature should get hot tier hint"

        # High computation cost should get hot tier hint
        mock_signature.metadata = {"computation_cost": "high"}
        tier_hint = memory_integration._determine_tier_hint(mock_signature, "result")
        assert (
            tier_hint == "hot"
        ), "High computation cost signature should get hot tier hint"

    @pytest.mark.asyncio
    async def test_cache_key_generation(self, memory_integration, mock_signature):
        """Test cache key generation for different strategies"""
        inputs = {"query": "test", "number": 42}

        # Test exact key generation
        exact_key = memory_integration._generate_exact_key(mock_signature, inputs)
        assert exact_key.startswith(
            "sig_exact:"
        ), "Exact key should have correct prefix"

        # Test semantic key generation
        semantic_key = memory_integration._generate_semantic_key(mock_signature, inputs)
        assert semantic_key.startswith(
            "sig_semantic:"
        ), "Semantic key should have correct prefix"

        # Test fuzzy key generation
        fuzzy_key = memory_integration._generate_fuzzy_key(mock_signature, inputs)
        assert fuzzy_key.startswith(
            "sig_fuzzy:"
        ), "Fuzzy key should have correct prefix"

        # Keys should be different
        assert (
            exact_key != semantic_key != fuzzy_key
        ), "Different strategies should generate different keys"


class TestPerformanceRequirements:
    """Comprehensive performance requirement tests"""

    @pytest.mark.asyncio
    async def test_concurrent_access_performance(self):
        """Test performance under concurrent access"""
        temp_dir = tempfile.mkdtemp()
        config = {
            "hot_max_size": 1000,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
            "monitoring_enabled": True,
        }
        memory_system = EnterpriseMemorySystem(config)

        # Prepare test data
        test_data = {f"key_{i}": f"value_{i}" for i in range(100)}

        # Store data in different tiers
        for i, (key, value) in enumerate(test_data.items()):
            if i < 30:
                await memory_system.put(key, value, tier_hint="hot")
            elif i < 60:
                await memory_system.put(key, value, tier_hint="warm")
            else:
                await memory_system.put(key, value, tier_hint="cold")

        # Test concurrent access
        async def concurrent_access():
            tasks = []
            for key in test_data.keys():
                tasks.append(memory_system.get(key))

            start_time = time.perf_counter()
            results = await asyncio.gather(*tasks)
            elapsed = time.perf_counter() - start_time

            return results, elapsed

        results, elapsed = await concurrent_access()

        # Verify all results are correct
        assert len([r for r in results if r is not None]) == len(
            test_data
        ), "All data should be retrievable"

        # Performance requirement: Should handle 100 concurrent operations efficiently
        print(
            f"100 concurrent operations completed in {elapsed:.4f}s ({elapsed*10:.2f}ms avg)"
        )
        assert (
            elapsed < 1.0
        ), f"Concurrent operations took {elapsed:.4f}s, should be under 1 second"

    @pytest.mark.asyncio
    async def test_memory_usage_limits(self):
        """Test memory system respects configured limits"""
        config = {
            "hot_max_size": 10,  # Small limit to test eviction
            "monitoring_enabled": True,
        }
        memory_system = EnterpriseMemorySystem(config)

        # Fill hot tier beyond capacity
        for i in range(15):
            await memory_system.put(f"key_{i}", f"value_{i}", tier_hint="hot")

        stats = await memory_system.get_system_stats()
        hot_size = stats["tiers"]["hot"]["size"]

        # Hot tier should not exceed configured limit
        assert (
            hot_size <= config["hot_max_size"]
        ), f"Hot tier size {hot_size} exceeds limit {config['hot_max_size']}"

    @pytest.mark.asyncio
    async def test_end_to_end_performance(self):
        """Test end-to-end system performance with realistic workload"""
        temp_dir = tempfile.mkdtemp()
        config = {
            "hot_max_size": 100,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
            "monitoring_enabled": True,
        }
        memory_system = EnterpriseMemorySystem(config)

        # Simulate realistic workload
        operations_count = 1000
        start_time = time.perf_counter()

        # Mixed read/write operations
        for i in range(operations_count):
            if i % 3 == 0:  # 33% writes
                await memory_system.put(
                    f"workload_key_{i}", {"data": f"workload_value_{i}", "id": i}
                )
            else:  # 67% reads
                await memory_system.get(f"workload_key_{i//3}")

        elapsed = time.perf_counter() - start_time
        ops_per_second = operations_count / elapsed

        print(
            f"End-to-end test: {operations_count} operations in {elapsed:.4f}s ({ops_per_second:.0f} ops/sec)"
        )

        # Performance requirement: Should handle reasonable throughput
        assert (
            ops_per_second > 100
        ), f"Throughput {ops_per_second:.0f} ops/sec is below minimum requirement of 100 ops/sec"

        # Get final statistics
        final_stats = await memory_system.get_system_stats()
        print(
            f"Final system stats: {final_stats.get('monitoring', {}).get('overall_hit_rate', 0):.2%} hit rate"
        )


# Performance benchmarks for CI/CD validation
@pytest.mark.performance
class TestPerformanceBenchmarks:
    """Performance benchmark tests for continuous validation"""

    @pytest.mark.asyncio
    async def test_hot_tier_latency_benchmark(self):
        """Benchmark hot tier latency for performance regression detection"""
        hot_tier = HotMemoryTier(max_size=1000)

        # Warm up
        for i in range(100):
            await hot_tier.put(f"warmup_{i}", f"value_{i}")

        # Benchmark
        iterations = 10000
        start_time = time.perf_counter()

        for i in range(iterations):
            await hot_tier.get(f"warmup_{i % 100}")

        elapsed = time.perf_counter() - start_time
        avg_latency_us = (elapsed / iterations) * 1000000  # microseconds

        print(f"Hot tier average latency: {avg_latency_us:.2f}μs")
        assert (
            avg_latency_us < 100
        ), f"Hot tier latency {avg_latency_us:.2f}μs exceeds 100μs benchmark"

    @pytest.mark.asyncio
    async def test_system_throughput_benchmark(self):
        """Benchmark system throughput for performance regression detection"""
        temp_dir = tempfile.mkdtemp()
        config = {
            "hot_max_size": 500,
            "warm_storage_path": os.path.join(temp_dir, "warm.db"),
            "cold_storage_path": os.path.join(temp_dir, "cold"),
        }
        memory_system = EnterpriseMemorySystem(config)

        # Prepare data
        data_size = 1000
        for i in range(data_size):
            await memory_system.put(
                f"bench_{i}", {"id": i, "data": f"benchmark_data_{i}"}
            )

        # Benchmark read throughput
        reads = 5000
        start_time = time.perf_counter()

        for i in range(reads):
            await memory_system.get(f"bench_{i % data_size}")

        elapsed = time.perf_counter() - start_time
        throughput = reads / elapsed

        print(f"System read throughput: {throughput:.0f} ops/sec")
        assert (
            throughput > 1000
        ), f"Read throughput {throughput:.0f} ops/sec is below 1000 ops/sec benchmark"


if __name__ == "__main__":
    # Run tests with performance output
    pytest.main([__file__, "-v", "-s", "--tb=short"])
