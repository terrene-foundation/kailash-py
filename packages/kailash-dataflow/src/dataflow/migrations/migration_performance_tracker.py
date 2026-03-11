"""
Migration Performance Tracker - Phase 1B Component 3

Comprehensive performance benchmarking and regression detection for migration operations.
Provides real-time performance measurement, baseline tracking, and actionable insights.

Key Features:
- Real-time performance measurement during migration execution (<50ms overhead)
- Memory usage tracking with minimal overhead (<5MB measurement overhead)
- Regression detection with configurable thresholds (default 20% degradation)
- Historical performance trend analysis
- Integration with Migration Testing Framework and PostgreSQL Test Manager
- Comprehensive benchmarking across migration types
- Performance insights for optimization guidance

This component completes Phase 1B by providing the monitoring and validation
capabilities needed to measure the effectiveness of Phase 1A performance improvements.
"""

import asyncio
import gc
import json
import logging
import os
import resource
import sqlite3
import time
import tracemalloc
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import psutil

try:
    import asyncpg

    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

from .auto_migration_system import Migration, MigrationOperation, MigrationType
from .batched_migration_executor import BatchedMigrationExecutor, BatchMetrics
from .migration_connection_manager import MigrationConnectionManager
from .migration_test_framework import MigrationTestFramework, MigrationTestResult
from .schema_state_manager import SchemaStateManager

logger = logging.getLogger(__name__)


class PerformanceMetricType(Enum):
    """Types of performance metrics tracked."""

    EXECUTION_TIME = "execution_time"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    IO_OPERATIONS = "io_operations"
    DATABASE_OPERATIONS = "database_operations"
    BATCH_EFFICIENCY = "batch_efficiency"


class RegressionSeverity(Enum):
    """Severity levels for performance regressions."""

    NONE = "none"
    WARNING = "warning"  # 10-20% degradation
    MODERATE = "moderate"  # 20-40% degradation
    SEVERE = "severe"  # 40%+ degradation
    CRITICAL = "critical"  # 100%+ degradation


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for a migration operation."""

    # Basic metrics
    migration_version: str
    migration_name: str
    operation_count: int
    execution_time_ms: float

    # Memory metrics
    memory_before_mb: float
    memory_peak_mb: float
    memory_after_mb: float
    memory_delta_mb: float

    # CPU metrics
    cpu_percent: float
    cpu_time_user: float
    cpu_time_system: float

    # Database metrics
    database_type: str
    connection_time_ms: float
    query_count: int
    transaction_count: int

    # Batch performance (if applicable)
    batch_count: Optional[int] = None
    batch_efficiency: Optional[float] = None
    parallel_operations: Optional[int] = None

    # System metrics
    io_read_count: int = 0
    io_write_count: int = 0
    io_read_bytes: int = 0
    io_write_bytes: int = 0

    # Timing breakdown
    preparation_time_ms: float = 0.0
    validation_time_ms: float = 0.0
    rollback_time_ms: float = 0.0

    # Quality metrics
    success: bool = True
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    # Context
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    environment: str = "unknown"
    python_version: str = "unknown"
    postgresql_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PerformanceMetrics":
        """Create metrics from dictionary."""
        return cls(**data)


@dataclass
class RegressionAnalysis:
    """Analysis of performance regression between metrics."""

    metric_name: str
    baseline_value: float
    current_value: float
    change_percent: float
    change_absolute: float
    severity: RegressionSeverity
    threshold_breached: float

    # Trend analysis
    trend_direction: str  # "improving", "degrading", "stable"
    trend_confidence: float  # 0.0 to 1.0

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    def is_regression(self) -> bool:
        """Check if this represents a performance regression."""
        return self.severity != RegressionSeverity.NONE


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression detection."""

    operation_type: str
    baseline_metrics: PerformanceMetrics
    confidence_interval: Dict[str, Tuple[float, float]]
    sample_size: int
    created_at: str
    last_updated: str

    # Thresholds
    warning_threshold: float = 0.10  # 10%
    moderate_threshold: float = 0.20  # 20%
    severe_threshold: float = 0.40  # 40%
    critical_threshold: float = 1.00  # 100%


class MigrationPerformanceTracker:
    """
    Comprehensive performance tracker for DataFlow migration operations.

    Provides real-time performance measurement, regression detection, and
    historical analysis for migration operations with minimal overhead.
    """

    def __init__(
        self,
        database_type: str = "postgresql",
        baseline_file: Optional[str] = None,
        history_file: Optional[str] = None,
        max_history_size: int = 1000,
        enable_detailed_monitoring: bool = True,
        regression_thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize MigrationPerformanceTracker.

        Args:
            database_type: Database type being tracked
            baseline_file: Path to baseline metrics file
            history_file: Path to performance history file
            max_history_size: Maximum number of history entries to keep
            enable_detailed_monitoring: Enable detailed system monitoring
            regression_thresholds: Custom regression thresholds
        """
        self.database_type = database_type
        self.enable_detailed_monitoring = enable_detailed_monitoring
        self.max_history_size = max_history_size

        # File paths
        default_dir = Path(__file__).parent / "performance_data"
        default_dir.mkdir(exist_ok=True)

        self.baseline_file = Path(
            baseline_file or default_dir / "migration_baselines.json"
        )
        self.history_file = Path(
            history_file or default_dir / "migration_history.jsonl"
        )

        # Regression thresholds
        self.regression_thresholds = {
            "warning": 0.10,  # 10%
            "moderate": 0.20,  # 20%
            "severe": 0.40,  # 40%
            "critical": 1.00,  # 100%
        }
        if regression_thresholds:
            self.regression_thresholds.update(regression_thresholds)

        # Performance history for trend analysis
        self.performance_history: deque = deque(maxlen=max_history_size)
        self.baselines: Dict[str, PerformanceBaseline] = {}

        # Current monitoring state
        self._monitoring_active = False
        self._current_metrics: Optional[PerformanceMetrics] = None
        self._start_time: Optional[float] = None
        self._start_memory: Optional[int] = None
        self._start_cpu_times: Optional[Tuple[float, float]] = None
        self._start_io_counters: Optional[Any] = None

        # Component integration
        self.batched_executor: Optional[BatchedMigrationExecutor] = None
        self.connection_manager: Optional[MigrationConnectionManager] = None
        self.schema_state_manager: Optional[SchemaStateManager] = None
        self.test_framework: Optional[MigrationTestFramework] = None

        # Load existing data
        self._load_baselines()
        self._load_history()

        logger.info(f"MigrationPerformanceTracker initialized for {database_type}")

    def integrate_with_components(
        self,
        batched_executor: Optional[BatchedMigrationExecutor] = None,
        connection_manager: Optional[MigrationConnectionManager] = None,
        schema_state_manager: Optional[SchemaStateManager] = None,
        test_framework: Optional[MigrationTestFramework] = None,
    ):
        """
        Integrate with existing migration system components.

        Args:
            batched_executor: Phase 1A BatchedMigrationExecutor
            connection_manager: Phase 1A MigrationConnectionManager
            schema_state_manager: Phase 1A SchemaStateManager
            test_framework: Phase 1B MigrationTestFramework
        """
        self.batched_executor = batched_executor
        self.connection_manager = connection_manager
        self.schema_state_manager = schema_state_manager
        self.test_framework = test_framework

        logger.info("Performance tracker integrated with migration components")

    async def benchmark_migration(
        self,
        migration: Migration,
        connection: Any = None,
        executor_func: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> PerformanceMetrics:
        """
        Benchmark a migration operation with comprehensive performance measurement.

        Args:
            migration: Migration to benchmark
            connection: Database connection (optional)
            executor_func: Custom executor function (optional)
            context: Additional context for measurement

        Returns:
            Comprehensive performance metrics
        """
        logger.info(f"Benchmarking migration: {migration.name} (v{migration.version})")

        # Start performance monitoring
        await self._start_monitoring(migration)

        try:
            # Execute migration with timing
            if executor_func:
                # Use custom executor
                result = await executor_func(migration, connection)
                success = result is not None
                error_message = None
            elif self.batched_executor:
                # Use batched executor
                success = await self._benchmark_with_batched_executor(
                    migration, connection
                )
                error_message = None
            elif self.test_framework:
                # Use test framework
                test_result = await self._benchmark_with_test_framework(
                    migration, connection
                )
                success = test_result.success
                error_message = test_result.error
            else:
                # Direct execution fallback
                try:
                    success = await self._benchmark_direct_execution(
                        migration, connection
                    )
                    error_message = None
                except Exception as direct_error:
                    success = False
                    error_message = str(direct_error)

        except Exception as e:
            logger.error(f"Migration benchmark failed: {e}")
            success = False
            error_message = str(e)

        # Stop monitoring and get metrics
        metrics = await self._stop_monitoring(success, error_message)

        # Add to history
        self.performance_history.append(metrics)
        self._save_history_entry(metrics)

        logger.info(
            f"Migration benchmark completed: {metrics.execution_time_ms:.2f}ms, "
            f"Memory: {metrics.memory_delta_mb:.2f}MB"
        )

        return metrics

    async def _start_monitoring(self, migration: Migration):
        """Start performance monitoring for a migration."""
        if self._monitoring_active:
            logger.warning("Performance monitoring already active")
            return

        self._monitoring_active = True
        self._start_time = time.perf_counter()

        # Memory monitoring
        if self.enable_detailed_monitoring:
            gc.collect()  # Clean up before measurement
            tracemalloc.start()
            self._start_memory = tracemalloc.get_traced_memory()[0]
        else:
            # Lightweight memory tracking
            process = psutil.Process()
            self._start_memory = process.memory_info().rss

        # CPU monitoring
        if self.enable_detailed_monitoring:
            self._start_cpu_times = resource.getrusage(resource.RUSAGE_SELF)
            self._start_io_counters = (
                psutil.Process().io_counters()
                if hasattr(psutil.Process(), "io_counters")
                else None
            )

        # Initialize current metrics
        self._current_metrics = PerformanceMetrics(
            migration_version=migration.version,
            migration_name=migration.name,
            operation_count=len(migration.operations),
            execution_time_ms=0.0,
            memory_before_mb=self._start_memory / (1024 * 1024),
            memory_peak_mb=0.0,
            memory_after_mb=0.0,
            memory_delta_mb=0.0,
            cpu_percent=0.0,
            cpu_time_user=0.0,
            cpu_time_system=0.0,
            database_type=self.database_type,
            connection_time_ms=0.0,
            query_count=0,
            transaction_count=0,
            environment=os.getenv("DATAFLOW_ENV", "development"),
            python_version=f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
        )

    async def _stop_monitoring(
        self, success: bool, error_message: Optional[str]
    ) -> PerformanceMetrics:
        """Stop performance monitoring and return metrics."""
        if not self._monitoring_active:
            raise RuntimeError("Performance monitoring not active")

        end_time = time.perf_counter()
        execution_time_ms = (end_time - self._start_time) * 1000

        # Memory monitoring
        if self.enable_detailed_monitoring and tracemalloc.is_tracing():
            current_memory, peak_memory = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            memory_after_mb = current_memory / (1024 * 1024)
            memory_peak_mb = peak_memory / (1024 * 1024)
            memory_delta_mb = memory_after_mb - self._current_metrics.memory_before_mb
        else:
            # Lightweight memory tracking
            process = psutil.Process()
            current_memory = process.memory_info().rss

            memory_after_mb = current_memory / (1024 * 1024)
            memory_peak_mb = memory_after_mb  # Approximation
            memory_delta_mb = memory_after_mb - self._current_metrics.memory_before_mb

        # CPU monitoring
        cpu_percent = 0.0
        cpu_time_user = 0.0
        cpu_time_system = 0.0

        if self.enable_detailed_monitoring and self._start_cpu_times:
            end_cpu_times = resource.getrusage(resource.RUSAGE_SELF)
            cpu_time_user = end_cpu_times.ru_utime - self._start_cpu_times.ru_utime
            cpu_time_system = end_cpu_times.ru_stime - self._start_cpu_times.ru_stime

            # Estimate CPU percentage
            total_time = execution_time_ms / 1000
            if total_time > 0:
                cpu_percent = ((cpu_time_user + cpu_time_system) / total_time) * 100

        # IO monitoring
        io_read_count = 0
        io_write_count = 0
        io_read_bytes = 0
        io_write_bytes = 0

        if self.enable_detailed_monitoring and self._start_io_counters:
            try:
                end_io_counters = psutil.Process().io_counters()
                io_read_count = (
                    end_io_counters.read_count - self._start_io_counters.read_count
                )
                io_write_count = (
                    end_io_counters.write_count - self._start_io_counters.write_count
                )
                io_read_bytes = (
                    end_io_counters.read_bytes - self._start_io_counters.read_bytes
                )
                io_write_bytes = (
                    end_io_counters.write_bytes - self._start_io_counters.write_bytes
                )
            except Exception:
                # IO counters not available on all systems
                pass

        # Get batch metrics if available
        batch_count = None
        batch_efficiency = None
        parallel_operations = None

        if self.batched_executor and hasattr(
            self.batched_executor, "get_execution_metrics"
        ):
            batch_metrics = self.batched_executor.get_execution_metrics()
            if batch_metrics:
                batch_count = batch_metrics.total_batches
                parallel_operations = batch_metrics.parallel_batches
                if batch_metrics.total_operations > 0:
                    batch_efficiency = (
                        batch_metrics.total_batches / batch_metrics.total_operations
                    )

        # Update metrics
        self._current_metrics.execution_time_ms = execution_time_ms
        self._current_metrics.memory_after_mb = memory_after_mb
        self._current_metrics.memory_peak_mb = memory_peak_mb
        self._current_metrics.memory_delta_mb = memory_delta_mb
        self._current_metrics.cpu_percent = cpu_percent
        self._current_metrics.cpu_time_user = cpu_time_user
        self._current_metrics.cpu_time_system = cpu_time_system
        self._current_metrics.batch_count = batch_count
        self._current_metrics.batch_efficiency = batch_efficiency
        self._current_metrics.parallel_operations = parallel_operations
        self._current_metrics.io_read_count = io_read_count
        self._current_metrics.io_write_count = io_write_count
        self._current_metrics.io_read_bytes = io_read_bytes
        self._current_metrics.io_write_bytes = io_write_bytes
        self._current_metrics.success = success
        self._current_metrics.error_message = error_message

        # Get database version if possible
        if self.database_type == "postgresql" and hasattr(
            self, "_get_postgresql_version"
        ):
            self._current_metrics.postgresql_version = (
                await self._get_postgresql_version()
            )

        self._monitoring_active = False
        return self._current_metrics

    async def _benchmark_with_batched_executor(
        self, migration: Migration, connection: Any
    ) -> bool:
        """Benchmark using BatchedMigrationExecutor."""
        if not self.batched_executor:
            raise RuntimeError("BatchedMigrationExecutor not available")

        # Convert migration to batched operations
        batches = self.batched_executor.batch_ddl_operations(migration.operations)

        # Execute with timing
        start_time = time.perf_counter()
        success = await self.batched_executor.execute_batched_migrations(batches)
        end_time = time.perf_counter()

        # Update connection and query metrics
        self._current_metrics.connection_time_ms = (end_time - start_time) * 1000
        self._current_metrics.query_count = sum(len(batch) for batch in batches)
        self._current_metrics.transaction_count = len(batches)

        return success

    async def _benchmark_with_test_framework(
        self, migration: Migration, connection: Any
    ) -> MigrationTestResult:
        """Benchmark using MigrationTestFramework."""
        if not self.test_framework:
            raise RuntimeError("MigrationTestFramework not available")

        # Execute migration with test framework
        start_time = time.perf_counter()
        result = await self.test_framework.execute_test_migration(migration, connection)
        end_time = time.perf_counter()

        # Update metrics from test result
        self._current_metrics.connection_time_ms = (end_time - start_time) * 1000
        self._current_metrics.query_count = len(migration.operations)
        self._current_metrics.transaction_count = 1

        if result.performance_metrics:
            # Integrate test framework metrics
            if "rollback_tested" in result.performance_metrics:
                self._current_metrics.rollback_time_ms = result.performance_metrics.get(
                    "rollback_time", 0.0
                )
            # Also check for custom rollback_time key from the test result
            if hasattr(result, "performance_metrics") and isinstance(
                result.performance_metrics, dict
            ):
                if "rollback_time" in result.performance_metrics:
                    self._current_metrics.rollback_time_ms = result.performance_metrics[
                        "rollback_time"
                    ]

        return result

    async def _benchmark_direct_execution(
        self, migration: Migration, connection: Any
    ) -> bool:
        """Fallback direct execution benchmark."""
        if not connection:
            raise ValueError("Connection required for direct execution")

        try:
            start_time = time.perf_counter()

            # Execute migration operations
            for operation in migration.operations:
                if hasattr(connection, "execute") and asyncio.iscoroutinefunction(
                    connection.execute
                ):
                    # AsyncPG style or async connection
                    await connection.execute(operation.sql_up)
                elif hasattr(connection, "execute"):
                    # Check if execute is async but not detected by iscoroutinefunction
                    try:
                        result = connection.execute(operation.sql_up)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        # Fall back to treating as sync
                        pass

                    if hasattr(connection, "commit"):
                        connection.commit()
                else:
                    # Traditional synchronous connection
                    cursor = connection.cursor()
                    cursor.execute(operation.sql_up)
                    connection.commit()

            end_time = time.perf_counter()

            # Update metrics
            self._current_metrics.connection_time_ms = (end_time - start_time) * 1000
            self._current_metrics.query_count = len(migration.operations)
            self._current_metrics.transaction_count = 1

            return True

        except Exception as e:
            logger.error(f"Direct execution failed: {e}")
            raise e  # Re-raise to be caught by benchmark_migration

    def detect_performance_regression(
        self,
        metrics: List[PerformanceMetrics],
        baseline: Optional[PerformanceMetrics] = None,
    ) -> List[RegressionAnalysis]:
        """
        Detect performance regressions in a list of metrics.

        Args:
            metrics: List of performance metrics to analyze
            baseline: Optional baseline for comparison (uses stored baseline if not provided)

        Returns:
            List of regression analyses
        """
        if not metrics:
            return []

        logger.info(f"Analyzing {len(metrics)} performance metrics for regressions")

        regressions = []

        # Group metrics by operation type
        operation_groups = defaultdict(list)
        for metric in metrics:
            operation_key = f"{metric.migration_name}_{metric.operation_count}"
            operation_groups[operation_key].append(metric)

        # Analyze each operation type
        for operation_key, operation_metrics in operation_groups.items():
            if len(operation_metrics) < 2:
                continue  # Need at least 2 samples for regression analysis

            # Get or create baseline
            if baseline:
                baseline_metric = baseline
            else:
                baseline_metric = self._get_baseline_for_operation(
                    operation_key, operation_metrics
                )
                if not baseline_metric:
                    continue  # No baseline available

            # Analyze recent metrics against baseline
            recent_metrics = operation_metrics[-5:]  # Last 5 samples

            # Check key performance indicators
            regression_checks = [
                ("execution_time_ms", "Execution Time", "ms"),
                ("memory_delta_mb", "Memory Usage", "MB"),
                ("cpu_percent", "CPU Usage", "%"),
            ]

            for metric_name, display_name, unit in regression_checks:
                regression = self._analyze_metric_regression(
                    metric_name, display_name, unit, baseline_metric, recent_metrics
                )
                if regression and regression.is_regression():
                    regressions.append(regression)

        logger.info(f"Found {len(regressions)} performance regressions")
        return regressions

    def _analyze_metric_regression(
        self,
        metric_name: str,
        display_name: str,
        unit: str,
        baseline: PerformanceMetrics,
        recent_metrics: List[PerformanceMetrics],
    ) -> Optional[RegressionAnalysis]:
        """Analyze a specific metric for regression."""
        # Get baseline value
        baseline_value = getattr(baseline, metric_name, 0.0)
        if baseline_value <= 0:
            return None  # Can't analyze zero or negative baseline

        # Get recent values
        recent_values = [
            getattr(m, metric_name, 0.0)
            for m in recent_metrics
            if getattr(m, metric_name, 0.0) > 0
        ]
        if not recent_values:
            return None

        # Calculate current value (median of recent values for stability)
        current_value = median(recent_values)

        # Calculate change
        change_absolute = current_value - baseline_value
        change_percent = (change_absolute / baseline_value) * 100

        # Determine severity
        severity = RegressionSeverity.NONE
        threshold_breached = 0.0

        abs_change_percent = abs(change_percent)
        if abs_change_percent > self.regression_thresholds["critical"] * 100:
            severity = RegressionSeverity.CRITICAL
            threshold_breached = self.regression_thresholds["critical"]
        elif abs_change_percent > self.regression_thresholds["severe"] * 100:
            severity = RegressionSeverity.SEVERE
            threshold_breached = self.regression_thresholds["severe"]
        elif abs_change_percent > self.regression_thresholds["moderate"] * 100:
            severity = RegressionSeverity.MODERATE
            threshold_breached = self.regression_thresholds["moderate"]
        elif abs_change_percent > self.regression_thresholds["warning"] * 100:
            severity = RegressionSeverity.WARNING
            threshold_breached = self.regression_thresholds["warning"]

        # Analyze trend
        trend_direction = "stable"
        trend_confidence = 0.0

        if len(recent_values) >= 3:
            # Calculate trend using linear regression
            trend_slope = self._calculate_trend_slope(recent_values)
            if trend_slope > 0.05:  # 5% threshold
                trend_direction = "degrading" if change_percent > 0 else "improving"
                trend_confidence = min(abs(trend_slope) * 10, 1.0)  # Scale to 0-1

            if abs(trend_slope) < 0.02:  # Very stable
                trend_direction = "stable"
                trend_confidence = 1.0 - abs(trend_slope) * 20

        # Generate recommendations
        recommendations = self._generate_performance_recommendations(
            metric_name, change_percent, severity, trend_direction
        )

        return RegressionAnalysis(
            metric_name=f"{display_name} ({unit})",
            baseline_value=baseline_value,
            current_value=current_value,
            change_percent=change_percent,
            change_absolute=change_absolute,
            severity=severity,
            threshold_breached=threshold_breached * 100,
            trend_direction=trend_direction,
            trend_confidence=trend_confidence,
            recommendations=recommendations,
        )

    def _calculate_trend_slope(self, values: List[float]) -> float:
        """Calculate trend slope using simple linear regression."""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x_values = list(range(n))

        # Calculate means
        x_mean = sum(x_values) / n
        y_mean = sum(values) / n

        # Calculate slope
        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
        denominator = sum((x - x_mean) ** 2 for x in x_values)

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _generate_performance_recommendations(
        self,
        metric_name: str,
        change_percent: float,
        severity: RegressionSeverity,
        trend_direction: str,
    ) -> List[str]:
        """Generate actionable performance recommendations."""
        recommendations = []

        if severity == RegressionSeverity.NONE:
            return recommendations

        # General recommendations based on metric type
        if "execution_time" in metric_name.lower():
            recommendations.extend(
                [
                    "Consider optimizing SQL queries for better performance",
                    "Review migration operation batching configuration",
                    "Check for database locks or concurrent operations",
                    "Analyze query execution plans for bottlenecks",
                ]
            )

            if self.batched_executor:
                recommendations.append(
                    "Verify BatchedMigrationExecutor is being used effectively"
                )

        elif "memory" in metric_name.lower():
            recommendations.extend(
                [
                    "Review migration operation memory usage patterns",
                    "Consider processing migrations in smaller batches",
                    "Check for memory leaks in migration operations",
                    "Monitor garbage collection frequency",
                ]
            )

        elif "cpu" in metric_name.lower():
            recommendations.extend(
                [
                    "Review CPU-intensive migration operations",
                    "Consider parallel execution for independent operations",
                    "Check for inefficient algorithms in migration logic",
                ]
            )

        # Severity-specific recommendations
        if severity in [RegressionSeverity.SEVERE, RegressionSeverity.CRITICAL]:
            recommendations.extend(
                [
                    "URGENT: Performance has degraded significantly",
                    "Consider reverting recent changes and investigating root cause",
                    "Review recent commits for performance-impacting changes",
                ]
            )

        # Trend-specific recommendations
        if trend_direction == "degrading":
            recommendations.append(
                "Performance is consistently degrading - investigate trend cause"
            )

        return recommendations

    def _get_baseline_for_operation(
        self, operation_key: str, metrics: List[PerformanceMetrics]
    ) -> Optional[PerformanceMetrics]:
        """Get baseline metrics for an operation type."""
        # Check stored baselines
        if operation_key in self.baselines:
            return self.baselines[operation_key].baseline_metrics

        # Create baseline from historical data if enough samples
        if len(metrics) >= 5:
            # Use the best performing samples as baseline
            sorted_metrics = sorted(metrics, key=lambda m: m.execution_time_ms)
            best_samples = sorted_metrics[:3]  # Top 3 performers

            # Create baseline from average of best samples
            baseline = self._create_baseline_from_samples(best_samples)

            # Store for future use
            self._store_baseline(operation_key, baseline, best_samples)

            return baseline

        return None

    def _create_baseline_from_samples(
        self, samples: List[PerformanceMetrics]
    ) -> PerformanceMetrics:
        """Create baseline metrics from a set of sample metrics."""
        if not samples:
            raise ValueError("Cannot create baseline from empty samples")

        # Use the first sample as template
        baseline = PerformanceMetrics(
            migration_version=samples[0].migration_version,
            migration_name=samples[0].migration_name,
            operation_count=samples[0].operation_count,
            execution_time_ms=mean([s.execution_time_ms for s in samples]),
            memory_before_mb=mean([s.memory_before_mb for s in samples]),
            memory_peak_mb=mean([s.memory_peak_mb for s in samples]),
            memory_after_mb=mean([s.memory_after_mb for s in samples]),
            memory_delta_mb=mean([s.memory_delta_mb for s in samples]),
            cpu_percent=mean([s.cpu_percent for s in samples]),
            cpu_time_user=mean([s.cpu_time_user for s in samples]),
            cpu_time_system=mean([s.cpu_time_system for s in samples]),
            database_type=samples[0].database_type,
            connection_time_ms=mean([s.connection_time_ms for s in samples]),
            query_count=samples[0].query_count,
            transaction_count=samples[0].transaction_count,
            environment="baseline",
            timestamp=datetime.now().isoformat(),
        )

        return baseline

    def _store_baseline(
        self,
        operation_key: str,
        baseline: PerformanceMetrics,
        samples: List[PerformanceMetrics],
    ):
        """Store baseline for future use."""
        # Calculate confidence intervals
        confidence_interval = {}
        metrics_to_track = ["execution_time_ms", "memory_delta_mb", "cpu_percent"]

        for metric_name in metrics_to_track:
            values = [getattr(s, metric_name) for s in samples]
            if len(values) > 1:
                avg = mean(values)
                std = stdev(values) if len(values) > 1 else 0
                confidence_interval[metric_name] = (avg - std, avg + std)
            else:
                value = values[0] if values else 0
                confidence_interval[metric_name] = (value, value)

        baseline_obj = PerformanceBaseline(
            operation_type=operation_key,
            baseline_metrics=baseline,
            confidence_interval=confidence_interval,
            sample_size=len(samples),
            created_at=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat(),
        )

        self.baselines[operation_key] = baseline_obj
        self._save_baselines()

    def get_performance_insights(
        self, metrics: List[PerformanceMetrics], include_trends: bool = True
    ) -> Dict[str, Any]:
        """
        Generate comprehensive performance insights from metrics.

        Args:
            metrics: List of performance metrics to analyze
            include_trends: Whether to include trend analysis

        Returns:
            Dictionary containing performance insights and recommendations
        """
        if not metrics:
            return {"status": "no_data", "insights": []}

        insights = {
            "summary": self._generate_performance_summary(metrics),
            "regressions": [],
            "trends": [],
            "recommendations": [],
            "key_metrics": {},
            "analysis_timestamp": datetime.now().isoformat(),
        }

        # Detect regressions
        regressions = self.detect_performance_regression(metrics)
        insights["regressions"] = [asdict(r) for r in regressions]

        # Generate trends if requested
        if include_trends and len(metrics) >= 3:
            insights["trends"] = self._analyze_performance_trends(metrics)

        # Calculate key metrics
        insights["key_metrics"] = self._calculate_key_performance_metrics(metrics)

        # Generate overall recommendations
        insights["recommendations"] = self._generate_overall_recommendations(
            metrics, regressions
        )

        return insights

    def _generate_performance_summary(
        self, metrics: List[PerformanceMetrics]
    ) -> Dict[str, Any]:
        """Generate high-level performance summary."""
        total_migrations = len(metrics)
        successful_migrations = sum(1 for m in metrics if m.success)

        if successful_migrations == 0:
            return {
                "total_migrations": total_migrations,
                "success_rate": 0.0,
                "avg_execution_time_ms": 0.0,
                "avg_memory_usage_mb": 0.0,
                "status": "all_failed",
            }

        successful_metrics = [m for m in metrics if m.success]

        return {
            "total_migrations": total_migrations,
            "successful_migrations": successful_migrations,
            "success_rate": (successful_migrations / total_migrations) * 100,
            "avg_execution_time_ms": mean(
                [m.execution_time_ms for m in successful_metrics]
            ),
            "avg_memory_usage_mb": mean(
                [m.memory_delta_mb for m in successful_metrics]
            ),
            "avg_cpu_percent": mean([m.cpu_percent for m in successful_metrics]),
            "total_operations": sum(m.operation_count for m in successful_metrics),
            "status": (
                "healthy" if successful_migrations == total_migrations else "degraded"
            ),
        }

    def _analyze_performance_trends(
        self, metrics: List[PerformanceMetrics]
    ) -> List[Dict[str, Any]]:
        """Analyze performance trends over time."""
        trends = []

        # Sort by timestamp
        sorted_metrics = sorted(metrics, key=lambda m: m.timestamp)
        successful_metrics = [m for m in sorted_metrics if m.success]

        if len(successful_metrics) < 3:
            return trends

        # Analyze trends for key metrics
        trend_metrics = [
            ("execution_time_ms", "Execution Time", "ms"),
            ("memory_delta_mb", "Memory Usage", "MB"),
            ("cpu_percent", "CPU Usage", "%"),
        ]

        for metric_name, display_name, unit in trend_metrics:
            values = [getattr(m, metric_name) for m in successful_metrics]
            slope = self._calculate_trend_slope(values)

            # Determine trend direction and strength
            if abs(slope) < 0.01:  # 1% threshold
                direction = "stable"
                strength = "weak"
            elif slope > 0:
                direction = "increasing"
                strength = "strong" if abs(slope) > 0.1 else "moderate"
            else:
                direction = "decreasing"
                strength = "strong" if abs(slope) > 0.1 else "moderate"

            trends.append(
                {
                    "metric": display_name,
                    "unit": unit,
                    "direction": direction,
                    "strength": strength,
                    "slope": slope,
                    "recent_value": values[-1],
                    "first_value": values[0],
                    "samples": len(values),
                }
            )

        return trends

    def _calculate_key_performance_metrics(
        self, metrics: List[PerformanceMetrics]
    ) -> Dict[str, Any]:
        """Calculate key performance indicators."""
        successful_metrics = [m for m in metrics if m.success]

        if not successful_metrics:
            return {}

        # Execution time statistics
        exec_times = [m.execution_time_ms for m in successful_metrics]
        memory_usage = [m.memory_delta_mb for m in successful_metrics]
        cpu_usage = [m.cpu_percent for m in successful_metrics]

        return {
            "execution_time": {
                "min_ms": min(exec_times),
                "max_ms": max(exec_times),
                "avg_ms": mean(exec_times),
                "median_ms": median(exec_times),
                "std_dev_ms": stdev(exec_times) if len(exec_times) > 1 else 0.0,
            },
            "memory_usage": {
                "min_mb": min(memory_usage),
                "max_mb": max(memory_usage),
                "avg_mb": mean(memory_usage),
                "median_mb": median(memory_usage),
                "std_dev_mb": stdev(memory_usage) if len(memory_usage) > 1 else 0.0,
            },
            "cpu_usage": {
                "min_percent": min(cpu_usage),
                "max_percent": max(cpu_usage),
                "avg_percent": mean(cpu_usage),
                "median_percent": median(cpu_usage),
                "std_dev_percent": stdev(cpu_usage) if len(cpu_usage) > 1 else 0.0,
            },
            "batch_efficiency": (
                {
                    "avg_efficiency": mean(
                        [
                            m.batch_efficiency
                            for m in successful_metrics
                            if m.batch_efficiency
                        ]
                    ),
                    "parallel_usage": sum(
                        1
                        for m in successful_metrics
                        if m.parallel_operations and m.parallel_operations > 0
                    ),
                    "total_batches": sum(
                        m.batch_count for m in successful_metrics if m.batch_count
                    ),
                }
                if any(m.batch_efficiency for m in successful_metrics)
                else None
            ),
        }

    def _generate_overall_recommendations(
        self, metrics: List[PerformanceMetrics], regressions: List[RegressionAnalysis]
    ) -> List[str]:
        """Generate overall performance recommendations."""
        recommendations = []

        # Regression-based recommendations
        severe_regressions = [
            r
            for r in regressions
            if r.severity in [RegressionSeverity.SEVERE, RegressionSeverity.CRITICAL]
        ]
        if severe_regressions:
            recommendations.append(
                "CRITICAL: Severe performance regressions detected - immediate investigation required"
            )

        # Component-specific recommendations
        if not self.batched_executor:
            recommendations.append(
                "Consider using BatchedMigrationExecutor for improved performance"
            )

        if not self.connection_manager:
            recommendations.append(
                "Consider using MigrationConnectionManager for optimized connection handling"
            )

        # Usage pattern recommendations
        successful_metrics = [m for m in metrics if m.success]
        if successful_metrics:
            avg_execution_time = mean([m.execution_time_ms for m in successful_metrics])
            if avg_execution_time > 5000:  # 5 seconds
                recommendations.append(
                    "Average execution time exceeds 5 seconds - consider optimization"
                )

            avg_memory_usage = mean([m.memory_delta_mb for m in successful_metrics])
            if avg_memory_usage > 100:  # 100 MB
                recommendations.append(
                    "High memory usage detected - consider batch size optimization"
                )

        return recommendations

    def _load_baselines(self):
        """Load performance baselines from file."""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, "r") as f:
                    data = json.load(f)

                for key, baseline_data in data.items():
                    baseline_metrics = PerformanceMetrics.from_dict(
                        baseline_data["baseline_metrics"]
                    )
                    baseline = PerformanceBaseline(
                        operation_type=baseline_data["operation_type"],
                        baseline_metrics=baseline_metrics,
                        confidence_interval=baseline_data["confidence_interval"],
                        sample_size=baseline_data["sample_size"],
                        created_at=baseline_data["created_at"],
                        last_updated=baseline_data["last_updated"],
                    )
                    self.baselines[key] = baseline

                logger.info(f"Loaded {len(self.baselines)} performance baselines")

            except Exception as e:
                logger.warning(f"Failed to load baselines: {e}")

    def _save_baselines(self):
        """Save performance baselines to file."""
        try:
            data = {}
            for key, baseline in self.baselines.items():
                data[key] = {
                    "operation_type": baseline.operation_type,
                    "baseline_metrics": baseline.baseline_metrics.to_dict(),
                    "confidence_interval": baseline.confidence_interval,
                    "sample_size": baseline.sample_size,
                    "created_at": baseline.created_at,
                    "last_updated": baseline.last_updated,
                }

            with open(self.baseline_file, "w") as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save baselines: {e}")

    def _load_history(self):
        """Load performance history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r") as f:
                    for line in f:
                        if line.strip():
                            entry = json.loads(line)
                            metrics = PerformanceMetrics.from_dict(entry)
                            self.performance_history.append(metrics)

                logger.info(
                    f"Loaded {len(self.performance_history)} historical performance entries"
                )

            except Exception as e:
                logger.warning(f"Failed to load history: {e}")

    def _save_history_entry(self, metrics: PerformanceMetrics):
        """Save a single history entry to file."""
        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(metrics.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Failed to save history entry: {e}")

    def export_performance_report(
        self,
        output_file: str,
        metrics: Optional[List[PerformanceMetrics]] = None,
        include_detailed_analysis: bool = True,
    ) -> bool:
        """
        Export comprehensive performance report.

        Args:
            output_file: Path to output file
            metrics: Optional metrics to include (uses history if not provided)
            include_detailed_analysis: Whether to include detailed analysis

        Returns:
            True if export successful
        """
        try:
            report_metrics = metrics or list(self.performance_history)

            if not report_metrics:
                logger.warning("No metrics available for report export")
                return False

            # Generate comprehensive report
            report = {
                "report_metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "metrics_count": len(report_metrics),
                    "date_range": {
                        "start": min(m.timestamp for m in report_metrics),
                        "end": max(m.timestamp for m in report_metrics),
                    },
                    "database_type": self.database_type,
                },
                "performance_summary": self._generate_performance_summary(
                    report_metrics
                ),
                "key_metrics": self._calculate_key_performance_metrics(report_metrics),
                "regressions": [
                    asdict(r)
                    for r in self.detect_performance_regression(report_metrics)
                ],
                "trends": self._analyze_performance_trends(report_metrics),
                "insights": self.get_performance_insights(report_metrics),
                "baselines": {k: asdict(v) for k, v in self.baselines.items()},
                "raw_metrics": (
                    [m.to_dict() for m in report_metrics]
                    if include_detailed_analysis
                    else []
                ),
            }

            with open(output_file, "w") as f:
                json.dump(report, f, indent=2)

            logger.info(f"Performance report exported to {output_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to export performance report: {e}")
            return False

    def reset_baselines(self):
        """Reset all performance baselines."""
        self.baselines.clear()
        if self.baseline_file.exists():
            self.baseline_file.unlink()
        logger.info("Performance baselines reset")

    def cleanup_old_history(self, days_to_keep: int = 30):
        """Clean up old performance history entries."""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        cutoff_str = cutoff_date.isoformat()

        # Filter history
        original_count = len(self.performance_history)
        self.performance_history = deque(
            [m for m in self.performance_history if m.timestamp >= cutoff_str],
            maxlen=self.max_history_size,
        )

        # Rewrite history file
        try:
            with open(self.history_file, "w") as f:
                for metrics in self.performance_history:
                    f.write(json.dumps(metrics.to_dict()) + "\n")

            removed_count = original_count - len(self.performance_history)
            logger.info(f"Cleaned up {removed_count} old performance history entries")

        except Exception as e:
            logger.warning(f"Failed to cleanup history: {e}")
