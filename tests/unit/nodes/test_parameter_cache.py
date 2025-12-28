"""Unit tests for parameter resolution caching system."""

import os
import threading
import time
from typing import Any, Dict

import pytest
from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import NodeValidationError


class CacheTestNode(Node):
    """Test node with various parameter configurations."""

    def __init__(self, **kwargs):
        # Set parameter configuration before super init
        self.use_aliases = kwargs.pop("use_aliases", False)
        self.use_auto_map = kwargs.pop("use_auto_map", False)
        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        params = {
            "param_a": NodeParameter(
                name="param_a",
                type=int,
                required=True,
                default=1,
            ),
            "param_b": NodeParameter(
                name="param_b",
                type=int,
                required=True,
                default=2,
            ),
            "param_c": NodeParameter(
                name="param_c",
                type=int,
                required=True,
                default=3,
            ),
        }

        if self.use_aliases:
            params["param_a"].workflow_alias = "alias_a"
            params["param_b"].workflow_alias = "alias_b"

        if self.use_auto_map:
            params["param_a"].auto_map_from = ["alt_a", "opt_a"]
            params["param_b"].auto_map_from = ["alt_b", "opt_b"]

        return params

    def run(self, **kwargs) -> Dict[str, Any]:
        return {
            "sum": kwargs.get("param_a", 0)
            + kwargs.get("param_b", 0)
            + kwargs.get("param_c", 0)
        }


class TestParameterCache:
    """Test parameter resolution caching functionality."""

    def test_basic_cache_operation(self):
        """Test basic cache hit/miss behavior."""
        node = CacheTestNode()

        # Clear cache
        node.clear_cache()

        # First call - cache miss
        inputs1 = {"param_a": 10, "param_b": 20, "param_c": 30}
        result1 = node.validate_inputs(**inputs1)
        assert result1["param_a"] == 10
        assert result1["param_b"] == 20
        assert result1["param_c"] == 30

        stats = node.get_cache_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1
        assert stats["size"] == 1

        # Second call with same pattern - cache hit
        inputs2 = {"param_a": 15, "param_b": 25, "param_c": 35}
        result2 = node.validate_inputs(**inputs2)
        assert result2["param_a"] == 15
        assert result2["param_b"] == 25
        assert result2["param_c"] == 35

        stats = node.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_cache_key_generation(self):
        """Test that cache keys ignore special parameters and values."""
        node = CacheTestNode()
        node.clear_cache()

        # Call with context (special parameter)
        inputs1 = {"param_a": 1, "param_b": 2, "context": {"run_id": "123"}}
        node.validate_inputs(**inputs1)

        # Call with different context but same params - should hit cache
        inputs2 = {"param_a": 5, "param_b": 6, "context": {"run_id": "456"}}
        node.validate_inputs(**inputs2)

        stats = node.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_parameter_value_collision_fix(self):
        """Test that the cache correctly handles parameters with same values."""
        node = CacheTestNode()
        node.clear_cache()

        # Test the original bug scenario: a=3, b=8, c=3
        inputs = {"param_a": 3, "param_b": 8, "param_c": 3}
        result = node.validate_inputs(**inputs)

        # Verify each parameter gets its correct value
        assert result["param_a"] == 3
        assert result["param_b"] == 8
        assert result["param_c"] == 3  # This was returning wrong value in bug

        # Test with all same values
        inputs2 = {"param_a": 5, "param_b": 5, "param_c": 5}
        result2 = node.validate_inputs(**inputs2)
        assert result2["param_a"] == 5
        assert result2["param_b"] == 5
        assert result2["param_c"] == 5

    def test_lru_eviction(self):
        """Test LRU cache eviction behavior."""
        # Create node with small cache
        os.environ["KAILASH_PARAM_CACHE_SIZE"] = "3"
        node = CacheTestNode()
        node.clear_cache()

        # Fill cache with 3 patterns
        patterns = [
            {"param_a": 1},
            {"param_b": 2},
            {"param_c": 3},
        ]

        for pattern in patterns:
            node.validate_inputs(**pattern)

        stats = node.get_cache_stats()
        assert stats["size"] == 3
        assert stats["evictions"] == 0

        # Add 4th pattern - should evict oldest
        node.validate_inputs(param_a=1, param_b=2)

        stats = node.get_cache_stats()
        assert stats["size"] == 3
        assert stats["evictions"] == 1

        # Access first pattern again - should be cache miss
        node.validate_inputs(param_a=1)
        stats = node.get_cache_stats()
        assert stats["misses"] == 5  # 4 initial + 1 miss

        # Cleanup
        del os.environ["KAILASH_PARAM_CACHE_SIZE"]

    def test_cache_with_aliases(self):
        """Test cache with workflow aliases."""
        node = CacheTestNode(use_aliases=True)
        node.clear_cache()

        # Use alias
        inputs1 = {"alias_a": 10, "alias_b": 20, "param_c": 30}
        result1 = node.validate_inputs(**inputs1)
        assert result1["param_a"] == 10  # Resolved from alias
        assert result1["param_b"] == 20  # Resolved from alias
        assert result1["param_c"] == 30

        # Same pattern with different values - should hit cache
        inputs2 = {"alias_a": 15, "alias_b": 25, "param_c": 35}
        result2 = node.validate_inputs(**inputs2)
        assert result2["param_a"] == 15
        assert result2["param_b"] == 25
        assert result2["param_c"] == 35

        stats = node.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_with_auto_mapping(self):
        """Test cache with auto-mapped parameters."""
        node = CacheTestNode(use_auto_map=True)
        node.clear_cache()

        # Use auto-mapped alternatives
        inputs1 = {"alt_a": 10, "opt_b": 20, "param_c": 30}
        result1 = node.validate_inputs(**inputs1)
        assert result1["param_a"] == 10  # Resolved from alt_a
        assert result1["param_b"] == 20  # Resolved from opt_b
        assert result1["param_c"] == 30

        # Same pattern - should hit cache
        inputs2 = {"alt_a": 15, "opt_b": 25, "param_c": 35}
        result2 = node.validate_inputs(**inputs2)
        assert result2["param_a"] == 15
        assert result2["param_b"] == 25
        assert result2["param_c"] == 35

        stats = node.get_cache_stats()
        assert stats["hits"] == 1

    def test_cache_disabled(self):
        """Test behavior when cache is disabled."""
        os.environ["KAILASH_DISABLE_PARAM_CACHE"] = "true"
        node = CacheTestNode()

        # Multiple calls with same pattern
        for i in range(3):
            result = node.validate_inputs(param_a=i, param_b=i + 1, param_c=i + 2)
            assert result["param_a"] == i
            assert result["param_b"] == i + 1
            assert result["param_c"] == i + 2

        # Stats should show no activity
        stats = node.get_cache_stats()
        assert stats["enabled"] is False
        assert stats["hits"] == 0
        assert stats["misses"] == 0

        # Cleanup
        del os.environ["KAILASH_DISABLE_PARAM_CACHE"]

    def test_thread_safety(self):
        """Test cache thread safety with concurrent access."""
        node = CacheTestNode()
        node.clear_cache()

        errors = []
        iterations_per_thread = 100

        def worker(thread_id):
            try:
                for i in range(iterations_per_thread):
                    # Mix of patterns to test concurrent access
                    if i % 3 == 0:
                        inputs = {"param_a": thread_id, "param_b": i}
                    elif i % 3 == 1:
                        inputs = {"param_b": thread_id, "param_c": i}
                    else:
                        inputs = {"param_a": thread_id, "param_c": i}

                    result = node.validate_inputs(**inputs)
                    # Verify correctness
                    for key, value in inputs.items():
                        if key in result:
                            assert result[key] == value
            except Exception as e:
                errors.append(e)

        # Run multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        # Wait for completion
        for t in threads:
            t.join()

        # Check no errors
        assert len(errors) == 0

        # Verify cache stats are reasonable
        stats = node.get_cache_stats()
        total_calls = stats["hits"] + stats["misses"]
        assert total_calls == 5 * iterations_per_thread
        assert stats["size"] <= node._cache_max_size

    def test_cache_warmup(self):
        """Test cache warming functionality."""
        node = CacheTestNode()
        node.clear_cache()

        # Warm cache with known patterns
        patterns = [
            {"param_a": 1, "param_b": 2, "param_c": 3},
            {"param_a": 10, "param_b": 20},
            {"param_b": 100, "param_c": 200},
        ]

        node.warm_cache(patterns)

        # Verify patterns are cached
        stats = node.get_cache_stats()
        assert stats["size"] == 3

        # Using warmed patterns should hit cache
        result = node.validate_inputs(param_a=5, param_b=6, param_c=7)
        stats = node.get_cache_stats()
        assert stats["hits"] == 1

    def test_performance_improvement(self):
        """Test that caching actually improves performance."""

        # Create node with many parameters
        class ComplexNode(Node):
            def get_parameters(self):
                return {
                    f"param_{i}": NodeParameter(
                        name=f"param_{i}",
                        type=int,
                        required=False,
                        default=i,
                        workflow_alias=f"alias_{i}",
                        auto_map_from=[f"alt_{i}", f"opt_{i}"],
                    )
                    for i in range(20)
                }

            def run(self, **kwargs):
                return {"result": sum(kwargs.values())}

        node = ComplexNode()
        node.clear_cache()

        # Test inputs using various mappings
        test_inputs = {
            "param_0": 10,
            "alias_5": 20,
            "alt_10": 30,
            "opt_15": 40,
        }

        # Measure time without cache (first call)
        start = time.time()
        for _ in range(100):
            node.validate_inputs(**test_inputs)
        first_100_time = time.time() - start

        # Measure time with cache (next 100 calls)
        start = time.time()
        for _ in range(100):
            node.validate_inputs(**test_inputs)
        next_100_time = time.time() - start

        # Cache should provide speedup
        stats = node.get_cache_stats()
        assert stats["hits"] == 199  # First call was miss, rest hits
        assert stats["misses"] == 1

        # With cache should be faster (at least 10% improvement)
        # Note: This might be flaky in CI, so we're very lenient
        if (
            first_100_time > 0.002
        ):  # Only check if resolution takes measurable time (2ms threshold)
            # Allow up to 20% margin for timing variations in CI environments
            assert next_100_time < first_100_time * 0.8

    def test_cache_statistics_accuracy(self):
        """Test accuracy of cache statistics."""
        node = CacheTestNode()
        node.clear_cache()

        # Known sequence of operations
        patterns = [
            {"param_a": 1},  # Miss
            {"param_a": 2},  # Hit
            {"param_b": 1},  # Miss
            {"param_a": 3},  # Hit
            {"param_b": 2},  # Hit
            {"param_c": 1},  # Miss
        ]

        for pattern in patterns:
            node.validate_inputs(**pattern)

        stats = node.get_cache_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 3
        assert stats["size"] == 3
        assert stats["hit_rate"] == 0.5

    def test_edge_cases(self):
        """Test edge cases and error conditions."""
        node = CacheTestNode()

        # Empty inputs
        result = node.validate_inputs()
        assert result["param_a"] == 1  # Default
        assert result["param_b"] == 2  # Default
        assert result["param_c"] == 3  # Default

        # Extra parameters are ignored (not an error in current implementation)
        result = node.validate_inputs(param_a=10, invalid_param=123)
        assert result["param_a"] == 10
        assert "invalid_param" not in result

        # Cache should work normally
        result = node.validate_inputs(param_a=10)
        assert result["param_a"] == 10

        # Test with partial inputs - uses defaults
        result = node.validate_inputs(param_b=5)
        assert result["param_a"] == 1  # Default
        assert result["param_b"] == 5
        assert result["param_c"] == 3  # Default
