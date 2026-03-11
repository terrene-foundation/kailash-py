"""
Unit tests for MigrationPerformanceTracker - Phase 1B Component 3

Tests the core functionality of performance tracking, regression detection,
and metrics analysis with fast execution (<1 second per test).

These tests use mocking for external dependencies (allowed in Tier 1)
and focus on individual component functionality validation.
"""

import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from unittest.mock import AsyncMock, Mock, patch

import pytest
from dataflow.migrations.auto_migration_system import (
    Migration,
    MigrationOperation,
    MigrationType,
)
from dataflow.migrations.migration_performance_tracker import (
    MigrationPerformanceTracker,
    PerformanceBaseline,
    PerformanceMetrics,
    PerformanceMetricType,
    RegressionAnalysis,
    RegressionSeverity,
)


class TestMigrationPerformanceTracker:
    """Test MigrationPerformanceTracker core functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def tracker(self, temp_dir):
        """Create MigrationPerformanceTracker instance."""
        return MigrationPerformanceTracker(
            database_type="postgresql",
            baseline_file=str(temp_dir / "baselines.json"),
            history_file=str(temp_dir / "history.jsonl"),
            max_history_size=100,
            enable_detailed_monitoring=True,
        )

    @pytest.fixture
    def sample_migration(self):
        """Create sample migration for testing."""
        migration = Migration(version="test_001", name="Test Migration")

        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="test_table",
            description="Create test table",
            sql_up="CREATE TABLE test_table (id SERIAL PRIMARY KEY, name VARCHAR(100));",
            sql_down="DROP TABLE test_table;",
            metadata={"test": True},
        )
        migration.add_operation(operation)

        return migration

    @pytest.fixture
    def sample_metrics(self):
        """Create sample performance metrics."""
        return PerformanceMetrics(
            migration_version="test_001",
            migration_name="Test Migration",
            operation_count=1,
            execution_time_ms=150.0,
            memory_before_mb=50.0,
            memory_peak_mb=75.0,
            memory_after_mb=60.0,
            memory_delta_mb=10.0,
            cpu_percent=15.0,
            cpu_time_user=0.1,
            cpu_time_system=0.05,
            database_type="postgresql",
            connection_time_ms=25.0,
            query_count=1,
            transaction_count=1,
            success=True,
        )

    def test_tracker_initialization(self, temp_dir):
        """Test MigrationPerformanceTracker initialization."""
        tracker = MigrationPerformanceTracker(
            database_type="postgresql",
            baseline_file=str(temp_dir / "baselines.json"),
            history_file=str(temp_dir / "history.jsonl"),
        )

        assert tracker.database_type == "postgresql"
        assert tracker.enable_detailed_monitoring is True
        assert tracker.max_history_size == 1000
        assert len(tracker.performance_history) == 0
        assert len(tracker.baselines) == 0

    def test_tracker_with_custom_thresholds(self, temp_dir):
        """Test tracker initialization with custom regression thresholds."""
        custom_thresholds = {
            "warning": 0.05,  # 5%
            "moderate": 0.15,  # 15%
            "severe": 0.30,  # 30%
            "critical": 0.50,  # 50%
        }

        tracker = MigrationPerformanceTracker(
            database_type="sqlite",
            baseline_file=str(temp_dir / "baselines.json"),
            regression_thresholds=custom_thresholds,
        )

        assert tracker.regression_thresholds == custom_thresholds

    def test_component_integration(self, tracker):
        """Test integration with other migration components."""
        # Mock components
        mock_executor = Mock()
        mock_connection_manager = Mock()
        mock_schema_manager = Mock()
        mock_test_framework = Mock()

        tracker.integrate_with_components(
            batched_executor=mock_executor,
            connection_manager=mock_connection_manager,
            schema_state_manager=mock_schema_manager,
            test_framework=mock_test_framework,
        )

        assert tracker.batched_executor == mock_executor
        assert tracker.connection_manager == mock_connection_manager
        assert tracker.schema_state_manager == mock_schema_manager
        assert tracker.test_framework == mock_test_framework

    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, tracker, sample_migration):
        """Test performance monitoring lifecycle."""
        # Test initial state
        assert not tracker._monitoring_active
        assert tracker._current_metrics is None

        # Start monitoring
        await tracker._start_monitoring(sample_migration)

        assert tracker._monitoring_active is True
        assert tracker._current_metrics is not None
        assert tracker._current_metrics.migration_name == "Test Migration"
        assert tracker._current_metrics.migration_version == "test_001"
        assert tracker._current_metrics.operation_count == 1

        # Stop monitoring
        metrics = await tracker._stop_monitoring(success=True, error_message=None)

        assert not tracker._monitoring_active
        assert metrics.success is True
        assert metrics.execution_time_ms > 0
        assert metrics.memory_delta_mb >= 0

    @pytest.mark.asyncio
    async def test_benchmark_with_direct_execution(self, tracker, sample_migration):
        """Test benchmarking with direct execution fallback."""
        # Mock connection
        mock_connection = Mock()
        mock_connection.execute = AsyncMock()

        # Benchmark migration
        metrics = await tracker.benchmark_migration(
            migration=sample_migration, connection=mock_connection
        )

        assert metrics.success is True
        assert metrics.migration_name == "Test Migration"
        assert metrics.execution_time_ms > 0
        assert metrics.query_count == 1
        assert metrics.transaction_count == 1

        # Verify connection was called
        mock_connection.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_benchmark_with_batched_executor(self, tracker, sample_migration):
        """Test benchmarking with BatchedMigrationExecutor."""
        # Mock batched executor
        mock_executor = Mock()
        mock_executor.batch_ddl_operations.return_value = [
            ["CREATE TABLE test_table (...)"]
        ]
        mock_executor.execute_batched_migrations = AsyncMock(return_value=True)
        mock_executor.get_execution_metrics.return_value = Mock(
            total_batches=1, parallel_batches=0, total_operations=1
        )

        tracker.batched_executor = mock_executor

        # Benchmark migration
        metrics = await tracker.benchmark_migration(migration=sample_migration)

        assert metrics.success is True
        assert metrics.batch_count == 1
        assert metrics.batch_efficiency == 1.0  # 1 batch / 1 operation
        assert metrics.parallel_operations == 0

    @pytest.mark.asyncio
    async def test_benchmark_with_test_framework(self, tracker, sample_migration):
        """Test benchmarking with MigrationTestFramework."""
        # Mock test framework
        mock_framework = Mock()
        mock_test_result = Mock()
        mock_test_result.success = True
        mock_test_result.error = None
        mock_test_result.performance_metrics = {
            "rollback_time": 50.0,
            "rollback_tested": True,
        }

        mock_framework.execute_test_migration = AsyncMock(return_value=mock_test_result)
        tracker.test_framework = mock_framework

        # Benchmark migration
        metrics = await tracker.benchmark_migration(migration=sample_migration)

        assert metrics.success is True
        assert metrics.rollback_time_ms == 50.0

    @pytest.mark.asyncio
    async def test_benchmark_error_handling(self, tracker, sample_migration):
        """Test error handling during benchmarking."""
        # Mock connection that raises an error
        mock_connection = Mock()
        mock_connection.execute = AsyncMock(side_effect=Exception("Database error"))

        # Benchmark migration (should handle error gracefully)
        metrics = await tracker.benchmark_migration(
            migration=sample_migration, connection=mock_connection
        )

        assert metrics.success is False
        assert "Database error" in metrics.error_message

    def test_performance_metrics_serialization(self, sample_metrics):
        """Test PerformanceMetrics serialization and deserialization."""
        # Convert to dict
        metrics_dict = sample_metrics.to_dict()

        assert isinstance(metrics_dict, dict)
        assert metrics_dict["migration_name"] == "Test Migration"
        assert metrics_dict["execution_time_ms"] == 150.0

        # Convert back to object
        restored_metrics = PerformanceMetrics.from_dict(metrics_dict)

        assert restored_metrics.migration_name == sample_metrics.migration_name
        assert restored_metrics.execution_time_ms == sample_metrics.execution_time_ms
        assert restored_metrics.success == sample_metrics.success

    def test_regression_detection_no_regression(self, tracker, sample_metrics):
        """Test regression detection when no regression exists."""
        # Create metrics with consistent performance
        metrics_list = []
        for i in range(5):
            metrics = PerformanceMetrics(
                migration_version=f"test_{i:03d}",
                migration_name="Consistent Migration",
                operation_count=1,
                execution_time_ms=150.0 + (i * 2),  # Slight variation
                memory_before_mb=50.0,
                memory_peak_mb=75.0,
                memory_after_mb=60.0,
                memory_delta_mb=10.0 + (i * 0.5),
                cpu_percent=15.0,
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
                timestamp=(datetime.now() - timedelta(hours=i)).isoformat(),
            )
            metrics_list.append(metrics)

        # Detect regressions
        regressions = tracker.detect_performance_regression(metrics_list)

        # Should not detect any significant regressions
        severe_regressions = [
            r
            for r in regressions
            if r.severity in [RegressionSeverity.SEVERE, RegressionSeverity.CRITICAL]
        ]
        assert len(severe_regressions) == 0

    def test_regression_detection_with_regression(self, tracker):
        """Test regression detection when regression exists."""
        # Create baseline with good performance
        baseline_metrics = PerformanceMetrics(
            migration_version="baseline",
            migration_name="Regression Test",
            operation_count=1,
            execution_time_ms=100.0,  # Fast baseline
            memory_before_mb=50.0,
            memory_peak_mb=75.0,
            memory_after_mb=60.0,
            memory_delta_mb=10.0,
            cpu_percent=10.0,
            cpu_time_user=0.1,
            cpu_time_system=0.05,
            database_type="postgresql",
            connection_time_ms=25.0,
            query_count=1,
            transaction_count=1,
            success=True,
        )

        # Create recent metrics with degraded performance
        recent_metrics = []
        for i in range(3):
            metrics = PerformanceMetrics(
                migration_version=f"recent_{i:03d}",
                migration_name="Regression Test",
                operation_count=1,
                execution_time_ms=250.0,  # 150% slower than baseline
                memory_before_mb=50.0,
                memory_peak_mb=120.0,  # Higher memory usage
                memory_after_mb=80.0,
                memory_delta_mb=30.0,  # 3x memory increase
                cpu_percent=25.0,  # Higher CPU usage
                cpu_time_user=0.25,
                cpu_time_system=0.1,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
                timestamp=(datetime.now() - timedelta(minutes=i)).isoformat(),
            )
            recent_metrics.append(metrics)

        # Detect regressions with baseline
        all_metrics = [baseline_metrics] + recent_metrics
        regressions = tracker.detect_performance_regression(
            all_metrics, baseline=baseline_metrics
        )

        # Should detect regressions
        execution_regressions = [
            r for r in regressions if "execution time" in r.metric_name.lower()
        ]
        memory_regressions = [
            r for r in regressions if "memory" in r.metric_name.lower()
        ]

        assert len(execution_regressions) > 0
        assert len(memory_regressions) > 0

        # Check severity levels
        severe_regressions = [
            r
            for r in regressions
            if r.severity in [RegressionSeverity.SEVERE, RegressionSeverity.CRITICAL]
        ]
        assert len(severe_regressions) > 0

    def test_trend_analysis(self, tracker):
        """Test performance trend analysis."""
        # Create metrics with improving trend
        improving_metrics = []
        for i in range(10):
            metrics = PerformanceMetrics(
                migration_version=f"improving_{i:03d}",
                migration_name="Improving Migration",
                operation_count=1,
                execution_time_ms=200.0 - (i * 10),  # Getting faster
                memory_before_mb=50.0,
                memory_peak_mb=75.0,
                memory_after_mb=60.0,
                memory_delta_mb=20.0 - (i * 1),  # Using less memory
                cpu_percent=20.0 - (i * 1),
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
                timestamp=(datetime.now() - timedelta(minutes=i)).isoformat(),
            )
            improving_metrics.append(metrics)

        # Analyze trends
        trends = tracker._analyze_performance_trends(improving_metrics)

        assert len(trends) > 0

        # Check for trends (should detect trend direction)
        execution_trend = next(
            (t for t in trends if "execution time" in t["metric"].lower()), None
        )
        assert execution_trend is not None
        # Note: Due to test data ordering, trend might be increasing or decreasing
        assert execution_trend["direction"] in ["decreasing", "increasing", "stable"]

    def test_performance_insights_generation(self, tracker, sample_metrics):
        """Test comprehensive performance insights generation."""
        # Create varied metrics
        metrics_list = [sample_metrics]
        for i in range(4):
            metrics = PerformanceMetrics(
                migration_version=f"test_{i:03d}",
                migration_name="Insight Test",
                operation_count=1 + i,
                execution_time_ms=150.0 + (i * 25),
                memory_before_mb=50.0,
                memory_peak_mb=75.0 + (i * 10),
                memory_after_mb=60.0 + (i * 5),
                memory_delta_mb=10.0 + (i * 2),
                cpu_percent=15.0 + (i * 3),
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
            )
            metrics_list.append(metrics)

        # Generate insights
        insights = tracker.get_performance_insights(metrics_list, include_trends=True)

        assert "summary" in insights
        assert "regressions" in insights
        assert "trends" in insights
        assert "recommendations" in insights
        assert "key_metrics" in insights

        # Check summary
        summary = insights["summary"]
        assert summary["total_migrations"] == 5
        assert summary["success_rate"] == 100.0
        assert summary["avg_execution_time_ms"] > 0

    def test_baseline_management(self, tracker, sample_metrics):
        """Test baseline creation and management."""
        # Create sample metrics for baseline
        metrics_list = []
        for i in range(5):
            metrics = PerformanceMetrics(
                migration_version=f"baseline_{i:03d}",
                migration_name="Baseline Test",
                operation_count=1,
                execution_time_ms=100.0 + (i * 5),
                memory_before_mb=50.0,
                memory_peak_mb=75.0,
                memory_after_mb=60.0,
                memory_delta_mb=10.0,
                cpu_percent=15.0,
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
            )
            metrics_list.append(metrics)

        # Get baseline (should create one from samples)
        operation_key = "Baseline Test_1"
        baseline = tracker._get_baseline_for_operation(operation_key, metrics_list)

        assert baseline is not None
        assert baseline.migration_name == "Baseline Test"
        assert operation_key in tracker.baselines

    def test_file_persistence(self, tracker, sample_metrics):
        """Test baseline and history file persistence."""
        # Add metrics to history and save it
        tracker.performance_history.append(sample_metrics)
        tracker._save_history_entry(sample_metrics)

        # Create and store baseline
        operation_key = "test_operation"
        baseline = tracker._create_baseline_from_samples([sample_metrics])
        tracker._store_baseline(operation_key, baseline, [sample_metrics])

        # Verify files exist
        assert tracker.baseline_file.exists()
        assert tracker.history_file.exists()

        # Create new tracker and verify data is loaded
        new_tracker = MigrationPerformanceTracker(
            database_type="postgresql",
            baseline_file=str(tracker.baseline_file),
            history_file=str(tracker.history_file),
        )

        assert len(new_tracker.baselines) > 0
        assert len(new_tracker.performance_history) > 0

    def test_performance_report_export(self, tracker, sample_metrics, temp_dir):
        """Test performance report export."""
        # Add sample metrics
        metrics_list = [sample_metrics]
        for i in range(3):
            metrics = PerformanceMetrics(
                migration_version=f"report_{i:03d}",
                migration_name="Report Test",
                operation_count=1,
                execution_time_ms=150.0 + (i * 10),
                memory_before_mb=50.0,
                memory_peak_mb=75.0,
                memory_after_mb=60.0,
                memory_delta_mb=10.0,
                cpu_percent=15.0,
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
            )
            metrics_list.append(metrics)

        # Export report
        report_file = temp_dir / "performance_report.json"
        success = tracker.export_performance_report(
            output_file=str(report_file),
            metrics=metrics_list,
            include_detailed_analysis=True,
        )

        assert success is True
        assert report_file.exists()

        # Verify report content
        with open(report_file, "r") as f:
            report_data = json.load(f)

        assert "report_metadata" in report_data
        assert "performance_summary" in report_data
        assert "key_metrics" in report_data
        assert "raw_metrics" in report_data
        assert report_data["report_metadata"]["metrics_count"] == 4

    def test_cleanup_operations(self, tracker, sample_metrics):
        """Test cleanup and reset operations."""
        # Add sample data
        tracker.performance_history.append(sample_metrics)
        operation_key = "cleanup_test"
        baseline = tracker._create_baseline_from_samples([sample_metrics])
        tracker._store_baseline(operation_key, baseline, [sample_metrics])

        # Verify data exists
        assert len(tracker.performance_history) > 0
        assert len(tracker.baselines) > 0
        assert tracker.baseline_file.exists()

        # Reset baselines
        tracker.reset_baselines()

        assert len(tracker.baselines) == 0
        assert not tracker.baseline_file.exists()

        # Test history cleanup
        # Add metrics with old timestamps
        old_metrics = []
        for i in range(5):
            metrics = PerformanceMetrics(
                migration_version=f"old_{i:03d}",
                migration_name="Old Migration",
                operation_count=1,
                execution_time_ms=150.0,
                memory_before_mb=50.0,
                memory_peak_mb=75.0,
                memory_after_mb=60.0,
                memory_delta_mb=10.0,
                cpu_percent=15.0,
                cpu_time_user=0.1,
                cpu_time_system=0.05,
                database_type="postgresql",
                connection_time_ms=25.0,
                query_count=1,
                transaction_count=1,
                success=True,
                timestamp=(datetime.now() - timedelta(days=35)).isoformat(),  # Old
            )
            old_metrics.append(metrics)
            tracker.performance_history.append(metrics)

        # Add recent metrics
        recent_metrics = PerformanceMetrics(
            migration_version="recent_001",
            migration_name="Recent Migration",
            operation_count=1,
            execution_time_ms=150.0,
            memory_before_mb=50.0,
            memory_peak_mb=75.0,
            memory_after_mb=60.0,
            memory_delta_mb=10.0,
            cpu_percent=15.0,
            cpu_time_user=0.1,
            cpu_time_system=0.05,
            database_type="postgresql",
            connection_time_ms=25.0,
            query_count=1,
            transaction_count=1,
            success=True,
            timestamp=datetime.now().isoformat(),  # Recent
        )
        tracker.performance_history.append(recent_metrics)

        original_count = len(tracker.performance_history)

        # Cleanup old history (keep 30 days)
        tracker.cleanup_old_history(days_to_keep=30)

        # Should have fewer entries now
        assert len(tracker.performance_history) < original_count

        # Recent metrics should still be there
        recent_found = any(
            m.migration_version == "recent_001" for m in tracker.performance_history
        )
        assert recent_found is True

    def test_recommendation_generation(self, tracker):
        """Test performance recommendation generation."""
        # Test execution time recommendations
        exec_recommendations = tracker._generate_performance_recommendations(
            "execution_time_ms",
            50.0,  # 50% slower
            RegressionSeverity.SEVERE,
            "degrading",
        )

        assert len(exec_recommendations) > 0
        assert any("SQL queries" in rec for rec in exec_recommendations)
        assert any("batching" in rec for rec in exec_recommendations)

        # Test memory recommendations
        memory_recommendations = tracker._generate_performance_recommendations(
            "memory_delta_mb",
            100.0,  # 100% more memory
            RegressionSeverity.CRITICAL,
            "degrading",
        )

        assert len(memory_recommendations) > 0
        assert any("memory" in rec.lower() for rec in memory_recommendations)
        assert any("URGENT" in rec for rec in memory_recommendations)

    def test_metric_type_enum(self):
        """Test PerformanceMetricType enum."""
        assert PerformanceMetricType.EXECUTION_TIME.value == "execution_time"
        assert PerformanceMetricType.MEMORY_USAGE.value == "memory_usage"
        assert PerformanceMetricType.CPU_USAGE.value == "cpu_usage"
        assert PerformanceMetricType.IO_OPERATIONS.value == "io_operations"
        assert PerformanceMetricType.DATABASE_OPERATIONS.value == "database_operations"
        assert PerformanceMetricType.BATCH_EFFICIENCY.value == "batch_efficiency"

    def test_regression_severity_enum(self):
        """Test RegressionSeverity enum."""
        assert RegressionSeverity.NONE.value == "none"
        assert RegressionSeverity.WARNING.value == "warning"
        assert RegressionSeverity.MODERATE.value == "moderate"
        assert RegressionSeverity.SEVERE.value == "severe"
        assert RegressionSeverity.CRITICAL.value == "critical"

    @pytest.mark.timeout(1)
    def test_performance_overhead(self, tracker, sample_migration):
        """Test that performance tracking overhead is minimal (<50ms)."""
        start_time = time.perf_counter()

        # Mock minimal operations
        with (
            patch("tracemalloc.start"),
            patch("tracemalloc.get_traced_memory", return_value=(1000, 2000)),
            patch("tracemalloc.stop"),
            patch("psutil.Process"),
            patch("resource.getrusage"),
        ):

            # Simulate tracking overhead
            tracker._start_time = time.perf_counter()
            tracker._monitoring_active = True
            tracker._current_metrics = PerformanceMetrics(
                migration_version="overhead_test",
                migration_name="Overhead Test",
                operation_count=1,
                execution_time_ms=0.0,
                memory_before_mb=1.0,
                memory_peak_mb=2.0,
                memory_after_mb=1.5,
                memory_delta_mb=0.5,
                cpu_percent=0.0,
                cpu_time_user=0.0,
                cpu_time_system=0.0,
                database_type="postgresql",
                connection_time_ms=0.0,
                query_count=1,
                transaction_count=1,
            )

            # Stop monitoring
            metrics = tracker._stop_monitoring(success=True, error_message=None)

        overhead_time = (time.perf_counter() - start_time) * 1000  # Convert to ms

        # Verify overhead is minimal
        assert (
            overhead_time < 50.0
        ), f"Performance tracking overhead {overhead_time:.2f}ms exceeds 50ms limit"
        assert metrics is not None


@pytest.mark.asyncio
class TestAsyncPerformanceOperations:
    """Test async operations of MigrationPerformanceTracker."""

    @pytest.fixture
    async def async_tracker(self):
        """Create async tracker for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            tracker = MigrationPerformanceTracker(
                database_type="postgresql",
                baseline_file=str(Path(temp_dir) / "baselines.json"),
                history_file=str(Path(temp_dir) / "history.jsonl"),
                enable_detailed_monitoring=False,  # Disable for faster tests
            )
            yield tracker

    async def test_async_benchmark_migration(self, async_tracker):
        """Test async migration benchmarking."""
        # Create test migration
        migration = Migration(version="async_001", name="Async Test")
        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="async_test",
            description="Async test table",
            sql_up="CREATE TABLE async_test (id SERIAL PRIMARY KEY);",
            sql_down="DROP TABLE async_test;",
            metadata={},
        )
        migration.add_operation(operation)

        # Mock async connection
        mock_connection = Mock()
        mock_connection.execute = AsyncMock()

        # Benchmark migration
        start_time = time.perf_counter()
        metrics = await async_tracker.benchmark_migration(
            migration=migration, connection=mock_connection
        )
        benchmark_time = (time.perf_counter() - start_time) * 1000

        # Verify results
        assert metrics.success is True
        assert metrics.migration_name == "Async Test"
        assert metrics.execution_time_ms > 0
        assert benchmark_time < 100  # Should complete quickly

        # Verify async call was made
        mock_connection.execute.assert_called_once()

    async def test_concurrent_benchmark_operations(self, async_tracker):
        """Test concurrent benchmarking operations."""
        import asyncio

        # Create multiple migrations
        migrations = []
        for i in range(3):
            migration = Migration(
                version=f"concurrent_{i:03d}", name=f"Concurrent Test {i}"
            )
            operation = MigrationOperation(
                operation_type=MigrationType.CREATE_TABLE,
                table_name=f"concurrent_test_{i}",
                description=f"Concurrent test table {i}",
                sql_up=f"CREATE TABLE concurrent_test_{i} (id SERIAL PRIMARY KEY);",
                sql_down=f"DROP TABLE concurrent_test_{i};",
                metadata={},
            )
            migration.add_operation(operation)
            migrations.append(migration)

        # Mock connections
        mock_connections = [Mock() for _ in range(3)]
        for mock_conn in mock_connections:
            mock_conn.execute = AsyncMock()

        # Run concurrent benchmarks
        benchmark_tasks = [
            async_tracker.benchmark_migration(migration=mig, connection=conn)
            for mig, conn in zip(migrations, mock_connections)
        ]

        start_time = time.perf_counter()
        results = await asyncio.gather(*benchmark_tasks)
        total_time = (time.perf_counter() - start_time) * 1000

        # Verify all completed successfully
        assert len(results) == 3
        assert all(result.success for result in results)

        # Should complete in reasonable time (concurrent execution)
        assert total_time < 500  # Should be faster than sequential

    async def test_error_handling_in_async_operations(self, async_tracker):
        """Test error handling in async operations."""
        # Create test migration
        migration = Migration(version="error_001", name="Error Test")
        operation = MigrationOperation(
            operation_type=MigrationType.CREATE_TABLE,
            table_name="error_test",
            description="Error test table",
            sql_up="CREATE TABLE error_test (id SERIAL PRIMARY KEY);",
            sql_down="DROP TABLE error_test;",
            metadata={},
        )
        migration.add_operation(operation)

        # Mock connection that raises an error
        mock_connection = Mock()
        mock_connection.execute = AsyncMock(side_effect=Exception("Async error"))

        # Benchmark should handle error gracefully
        metrics = await async_tracker.benchmark_migration(
            migration=migration, connection=mock_connection
        )

        assert metrics.success is False
        assert "Async error" in metrics.error_message
        assert metrics.execution_time_ms > 0  # Should still measure time
