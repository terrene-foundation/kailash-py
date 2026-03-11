"""
Benchmark Framework for Kaizen Performance Testing (TODO-171).

Production-grade benchmark harness with statistical rigor, resource monitoring,
and comprehensive reporting.

Features:
- Percentile metrics (p50, p95, p99, mean, stddev)
- Statistical rigor (100+ iterations, outlier removal, confidence intervals)
- Resource monitoring (CPU%, memory MB via psutil)
- JSON report generation
- Warm-up runs excluded from results
- Fixed random seeds for reproducibility

Usage:
    from benchmarks.framework import BenchmarkSuite, BenchmarkCase, BenchmarkResult

    suite = BenchmarkSuite(name="Memory Performance")

    @suite.benchmark(name="Hot Tier Access", warmup=10, iterations=100)
    def bench_hot_tier():
        # Benchmark code here
        pass

    results = suite.run()
    suite.export_results("results.json")
"""

import json
import logging
import random
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════


@dataclass
class ResourceSnapshot:
    """Single resource measurement snapshot."""

    timestamp: float
    cpu_percent: float
    memory_mb: float
    threads: int


@dataclass
class PercentileMetrics:
    """Percentile statistics for benchmark results."""

    p50: float  # Median
    p95: float  # 95th percentile
    p99: float  # 99th percentile
    mean: float  # Average
    stddev: float  # Standard deviation
    min: float  # Minimum
    max: float  # Maximum
    count: int  # Sample count


@dataclass
class ConfidenceInterval:
    """95% confidence interval for mean estimate."""

    lower: float
    upper: float
    confidence: float = 0.95


@dataclass
class ResourceMetrics:
    """Resource usage metrics."""

    cpu_mean: float
    cpu_peak: float
    memory_mean_mb: float
    memory_peak_mb: float
    threads_mean: float
    threads_peak: int


@dataclass
class BenchmarkResult:
    """Complete benchmark result with metrics and metadata."""

    name: str
    iterations: int
    warmup_iterations: int
    latency_ms: PercentileMetrics
    throughput_ops_per_sec: float
    resources: ResourceMetrics
    confidence_interval: ConfidenceInterval
    outliers_removed: int
    timestamp: str
    duration_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SuiteResult:
    """Complete suite result with all benchmarks."""

    suite_name: str
    benchmark_results: List[BenchmarkResult]
    total_duration_seconds: float
    timestamp: str
    environment: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Benchmark Case
# ═══════════════════════════════════════════════════════════════


class BenchmarkCase:
    """
    Individual benchmark case with configuration.

    Args:
        name: Benchmark name
        func: Benchmark function to execute
        warmup: Number of warmup iterations (excluded from results)
        iterations: Number of measurement iterations
        outlier_threshold: Standard deviations for outlier removal
        seed: Random seed for reproducibility
    """

    def __init__(
        self,
        name: str,
        func: Callable,
        warmup: int = 10,
        iterations: int = 100,
        outlier_threshold: float = 3.0,
        seed: int = 42,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.func = func
        self.warmup = warmup
        self.iterations = iterations
        self.outlier_threshold = outlier_threshold
        self.seed = seed
        self.metadata = metadata or {}

        self._resource_snapshots: List[ResourceSnapshot] = []
        self._latencies: List[float] = []
        self._process = psutil.Process()

    def _take_resource_snapshot(self) -> ResourceSnapshot:
        """Take resource usage snapshot."""
        return ResourceSnapshot(
            timestamp=time.time(),
            cpu_percent=self._process.cpu_percent(),
            memory_mb=self._process.memory_info().rss / (1024 * 1024),
            threads=self._process.num_threads(),
        )

    def _remove_outliers(self, data: List[float]) -> List[float]:
        """
        Remove outliers using standard deviation method.

        Args:
            data: List of measurements

        Returns:
            Filtered list with outliers removed (>3 std dev)
        """
        if len(data) < 10:
            return data  # Not enough data

        mean = statistics.mean(data)
        stddev = statistics.stdev(data)

        # Remove values >3 standard deviations from mean
        lower_bound = mean - (self.outlier_threshold * stddev)
        upper_bound = mean + (self.outlier_threshold * stddev)

        filtered = [x for x in data if lower_bound <= x <= upper_bound]

        removed_count = len(data) - len(filtered)
        if removed_count > 0:
            logger.debug(
                f"Removed {removed_count} outliers from {self.name} "
                f"(>{self.outlier_threshold} std dev)"
            )

        return filtered

    def _calculate_percentiles(self, data: List[float]) -> PercentileMetrics:
        """Calculate percentile metrics."""
        if not data:
            return PercentileMetrics(
                p50=0.0,
                p95=0.0,
                p99=0.0,
                mean=0.0,
                stddev=0.0,
                min=0.0,
                max=0.0,
                count=0,
            )

        sorted_data = sorted(data)
        n = len(sorted_data)

        return PercentileMetrics(
            p50=sorted_data[int(n * 0.50)] if n > 0 else 0.0,
            p95=sorted_data[int(n * 0.95)] if n > 0 else 0.0,
            p99=sorted_data[int(n * 0.99)] if n > 0 else 0.0,
            mean=statistics.mean(data),
            stddev=statistics.stdev(data) if len(data) > 1 else 0.0,
            min=min(data),
            max=max(data),
            count=n,
        )

    def _calculate_confidence_interval(
        self, data: List[float], confidence: float = 0.95
    ) -> ConfidenceInterval:
        """
        Calculate 95% confidence interval for mean.

        Uses normal approximation: mean ± 1.96 * (stddev / sqrt(n))
        """
        if len(data) < 2:
            mean_val = statistics.mean(data) if data else 0.0
            return ConfidenceInterval(lower=mean_val, upper=mean_val, confidence=0.0)

        mean_val = statistics.mean(data)
        stddev = statistics.stdev(data)
        n = len(data)

        # Z-score for 95% confidence = 1.96
        margin = 1.96 * (stddev / (n**0.5))

        return ConfidenceInterval(
            lower=mean_val - margin, upper=mean_val + margin, confidence=confidence
        )

    def _calculate_resource_metrics(self) -> ResourceMetrics:
        """Calculate resource usage metrics."""
        if not self._resource_snapshots:
            return ResourceMetrics(
                cpu_mean=0.0,
                cpu_peak=0.0,
                memory_mean_mb=0.0,
                memory_peak_mb=0.0,
                threads_mean=0.0,
                threads_peak=0,
            )

        cpu_values = [s.cpu_percent for s in self._resource_snapshots]
        memory_values = [s.memory_mb for s in self._resource_snapshots]
        thread_values = [s.threads for s in self._resource_snapshots]

        return ResourceMetrics(
            cpu_mean=statistics.mean(cpu_values),
            cpu_peak=max(cpu_values),
            memory_mean_mb=statistics.mean(memory_values),
            memory_peak_mb=max(memory_values),
            threads_mean=statistics.mean(thread_values),
            threads_peak=max(thread_values),
        )

    def run(self) -> BenchmarkResult:
        """
        Execute benchmark with warmup and measurement phases.

        Returns:
            BenchmarkResult with complete metrics
        """
        # Set random seed for reproducibility
        random.seed(self.seed)

        logger.info(f"Running benchmark: {self.name}")
        logger.info(f"  Warmup: {self.warmup} iterations")
        logger.info(f"  Measurement: {self.iterations} iterations")

        start_time = time.time()

        # Phase 1: Warmup (excluded from results)
        logger.debug(f"Warmup phase: {self.warmup} iterations...")
        for i in range(self.warmup):
            try:
                self.func()
            except Exception as e:
                logger.error(f"Warmup iteration {i+1} failed: {e}")
                raise

        # Phase 2: Measurement
        logger.debug(f"Measurement phase: {self.iterations} iterations...")
        for i in range(self.iterations):
            # Take resource snapshot before measurement
            self._resource_snapshots.append(self._take_resource_snapshot())

            # Measure execution time
            iter_start = time.perf_counter()
            try:
                self.func()
            except Exception as e:
                logger.error(f"Measurement iteration {i+1} failed: {e}")
                raise
            iter_elapsed = (time.perf_counter() - iter_start) * 1000  # Convert to ms

            self._latencies.append(iter_elapsed)

            # Take resource snapshot after measurement
            self._resource_snapshots.append(self._take_resource_snapshot())

        # Phase 3: Analysis
        # Remove outliers
        original_count = len(self._latencies)
        filtered_latencies = self._remove_outliers(self._latencies)
        outliers_removed = original_count - len(filtered_latencies)

        # Calculate metrics
        latency_metrics = self._calculate_percentiles(filtered_latencies)
        confidence_interval = self._calculate_confidence_interval(filtered_latencies)
        resource_metrics = self._calculate_resource_metrics()

        # Calculate throughput
        throughput = 1000.0 / latency_metrics.mean if latency_metrics.mean > 0 else 0.0

        duration = time.time() - start_time

        result = BenchmarkResult(
            name=self.name,
            iterations=self.iterations,
            warmup_iterations=self.warmup,
            latency_ms=latency_metrics,
            throughput_ops_per_sec=throughput,
            resources=resource_metrics,
            confidence_interval=confidence_interval,
            outliers_removed=outliers_removed,
            timestamp=datetime.now().isoformat(),
            duration_seconds=duration,
            metadata=self.metadata,
        )

        logger.info(f"Benchmark complete: {self.name}")
        logger.info(f"  Mean latency: {latency_metrics.mean:.2f}ms")
        logger.info(f"  P95 latency: {latency_metrics.p95:.2f}ms")
        logger.info(f"  Throughput: {throughput:.2f} ops/sec")

        return result


# ═══════════════════════════════════════════════════════════════
# Benchmark Suite
# ═══════════════════════════════════════════════════════════════


class BenchmarkSuite:
    """
    Collection of benchmark cases with unified execution and reporting.

    Example:
        suite = BenchmarkSuite(name="Memory Performance")

        @suite.benchmark(name="Hot Tier", warmup=10, iterations=100)
        def bench_hot():
            # benchmark code
            pass

        results = suite.run()
        suite.export_results("results.json")
    """

    def __init__(
        self,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.metadata = metadata or {}
        self._benchmarks: List[BenchmarkCase] = []
        self._results: Optional[SuiteResult] = None

    def benchmark(
        self,
        name: str,
        warmup: int = 10,
        iterations: int = 100,
        outlier_threshold: float = 3.0,
        seed: int = 42,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Decorator to register a benchmark function.

        Args:
            name: Benchmark name
            warmup: Number of warmup iterations
            iterations: Number of measurement iterations
            outlier_threshold: Standard deviations for outlier removal
            seed: Random seed for reproducibility
            metadata: Additional metadata
        """

        def decorator(func: Callable):
            case = BenchmarkCase(
                name=name,
                func=func,
                warmup=warmup,
                iterations=iterations,
                outlier_threshold=outlier_threshold,
                seed=seed,
                metadata=metadata or {},
            )
            self._benchmarks.append(case)
            return func

        return decorator

    def add_benchmark(self, case: BenchmarkCase):
        """Manually add a benchmark case."""
        self._benchmarks.append(case)

    def run(self) -> SuiteResult:
        """
        Execute all benchmarks in the suite.

        Returns:
            SuiteResult with all benchmark results
        """
        logger.info(f"Running benchmark suite: {self.name}")
        logger.info(f"Benchmarks: {len(self._benchmarks)}")

        start_time = time.time()
        results = []

        for case in self._benchmarks:
            result = case.run()
            results.append(result)

        duration = time.time() - start_time

        # Collect environment info
        environment = {
            "python_version": "3.12+",
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            "platform": "darwin",  # From CLAUDE.md env
        }

        self._results = SuiteResult(
            suite_name=self.name,
            benchmark_results=results,
            total_duration_seconds=duration,
            timestamp=datetime.now().isoformat(),
            environment=environment,
            metadata=self.metadata,
        )

        logger.info(f"Suite complete: {self.name}")
        logger.info(f"  Duration: {duration:.2f}s")
        logger.info(f"  Benchmarks: {len(results)}")

        return self._results

    def export_results(self, path: Path):
        """
        Export results to JSON file.

        Args:
            path: Output file path
        """
        if not self._results:
            raise ValueError("No results to export. Run suite first.")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to JSON-serializable format
        data = asdict(self._results)

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Results exported to {path}")

    def print_summary(self):
        """Print human-readable summary of results."""
        if not self._results:
            raise ValueError("No results to print. Run suite first.")

        print("\n" + "=" * 80)
        print(f"BENCHMARK SUITE: {self._results.suite_name}")
        print("=" * 80)
        print(f"Timestamp: {self._results.timestamp}")
        print(f"Duration: {self._results.total_duration_seconds:.2f}s")
        print(f"Benchmarks: {len(self._results.benchmark_results)}")
        print()

        for result in self._results.benchmark_results:
            print(f"Benchmark: {result.name}")
            print(
                f"  Iterations: {result.iterations} (warmup: {result.warmup_iterations})"
            )
            print("  Latency:")
            print(f"    - Mean:   {result.latency_ms.mean:.2f}ms")
            print(f"    - Median: {result.latency_ms.p50:.2f}ms")
            print(f"    - P95:    {result.latency_ms.p95:.2f}ms")
            print(f"    - P99:    {result.latency_ms.p99:.2f}ms")
            print(f"    - StdDev: {result.latency_ms.stddev:.2f}ms")
            print(f"  Throughput: {result.throughput_ops_per_sec:.2f} ops/sec")
            print("  Resources:")
            print(f"    - CPU Mean: {result.resources.cpu_mean:.1f}%")
            print(f"    - CPU Peak: {result.resources.cpu_peak:.1f}%")
            print(f"    - Memory Mean: {result.resources.memory_mean_mb:.1f}MB")
            print(f"    - Memory Peak: {result.resources.memory_peak_mb:.1f}MB")
            print(
                f"  Confidence Interval (95%): [{result.confidence_interval.lower:.2f}, {result.confidence_interval.upper:.2f}]ms"
            )
            print(f"  Outliers Removed: {result.outliers_removed}")
            print()

        print("=" * 80)


# ═══════════════════════════════════════════════════════════════
# Convenience Exports
# ═══════════════════════════════════════════════════════════════

__all__ = [
    "BenchmarkSuite",
    "BenchmarkCase",
    "BenchmarkResult",
    "SuiteResult",
    "PercentileMetrics",
    "ResourceMetrics",
    "ConfidenceInterval",
]
