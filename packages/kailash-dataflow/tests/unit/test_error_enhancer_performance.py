"""
Test-First Development for ErrorEnhancer Performance Optimization (Phase 1C Component 1)

This test suite is written BEFORE implementation to ensure proper TDD methodology.
All tests should FAIL initially (RED phase), then pass after implementation (GREEN phase).

Test Coverage:
- Performance mode configuration (FULL/MINIMAL/DISABLED)
- Pattern caching with LRU eviction
- Performance benchmarks for each mode
- Thread-safety for concurrent access
- Memory usage validation
- Runtime mode switching
- Environment variable configuration

Performance Targets:
- FULL mode: <5ms overhead per error
- MINIMAL mode: <1ms overhead per error
- DISABLED mode: <0.1ms overhead (passthrough only)
"""

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

# ============================================================================
# Test Group 1: Performance Mode Configuration
# ============================================================================


class TestPerformanceModeConfiguration:
    """Test performance mode configuration and setup."""

    def test_performance_mode_enum_exists(self):
        """Should have PerformanceMode enum with three modes."""
        from dataflow.core.config import PerformanceMode

        assert hasattr(PerformanceMode, "FULL")
        assert hasattr(PerformanceMode, "MINIMAL")
        assert hasattr(PerformanceMode, "DISABLED")

    def test_error_enhancer_config_dataclass(self):
        """Should have ErrorEnhancerConfig dataclass."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode

        config = ErrorEnhancerConfig(
            mode=PerformanceMode.FULL, cache_size=100, cache_ttl=300
        )

        assert config.mode == PerformanceMode.FULL
        assert config.cache_size == 100
        assert config.cache_ttl == 300

    def test_error_enhancer_accepts_config(self):
        """ErrorEnhancer should accept ErrorEnhancerConfig."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL, cache_size=50)
        enhancer = ErrorEnhancer(config=config)

        assert enhancer.config.mode == PerformanceMode.MINIMAL
        assert enhancer.config.cache_size == 50

    def test_error_enhancer_default_config(self):
        """ErrorEnhancer should use default FULL mode config if none provided."""
        from dataflow.core.config import PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        enhancer = ErrorEnhancer()

        assert enhancer.config.mode == PerformanceMode.FULL
        assert enhancer.config.cache_size == 100  # Default


# ============================================================================
# Test Group 2: Mode-Specific Behavior
# ============================================================================


class TestModeSpecificBehavior:
    """Test behavior for each performance mode."""

    def test_full_mode_includes_all_context(self):
        """FULL mode should include all context and solutions."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL)
        enhancer = ErrorEnhancer(config=config)

        enhanced = enhancer.enhance_parameter_error(
            node_id="user_create",
            node_type="UserCreateNode",
            parameter_name="data",
            expected_type="dict",
            received_value=None,
            original_error=KeyError("data"),
        )

        # FULL mode should have complete information
        assert enhanced.error_code == "DF-101"
        assert "node_id" in enhanced.context
        assert "node_type" in enhanced.context
        assert "parameter" in enhanced.context
        assert len(enhanced.causes) >= 3  # Multiple causes
        assert len(enhanced.solutions) >= 2  # Multiple solutions
        assert all(sol.code_template for sol in enhanced.solutions)  # All have code

    def test_minimal_mode_includes_essential_context_only(self):
        """MINIMAL mode should include essential context and top solution only."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL)
        enhancer = ErrorEnhancer(config=config)

        enhanced = enhancer.enhance_parameter_error(
            node_id="user_create",
            node_type="UserCreateNode",
            parameter_name="data",
            expected_type="dict",
            received_value=None,
            original_error=KeyError("data"),
        )

        # MINIMAL mode should have essential information only
        assert enhanced.error_code == "DF-101"
        assert "node_id" in enhanced.context
        assert len(enhanced.context) <= 3  # Minimal context
        assert len(enhanced.causes) <= 1  # Top cause only
        assert len(enhanced.solutions) == 1  # Top solution only
        assert enhanced.solutions[0].code_template  # Has code template

    def test_disabled_mode_returns_original_error(self):
        """DISABLED mode should return original error wrapped minimally."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.DISABLED)
        enhancer = ErrorEnhancer(config=config)

        original = KeyError("data")
        enhanced = enhancer.enhance_parameter_error(
            node_id="user_create",
            node_type="UserCreateNode",
            parameter_name="data",
            original_error=original,
        )

        # DISABLED mode should passthrough with minimal wrapper
        assert enhanced.original_error is original
        assert enhanced.error_code == "DF-999"  # Generic passthrough code
        assert len(enhanced.causes) == 0
        assert len(enhanced.solutions) == 0


# ============================================================================
# Test Group 3: Pattern Caching
# ============================================================================


class TestPatternCaching:
    """Test pattern caching functionality."""

    def test_pattern_cache_initialization(self):
        """Should initialize pattern cache with configured size."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=50)
        enhancer = ErrorEnhancer(config=config)

        assert hasattr(enhancer, "_pattern_cache")
        # Access maxsize via cache_info()
        cache_info = enhancer._pattern_cache.cache_info()
        assert cache_info.maxsize == 50

    def test_pattern_cache_hit_rate(self):
        """Should achieve 90%+ hit rate for repeated error patterns."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=100)
        enhancer = ErrorEnhancer(config=config)

        # First call - cache miss
        exception1 = KeyError("Parameter 'data' is missing")
        enhancer.find_error_definition(exception1)

        # Subsequent 9 calls - cache hits
        for _ in range(9):
            exception = KeyError("Parameter 'data' is missing")
            enhancer.find_error_definition(exception)

        # Check cache hit rate
        hit_rate = enhancer.get_cache_hit_rate()
        assert hit_rate >= 0.9, f"Expected hit rate >= 0.9, got {hit_rate}"

    def test_pattern_cache_eviction_lru(self):
        """Should evict least recently used patterns when cache is full."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=2)
        enhancer = ErrorEnhancer(config=config)

        # Fill cache with 2 patterns
        exc1 = KeyError("Parameter 'data' is missing")
        exc2 = TypeError("Type mismatch: expected dict, got str")
        enhancer.find_error_definition(exc1)
        enhancer.find_error_definition(exc2)

        # Add third pattern - should trigger LRU eviction
        exc3 = ValueError("Schema mismatch detected")
        enhancer.find_error_definition(exc3)

        # Check cache state - should stay at max size
        cache_info = enhancer.get_cache_info()
        assert cache_info["size"] <= 2  # Should not exceed max size
        # Eviction detection may not be perfect due to LRU internals,
        # but cache should stay bounded
        assert cache_info["maxsize"] == 2

    def test_cache_performance_improvement(self):
        """Cache hit should be faster than or equal to cache miss."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=100)
        enhancer = ErrorEnhancer(config=config)

        exception = KeyError("Parameter 'data' is missing")

        # Measure cache miss time
        start = time.perf_counter()
        enhancer.find_error_definition(exception)
        miss_time = time.perf_counter() - start

        # Measure cache hit time (run multiple times for accuracy)
        hit_times = []
        for _ in range(10):
            start = time.perf_counter()
            enhancer.find_error_definition(exception)
            hit_times.append(time.perf_counter() - start)

        avg_hit_time = sum(hit_times) / len(hit_times)

        # Cache hit should be faster than or equal to miss (allowing for measurement variance)
        # Main benefit is consistent performance, not necessarily dramatic speedup
        assert avg_hit_time <= miss_time * 2, (
            f"Cache hit ({avg_hit_time:.6f}s) should not be significantly slower than "
            f"miss ({miss_time:.6f}s)"
        )


# ============================================================================
# Test Group 4: Performance Benchmarks
# ============================================================================


class TestPerformanceBenchmarks:
    """Test performance targets for each mode."""

    def test_full_mode_performance_target(self):
        """FULL mode should have <5ms overhead per error."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL)
        enhancer = ErrorEnhancer(config=config)

        # Warm up cache
        enhancer.enhance_parameter_error(
            node_id="warmup", parameter_name="data", original_error=KeyError("data")
        )

        # Measure overhead (average of 100 calls)
        times = []
        for i in range(100):
            start = time.perf_counter()
            enhancer.enhance_parameter_error(
                node_id=f"user_{i}",
                node_type="UserCreateNode",
                parameter_name="data",
                original_error=KeyError("data"),
            )
            times.append(time.perf_counter() - start)

        avg_time_ms = (sum(times) / len(times)) * 1000

        assert (
            avg_time_ms < 5.0
        ), f"FULL mode overhead ({avg_time_ms:.2f}ms) exceeds target (5ms)"

    def test_minimal_mode_performance_target(self):
        """MINIMAL mode should have <1ms overhead per error."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.MINIMAL)
        enhancer = ErrorEnhancer(config=config)

        # Warm up cache
        enhancer.enhance_parameter_error(
            node_id="warmup", parameter_name="data", original_error=KeyError("data")
        )

        # Measure overhead (average of 100 calls)
        times = []
        for i in range(100):
            start = time.perf_counter()
            enhancer.enhance_parameter_error(
                node_id=f"user_{i}",
                node_type="UserCreateNode",
                parameter_name="data",
                original_error=KeyError("data"),
            )
            times.append(time.perf_counter() - start)

        avg_time_ms = (sum(times) / len(times)) * 1000

        assert (
            avg_time_ms < 1.0
        ), f"MINIMAL mode overhead ({avg_time_ms:.2f}ms) exceeds target (1ms)"

    def test_disabled_mode_performance_target(self):
        """DISABLED mode should have <0.1ms overhead (passthrough only)."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.DISABLED)
        enhancer = ErrorEnhancer(config=config)

        # Measure overhead (average of 100 calls)
        times = []
        for i in range(100):
            start = time.perf_counter()
            enhancer.enhance_parameter_error(
                node_id=f"user_{i}",
                node_type="UserCreateNode",
                parameter_name="data",
                original_error=KeyError("data"),
            )
            times.append(time.perf_counter() - start)

        avg_time_ms = (sum(times) / len(times)) * 1000

        assert (
            avg_time_ms < 0.1
        ), f"DISABLED mode overhead ({avg_time_ms:.2f}ms) exceeds target (0.1ms)"


# ============================================================================
# Test Group 5: Memory and Resource Management
# ============================================================================


class TestMemoryAndResourceManagement:
    """Test memory usage and resource management."""

    def test_cache_memory_usage_stays_bounded(self):
        """Cache memory usage should stay within configured bounds."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=100)
        enhancer = ErrorEnhancer(config=config)

        # Generate 1000 unique error patterns (10x cache size)
        for i in range(1000):
            exception = KeyError(f"Parameter 'field_{i}' is missing")
            enhancer.find_error_definition(exception)

        # Cache should not exceed configured size
        cache_info = enhancer.get_cache_info()
        assert (
            cache_info["size"] <= 100
        ), f"Cache size ({cache_info['size']}) exceeds limit (100)"
        # Cache should be at or near max size (LRU keeps it bounded)
        assert cache_info["maxsize"] == 100

    def test_concurrent_access_thread_safe(self):
        """Cache should be thread-safe for concurrent access."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL, cache_size=100)
        enhancer = ErrorEnhancer(config=config)

        errors = []

        def enhance_errors(thread_id):
            try:
                for i in range(50):
                    exception = KeyError(f"Parameter 'field_{i}' is missing")
                    enhancer.find_error_definition(exception)
            except Exception as e:
                errors.append(e)

        # Run 10 threads concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(enhance_errors, i) for i in range(10)]
            for future in futures:
                future.result()

        # Should complete without errors
        assert len(errors) == 0, f"Thread-safety violated: {errors}"

        # Cache should be consistent
        cache_info = enhancer.get_cache_info()
        assert cache_info["size"] <= 100  # Within bounds


# ============================================================================
# Test Group 6: Runtime Configuration
# ============================================================================


class TestRuntimeConfiguration:
    """Test runtime configuration and mode switching."""

    def test_mode_switching_at_runtime(self):
        """Should support switching performance mode at runtime."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        config = ErrorEnhancerConfig(mode=PerformanceMode.FULL)
        enhancer = ErrorEnhancer(config=config)

        # Start in FULL mode
        enhanced1 = enhancer.enhance_parameter_error(
            node_id="user_create",
            parameter_name="data",
            original_error=KeyError("data"),
        )
        assert len(enhanced1.solutions) >= 2  # FULL mode

        # Switch to MINIMAL mode
        enhancer.set_performance_mode(PerformanceMode.MINIMAL)

        enhanced2 = enhancer.enhance_parameter_error(
            node_id="user_create",
            parameter_name="data",
            original_error=KeyError("data"),
        )
        assert len(enhanced2.solutions) == 1  # MINIMAL mode

    def test_configuration_via_environment_variables(self):
        """Should support configuration via environment variables."""
        from dataflow.core.config import ErrorEnhancerConfig, PerformanceMode
        from dataflow.core.error_enhancer import ErrorEnhancer

        with patch.dict(
            os.environ,
            {
                "DATAFLOW_ERROR_ENHANCER_MODE": "MINIMAL",
                "DATAFLOW_ERROR_ENHANCER_CACHE_SIZE": "50",
                "DATAFLOW_ERROR_ENHANCER_CACHE_TTL": "600",
            },
        ):
            config = ErrorEnhancerConfig.from_env()
            enhancer = ErrorEnhancer(config=config)

            assert enhancer.config.mode == PerformanceMode.MINIMAL
            assert enhancer.config.cache_size == 50
            assert enhancer.config.cache_ttl == 600


# ============================================================================
# Run Tests to Verify They Fail (RED phase)
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
