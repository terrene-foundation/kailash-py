"""Unit tests for MCP metrics collection framework.

Tests for the metrics collection system components in kailash.mcp_server.utils.metrics.
NO MOCKING - This is a unit test file for isolated component testing.
"""

import asyncio
import json
import threading
import time
from collections import deque
from unittest.mock import patch

import pytest
from kailash.mcp_server.utils.metrics import (
    MetricsCollector,
    get_metrics,
    reset_metrics,
    track_tool,
)


class TestMetricsCollector:
    """Test MetricsCollector class functionality."""

    def test_init_default_settings(self):
        """Test initialization with default settings."""
        collector = MetricsCollector()

        assert collector.enabled is True
        assert collector.collect_performance is True
        assert collector.collect_usage is True
        assert collector.history_size == 1000
        assert isinstance(collector._lock, type(threading.RLock()))
        assert collector._total_calls == 0
        assert collector._total_errors == 0

    def test_init_custom_settings(self):
        """Test initialization with custom settings."""
        collector = MetricsCollector(
            enabled=False,
            collect_performance=False,
            collect_usage=False,
            history_size=500,
        )

        assert collector.enabled is False
        assert collector.collect_performance is False
        assert collector.collect_usage is False
        assert collector.history_size == 500

    def test_track_tool_call_when_disabled(self):
        """Test that tracking does nothing when collector is disabled."""
        collector = MetricsCollector(enabled=False)

        # Should not raise any exceptions
        collector.track_tool_call("test_tool", 0.1, True)

        # No metrics should be recorded
        assert collector._total_calls == 0
        assert len(collector._tool_calls) == 0

    def test_track_tool_call_success(self):
        """Test tracking successful tool calls."""
        collector = MetricsCollector()

        collector.track_tool_call("test_tool", 0.15, success=True)

        assert collector._total_calls == 1
        assert collector._tool_calls["test_tool"] == 1
        assert len(collector._tool_latencies["test_tool"]) == 1
        assert collector._tool_latencies["test_tool"][0] == 0.15
        assert collector._total_errors == 0
        assert len(collector._recent_calls) == 1

        # Check recent call structure
        recent_call = collector._recent_calls[0]
        assert recent_call["tool"] == "test_tool"
        assert recent_call["latency"] == 0.15
        assert recent_call["success"] is True
        assert "timestamp" in recent_call

    def test_track_tool_call_failure(self):
        """Test tracking failed tool calls."""
        collector = MetricsCollector()

        collector.track_tool_call(
            "failing_tool", 0.25, success=False, error_type="ValueError"
        )

        assert collector._total_calls == 1
        assert collector._total_errors == 1
        assert collector._tool_calls["failing_tool"] == 1
        assert collector._tool_errors["failing_tool"] == 1
        assert len(collector._recent_errors) == 1

        # Check recent error structure
        recent_error = collector._recent_errors[0]
        assert recent_error["tool"] == "failing_tool"
        assert recent_error["error_type"] == "ValueError"
        assert "timestamp" in recent_error

    def test_track_tool_call_usage_only(self):
        """Test tracking with only usage collection enabled."""
        collector = MetricsCollector(collect_performance=False, collect_usage=True)

        collector.track_tool_call("test_tool", 0.1, True)

        assert collector._tool_calls["test_tool"] == 1
        assert (
            len(collector._tool_latencies["test_tool"]) == 0
        )  # No performance tracking
        assert len(collector._recent_calls) == 0  # No recent history

    def test_track_tool_call_performance_only(self):
        """Test tracking with only performance collection enabled."""
        collector = MetricsCollector(collect_performance=True, collect_usage=False)

        collector.track_tool_call("test_tool", 0.1, True)

        assert "test_tool" not in collector._tool_calls  # No usage tracking
        assert len(collector._tool_latencies["test_tool"]) == 1
        assert len(collector._recent_calls) == 1

    def test_latency_list_size_limit(self):
        """Test that latency lists are limited to prevent memory growth."""
        collector = MetricsCollector()

        # Add more than 100 latencies
        for i in range(150):
            collector.track_tool_call("test_tool", float(i), True)

        # Should only keep the last 100
        assert len(collector._tool_latencies["test_tool"]) == 100
        # Should have the last 100 values (50-149)
        assert collector._tool_latencies["test_tool"][0] == 50.0
        assert collector._tool_latencies["test_tool"][-1] == 149.0

    def test_history_size_limit(self):
        """Test that recent history respects size limit."""
        collector = MetricsCollector(history_size=10)

        # Add more than history_size calls
        for i in range(20):
            collector.track_tool_call(f"tool_{i}", 0.1, True)

        # Should only keep the last 10
        assert len(collector._recent_calls) == 10
        # Should have tools 10-19
        assert collector._recent_calls[0]["tool"] == "tool_10"
        assert collector._recent_calls[-1]["tool"] == "tool_19"

    def test_get_tool_stats_empty(self):
        """Test getting stats when no tools have been tracked."""
        collector = MetricsCollector()
        stats = collector.get_tool_stats()

        assert stats == {}

    def test_get_tool_stats_with_data(self):
        """Test getting tool statistics with tracked data."""
        collector = MetricsCollector()

        # Track some successful calls
        for i in range(5):
            collector.track_tool_call("good_tool", 0.1 * (i + 1), True)

        # Track some failed calls
        for i in range(2):
            collector.track_tool_call("bad_tool", 0.2, False, "RuntimeError")

        stats = collector.get_tool_stats()

        # Check good_tool stats
        assert stats["good_tool"]["calls"] == 5
        assert stats["good_tool"]["errors"] == 0
        assert stats["good_tool"]["error_rate"] == 0
        assert stats["good_tool"]["avg_latency"] == pytest.approx(
            0.3
        )  # (0.1+0.2+0.3+0.4+0.5)/5
        assert stats["good_tool"]["min_latency"] == 0.1
        assert stats["good_tool"]["max_latency"] == 0.5
        assert "p95_latency" in stats["good_tool"]
        assert "p99_latency" in stats["good_tool"]

        # Check bad_tool stats
        assert stats["bad_tool"]["calls"] == 2
        assert stats["bad_tool"]["errors"] == 2
        assert stats["bad_tool"]["error_rate"] == 1.0

    def test_get_server_stats(self):
        """Test getting overall server statistics."""
        collector = MetricsCollector()

        # Track some calls
        for i in range(10):
            collector.track_tool_call("tool1", 0.1, success=(i % 3 != 0))

        # Sleep a bit to have meaningful uptime
        time.sleep(0.1)

        stats = collector.get_server_stats()

        assert stats["total_calls"] == 10
        assert stats["total_errors"] == 4  # Failures when i % 3 == 0
        assert stats["overall_error_rate"] == 0.4
        assert stats["uptime_seconds"] >= 0.09  # Allow for fast test execution
        assert stats["calls_per_second"] > 0

        # Recent stats should be present
        assert "recent_calls_5min" in stats
        assert "recent_errors_5min" in stats
        assert "recent_error_rate_5min" in stats

    def test_get_server_stats_no_performance_collection(self):
        """Test server stats when performance collection is disabled."""
        collector = MetricsCollector(collect_performance=False)

        collector.track_tool_call("tool1", 0.1, True)

        stats = collector.get_server_stats()

        # Basic stats should be present
        assert stats["total_calls"] == 1
        assert stats["total_errors"] == 0

        # Recent stats should not be present
        assert "recent_calls_5min" not in stats

    def test_get_error_summary(self):
        """Test getting error summary."""
        collector = MetricsCollector()

        # Track various errors
        collector.track_tool_call("tool1", 0.1, False, "ValueError")
        collector.track_tool_call("tool1", 0.1, False, "ValueError")
        collector.track_tool_call("tool2", 0.1, False, "RuntimeError")
        collector.track_tool_call("tool3", 0.1, False, "TypeError")

        summary = collector.get_error_summary()

        assert summary["total_recent_errors"] == 4
        assert summary["error_types"]["ValueError"] == 2
        assert summary["error_types"]["RuntimeError"] == 1
        assert summary["error_types"]["TypeError"] == 1
        assert summary["error_by_tool"]["tool1"] == 2
        assert summary["error_by_tool"]["tool2"] == 1
        assert summary["error_by_tool"]["tool3"] == 1
        assert summary["window_hours"] == 1

    def test_get_error_summary_performance_disabled(self):
        """Test error summary when performance collection is disabled."""
        collector = MetricsCollector(collect_performance=False)

        summary = collector.get_error_summary()

        assert summary == {"error": "Performance collection disabled"}

    def test_percentile_calculation(self):
        """Test percentile calculation method."""
        collector = MetricsCollector()

        # Test with empty list
        assert collector._percentile([], 50) == 0.0

        # Test with single value
        assert collector._percentile([5.0], 50) == 5.0

        # Test with multiple values
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert collector._percentile(values, 50) == 3.0  # Median
        assert collector._percentile(values, 0) == 1.0  # Min
        assert collector._percentile(values, 100) == 5.0  # Max

        # Test with more complex case
        values = list(range(1, 101))  # 1 to 100
        assert collector._percentile(values, 95) == pytest.approx(95.05)
        assert collector._percentile(values, 99) == pytest.approx(99.01)

    def test_export_metrics_dict_format(self):
        """Test exporting metrics in dictionary format."""
        collector = MetricsCollector()

        # Add some data
        collector.track_tool_call("tool1", 0.1, True)
        collector.track_tool_call("tool2", 0.2, False, "ValueError")

        metrics = collector.export_metrics(format="dict")

        assert isinstance(metrics, dict)
        assert "server" in metrics
        assert "tools" in metrics
        assert "errors" in metrics
        assert "collection_config" in metrics

        # Check collection config
        config = metrics["collection_config"]
        assert config["enabled"] is True
        assert config["collect_performance"] is True
        assert config["collect_usage"] is True
        assert config["history_size"] == 1000

    def test_export_metrics_json_format(self):
        """Test exporting metrics in JSON format."""
        collector = MetricsCollector()

        collector.track_tool_call("tool1", 0.1, True)

        metrics_json = collector.export_metrics(format="json")

        assert isinstance(metrics_json, str)

        # Should be valid JSON
        metrics = json.loads(metrics_json)
        assert isinstance(metrics, dict)
        assert "server" in metrics
        assert "tools" in metrics

    def test_export_metrics_prometheus_format(self):
        """Test exporting metrics in Prometheus format."""
        collector = MetricsCollector()

        # Add some data
        collector.track_tool_call("tool1", 0.1, True)
        collector.track_tool_call("tool1", 0.2, False, "ValueError")
        collector.track_tool_call("tool2", 0.15, True)

        prometheus_output = collector.export_metrics(format="prometheus")

        assert isinstance(prometheus_output, str)
        lines = prometheus_output.split("\n")

        # Check for expected metric lines
        metric_names = [line.split()[0] for line in lines if line]
        assert "mcp_server_uptime_seconds" in metric_names
        assert "mcp_server_total_calls" in metric_names
        assert "mcp_server_total_errors" in metric_names
        assert "mcp_server_error_rate" in metric_names
        assert "mcp_server_calls_per_second" in metric_names

        # Check for tool-specific metrics with labels
        tool_metrics = [line for line in lines if "{tool=" in line]
        assert len(tool_metrics) > 0

        # Verify label format
        assert any('{tool="tool1"}' in line for line in tool_metrics)
        assert any('{tool="tool2"}' in line for line in tool_metrics)

    def test_export_metrics_invalid_format(self):
        """Test exporting metrics with invalid format."""
        collector = MetricsCollector()

        with pytest.raises(ValueError) as exc_info:
            collector.export_metrics(format="invalid_format")

        assert "Unsupported export format" in str(exc_info.value)

    def test_reset_metrics(self):
        """Test resetting all metrics."""
        collector = MetricsCollector()

        # Add some data
        for i in range(5):
            collector.track_tool_call(f"tool{i}", 0.1, success=(i % 2 == 0))

        # Verify data exists
        assert collector._total_calls == 5
        assert len(collector._tool_calls) > 0
        assert len(collector._recent_calls) > 0

        # Reset
        collector.reset()

        # Verify everything is cleared
        assert collector._total_calls == 0
        assert collector._total_errors == 0
        assert len(collector._tool_calls) == 0
        assert len(collector._tool_errors) == 0
        assert len(collector._tool_latencies) == 0
        assert len(collector._recent_calls) == 0
        assert len(collector._recent_errors) == 0

    def test_thread_safety(self):
        """Test thread safety of metrics collection."""
        collector = MetricsCollector()
        errors = []

        def track_calls(tool_name, count):
            try:
                for i in range(count):
                    collector.track_tool_call(tool_name, 0.01 * i, True)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=track_calls, args=(f"tool{i}", 100))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Check no errors occurred
        assert len(errors) == 0

        # Check total calls
        assert collector._total_calls == 500  # 5 threads * 100 calls each


class TestTrackToolDecorator:
    """Test track_tool decorator functionality."""

    def test_sync_function_decorator(self):
        """Test decorator on synchronous functions."""
        collector = MetricsCollector()

        @collector.track_tool("custom_tool_name")
        def test_function(x, y):
            return x + y

        result = test_function(2, 3)
        assert result == 5

        # Check metrics were tracked
        assert collector._total_calls == 1
        assert collector._tool_calls["custom_tool_name"] == 1
        assert len(collector._tool_latencies["custom_tool_name"]) == 1

    def test_sync_function_decorator_with_exception(self):
        """Test decorator on synchronous functions that raise exceptions."""
        collector = MetricsCollector()

        @collector.track_tool("failing_tool")
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

        # Check metrics were tracked
        assert collector._total_calls == 1
        assert collector._total_errors == 1
        assert collector._tool_errors["failing_tool"] == 1

        # Check error details
        recent_error = collector._recent_errors[0]
        assert recent_error["tool"] == "failing_tool"
        assert recent_error["error_type"] == "ValueError"

    def test_async_function_decorator(self):
        """Test decorator on asynchronous functions."""
        collector = MetricsCollector()

        @collector.track_tool("async_tool")
        async def async_function(x):
            await asyncio.sleep(0.01)
            return x * 2

        # Run async function
        result = asyncio.run(async_function(5))
        assert result == 10

        # Check metrics were tracked
        assert collector._total_calls == 1
        assert collector._tool_calls["async_tool"] == 1
        assert len(collector._tool_latencies["async_tool"]) == 1
        assert collector._tool_latencies["async_tool"][0] >= 0.01

    def test_async_function_decorator_with_exception(self):
        """Test decorator on async functions that raise exceptions."""
        collector = MetricsCollector()

        @collector.track_tool("async_failing_tool")
        async def async_failing_function():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async error")

        with pytest.raises(RuntimeError):
            asyncio.run(async_failing_function())

        # Check metrics were tracked
        assert collector._total_calls == 1
        assert collector._total_errors == 1
        assert collector._tool_errors["async_failing_tool"] == 1

    def test_decorator_without_tool_name(self):
        """Test decorator without explicit tool name uses function name."""
        collector = MetricsCollector()

        @collector.track_tool()
        def my_special_function():
            return 42

        result = my_special_function()
        assert result == 42

        # Should use function name
        assert collector._tool_calls["my_special_function"] == 1

    def test_decorator_when_disabled(self):
        """Test decorator behavior when metrics are disabled."""
        collector = MetricsCollector(enabled=False)

        @collector.track_tool("tool")
        def test_function():
            return "result"

        # Function should work normally
        assert test_function() == "result"

        # But no metrics should be collected
        assert collector._total_calls == 0

    def test_decorator_preserves_function_attributes(self):
        """Test that decorator preserves function attributes."""
        collector = MetricsCollector()

        @collector.track_tool("tool")
        def documented_function():
            """This is a test function."""
            return True

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a test function."


class TestGlobalMetricsFunctions:
    """Test global metrics functions."""

    def test_global_track_tool_decorator(self):
        """Test global track_tool decorator."""
        # Reset global metrics first
        reset_metrics()

        @track_tool("global_tool")
        def test_function():
            return "success"

        result = test_function()
        assert result == "success"

        # Check global metrics
        metrics = get_metrics()
        assert metrics["server"]["total_calls"] == 1
        assert "global_tool" in metrics["tools"]

    def test_get_metrics_function(self):
        """Test get_metrics global function."""
        # Reset first
        reset_metrics()

        # Get initial metrics
        metrics = get_metrics()
        assert isinstance(metrics, dict)
        assert metrics["server"]["total_calls"] == 0

        # Track some calls using global decorator
        @track_tool("test_tool")
        def test_func():
            return True

        test_func()
        test_func()

        # Get updated metrics
        metrics = get_metrics()
        assert metrics["server"]["total_calls"] == 2
        assert metrics["tools"]["test_tool"]["calls"] == 2

    def test_reset_metrics_function(self):
        """Test reset_metrics global function."""
        # Reset first to ensure clean state
        reset_metrics()

        # Add some data
        @track_tool("tool_to_reset")
        def test_func():
            return True

        for _ in range(5):
            test_func()

        # Verify data exists
        metrics = get_metrics()
        assert metrics["server"]["total_calls"] == 5

        # Reset
        reset_metrics()

        # Verify reset
        metrics = get_metrics()
        assert metrics["server"]["total_calls"] == 0
        assert len(metrics["tools"]) == 0


class TestMetricsEdgeCases:
    """Test edge cases and error conditions."""

    def test_concurrent_metrics_access(self):
        """Test concurrent access to metrics."""
        collector = MetricsCollector()

        def reader_thread():
            for _ in range(100):
                collector.get_tool_stats()
                collector.get_server_stats()
                collector.get_error_summary()

        def writer_thread(tool_name):
            for i in range(100):
                collector.track_tool_call(tool_name, 0.001 * i, success=(i % 5 != 0))

        # Start multiple reader and writer threads
        threads = []

        # Writers
        for i in range(3):
            thread = threading.Thread(target=writer_thread, args=(f"tool{i}",))
            threads.append(thread)
            thread.start()

        # Readers
        for i in range(2):
            thread = threading.Thread(target=reader_thread)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify final state is consistent
        stats = collector.get_tool_stats()
        total_calls = sum(s["calls"] for s in stats.values())
        assert total_calls == 300  # 3 writers * 100 calls each

    def test_very_long_tool_names(self):
        """Test handling of very long tool names."""
        collector = MetricsCollector()

        long_name = "x" * 1000
        collector.track_tool_call(long_name, 0.1, True)

        stats = collector.get_tool_stats()
        assert long_name in stats
        assert stats[long_name]["calls"] == 1

    def test_zero_latency(self):
        """Test handling of zero latency values."""
        collector = MetricsCollector()

        collector.track_tool_call("instant_tool", 0.0, True)

        stats = collector.get_tool_stats()
        assert stats["instant_tool"]["avg_latency"] == 0.0
        assert stats["instant_tool"]["min_latency"] == 0.0
        assert stats["instant_tool"]["max_latency"] == 0.0

    def test_negative_latency(self):
        """Test handling of negative latency values (clock issues)."""
        collector = MetricsCollector()

        # This shouldn't happen in practice but test it anyway
        collector.track_tool_call("time_travel_tool", -0.1, True)

        stats = collector.get_tool_stats()
        assert stats["time_travel_tool"]["avg_latency"] == -0.1

    def test_empty_error_type(self):
        """Test handling of empty error type."""
        collector = MetricsCollector()

        collector.track_tool_call("tool", 0.1, False, error_type=None)

        summary = collector.get_error_summary()
        # When error_type is None, it gets stored as None in the error dict
        # but get_error_summary() converts it to "Unknown"
        assert "Unknown" in summary["error_types"] or None in summary["error_types"]

    def test_unicode_tool_names(self):
        """Test handling of unicode characters in tool names."""
        collector = MetricsCollector()

        unicode_name = "测试工具_🔧"
        collector.track_tool_call(unicode_name, 0.1, True)

        stats = collector.get_tool_stats()
        assert unicode_name in stats
        assert stats[unicode_name]["calls"] == 1

        # Test Prometheus export with unicode
        prometheus = collector.export_metrics(format="prometheus")
        assert unicode_name in prometheus

    def test_time_window_filtering(self):
        """Test that time window filtering works correctly."""
        collector = MetricsCollector()

        # Mock time to control timestamps
        current_time = time.time()

        with patch("time.time") as mock_time:
            # Add old calls (>5 minutes ago)
            mock_time.return_value = current_time - 400  # 6.67 minutes ago
            for i in range(5):
                collector.track_tool_call("old_tool", 0.1, True)

            # Add recent calls
            mock_time.return_value = current_time
            for i in range(3):
                collector.track_tool_call("recent_tool", 0.2, True)

            # Get server stats
            stats = collector.get_server_stats()

            # Total should include all calls
            assert stats["total_calls"] == 8

            # Recent should only include last 3
            assert stats["recent_calls_5min"] == 3
            assert stats["recent_avg_latency_5min"] == pytest.approx(0.2)

    def test_decorator_with_arguments(self):
        """Test decorator works properly with function arguments."""
        collector = MetricsCollector()

        @collector.track_tool("math_tool")
        def add(a, b, c=0):
            return a + b + c

        # Test with positional args
        assert add(1, 2) == 3
        assert collector._tool_calls["math_tool"] == 1

        # Test with keyword args
        assert add(1, 2, c=3) == 6
        assert collector._tool_calls["math_tool"] == 2

        # Test with mixed args
        assert add(a=5, b=10) == 15
        assert collector._tool_calls["math_tool"] == 3

    def test_multiple_collectors_independence(self):
        """Test that multiple collectors maintain independent state."""
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()

        collector1.track_tool_call("tool1", 0.1, True)
        collector2.track_tool_call("tool2", 0.2, True)

        # Each collector should only have its own data
        stats1 = collector1.get_tool_stats()
        stats2 = collector2.get_tool_stats()

        assert "tool1" in stats1
        assert "tool1" not in stats2
        assert "tool2" in stats2
        assert "tool2" not in stats1

    def test_percentile_edge_cases(self):
        """Test percentile calculation with edge cases."""
        collector = MetricsCollector()

        # Test with identical values
        identical = [5.0] * 10
        assert collector._percentile(identical, 50) == 5.0
        assert collector._percentile(identical, 95) == 5.0

        # Test with two values
        two_values = [1.0, 2.0]
        assert collector._percentile(two_values, 50) == 1.5
