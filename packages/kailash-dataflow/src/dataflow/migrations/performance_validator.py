#!/usr/bin/env python3
"""
Performance Validator - TODO-141 Phase 2

Performance validation utilities for migration validation pipeline.
Provides baseline establishment, benchmark execution, and performance comparison.

CORE FEATURES:
- Performance baseline establishment pre-migration
- Performance benchmark execution post-migration
- Performance comparison with configurable thresholds
- Query execution metrics collection
- Resource usage monitoring (CPU, memory, disk)
- Performance degradation analysis

WORKFLOW:
1. Establish baseline performance metrics pre-migration
2. Execute migration in staging environment
3. Run performance benchmarks post-migration
4. Compare baseline vs benchmark performance
5. Determine if performance impact is acceptable

PERFORMANCE METRICS:
- Query execution time (primary metric)
- Memory usage during execution
- CPU utilization during execution
- Rows returned/affected
- Query plan analysis (optional)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from statistics import mean, median
from typing import Any, Dict, List, Optional, Union

import asyncpg
import psutil

from .staging_environment_manager import StagingEnvironment

logger = logging.getLogger(__name__)


@dataclass
class QueryPerformanceResult:
    """Result of individual query performance measurement."""

    query: str
    execution_time_seconds: float
    rows_returned: int
    memory_used_mb: float = 0.0
    cpu_percent: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    def get_performance_score(self) -> float:
        """Calculate overall performance score (lower is better)."""
        # Weighted combination of metrics (execution time is primary)
        score = (
            self.execution_time_seconds * 1.0  # 100% weight on execution time
            + (self.memory_used_mb / 1024) * 0.1  # 10% weight on memory (GB)
            + (self.cpu_percent / 100) * 0.1  # 10% weight on CPU
        )
        return score


@dataclass
class PerformanceMetrics:
    """Aggregated performance metrics for a query."""

    avg_execution_time: float
    max_execution_time: float = 0.0
    min_execution_time: float = 0.0
    avg_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    sample_count: int = 1

    def __post_init__(self):
        """Set defaults for optional fields."""
        if self.max_execution_time == 0.0:
            self.max_execution_time = self.avg_execution_time
        if self.min_execution_time == 0.0:
            self.min_execution_time = self.avg_execution_time

    @property
    def execution_time_variance(self) -> float:
        """Calculate execution time variance."""
        return self.max_execution_time - self.min_execution_time

    def is_consistent_performance(self, variance_threshold: float = 0.1) -> bool:
        """Check if performance is consistent across samples."""
        if self.avg_execution_time == 0:
            return True
        variance_ratio = self.execution_time_variance / self.avg_execution_time
        return variance_ratio <= variance_threshold


@dataclass
class PerformanceBaseline:
    """Performance baseline for comparison."""

    staging_environment_id: str
    query_baselines: Dict[str, PerformanceMetrics]
    established_at: datetime = field(default_factory=datetime.now)

    def get_query_baseline(self, query: str) -> Optional[PerformanceMetrics]:
        """Get baseline metrics for a specific query."""
        return self.query_baselines.get(query)

    def get_age_seconds(self) -> float:
        """Get age of baseline in seconds."""
        return (datetime.now() - self.established_at).total_seconds()

    def get_age_hours(self) -> float:
        """Get age of baseline in hours."""
        return self.get_age_seconds() / 3600.0


@dataclass
class PerformanceBenchmark:
    """Performance benchmark results."""

    staging_environment_id: str
    query_benchmarks: Dict[str, PerformanceMetrics]
    executed_at: datetime = field(default_factory=datetime.now)


@dataclass
class PerformanceComparison:
    """Comparison between baseline and benchmark performance."""

    baseline_environment_id: str
    benchmark_environment_id: str
    overall_degradation_percent: float
    worst_degradation_percent: float
    is_acceptable_performance: bool
    degraded_queries: List[str] = field(default_factory=list)
    query_comparisons: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    comparison_timestamp: datetime = field(default_factory=datetime.now)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Generate performance comparison summary."""
        return {
            "overall_degradation_percent": self.overall_degradation_percent,
            "worst_degradation_percent": self.worst_degradation_percent,
            "is_acceptable": self.is_acceptable_performance,
            "degraded_queries_count": len(self.degraded_queries),
            "total_queries_compared": len(self.query_comparisons),
        }


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""

    execution_time_degradation_percent: float = 20.0  # 20% degradation threshold
    memory_increase_percent: float = 30.0  # 30% memory increase threshold
    cpu_increase_percent: float = 40.0  # 40% CPU increase threshold

    def is_execution_time_acceptable(self, baseline: float, benchmark: float) -> bool:
        """Check if execution time degradation is acceptable."""
        if baseline == 0:
            return True
        degradation_percent = ((benchmark - baseline) / baseline) * 100
        return degradation_percent <= self.execution_time_degradation_percent

    def is_memory_usage_acceptable(self, baseline: float, benchmark: float) -> bool:
        """Check if memory usage increase is acceptable."""
        if baseline == 0:
            return True
        increase_percent = ((benchmark - baseline) / baseline) * 100
        return increase_percent <= self.memory_increase_percent

    def is_cpu_usage_acceptable(self, baseline: float, benchmark: float) -> bool:
        """Check if CPU usage increase is acceptable."""
        if baseline == 0:
            return True
        increase_percent = ((benchmark - baseline) / baseline) * 100
        return increase_percent <= self.cpu_increase_percent


@dataclass
class PerformanceValidationConfig:
    """Configuration for performance validation."""

    baseline_queries: List[str] = field(default_factory=lambda: ["SELECT 1"])
    performance_degradation_threshold: float = 0.20  # 20%
    baseline_execution_runs: int = 3
    benchmark_execution_runs: int = 3
    timeout_seconds: int = 30
    memory_threshold_mb: float = 512.0
    cpu_threshold_percent: float = 80.0

    def __post_init__(self):
        """Validate configuration parameters."""
        if self.performance_degradation_threshold <= 0:
            raise ValueError("Performance degradation threshold must be positive")
        if self.baseline_execution_runs <= 0:
            raise ValueError("Execution runs must be positive")
        if self.benchmark_execution_runs <= 0:
            raise ValueError("Execution runs must be positive")
        if len(self.baseline_queries) == 0:
            raise ValueError("Baseline queries cannot be empty")


class PerformanceValidator:
    """
    Performance validation utilities for migration validation pipeline.

    Provides comprehensive performance baseline establishment, benchmark execution,
    and performance comparison with configurable thresholds.
    """

    def __init__(self, config: PerformanceValidationConfig):
        """
        Initialize performance validator.

        Args:
            config: Performance validation configuration (required)

        Raises:
            ValueError: If config is None
        """
        if config is None:
            raise ValueError("Configuration cannot be None")

        self.config = config
        self.performance_threshold = PerformanceThreshold(
            execution_time_degradation_percent=config.performance_degradation_threshold
            * 100
        )

        logger.info(
            f"PerformanceValidator initialized with {len(config.baseline_queries)} baseline queries"
        )

    async def establish_baseline(
        self,
        staging_environment: StagingEnvironment,
        queries: Optional[List[str]] = None,
    ) -> PerformanceBaseline:
        """
        Establish performance baseline by executing queries multiple times.

        Args:
            staging_environment: Staging environment for testing
            queries: Optional list of queries (uses config queries if not provided)

        Returns:
            PerformanceBaseline: Established performance baseline
        """
        if queries is None:
            queries = self.config.baseline_queries

        logger.info(
            f"Establishing performance baseline with {len(queries)} queries, {self.config.baseline_execution_runs} runs each"
        )

        query_baselines = {}

        for query in queries:
            logger.debug(f"Establishing baseline for query: {query[:100]}...")

            # Execute query multiple times to get stable baseline
            execution_results = []
            for run in range(self.config.baseline_execution_runs):
                try:
                    result = await self._execute_query_with_metrics(
                        staging_environment=staging_environment, query=query
                    )
                    execution_results.append(result)

                except Exception as e:
                    logger.error(
                        f"Baseline execution failed for query (run {run + 1}): {e}"
                    )
                    raise

            # Calculate baseline metrics
            if execution_results:
                metrics = self._calculate_aggregated_metrics(execution_results)
                query_baselines[query] = metrics
                logger.debug(
                    f"Baseline established: avg={metrics.avg_execution_time:.3f}s, samples={metrics.sample_count}"
                )

        baseline = PerformanceBaseline(
            staging_environment_id=staging_environment.staging_id,
            query_baselines=query_baselines,
        )

        logger.info(
            f"Performance baseline established for {len(query_baselines)} queries"
        )
        return baseline

    async def run_benchmark(
        self, staging_environment: StagingEnvironment, baseline: PerformanceBaseline
    ) -> PerformanceBenchmark:
        """
        Run performance benchmark using the same queries as baseline.

        Args:
            staging_environment: Staging environment for testing
            baseline: Performance baseline for comparison

        Returns:
            PerformanceBenchmark: Benchmark execution results
        """
        logger.info(
            f"Running performance benchmark with {len(baseline.query_baselines)} queries"
        )

        query_benchmarks = {}

        for query, baseline_metrics in baseline.query_baselines.items():
            logger.debug(f"Running benchmark for query: {query[:100]}...")

            # Execute query multiple times for benchmark
            execution_results = []
            for run in range(self.config.benchmark_execution_runs):
                try:
                    result = await self._execute_query_with_metrics(
                        staging_environment=staging_environment, query=query
                    )
                    execution_results.append(result)

                except Exception as e:
                    logger.error(
                        f"Benchmark execution failed for query (run {run + 1}): {e}"
                    )
                    raise

            # Calculate benchmark metrics
            if execution_results:
                metrics = self._calculate_aggregated_metrics(execution_results)
                query_benchmarks[query] = metrics
                logger.debug(
                    f"Benchmark completed: avg={metrics.avg_execution_time:.3f}s, samples={metrics.sample_count}"
                )

        benchmark = PerformanceBenchmark(
            staging_environment_id=staging_environment.staging_id,
            query_benchmarks=query_benchmarks,
        )

        logger.info(
            f"Performance benchmark completed for {len(query_benchmarks)} queries"
        )
        return benchmark

    def compare_performance(
        self, baseline: PerformanceBaseline, benchmark: PerformanceBenchmark
    ) -> PerformanceComparison:
        """
        Compare baseline and benchmark performance.

        Args:
            baseline: Performance baseline
            benchmark: Performance benchmark

        Returns:
            PerformanceComparison: Detailed performance comparison
        """
        logger.info("Comparing baseline vs benchmark performance")

        degradations = []
        degraded_queries = []
        query_comparisons = {}

        # Compare each query's performance
        for query, baseline_metrics in baseline.query_baselines.items():
            if query in benchmark.query_benchmarks:
                benchmark_metrics = benchmark.query_benchmarks[query]

                # Calculate performance degradation
                degradation_percent = self._calculate_degradation_percent(
                    baseline_metrics.avg_execution_time,
                    benchmark_metrics.avg_execution_time,
                )

                degradations.append(degradation_percent)

                # Check if query performance degraded beyond threshold
                if degradation_percent > (
                    self.config.performance_degradation_threshold * 100
                ):
                    degraded_queries.append(query)

                # Store detailed comparison
                query_comparisons[query] = {
                    "baseline_time": baseline_metrics.avg_execution_time,
                    "benchmark_time": benchmark_metrics.avg_execution_time,
                    "degradation_percent": degradation_percent,
                    "baseline_memory": baseline_metrics.avg_memory_mb,
                    "benchmark_memory": benchmark_metrics.avg_memory_mb,
                    "baseline_cpu": baseline_metrics.avg_cpu_percent,
                    "benchmark_cpu": benchmark_metrics.avg_cpu_percent,
                }

                logger.debug(
                    f"Query performance: {degradation_percent:.1f}% degradation"
                )

        # Calculate overall performance metrics
        overall_degradation = mean(degradations) if degradations else 0.0
        worst_degradation = max(degradations) if degradations else 0.0
        is_acceptable = worst_degradation <= (
            self.config.performance_degradation_threshold * 100
        )

        comparison = PerformanceComparison(
            baseline_environment_id=baseline.staging_environment_id,
            benchmark_environment_id=benchmark.staging_environment_id,
            overall_degradation_percent=overall_degradation,
            worst_degradation_percent=worst_degradation,
            is_acceptable_performance=is_acceptable,
            degraded_queries=degraded_queries,
            query_comparisons=query_comparisons,
        )

        logger.info(
            f"Performance comparison completed: {overall_degradation:.1f}% avg degradation, "
            f"{worst_degradation:.1f}% worst, acceptable={is_acceptable}"
        )

        return comparison

    async def validate_performance(
        self, staging_environment: StagingEnvironment, migration_info: Dict[str, Any]
    ) -> PerformanceComparison:
        """
        Execute complete performance validation workflow.

        Args:
            staging_environment: Staging environment for validation
            migration_info: Migration information for context

        Returns:
            PerformanceComparison: Complete performance validation results
        """
        logger.info(
            f"Starting complete performance validation for migration {migration_info.get('migration_id', 'unknown')}"
        )

        # Step 1: Establish baseline
        baseline = await self.establish_baseline(staging_environment)

        # Step 2: Execute migration (simulated - migration would be executed by pipeline)
        logger.info("Migration execution would happen here (handled by pipeline)")

        # Step 3: Run benchmark
        benchmark = await self.run_benchmark(staging_environment, baseline)

        # Step 4: Compare performance
        comparison = self.compare_performance(baseline, benchmark)

        logger.info(
            f"Performance validation completed: acceptable={comparison.is_acceptable_performance}"
        )
        return comparison

    async def _execute_query_with_metrics(
        self, staging_environment: StagingEnvironment, query: str
    ) -> QueryPerformanceResult:
        """
        Execute query and collect performance metrics.

        Args:
            staging_environment: Staging environment for execution
            query: SQL query to execute

        Returns:
            QueryPerformanceResult: Performance metrics for query execution
        """
        # Get process info before execution
        process = psutil.Process()
        memory_before = process.memory_info().rss / (1024 * 1024)  # MB

        # Connect to staging database
        conn = await asyncpg.connect(
            host=staging_environment.staging_db.host,
            port=staging_environment.staging_db.port,
            database=staging_environment.staging_db.database,
            user=staging_environment.staging_db.user,
            password=staging_environment.staging_db.password,
            timeout=self.config.timeout_seconds,
        )

        try:
            # Execute query with timing
            start_time = time.time()
            cpu_start = time.time()

            try:
                # Execute query with timeout
                result = await asyncio.wait_for(
                    conn.fetch(query), timeout=self.config.timeout_seconds
                )

                execution_time = time.time() - start_time
                rows_returned = len(result) if result else 0

            except asyncio.TimeoutError:
                logger.warning(
                    f"Query execution timed out after {self.config.timeout_seconds}s"
                )
                raise

            # Collect resource usage metrics
            memory_after = process.memory_info().rss / (1024 * 1024)  # MB
            memory_used = max(0, memory_after - memory_before)

            # CPU usage (approximate)
            cpu_percent = psutil.cpu_percent(interval=0.1)

            query_result = QueryPerformanceResult(
                query=query,
                execution_time_seconds=execution_time,
                rows_returned=rows_returned,
                memory_used_mb=memory_used,
                cpu_percent=cpu_percent,
            )

            logger.debug(
                f"Query executed: {execution_time:.3f}s, {rows_returned} rows, "
                f"{memory_used:.1f}MB, {cpu_percent:.1f}% CPU"
            )

            return query_result

        finally:
            await conn.close()

    def _calculate_aggregated_metrics(
        self, execution_results: List[QueryPerformanceResult]
    ) -> PerformanceMetrics:
        """Calculate aggregated metrics from multiple execution results."""
        if not execution_results:
            raise ValueError("Cannot calculate metrics from empty results")

        execution_times = [r.execution_time_seconds for r in execution_results]
        memory_usage = [r.memory_used_mb for r in execution_results]
        cpu_usage = [r.cpu_percent for r in execution_results]

        metrics = PerformanceMetrics(
            avg_execution_time=mean(execution_times),
            max_execution_time=max(execution_times),
            min_execution_time=min(execution_times),
            avg_memory_mb=mean(memory_usage),
            avg_cpu_percent=mean(cpu_usage),
            sample_count=len(execution_results),
        )

        return metrics

    def _calculate_degradation_percent(
        self, baseline: float, benchmark: float
    ) -> float:
        """Calculate performance degradation percentage."""
        if baseline == 0:
            return 0.0 if benchmark == 0 else 100.0

        degradation = ((benchmark - baseline) / baseline) * 100
        return max(0.0, degradation)  # Only report degradation, not improvement

    def _validate_query_syntax(self, query: str) -> bool:
        """Basic SQL query syntax validation."""
        query = query.strip()
        if not query:
            return False

        # Basic checks for common SQL statements
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
        query_upper = query.upper()

        return any(query_upper.startswith(keyword) for keyword in sql_keywords)

    def get_performance_recommendations(
        self, comparison: PerformanceComparison
    ) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        if not comparison.is_acceptable_performance:
            recommendations.append(
                f"Performance degradation ({comparison.worst_degradation_percent:.1f}%) exceeds threshold. "
                "Consider optimizing queries or adding indexes."
            )

        if len(comparison.degraded_queries) > 0:
            recommendations.append(
                f"{len(comparison.degraded_queries)} queries show significant performance degradation. "
                "Review query execution plans and consider optimization."
            )

        # Analyze specific query patterns
        for query, comparison_data in comparison.query_comparisons.items():
            degradation = comparison_data["degradation_percent"]
            if degradation > 50:  # High degradation threshold
                recommendations.append(
                    f"Query shows high degradation ({degradation:.1f}%): {query[:100]}... "
                    "Consider adding indexes or rewriting the query."
                )

        return recommendations
