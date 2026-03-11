#!/usr/bin/env python3
"""
Unit tests for PerformanceValidator utilities - Phase 2

Tests the performance validation utilities including baseline establishment,
benchmark execution, and performance comparison logic.

TIER 1 REQUIREMENTS:
- Fast execution (<1 second per test)
- Mock database connections and query executions
- Test all performance validation methods and edge cases
- Focus on performance calculation and comparison logic
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the components we'll be testing (to be implemented)
from dataflow.migrations.performance_validator import (
    PerformanceBaseline,
    PerformanceBenchmark,
    PerformanceComparison,
    PerformanceMetrics,
    PerformanceThreshold,
    PerformanceValidationConfig,
    PerformanceValidator,
    QueryPerformanceResult,
)

# Import existing components to mock
from dataflow.migrations.staging_environment_manager import StagingEnvironment


class TestPerformanceValidator:
    """Test suite for PerformanceValidator core functionality."""

    @pytest.fixture
    def performance_config(self):
        """Standard performance validation configuration."""
        return PerformanceValidationConfig(
            baseline_queries=[
                "SELECT COUNT(*) FROM users",
                "SELECT * FROM users WHERE active = true LIMIT 100",
                "SELECT u.*, o.order_count FROM users u LEFT JOIN (SELECT user_id, COUNT(*) as order_count FROM orders GROUP BY user_id) o ON u.id = o.user_id",
            ],
            performance_degradation_threshold=0.20,  # 20%
            baseline_execution_runs=3,
            benchmark_execution_runs=3,
            timeout_seconds=30,
            memory_threshold_mb=512,
            cpu_threshold_percent=80,
        )

    @pytest.fixture
    def performance_validator(self, performance_config):
        """Create PerformanceValidator instance."""
        return PerformanceValidator(config=performance_config)

    @pytest.fixture
    def mock_staging_environment(self):
        """Mock staging environment."""
        from dataflow.migrations.staging_environment_manager import (
            ProductionDatabase,
            StagingDatabase,
        )

        # Create mock staging database object
        mock_staging_db = Mock(spec=StagingDatabase)
        mock_staging_db.host = "localhost"
        mock_staging_db.port = 5433
        mock_staging_db.database = "test_staging_db"
        mock_staging_db.user = "test_user"
        mock_staging_db.password = "test_password"

        # Create mock production database object
        mock_production_db = Mock(spec=ProductionDatabase)
        mock_production_db.host = "localhost"
        mock_production_db.port = 5432
        mock_production_db.database = "production_db"
        mock_production_db.user = "prod_user"
        mock_production_db.password = "prod_password"

        # Create staging environment with proper structure
        staging_env = Mock(spec=StagingEnvironment)
        staging_env.staging_id = "test_staging_001"
        staging_env.staging_db = mock_staging_db
        staging_env.production_db = mock_production_db

        return staging_env

    def test_performance_validator_initialization(
        self, performance_validator, performance_config
    ):
        """Test performance validator initialization."""
        assert performance_validator.config == performance_config
        assert performance_validator.config.performance_degradation_threshold == 0.20
        assert len(performance_validator.config.baseline_queries) == 3

    def test_performance_validator_invalid_config(self):
        """Test performance validator with invalid configuration."""
        with pytest.raises(ValueError, match="Configuration cannot be None"):
            PerformanceValidator(config=None)

        # Test invalid threshold
        with pytest.raises(
            ValueError, match="Performance degradation threshold must be positive"
        ):
            config = PerformanceValidationConfig(performance_degradation_threshold=-0.1)
            PerformanceValidator(config=config)

        # Test invalid execution runs
        with pytest.raises(ValueError, match="Execution runs must be positive"):
            config = PerformanceValidationConfig(baseline_execution_runs=0)
            PerformanceValidator(config=config)

    @pytest.mark.asyncio
    async def test_establish_baseline_success(
        self, performance_validator, mock_staging_environment
    ):
        """Test successful baseline establishment."""
        # Mock query execution
        with patch.object(
            performance_validator, "_execute_query_with_metrics"
        ) as mock_execute:
            mock_execute.side_effect = [
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.1,
                    rows_returned=1,
                    memory_used_mb=10.5,
                    cpu_percent=15.0,
                ),
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.11,
                    rows_returned=1,
                    memory_used_mb=10.2,
                    cpu_percent=14.5,
                ),
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.09,
                    rows_returned=1,
                    memory_used_mb=10.8,
                    cpu_percent=15.5,
                ),
            ]

            baseline = await performance_validator.establish_baseline(
                staging_environment=mock_staging_environment,
                queries=["SELECT COUNT(*) FROM users"],
            )

        assert isinstance(baseline, PerformanceBaseline)
        assert "SELECT COUNT(*) FROM users" in baseline.query_baselines

        query_baseline = baseline.query_baselines["SELECT COUNT(*) FROM users"]
        assert query_baseline.avg_execution_time == 0.1  # (0.1 + 0.11 + 0.09) / 3
        assert query_baseline.max_execution_time == 0.11
        assert query_baseline.min_execution_time == 0.09
        assert mock_execute.call_count == 3

    @pytest.mark.asyncio
    async def test_establish_baseline_query_failure(
        self, performance_validator, mock_staging_environment
    ):
        """Test baseline establishment with query failure."""
        # Mock query execution failure
        with patch.object(
            performance_validator, "_execute_query_with_metrics"
        ) as mock_execute:
            mock_execute.side_effect = Exception("Table does not exist")

            with pytest.raises(Exception, match="Table does not exist"):
                await performance_validator.establish_baseline(
                    staging_environment=mock_staging_environment,
                    queries=["SELECT COUNT(*) FROM nonexistent_table"],
                )

    @pytest.mark.asyncio
    async def test_run_benchmark_success(
        self, performance_validator, mock_staging_environment
    ):
        """Test successful benchmark execution."""
        # Create baseline
        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001",
            query_baselines={
                "SELECT COUNT(*) FROM users": PerformanceMetrics(
                    avg_execution_time=0.1,
                    max_execution_time=0.11,
                    min_execution_time=0.09,
                    avg_memory_mb=10.5,
                    avg_cpu_percent=15.0,
                    sample_count=3,
                )
            },
            established_at=datetime.now(),
        )

        # Mock benchmark query execution
        with patch.object(
            performance_validator, "_execute_query_with_metrics"
        ) as mock_execute:
            mock_execute.side_effect = [
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.12,  # Slightly slower
                    rows_returned=1,
                    memory_used_mb=11.0,
                    cpu_percent=16.0,
                ),
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.13,
                    rows_returned=1,
                    memory_used_mb=10.8,
                    cpu_percent=15.8,
                ),
                QueryPerformanceResult(
                    query="SELECT COUNT(*) FROM users",
                    execution_time_seconds=0.11,
                    rows_returned=1,
                    memory_used_mb=11.2,
                    cpu_percent=16.2,
                ),
            ]

            benchmark = await performance_validator.run_benchmark(
                staging_environment=mock_staging_environment, baseline=baseline
            )

        assert isinstance(benchmark, PerformanceBenchmark)
        assert "SELECT COUNT(*) FROM users" in benchmark.query_benchmarks

        query_benchmark = benchmark.query_benchmarks["SELECT COUNT(*) FROM users"]
        assert query_benchmark.avg_execution_time == 0.12  # (0.12 + 0.13 + 0.11) / 3
        assert mock_execute.call_count == 3

    @pytest.mark.asyncio
    async def test_compare_performance_acceptable(self, performance_validator):
        """Test performance comparison with acceptable degradation."""
        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001",
            query_baselines={
                "SELECT COUNT(*) FROM users": PerformanceMetrics(
                    avg_execution_time=0.1,
                    max_execution_time=0.11,
                    min_execution_time=0.09,
                    avg_memory_mb=10.5,
                    avg_cpu_percent=15.0,
                    sample_count=3,
                )
            },
        )

        benchmark = PerformanceBenchmark(
            staging_environment_id="test_staging_001",
            query_benchmarks={
                "SELECT COUNT(*) FROM users": PerformanceMetrics(
                    avg_execution_time=0.11,  # 10% slower - acceptable
                    max_execution_time=0.12,
                    min_execution_time=0.10,
                    avg_memory_mb=11.0,
                    avg_cpu_percent=16.0,
                    sample_count=3,
                )
            },
        )

        comparison = performance_validator.compare_performance(baseline, benchmark)

        assert isinstance(comparison, PerformanceComparison)
        assert comparison.is_acceptable_performance is True
        assert (
            abs(comparison.overall_degradation_percent - 10.0) < 0.01
        )  # (0.11 - 0.1) / 0.1 * 100
        assert abs(comparison.worst_degradation_percent - 10.0) < 0.01

    @pytest.mark.asyncio
    async def test_compare_performance_unacceptable(self, performance_validator):
        """Test performance comparison with unacceptable degradation."""
        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001",
            query_baselines={
                "SELECT COUNT(*) FROM users": PerformanceMetrics(
                    avg_execution_time=0.1,
                    avg_memory_mb=10.5,
                    avg_cpu_percent=15.0,
                    sample_count=3,
                )
            },
        )

        benchmark = PerformanceBenchmark(
            staging_environment_id="test_staging_001",
            query_benchmarks={
                "SELECT COUNT(*) FROM users": PerformanceMetrics(
                    avg_execution_time=0.15,  # 50% slower - unacceptable (> 20% threshold)
                    avg_memory_mb=15.0,  # 43% more memory
                    avg_cpu_percent=25.0,  # 67% more CPU
                    sample_count=3,
                )
            },
        )

        comparison = performance_validator.compare_performance(baseline, benchmark)

        assert comparison.is_acceptable_performance is False
        assert abs(comparison.overall_degradation_percent - 50.0) < 0.01
        assert abs(comparison.worst_degradation_percent - 50.0) < 0.01
        assert len(comparison.degraded_queries) == 1

    @pytest.mark.asyncio
    async def test_validate_performance_full_workflow(
        self, performance_validator, mock_staging_environment
    ):
        """Test complete performance validation workflow."""
        migration_info = {"table_name": "users", "column_name": "indexed_field"}

        # Mock query execution for baseline and benchmark
        # We have 3 queries, each runs 3 times for baseline and 3 times for benchmark
        baseline_results = [
            # Query 1 baseline runs (3 times)
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.1, 1, 10.0, 15.0),
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.11, 1, 10.2, 14.8),
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.09, 1, 9.8, 15.2),
            # Query 2 baseline runs (3 times)
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.2,
                100,
                12.0,
                18.0,
            ),
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.21,
                100,
                12.1,
                17.9,
            ),
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.19,
                100,
                11.9,
                18.1,
            ),
            # Query 3 baseline runs (3 times)
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.3, 50, 15.0, 20.0
            ),
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.31, 50, 15.1, 19.9
            ),
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.29, 50, 14.9, 20.1
            ),
        ]

        benchmark_results = [
            # Query 1 benchmark runs (3 times)
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.12, 1, 11.0, 16.0),
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.13, 1, 10.8, 15.8),
            QueryPerformanceResult("SELECT COUNT(*) FROM users", 0.11, 1, 11.2, 16.2),
            # Query 2 benchmark runs (3 times)
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.22,
                100,
                13.0,
                19.0,
            ),
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.23,
                100,
                12.9,
                18.9,
            ),
            QueryPerformanceResult(
                "SELECT * FROM users WHERE active = true LIMIT 100",
                0.21,
                100,
                13.1,
                19.1,
            ),
            # Query 3 benchmark runs (3 times)
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.33, 50, 16.0, 22.0
            ),
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.34, 50, 15.9, 21.9
            ),
            QueryPerformanceResult(
                "SELECT u.*, o.order_count FROM users u LEFT JOIN", 0.32, 50, 16.1, 22.1
            ),
        ]

        from unittest.mock import AsyncMock

        # Create AsyncMock that returns the results in sequence
        async def mock_execute(*args, **kwargs):
            if not hasattr(mock_execute, "call_count"):
                mock_execute.call_count = 0
            result = (baseline_results + benchmark_results)[mock_execute.call_count]
            mock_execute.call_count += 1
            return result

        with patch.object(
            performance_validator, "_execute_query_with_metrics", new=mock_execute
        ):

            comparison = await performance_validator.validate_performance(
                staging_environment=mock_staging_environment,
                migration_info=migration_info,
            )

        assert isinstance(comparison, PerformanceComparison)
        assert (
            comparison.is_acceptable_performance is True
        )  # ~20% degradation, at threshold
        assert (
            mock_execute.call_count == 18
        )  # 3 queries * 3 baseline runs + 3 queries * 3 benchmark runs

    @pytest.mark.asyncio
    async def test_execute_query_with_metrics_success(
        self, performance_validator, mock_staging_environment
    ):
        """Test query execution with performance metrics collection."""
        query = "SELECT COUNT(*) FROM users"

        # Mock database connection and execution
        mock_connection = AsyncMock()
        mock_connection.fetch = AsyncMock(return_value=[{"count": 1000}])

        with patch("asyncpg.connect", return_value=mock_connection):
            # Use a counter to simulate time progression
            time_counter = [1000.0]

            def mock_time():
                current = time_counter[0]
                time_counter[0] += 0.05  # Each call advances time
                return current

            with patch(
                "time.time", side_effect=mock_time
            ):  # Simulates time progression
                with patch("psutil.virtual_memory") as mock_memory:
                    mock_memory.return_value.used = 1024 * 1024 * 100  # 100MB

                    with patch("psutil.cpu_percent", return_value=25.0):
                        result = (
                            await performance_validator._execute_query_with_metrics(
                                staging_environment=mock_staging_environment,
                                query=query,
                            )
                        )

        assert isinstance(result, QueryPerformanceResult)
        assert result.query == query
        assert abs(result.execution_time_seconds - 0.1) < 0.01
        assert result.rows_returned == 1
        assert result.cpu_percent == 25.0

    @pytest.mark.asyncio
    async def test_execute_query_with_metrics_timeout(
        self, performance_validator, mock_staging_environment
    ):
        """Test query execution timeout handling."""
        query = "SELECT * FROM large_table"

        # Mock connection that times out
        mock_connection = AsyncMock()
        mock_connection.fetch = AsyncMock(
            side_effect=asyncio.TimeoutError("Query timeout")
        )

        with patch("asyncpg.connect", return_value=mock_connection):
            with pytest.raises(asyncio.TimeoutError, match="Query timeout"):
                await performance_validator._execute_query_with_metrics(
                    staging_environment=mock_staging_environment, query=query
                )

    @pytest.mark.asyncio
    async def test_multiple_queries_baseline(
        self, performance_validator, mock_staging_environment
    ):
        """Test baseline establishment with multiple queries."""
        queries = [
            "SELECT COUNT(*) FROM users",
            "SELECT * FROM users LIMIT 10",
            "SELECT u.*, p.name FROM users u JOIN profiles p ON u.id = p.user_id",
        ]

        # Mock query execution for all queries and runs
        mock_results = []
        for query in queries:
            for run in range(3):  # 3 runs per query
                mock_results.append(
                    QueryPerformanceResult(
                        query=query,
                        execution_time_seconds=0.1
                        + run * 0.01,  # Vary execution time slightly
                        rows_returned=10,
                        memory_used_mb=10.0 + run,
                        cpu_percent=15.0 + run,
                    )
                )

        with patch.object(
            performance_validator, "_execute_query_with_metrics"
        ) as mock_execute:
            mock_execute.side_effect = mock_results

            baseline = await performance_validator.establish_baseline(
                staging_environment=mock_staging_environment, queries=queries
            )

        assert len(baseline.query_baselines) == 3
        assert mock_execute.call_count == 9  # 3 queries * 3 runs each

        # Verify each query has baseline metrics
        for query in queries:
            assert query in baseline.query_baselines
            metrics = baseline.query_baselines[query]
            assert metrics.sample_count == 3
            assert metrics.avg_execution_time > 0

    def test_performance_threshold_validation(self):
        """Test PerformanceThreshold validation logic."""
        threshold = PerformanceThreshold(
            execution_time_degradation_percent=20.0,
            memory_increase_percent=30.0,
            cpu_increase_percent=40.0,
        )

        # Test acceptable performance
        assert threshold.is_execution_time_acceptable(0.1, 0.11) is True  # 10% increase
        assert threshold.is_memory_usage_acceptable(100, 120) is True  # 20% increase
        assert threshold.is_cpu_usage_acceptable(20, 25) is True  # 25% increase

        # Test unacceptable performance
        assert (
            threshold.is_execution_time_acceptable(0.1, 0.13) is False
        )  # 30% increase
        assert threshold.is_memory_usage_acceptable(100, 140) is False  # 40% increase
        assert threshold.is_cpu_usage_acceptable(20, 30) is False  # 50% increase

    def test_performance_metrics_calculations(self):
        """Test PerformanceMetrics calculation methods."""
        metrics = PerformanceMetrics(
            avg_execution_time=0.15,
            max_execution_time=0.20,
            min_execution_time=0.10,
            avg_memory_mb=50.0,
            avg_cpu_percent=30.0,
            sample_count=5,
        )

        assert metrics.avg_execution_time == 0.15
        assert metrics.execution_time_variance == 0.10  # max - min
        assert (
            metrics.is_consistent_performance(variance_threshold=0.05) is False
        )  # High variance
        assert (
            metrics.is_consistent_performance(variance_threshold=0.70) is True
        )  # Acceptable variance (0.10/0.15 = 0.666)


class TestPerformanceValidationConfig:
    """Test suite for PerformanceValidationConfig."""

    def test_config_creation_valid(self):
        """Test valid configuration creation."""
        config = PerformanceValidationConfig(
            baseline_queries=["SELECT 1", "SELECT COUNT(*) FROM users"],
            performance_degradation_threshold=0.25,
            baseline_execution_runs=5,
            benchmark_execution_runs=3,
            timeout_seconds=60,
        )

        assert len(config.baseline_queries) == 2
        assert config.performance_degradation_threshold == 0.25
        assert config.baseline_execution_runs == 5
        assert config.benchmark_execution_runs == 3
        assert config.timeout_seconds == 60

    def test_config_validation_invalid_threshold(self):
        """Test configuration validation with invalid threshold."""
        with pytest.raises(
            ValueError, match="Performance degradation threshold must be positive"
        ):
            PerformanceValidationConfig(performance_degradation_threshold=0.0)

        with pytest.raises(
            ValueError, match="Performance degradation threshold must be positive"
        ):
            PerformanceValidationConfig(performance_degradation_threshold=-0.1)

    def test_config_validation_invalid_runs(self):
        """Test configuration validation with invalid execution runs."""
        with pytest.raises(ValueError, match="Execution runs must be positive"):
            PerformanceValidationConfig(baseline_execution_runs=0)

        with pytest.raises(ValueError, match="Execution runs must be positive"):
            PerformanceValidationConfig(benchmark_execution_runs=-1)

    def test_config_validation_empty_queries(self):
        """Test configuration validation with empty queries."""
        with pytest.raises(ValueError, match="Baseline queries cannot be empty"):
            PerformanceValidationConfig(baseline_queries=[])

    def test_config_defaults(self):
        """Test configuration default values."""
        config = PerformanceValidationConfig()

        # Test that defaults are set appropriately
        assert config.performance_degradation_threshold > 0
        assert config.baseline_execution_runs >= 1
        assert config.benchmark_execution_runs >= 1
        assert config.timeout_seconds > 0
        assert len(config.baseline_queries) > 0


class TestPerformanceBaseline:
    """Test suite for PerformanceBaseline."""

    def test_baseline_creation(self):
        """Test baseline creation and validation."""
        query_baselines = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.1, sample_count=3
            )
        }

        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001",
            query_baselines=query_baselines,
            established_at=datetime.now(),
        )

        assert baseline.staging_environment_id == "test_staging_001"
        assert len(baseline.query_baselines) == 1
        assert baseline.established_at is not None

    def test_baseline_query_lookup(self):
        """Test baseline query lookup functionality."""
        query_baselines = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.1, sample_count=3
            ),
            "SELECT * FROM users LIMIT 10": PerformanceMetrics(
                avg_execution_time=0.05, sample_count=3
            ),
        }

        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001", query_baselines=query_baselines
        )

        # Test successful query lookup
        metrics = baseline.get_query_baseline("SELECT COUNT(*) FROM users")
        assert metrics.avg_execution_time == 0.1

        # Test non-existent query lookup
        missing_metrics = baseline.get_query_baseline("SELECT * FROM nonexistent")
        assert missing_metrics is None

    def test_baseline_age_calculation(self):
        """Test baseline age calculation."""
        past_time = datetime.now() - timedelta(hours=2)
        baseline = PerformanceBaseline(
            staging_environment_id="test_staging_001",
            query_baselines={},
            established_at=past_time,
        )

        age_seconds = baseline.get_age_seconds()
        assert age_seconds >= 7200  # At least 2 hours (7200 seconds)

        age_hours = baseline.get_age_hours()
        assert age_hours >= 2.0


class TestPerformanceBenchmark:
    """Test suite for PerformanceBenchmark."""

    def test_benchmark_creation(self):
        """Test benchmark creation and validation."""
        query_benchmarks = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.12, sample_count=3
            )
        }

        benchmark = PerformanceBenchmark(
            staging_environment_id="test_staging_001",
            query_benchmarks=query_benchmarks,
            executed_at=datetime.now(),
        )

        assert benchmark.staging_environment_id == "test_staging_001"
        assert len(benchmark.query_benchmarks) == 1
        assert benchmark.executed_at is not None

    def test_benchmark_comparison_compatibility(self):
        """Test benchmark compatibility with baseline for comparison."""
        baseline_queries = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.1, sample_count=3
            ),
            "SELECT * FROM users LIMIT 10": PerformanceMetrics(
                avg_execution_time=0.05, sample_count=3
            ),
        }

        # Compatible benchmark (same queries)
        compatible_benchmark_queries = {
            "SELECT COUNT(*) FROM users": PerformanceMetrics(
                avg_execution_time=0.12, sample_count=3
            ),
            "SELECT * FROM users LIMIT 10": PerformanceMetrics(
                avg_execution_time=0.06, sample_count=3
            ),
        }

        baseline = PerformanceBaseline("test_staging_001", baseline_queries)
        compatible_benchmark = PerformanceBenchmark(
            "test_staging_001", compatible_benchmark_queries
        )

        # Should have matching queries
        baseline_query_keys = set(baseline.query_baselines.keys())
        benchmark_query_keys = set(compatible_benchmark.query_benchmarks.keys())
        assert baseline_query_keys == benchmark_query_keys


class TestPerformanceComparison:
    """Test suite for PerformanceComparison."""

    def test_comparison_creation(self):
        """Test performance comparison creation."""
        comparison = PerformanceComparison(
            baseline_environment_id="test_baseline",
            benchmark_environment_id="test_benchmark",
            overall_degradation_percent=15.0,
            worst_degradation_percent=25.0,
            is_acceptable_performance=True,
            degraded_queries=["SELECT * FROM large_table"],
            comparison_timestamp=datetime.now(),
        )

        assert comparison.overall_degradation_percent == 15.0
        assert comparison.worst_degradation_percent == 25.0
        assert comparison.is_acceptable_performance is True
        assert len(comparison.degraded_queries) == 1

    def test_comparison_acceptance_logic(self):
        """Test performance comparison acceptance logic."""
        # Acceptable performance (under threshold)
        acceptable_comparison = PerformanceComparison(
            baseline_environment_id="test",
            benchmark_environment_id="test",
            overall_degradation_percent=10.0,
            worst_degradation_percent=15.0,
            is_acceptable_performance=True,
            degraded_queries=[],
        )

        # Unacceptable performance (over threshold)
        unacceptable_comparison = PerformanceComparison(
            baseline_environment_id="test",
            benchmark_environment_id="test",
            overall_degradation_percent=35.0,
            worst_degradation_percent=50.0,
            is_acceptable_performance=False,
            degraded_queries=[
                "SELECT * FROM large_table",
                "SELECT COUNT(*) FROM orders",
            ],
        )

        assert acceptable_comparison.is_acceptable_performance is True
        assert len(acceptable_comparison.degraded_queries) == 0

        assert unacceptable_comparison.is_acceptable_performance is False
        assert len(unacceptable_comparison.degraded_queries) == 2

    def test_comparison_summary_generation(self):
        """Test performance comparison summary generation."""
        comparison = PerformanceComparison(
            baseline_environment_id="test_baseline",
            benchmark_environment_id="test_benchmark",
            overall_degradation_percent=22.5,
            worst_degradation_percent=30.0,
            is_acceptable_performance=False,
            degraded_queries=["SELECT * FROM users WHERE active = true"],
            query_comparisons={
                "SELECT * FROM users WHERE active = true": {
                    "baseline_time": 0.1,
                    "benchmark_time": 0.13,
                    "degradation_percent": 30.0,
                }
            },
        )

        # Should be able to generate summary information
        assert comparison.overall_degradation_percent > 20.0
        assert comparison.worst_degradation_percent == 30.0
        assert comparison.is_acceptable_performance is False
        assert "SELECT * FROM users WHERE active = true" in comparison.degraded_queries
