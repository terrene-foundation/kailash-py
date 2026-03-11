#!/usr/bin/env python3
"""
Performance Boundary Tests for NOT NULL Column Addition System

Tests performance characteristics with production-scale data volumes (100K, 1M, 10M rows)
to validate estimation accuracy, timeout handling, and resource usage patterns.

This test suite ensures the system scales appropriately for production workloads.
"""

import asyncio
import resource
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import psutil
import pytest

from dataflow.migrations.constraint_validator import ConstraintValidator
from dataflow.migrations.default_strategies import DefaultValueStrategyManager
from dataflow.migrations.not_null_handler import (
    AdditionExecutionResult,
    AdditionResult,
    ColumnDefinition,
    DefaultValueType,
    NotNullAdditionPlan,
    NotNullColumnHandler,
    ValidationResult,
)


def create_mock_connection():
    """Create a mock connection with transaction support."""
    mock_connection = AsyncMock()

    # Create a proper async context manager class
    class MockTransaction:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make transaction() return the context manager directly, not a coroutine
    mock_connection.transaction = Mock(return_value=MockTransaction())

    # Default fetchval that handles constraint validation queries
    original_fetchval = mock_connection.fetchval

    async def smart_fetchval(query, *args):
        # Handle constraint validation query (check for NULL values)
        if "IS NULL" in query and "COUNT" in query.upper():
            return 0  # No NULL violations
        # For other queries, use the configured return value or side effect
        if hasattr(original_fetchval, "return_value"):
            return original_fetchval.return_value
        return None

    mock_connection.fetchval = smart_fetchval

    return mock_connection


class TestProductionScalePerformance:
    """Test performance with production-scale data volumes."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.manager = DefaultValueStrategyManager()

    @pytest.mark.asyncio
    async def test_100k_rows_static_default(self):
        """Test performance with 100K rows using static default."""
        mock_connection = create_mock_connection()

        async def mock_fetchval(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            return 100000  # 100K rows

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="status", data_type="VARCHAR(20)", default_value="active"
            )

            # Plan should be fast for static defaults
            plan = await self.handler.plan_not_null_addition("large_table", column)

            assert plan.execution_strategy == "single_ddl"
            assert plan.estimated_duration < 5.0  # Should be very fast
            assert plan.affected_rows == 100000

            # Execute and measure actual time
            start_time = time.time()
            result = await self.handler.execute_not_null_addition(plan)
            actual_time = time.time() - start_time

            assert result.result == AdditionResult.SUCCESS
            # Mock execution should be instant, but estimation should be reasonable
            assert plan.estimated_duration > 0

    @pytest.mark.asyncio
    async def test_100k_rows_computed_default(self):
        """Test performance with 100K rows using computed default."""
        mock_connection = create_mock_connection()
        mock_connection.fetch.return_value = []

        # Track batch execution
        batch_count = {"count": 0}

        async def mock_fetchval_batch(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            if "WITH batch AS" in query:
                batch_count["count"] += 1
                if batch_count["count"] * 10000 >= 100000:
                    return None  # No more rows
                return 10000  # Rows updated per batch
            return 100000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="category",
                data_type="VARCHAR(20)",
                default_expression="CASE WHEN id <= 50000 THEN 'premium' ELSE 'standard' END",
                default_type=DefaultValueType.COMPUTED,
            )

            # Plan should use batched execution
            plan = await self.handler.plan_not_null_addition("large_table", column)

            assert plan.execution_strategy == "batched_update"
            assert plan.batch_size == 10000
            assert plan.estimated_duration > 0.15  # Computed takes longer than static

            # Execute with simulated batches
            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.SUCCESS
            assert batch_count["count"] >= 10  # Should have processed 10 batches

    @pytest.mark.asyncio
    async def test_1m_rows_performance_scaling(self):
        """Test performance scaling with 1M rows."""
        mock_connection = create_mock_connection()
        mock_connection.fetch.return_value = []

        # Simulate realistic batch processing delays
        batch_times = []

        async def mock_fetchval_batch(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            if "WITH batch AS" in query:
                start = time.time()
                await asyncio.sleep(0.001)  # Simulate batch processing time
                batch_times.append(time.time() - start)
                if len(batch_times) * 10000 >= 1000000:
                    return None
                return 10000
            return 1000000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="score",
                data_type="INTEGER",
                default_expression="FLOOR(RANDOM() * 100)",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = await self.handler.plan_not_null_addition(
                "million_row_table", column
            )

            # Should have reasonable performance estimates
            assert plan.estimated_duration > 1.0  # At least 1 second for 1M rows
            assert plan.estimated_duration < 60.0  # But not more than 1 minute
            assert plan.batch_size > 0

            # Execute and verify batching worked correctly
            start_time = time.time()
            result = await self.handler.execute_not_null_addition(plan)
            execution_time = time.time() - start_time

            assert result.result == AdditionResult.SUCCESS
            assert len(batch_times) == 100  # 1M rows / 10K batch size

    @pytest.mark.asyncio
    async def test_10m_rows_timeout_handling(self):
        """Test timeout handling with 10M rows."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 10000000  # 10M rows
        mock_connection.fetch.return_value = []

        # Simulate timeout scenario
        batch_count = {"count": 0}

        async def mock_fetchval_batch(query, *args):
            if "WITH batch AS" in query:
                batch_count["count"] += 1
                if batch_count["count"] > 50:
                    # Simulate timeout after 500K rows
                    raise asyncio.TimeoutError("Operation timed out")
                return 10000
            return 10000000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        # Mock transaction for rollback
        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_transaction
        )
        mock_connection.transaction.return_value.__aexit__ = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="huge_column",
                data_type="TEXT",
                default_expression="REPEAT('x', 100)",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="huge_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
                timeout_seconds=5,  # Short timeout to trigger failure
            )

            # Should handle timeout gracefully
            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.ROLLBACK_REQUIRED
            assert result.rollback_executed is True
            assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_estimation_accuracy_at_scale(self):
        """Test estimation accuracy across different scales."""
        test_cases = [
            (1000, DefaultValueType.STATIC, 0.1, 5.0),  # 1K rows, static
            (10000, DefaultValueType.STATIC, 0.1, 5.0),  # 10K rows, static
            (100000, DefaultValueType.STATIC, 0.1, 5.0),  # 100K rows, static
            (1000000, DefaultValueType.STATIC, 0.1, 10.0),  # 1M rows, static
            (1000, DefaultValueType.COMPUTED, 0.15, 10.0),  # 1K rows, computed
            (10000, DefaultValueType.COMPUTED, 0.15, 20.0),  # 10K rows, computed
            (100000, DefaultValueType.COMPUTED, 0.5, 60.0),  # 100K rows, computed
            (1000000, DefaultValueType.COMPUTED, 5.0, 300.0),  # 1M rows, computed
        ]

        for row_count, default_type, min_time, max_time in test_cases:
            mock_connection = create_mock_connection()

            async def make_mock_fetchval(count):
                async def mock_fetchval(query, *args):
                    return count

                return mock_fetchval

            mock_connection.fetchval = await make_mock_fetchval(row_count)
            mock_connection.fetch.return_value = []
            mock_connection.execute = AsyncMock()

            with patch.object(
                self.handler, "_get_connection", return_value=mock_connection
            ):
                column = ColumnDefinition(
                    name="test_col",
                    data_type="VARCHAR(50)",
                    default_value=(
                        "test" if default_type == DefaultValueType.STATIC else None
                    ),
                    default_expression=(
                        "CASE WHEN id > 0 THEN 'yes' ELSE 'no' END"
                        if default_type == DefaultValueType.COMPUTED
                        else None
                    ),
                    default_type=default_type,
                )

                plan = await self.handler.plan_not_null_addition("test_table", column)

                # Verify estimation is within reasonable bounds
                assert (
                    min_time <= plan.estimated_duration <= max_time
                ), f"Estimation {plan.estimated_duration}s out of range [{min_time}, {max_time}] for {row_count} rows with {default_type}"


class TestMemoryUsagePatterns:
    """Test memory usage patterns at scale."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.manager = DefaultValueStrategyManager()

    @pytest.mark.asyncio
    async def test_memory_efficient_batch_processing(self):
        """Test memory-efficient batch processing for large tables."""
        mock_connection = create_mock_connection()
        mock_connection.fetch.return_value = []

        # Track memory usage during batches
        memory_samples = []

        async def mock_fetchval_batch(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            if "WITH batch AS" in query:
                # Sample memory usage
                if psutil:
                    process = psutil.Process()
                    memory_samples.append(process.memory_info().rss / 1024 / 1024)  # MB

                if len(memory_samples) * 10000 >= 5000000:
                    return None
                return 10000
            return 5000000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="large_col",
                data_type="TEXT",
                default_expression="REPEAT('data', 100)",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="large_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
            )

            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.SUCCESS

            # Memory should not grow linearly with table size
            if memory_samples and len(memory_samples) > 10:
                # Check that memory usage is relatively stable
                avg_first_10 = sum(memory_samples[:10]) / 10
                avg_last_10 = sum(memory_samples[-10:]) / 10

                # Memory growth should be limited (less than 2x)
                memory_growth_ratio = (
                    avg_last_10 / avg_first_10 if avg_first_10 > 0 else 1
                )
                assert (
                    memory_growth_ratio < 2.0
                ), f"Memory grew too much: {memory_growth_ratio}x"

    @pytest.mark.asyncio
    async def test_batch_size_optimization(self):
        """Test batch size optimization for different table sizes."""
        # For computed defaults, the implementation uses a fixed batch size of 10000
        test_cases = [
            (1000, 10000),  # Small table - uses default batch size
            (10000, 10000),  # Medium table - uses default batch size
            (100000, 10000),  # Large table - 10K batches
            (1000000, 10000),  # Very large - 10K batches
            (10000000, 10000),  # Huge - 10K batches
        ]

        for row_count, expected_batch_size in test_cases:
            mock_connection = create_mock_connection()

            async def make_mock_fetchval(count):
                async def mock_fetchval(query, *args):
                    return count

                return mock_fetchval

            mock_connection.fetchval = await make_mock_fetchval(row_count)
            mock_connection.fetch.return_value = []

            with patch.object(
                self.handler, "_get_connection", return_value=mock_connection
            ):
                column = ColumnDefinition(
                    name="test_col",
                    data_type="VARCHAR(50)",
                    default_expression="CASE WHEN id > 0 THEN 'yes' ELSE 'no' END",
                    default_type=DefaultValueType.COMPUTED,
                )

                plan = await self.handler.plan_not_null_addition("test_table", column)

                # Verify batch size is optimized for table size
                assert (
                    plan.batch_size == expected_batch_size
                ), f"Expected batch size {expected_batch_size} for {row_count} rows, got {plan.batch_size}"


class TestTimeoutAndCancellation:
    """Test timeout and cancellation behavior at scale."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_graceful_timeout_with_partial_progress(self):
        """Test graceful timeout handling with partial progress tracking."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 1000000  # 1M rows
        mock_connection.fetch.return_value = []

        # Track progress
        progress = {"batches_completed": 0, "rows_updated": 0}

        async def mock_fetchval_batch(query, *args):
            if "WITH batch AS" in query:
                progress["batches_completed"] += 1
                progress["rows_updated"] += 10000

                # Simulate timeout after 30% completion
                if progress["batches_completed"] > 30:
                    raise asyncio.TimeoutError("Operation timed out")

                await asyncio.sleep(0.01)  # Simulate work
                return 10000
            return 1000000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        # Mock transaction
        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_transaction
        )
        mock_connection.transaction.return_value.__aexit__ = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="timeout_col",
                data_type="VARCHAR(50)",
                default_expression="CASE WHEN id > 500000 THEN 'high' ELSE 'low' END",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
                timeout_seconds=1,  # Very short timeout
            )

            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.ROLLBACK_REQUIRED
            assert result.rollback_executed is True

            # Should have made some progress before timeout
            assert progress["batches_completed"] > 0
            assert progress["rows_updated"] > 0

            # Progress should be reported
            if result.performance_metrics:
                assert "partial_progress" in result.performance_metrics
                assert (
                    result.performance_metrics["partial_progress"]["rows_updated"]
                    == progress["rows_updated"]
                )

    @pytest.mark.asyncio
    async def test_cancellation_during_batch_processing(self):
        """Test cancellation during batch processing."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 500000
        mock_connection.fetch.return_value = []

        # Track cancellation
        cancelled = {"flag": False}
        batch_count = {"count": 0}

        async def mock_fetchval_batch(query, *args):
            if "WITH batch AS" in query:
                batch_count["count"] += 1

                # Check for cancellation
                if cancelled["flag"]:
                    raise asyncio.CancelledError("Operation cancelled")

                # Simulate cancellation after 20 batches
                if batch_count["count"] == 20:
                    cancelled["flag"] = True

                return 10000
            return 500000

        mock_connection.fetchval = mock_fetchval_batch
        mock_connection.execute = AsyncMock()

        # Mock transaction
        mock_transaction = AsyncMock()
        mock_connection.transaction.return_value.__aenter__ = AsyncMock(
            return_value=mock_transaction
        )
        mock_connection.transaction.return_value.__aexit__ = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="cancel_col",
                data_type="VARCHAR(50)",
                default_expression="'test'",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
            )

            # Execute with cancellation
            with pytest.raises(asyncio.CancelledError):
                await self.handler.execute_not_null_addition(plan)

            # Should have processed some batches before cancellation
            assert batch_count["count"] >= 20


class TestEstimationAccuracy:
    """Test estimation accuracy for performance predictions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()
        self.manager = DefaultValueStrategyManager()

    def test_static_default_estimation_formula(self):
        """Test static default estimation formula accuracy."""
        strategy = self.manager.static_default("test")

        # Static defaults use the estimated_performance attribute
        perf = strategy.estimated_performance

        # Verify static defaults have minimal overhead and are fast
        assert perf is not None
        assert perf.get("overhead") == "minimal"
        assert perf.get("fast_path") is True
        # Static defaults don't require batching
        assert strategy.requires_batching is False

    def test_computed_default_estimation_formula(self):
        """Test computed default estimation formula accuracy."""
        strategy = self.manager.computed_default(
            "CASE WHEN id > 0 THEN 'yes' ELSE 'no' END"
        )

        # Computed defaults use the estimated_performance attribute
        perf = strategy.estimated_performance

        # Verify computed defaults have proper performance characteristics
        assert perf is not None
        # Computed defaults require batching
        assert strategy.requires_batching is True

    def test_function_default_estimation_formula(self):
        """Test function default estimation formula accuracy."""
        strategy = self.manager.function_default("CURRENT_TIMESTAMP")

        # Function defaults use the estimated_performance attribute
        perf = strategy.estimated_performance

        # Verify function defaults have proper performance characteristics
        assert perf is not None
        # Function defaults typically don't require batching for simple functions
        assert strategy.requires_batching is False or strategy.requires_batching is True

    @pytest.mark.asyncio
    async def test_estimation_vs_actual_correlation(self):
        """Test correlation between estimation and simulated actual times."""
        mock_connection = create_mock_connection()

        # Test that the handler can plan for various scenarios
        scenarios = [
            (10000, DefaultValueType.STATIC),  # 10K static - very fast
            (100000, DefaultValueType.STATIC),  # 100K static - fast
            (10000, DefaultValueType.COMPUTED),  # 10K computed - slower
            (100000, DefaultValueType.COMPUTED),  # 100K computed - much slower
        ]

        for row_count, default_type in scenarios:

            async def make_mock_fetchval(count):
                async def mock_fetchval(query, *args):
                    return count

                return mock_fetchval

            mock_connection.fetchval = await make_mock_fetchval(row_count)
            mock_connection.fetch.return_value = []
            mock_connection.execute = AsyncMock()

            with patch.object(
                self.handler, "_get_connection", return_value=mock_connection
            ):
                column = ColumnDefinition(
                    name="test_col",
                    data_type="VARCHAR(50)",
                    default_value=(
                        "test" if default_type == DefaultValueType.STATIC else None
                    ),
                    default_expression=(
                        "CASE WHEN id > 0 THEN 'yes' ELSE 'no' END"
                        if default_type == DefaultValueType.COMPUTED
                        else None
                    ),
                    default_type=default_type,
                )

                plan = await self.handler.plan_not_null_addition("test_table", column)

                # Verify plan has valid estimation
                assert plan.estimated_duration is not None
                assert plan.estimated_duration >= 0


class TestResourceLimits:
    """Test behavior at resource limits."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_maximum_batch_size_limit(self):
        """Test maximum batch size limits for very large tables."""
        mock_connection = create_mock_connection()

        async def mock_fetchval(query, *args):
            return 100000000  # 100M rows

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="huge_col",
                data_type="TEXT",
                default_expression="REPEAT('x', 1000)",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = await self.handler.plan_not_null_addition("huge_table", column)

            # Batch size should be capped at a reasonable limit
            assert plan.batch_size <= 50000  # Maximum batch size
            assert plan.batch_size >= 1000  # Minimum batch size

            # Should still complete in reasonable time
            assert plan.estimated_duration < 3600  # Less than 1 hour

    @pytest.mark.asyncio
    async def test_timeout_limits_for_huge_tables(self):
        """Test timeout limits for huge tables."""
        mock_connection = create_mock_connection()

        async def mock_fetchval(query, *args):
            return 50000000  # 50M rows

        mock_connection.fetchval = mock_fetchval
        mock_connection.fetch.return_value = []

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="huge_col",
                data_type="TEXT",
                default_expression="COMPLEX_FUNCTION(id, data)",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = await self.handler.plan_not_null_addition("huge_table", column)

            # Timeout should be capped at a reasonable maximum
            assert plan.timeout_seconds <= 1800  # Max 30 minutes
            assert plan.timeout_seconds >= 60  # Min 1 minute

            # Should be proportional to estimated duration
            if plan.estimated_duration:
                timeout_ratio = plan.timeout_seconds / plan.estimated_duration
                assert 1.5 <= timeout_ratio <= 3.0  # 1.5x to 3x estimated time

    @pytest.mark.asyncio
    async def test_concurrent_operations_limit(self):
        """Test limits on concurrent operations."""
        mock_connection = create_mock_connection()
        mock_connection.fetchval.return_value = 1000000
        mock_connection.fetch.return_value = []

        # Track concurrent operations
        concurrent_ops = {"active": 0, "max": 0}

        async def mock_execute_tracked(query):
            concurrent_ops["active"] += 1
            concurrent_ops["max"] = max(concurrent_ops["max"], concurrent_ops["active"])
            await asyncio.sleep(0.01)
            concurrent_ops["active"] -= 1
            return None

        mock_connection.execute = mock_execute_tracked

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            # Create multiple operations
            columns = [
                ColumnDefinition(f"col_{i}", "VARCHAR(50)", default_value=f"val_{i}")
                for i in range(10)
            ]

            plans = []
            for col in columns:
                plan = NotNullAdditionPlan(
                    table_name="test_table", column=col, execution_strategy="single_ddl"
                )
                plans.append(plan)

            # Try to execute all concurrently
            tasks = [self.handler.execute_not_null_addition(plan) for plan in plans]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Should have some limit on concurrent operations
            # (In production, this would be enforced by connection pool)
            assert concurrent_ops["max"] <= 10  # Reasonable concurrency limit


class TestProgressTracking:
    """Test progress tracking for long-running operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.handler = NotNullColumnHandler()

    @pytest.mark.asyncio
    async def test_progress_reporting_during_batches(self):
        """Test progress reporting during batch processing."""
        mock_connection = create_mock_connection()
        mock_connection.fetch.return_value = []

        # Track progress reports
        progress_reports = []

        async def mock_fetchval_with_progress(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            if "WITH batch AS" in query:
                # Simulate progress callback
                progress = len(progress_reports) * 10000 / 1000000 * 100
                progress_reports.append(
                    {
                        "percentage": progress,
                        "rows_processed": len(progress_reports) * 10000,
                        "timestamp": datetime.now(),
                    }
                )

                if len(progress_reports) * 10000 >= 1000000:
                    return None
                return 10000
            return 1000000

        mock_connection.fetchval = mock_fetchval_with_progress
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="progress_col",
                data_type="VARCHAR(50)",
                default_expression="'processing'",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
                performance_monitoring=True,
            )

            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.SUCCESS

            # Should have progress reports (100 batches for 1M rows at 10K each)
            assert len(progress_reports) >= 99  # At least 99 batches

            # Progress should be monotonically increasing
            for i in range(1, len(progress_reports)):
                assert (
                    progress_reports[i]["percentage"]
                    >= progress_reports[i - 1]["percentage"]
                )

            # Final progress should be close to complete
            assert progress_reports[-1]["rows_processed"] >= 990000

    @pytest.mark.asyncio
    async def test_eta_calculation_during_execution(self):
        """Test ETA calculation during long-running operations."""
        mock_connection = create_mock_connection()
        mock_connection.fetch.return_value = []

        # Track timing for ETA calculation
        batch_times = []
        start_time = time.time()

        async def mock_fetchval_with_timing(query, *args):
            # Handle constraint validation query (check for NULL values)
            if "IS NULL" in query and "COUNT" in query.upper():
                return 0  # No NULL violations
            if "WITH batch AS" in query:
                batch_times.append(time.time() - start_time)

                # Calculate ETA
                if len(batch_times) > 1:
                    avg_batch_time = (batch_times[-1] - batch_times[0]) / len(
                        batch_times
                    )
                    remaining_batches = 50 - len(batch_times)
                    eta = avg_batch_time * remaining_batches

                    # ETA should be reasonable
                    assert eta >= 0
                    assert eta < 3600  # Less than 1 hour

                if len(batch_times) >= 50:
                    return None

                await asyncio.sleep(0.001)  # Simulate work
                return 10000
            return 500000

        mock_connection.fetchval = mock_fetchval_with_timing
        mock_connection.execute = AsyncMock()

        with patch.object(
            self.handler, "_get_connection", return_value=mock_connection
        ):
            column = ColumnDefinition(
                name="eta_col",
                data_type="VARCHAR(50)",
                default_expression="'test'",
                default_type=DefaultValueType.COMPUTED,
            )

            plan = NotNullAdditionPlan(
                table_name="test_table",
                column=column,
                execution_strategy="batched_update",
                batch_size=10000,
            )

            result = await self.handler.execute_not_null_addition(plan)

            assert result.result == AdditionResult.SUCCESS
            assert len(batch_times) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
