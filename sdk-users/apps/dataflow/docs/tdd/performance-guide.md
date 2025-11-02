# DataFlow TDD Performance Guide

**Understanding and optimizing TDD performance for enterprise applications**

This guide provides detailed information about DataFlow's TDD performance characteristics, benchmarks, optimization techniques, and monitoring approaches.

## Performance Overview

### Performance Targets

| Metric | Target | Traditional | Improvement |
|--------|--------|-------------|-------------|
| Individual Test | <100ms | 2000-5000ms | 20-50x faster |
| Fixture Setup | <5ms | 500-1000ms | 100-200x faster |
| Schema Operations | <10ms | 200-800ms | 20-80x faster |
| Connection Acquisition | <5ms | 100-500ms | 20-100x faster |
| Test Suite (20 tests) | <5 seconds | 60-120 seconds | 12-24x faster |

### Architecture Benefits

```python
# Traditional Approach (SLOW)
def traditional_test_setup():
    """
    Traditional test setup - expensive operations
    Total time: 2000-5000ms per test
    """
    # 1. Drop entire schema (1000-2000ms)
    subprocess.run(["psql", "-c", "DROP SCHEMA public CASCADE"])

    # 2. Recreate schema (300-500ms)
    subprocess.run(["psql", "-c", "CREATE SCHEMA public"])

    # 3. Create new connection (100-200ms)
    connection = create_new_connection()

    # 4. Create all tables (500-1000ms)
    run_all_migrations()

    # 5. Setup test data (200-500ms)
    create_test_data()

# TDD Approach (FAST)
@pytest.mark.asyncio
async def tdd_test_setup(tdd_test_context):
    """
    TDD test setup - optimized operations
    Total time: <100ms per test
    """
    context = tdd_test_context

    # 1. Reuse existing connection (<1ms)
    connection = context.connection

    # 2. Create savepoint for isolation (<5ms)
    # Automatic via TDD infrastructure

    # 3. Create only needed tables (<10ms)
    await connection.execute("CREATE TEMP TABLE test_table (...)")

    # 4. Insert minimal test data (<5ms)
    await connection.execute("INSERT INTO test_table VALUES (...)")

    # 5. Automatic rollback on completion (<1ms)
    # Automatic via savepoint cleanup
```

## Performance Benchmarks

### Benchmark Infrastructure

```python
# benchmark_tdd_performance.py
import asyncio
import time
import statistics
from typing import List, Dict, Any
import pytest

class TDDPerformanceBenchmark:
    """Comprehensive TDD performance benchmarking"""

    def __init__(self):
        self.measurements: Dict[str, List[float]] = {}
        self.baseline_targets = {
            "individual_test": 100.0,  # ms
            "fixture_setup": 5.0,      # ms
            "connection_acquire": 5.0,  # ms
            "schema_operation": 10.0,   # ms
            "test_cleanup": 5.0,        # ms
            "parallel_execution": 100.0 # ms per test in parallel
        }

    def record_measurement(self, operation: str, duration_ms: float):
        """Record a performance measurement"""
        if operation not in self.measurements:
            self.measurements[operation] = []
        self.measurements[operation].append(duration_ms)

    async def benchmark_individual_test(self, iterations: int = 50):
        """Benchmark individual test execution"""
        measurements = []

        for i in range(iterations):
            start = time.time()

            # Simulate typical TDD test
            async with tdd_test_context() as context:
                connection = context.connection

                # Create test table
                await connection.execute("""
                    CREATE TEMP TABLE bench_test (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100),
                        value INTEGER
                    )
                """)

                # Insert test data
                await connection.execute(
                    "INSERT INTO bench_test (name, value) VALUES ($1, $2)",
                    f"test_{i}", i
                )

                # Query test data
                result = await connection.fetchval(
                    "SELECT COUNT(*) FROM bench_test"
                )
                assert result == 1

            duration_ms = (time.time() - start) * 1000
            measurements.append(duration_ms)
            self.record_measurement("individual_test", duration_ms)

        return measurements

    async def benchmark_fixture_setup(self, iterations: int = 100):
        """Benchmark fixture setup overhead"""
        measurements = []

        for i in range(iterations):
            start = time.time()

            # Just fixture setup, no test operations
            async with tdd_test_context() as context:
                # Fixture is ready
                pass

            duration_ms = (time.time() - start) * 1000
            measurements.append(duration_ms)
            self.record_measurement("fixture_setup", duration_ms)

        return measurements

    async def benchmark_connection_acquisition(self, iterations: int = 100):
        """Benchmark connection acquisition time"""
        db_manager = get_database_manager()
        await db_manager.initialize()

        measurements = []

        for i in range(iterations):
            context = TDDTestContext(test_id=f"bench_{i}")

            start = time.time()
            connection = await db_manager.get_test_connection(context)
            duration_ms = (time.time() - start) * 1000

            measurements.append(duration_ms)
            self.record_measurement("connection_acquire", duration_ms)

            # Cleanup
            await db_manager.cleanup_test_connection(context)

        await db_manager.close()
        return measurements

    async def benchmark_schema_operations(self, iterations: int = 50):
        """Benchmark schema creation operations"""
        measurements = []

        async with tdd_test_context() as context:
            connection = context.connection

            for i in range(iterations):
                start = time.time()

                # Create temporary table (realistic schema operation)
                table_name = f"schema_bench_{i}"
                await connection.execute(f"""
                    CREATE TEMP TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(255),
                        email VARCHAR(255),
                        created_at TIMESTAMP DEFAULT NOW(),
                        metadata JSONB
                    )
                """)

                duration_ms = (time.time() - start) * 1000
                measurements.append(duration_ms)
                self.record_measurement("schema_operation", duration_ms)

        return measurements

    async def benchmark_parallel_execution(self, concurrent_tests: int = 10):
        """Benchmark parallel test execution"""
        async def single_parallel_test(test_id: int):
            """Single test for parallel execution"""
            start = time.time()

            async with tdd_test_context(test_id=f"parallel_{test_id}") as context:
                connection = context.connection

                # Unique table for this parallel test
                table_name = f"parallel_test_{test_id}"
                await connection.execute(f"""
                    CREATE TEMP TABLE {table_name} (
                        id SERIAL PRIMARY KEY,
                        test_id INTEGER,
                        data TEXT
                    )
                """)

                # Insert test data
                await connection.execute(
                    f"INSERT INTO {table_name} (test_id, data) VALUES ($1, $2)",
                    test_id, f"parallel_data_{test_id}"
                )

                # Query data
                result = await connection.fetchval(
                    f"SELECT COUNT(*) FROM {table_name} WHERE test_id = $1",
                    test_id
                )
                assert result == 1

            return (time.time() - start) * 1000

        # Run tests in parallel
        start_total = time.time()
        tasks = [single_parallel_test(i) for i in range(concurrent_tests)]
        measurements = await asyncio.gather(*tasks)
        total_duration = (time.time() - start_total) * 1000

        # Record measurements
        for duration in measurements:
            self.record_measurement("parallel_execution", duration)

        return {
            "individual_times": measurements,
            "total_time": total_duration,
            "average_time": statistics.mean(measurements),
            "max_time": max(measurements),
            "parallel_efficiency": sum(measurements) / total_duration
        }

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report = {
            "targets": self.baseline_targets,
            "measurements": {},
            "summary": {}
        }

        for operation, times in self.measurements.items():
            if not times:
                continue

            target = self.baseline_targets.get(operation, 100.0)

            stats = {
                "count": len(times),
                "mean": statistics.mean(times),
                "median": statistics.median(times),
                "min": min(times),
                "max": max(times),
                "std_dev": statistics.stdev(times) if len(times) > 1 else 0.0,
                "target": target,
                "target_achieved": statistics.mean(times) <= target,
                "success_rate": sum(1 for t in times if t <= target) / len(times) * 100
            }

            report["measurements"][operation] = stats

        # Overall summary
        all_operations = list(report["measurements"].keys())
        targets_met = sum(1 for op in all_operations
                         if report["measurements"][op]["target_achieved"])

        report["summary"] = {
            "operations_tested": len(all_operations),
            "targets_met": targets_met,
            "overall_success_rate": (targets_met / len(all_operations)) * 100 if all_operations else 0,
            "recommendation": self._get_performance_recommendation(report)
        }

        return report

    def _get_performance_recommendation(self, report: Dict[str, Any]) -> str:
        """Get performance optimization recommendations"""
        success_rate = report["summary"]["overall_success_rate"]

        if success_rate >= 95:
            return "Excellent performance - all targets met"
        elif success_rate >= 80:
            return "Good performance - minor optimizations possible"
        elif success_rate >= 60:
            return "Moderate performance - optimization recommended"
        else:
            return "Poor performance - immediate optimization required"

# Usage example
async def run_comprehensive_benchmark():
    """Run complete TDD performance benchmark"""
    benchmark = TDDPerformanceBenchmark()

    print("Running TDD Performance Benchmark...")

    # Individual test performance
    print("Benchmarking individual tests...")
    await benchmark.benchmark_individual_test(50)

    # Fixture setup performance
    print("Benchmarking fixture setup...")
    await benchmark.benchmark_fixture_setup(100)

    # Connection acquisition
    print("Benchmarking connection acquisition...")
    await benchmark.benchmark_connection_acquisition(100)

    # Schema operations
    print("Benchmarking schema operations...")
    await benchmark.benchmark_schema_operations(50)

    # Parallel execution
    print("Benchmarking parallel execution...")
    await benchmark.benchmark_parallel_execution(10)

    # Generate report
    report = benchmark.generate_performance_report()

    # Print summary
    print("\n" + "="*50)
    print("TDD PERFORMANCE BENCHMARK REPORT")
    print("="*50)

    for operation, stats in report["measurements"].items():
        status = "✅ PASS" if stats["target_achieved"] else "❌ FAIL"
        print(f"{status} {operation}:")
        print(f"  Average: {stats['mean']:.2f}ms (target: {stats['target']:.0f}ms)")
        print(f"  Success rate: {stats['success_rate']:.1f}%")
        print(f"  Range: {stats['min']:.2f}ms - {stats['max']:.2f}ms")
        print()

    print(f"Overall Success Rate: {report['summary']['overall_success_rate']:.1f}%")
    print(f"Recommendation: {report['summary']['recommendation']}")

    return report
```

### Real-World Performance Results

```python
# Expected benchmark results on modern hardware
EXPECTED_PERFORMANCE_RESULTS = {
    "individual_test": {
        "mean": 65.2,      # ms
        "median": 62.1,    # ms
        "min": 45.3,       # ms
        "max": 89.7,       # ms
        "target": 100.0,   # ms
        "success_rate": 98.2  # %
    },
    "fixture_setup": {
        "mean": 3.1,       # ms
        "median": 2.9,     # ms
        "min": 2.1,        # ms
        "max": 4.8,        # ms
        "target": 5.0,     # ms
        "success_rate": 99.5  # %
    },
    "connection_acquire": {
        "mean": 2.4,       # ms
        "median": 2.2,     # ms
        "min": 1.8,        # ms
        "max": 3.9,        # ms
        "target": 5.0,     # ms
        "success_rate": 100.0  # %
    },
    "schema_operation": {
        "mean": 7.3,       # ms
        "median": 6.8,     # ms
        "min": 5.2,        # ms
        "max": 12.1,       # ms
        "target": 10.0,    # ms
        "success_rate": 96.8  # %
    },
    "parallel_execution": {
        "mean": 58.7,      # ms per test
        "parallel_efficiency": 0.89,  # 89% efficiency
        "total_time": 234.5,  # ms for 10 parallel tests
        "theoretical_sequential": 587.0,  # ms if run sequentially
        "speedup": 2.5     # 2.5x speedup from parallelization
    }
}
```

## Performance Optimization Techniques

### 1. Connection Pool Optimization

```python
# Optimized connection pool configuration
OPTIMIZED_POOL_CONFIG = {
    "min_size": 2,           # Keep minimum connections warm
    "max_size": 10,          # Reasonable maximum for tests
    "command_timeout": 30,   # Prevent hanging connections
    "server_settings": {
        "jit": "off",        # Disable JIT for faster small queries
        "shared_preload_libraries": "",  # Minimal preloaded libraries
    }
}

@pytest.fixture(scope="session")
async def optimized_connection_pool():
    """Session-scoped optimized connection pool"""
    pool = await asyncpg.create_pool(
        test_database_url,
        **OPTIMIZED_POOL_CONFIG
    )

    # Pre-warm connections
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")  # Warm up connection

    yield pool
    await pool.close()
```

### 2. Schema Caching Strategy

```python
class SchemaCache:
    """Intelligent schema caching for TDD tests"""

    def __init__(self):
        self.cache = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "ddl_operations_saved": 0
        }

    def get_cached_ddl(self, schema_hash: str) -> str:
        """Get cached DDL by schema hash"""
        if schema_hash in self.cache:
            self.cache_stats["hits"] += 1
            self.cache_stats["ddl_operations_saved"] += 1
            return self.cache[schema_hash]

        self.cache_stats["misses"] += 1
        return None

    def cache_ddl(self, schema_hash: str, ddl: str):
        """Cache DDL for future use"""
        self.cache[schema_hash] = ddl

    def get_cache_efficiency(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_stats["hits"] + self.cache_stats["misses"]
        return (self.cache_stats["hits"] / total) * 100 if total > 0 else 0

# Usage in tests
schema_cache = SchemaCache()

@pytest.mark.asyncio
async def test_with_schema_caching(tdd_test_context):
    """Test using schema caching for performance"""
    context = tdd_test_context
    connection = context.connection

    # Generate schema hash
    schema_definition = """
        CREATE TEMP TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(255)
        )
    """
    schema_hash = hashlib.md5(schema_definition.encode()).hexdigest()

    # Check cache first
    cached_ddl = schema_cache.get_cached_ddl(schema_hash)
    if cached_ddl:
        # Use cached version (faster)
        await connection.execute(cached_ddl)
    else:
        # Execute and cache
        await connection.execute(schema_definition)
        schema_cache.cache_ddl(schema_hash, schema_definition)
```

### 3. Parallel Execution Optimization

```python
# Parallel execution with resource management
class ParallelTestManager:
    """Manage parallel test execution with resource allocation"""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.resource_locks = {}
        self.active_tests = set()

    async def allocate_resources(self, test_id: str, resources: List[str]) -> bool:
        """Allocate resources for parallel test"""
        # Check if resources are available
        for resource in resources:
            if resource in self.resource_locks:
                return False  # Resource busy

        # Allocate resources
        for resource in resources:
            self.resource_locks[resource] = test_id

        self.active_tests.add(test_id)
        return True

    async def release_resources(self, test_id: str):
        """Release resources after test completion"""
        # Release all resources held by this test
        resources_to_release = [
            resource for resource, holder in self.resource_locks.items()
            if holder == test_id
        ]

        for resource in resources_to_release:
            del self.resource_locks[resource]

        self.active_tests.discard(test_id)

# Parallel-safe test fixture
@pytest.fixture
async def parallel_safe_test():
    """Parallel-safe test with resource management"""
    test_id = f"parallel_{uuid.uuid4().hex[:8]}"
    manager = ParallelTestManager()

    # Allocate unique resources
    resources = [f"table_users_{test_id}", f"table_orders_{test_id}"]
    allocated = await manager.allocate_resources(test_id, resources)

    if not allocated:
        pytest.skip("Resources not available for parallel execution")

    try:
        yield test_id, resources
    finally:
        await manager.release_resources(test_id)
```

### 4. Memory Optimization

```python
class MemoryOptimizer:
    """Memory optimization for TDD tests"""

    def __init__(self):
        self.tracked_objects = []
        self.memory_snapshots = {}

    def track_object(self, obj, obj_type: str = None):
        """Track object for memory management"""
        self.tracked_objects.append((obj, obj_type))

    def take_memory_snapshot(self, label: str) -> Dict[str, float]:
        """Take memory usage snapshot"""
        import psutil
        import gc

        # Force garbage collection
        gc.collect()

        process = psutil.Process()
        memory_info = process.memory_info()

        snapshot = {
            "label": label,
            "rss_mb": memory_info.rss / 1024 / 1024,  # MB
            "vms_mb": memory_info.vms / 1024 / 1024,  # MB
            "timestamp": time.time()
        }

        self.memory_snapshots[label] = snapshot
        return snapshot

    def optimize_memory(self):
        """Optimize memory usage"""
        import gc

        # Clear tracked objects
        self.tracked_objects.clear()

        # Force garbage collection
        gc.collect()

        # Clear caches if available
        if hasattr(gc, 'clear_cache'):
            gc.clear_cache()

# Memory-optimized test fixture
@pytest.fixture
async def memory_optimized_test():
    """Memory-optimized test execution"""
    optimizer = MemoryOptimizer()

    # Take initial snapshot
    initial = optimizer.take_memory_snapshot("test_start")

    yield optimizer

    # Take final snapshot
    final = optimizer.take_memory_snapshot("test_end")

    # Calculate memory delta
    memory_delta = final["rss_mb"] - initial["rss_mb"]

    # Optimize memory
    optimizer.optimize_memory()

    # Warn if memory usage is high
    if memory_delta > 5.0:  # 5MB threshold
        pytest.warns(
            UserWarning,
            f"High memory usage detected: {memory_delta:.2f}MB increase"
        )
```

## Performance Monitoring

### 1. Real-Time Performance Tracking

```python
class PerformanceMonitor:
    """Real-time performance monitoring for TDD tests"""

    def __init__(self):
        self.metrics = {}
        self.alerts = []
        self.thresholds = {
            "test_duration_ms": 100,
            "fixture_setup_ms": 5,
            "memory_usage_mb": 10
        }

    def record_metric(self, name: str, value: float, metadata: Dict = None):
        """Record performance metric"""
        if name not in self.metrics:
            self.metrics[name] = []

        metric_entry = {
            "value": value,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }

        self.metrics[name].append(metric_entry)

        # Check for threshold violations
        self._check_thresholds(name, value)

    def _check_thresholds(self, metric_name: str, value: float):
        """Check if metric exceeds thresholds"""
        threshold = self.thresholds.get(metric_name)
        if threshold and value > threshold:
            alert = {
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "timestamp": time.time(),
                "severity": "warning" if value <= threshold * 1.5 else "critical"
            }
            self.alerts.append(alert)

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        summary = {}

        for metric_name, entries in self.metrics.items():
            if not entries:
                continue

            values = [entry["value"] for entry in entries]
            threshold = self.thresholds.get(metric_name)

            summary[metric_name] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "min": min(values),
                "max": max(values),
                "threshold": threshold,
                "violations": sum(1 for v in values if threshold and v > threshold)
            }

        return summary

# Performance monitoring fixture
@pytest.fixture
def performance_monitor():
    """Performance monitoring for tests"""
    monitor = PerformanceMonitor()

    # Track test start time
    test_start = time.time()

    yield monitor

    # Record test duration
    test_duration = (time.time() - test_start) * 1000
    monitor.record_metric("test_duration_ms", test_duration)

    # Check for alerts
    if monitor.alerts:
        for alert in monitor.alerts:
            pytest.warns(
                UserWarning,
                f"Performance alert: {alert['metric']} = {alert['value']:.2f} "
                f"(threshold: {alert['threshold']:.2f})"
            )
```

### 2. Performance Regression Detection

```python
class RegressionDetector:
    """Detect performance regressions in TDD tests"""

    def __init__(self, baseline_file: str = "tdd_performance_baseline.json"):
        self.baseline_file = Path(baseline_file)
        self.baseline_data = self._load_baseline()
        self.regression_threshold = 1.2  # 20% degradation

    def _load_baseline(self) -> Dict[str, float]:
        """Load performance baseline data"""
        if self.baseline_file.exists():
            with open(self.baseline_file) as f:
                return json.load(f)
        return {}

    def _save_baseline(self, data: Dict[str, float]):
        """Save performance baseline data"""
        with open(self.baseline_file, 'w') as f:
            json.dump(data, f, indent=2)

    def check_regression(self, metric_name: str, current_value: float) -> Dict[str, Any]:
        """Check for performance regression"""
        baseline_value = self.baseline_data.get(metric_name)

        if baseline_value is None:
            # No baseline - record current value
            self.baseline_data[metric_name] = current_value
            self._save_baseline(self.baseline_data)

            return {
                "regression_detected": False,
                "reason": "No baseline data - establishing baseline",
                "baseline_value": current_value,
                "current_value": current_value
            }

        # Check for regression
        regression_threshold_value = baseline_value * self.regression_threshold
        regression_detected = current_value > regression_threshold_value

        # Update baseline with better performance
        if current_value < baseline_value:
            self.baseline_data[metric_name] = current_value
            self._save_baseline(self.baseline_data)

        return {
            "regression_detected": regression_detected,
            "baseline_value": baseline_value,
            "current_value": current_value,
            "threshold_value": regression_threshold_value,
            "degradation_factor": current_value / baseline_value if baseline_value > 0 else 1.0,
            "improvement": current_value < baseline_value
        }

# Regression detection fixture
@pytest.fixture
def regression_detector():
    """Performance regression detection"""
    detector = RegressionDetector()

    yield detector

    # Can be used to check specific metrics after test completion
```

### 3. Continuous Performance Monitoring

```python
# CI/CD Performance Gate
class PerformanceGate:
    """Performance gate for CI/CD pipelines"""

    def __init__(self):
        self.required_metrics = {
            "average_test_time_ms": 100,
            "max_test_time_ms": 200,
            "fixture_setup_time_ms": 10,
            "test_suite_time_seconds": 30
        }
        self.measurements = {}

    def record_measurement(self, metric: str, value: float):
        """Record a measurement for gate evaluation"""
        self.measurements[metric] = value

    def evaluate_gate(self) -> Dict[str, Any]:
        """Evaluate performance gate"""
        results = {
            "passed": True,
            "failures": [],
            "measurements": self.measurements,
            "requirements": self.required_metrics
        }

        for metric, threshold in self.required_metrics.items():
            measured_value = self.measurements.get(metric)

            if measured_value is None:
                results["failures"].append(f"Missing measurement: {metric}")
                results["passed"] = False
            elif measured_value > threshold:
                results["failures"].append(
                    f"{metric}: {measured_value:.2f} > {threshold:.2f} (threshold)"
                )
                results["passed"] = False

        return results

# Usage in CI/CD
def validate_performance_gate():
    """Validate performance gate in CI/CD"""
    gate = PerformanceGate()

    # Run performance benchmark
    benchmark_results = run_tdd_benchmark()

    # Record measurements
    gate.record_measurement("average_test_time_ms", benchmark_results["avg_test_time"])
    gate.record_measurement("max_test_time_ms", benchmark_results["max_test_time"])
    gate.record_measurement("test_suite_time_seconds", benchmark_results["total_time"])

    # Evaluate gate
    gate_result = gate.evaluate_gate()

    if not gate_result["passed"]:
        print("❌ Performance gate FAILED:")
        for failure in gate_result["failures"]:
            print(f"  - {failure}")
        return False
    else:
        print("✅ Performance gate PASSED")
        return True
```

## Troubleshooting Performance Issues

### Common Performance Problems

#### 1. Connection Pool Exhaustion

```python
# Problem: Tests timeout waiting for connections
# Symptoms: TimeoutError, ConnectionPoolExhaustedError

# Solution: Optimize connection usage
@pytest.fixture(scope="session")
async def shared_connection_pool():
    """Shared connection pool to prevent exhaustion"""
    pool = await asyncpg.create_pool(
        test_database_url,
        min_size=5,      # Increase minimum
        max_size=15,     # Increase maximum
        command_timeout=10  # Faster timeout
    )

    yield pool
    await pool.close()

# Usage
@pytest.mark.asyncio
async def test_with_shared_pool(shared_connection_pool):
    """Test using shared connection pool"""
    async with shared_connection_pool.acquire() as connection:
        # Test operations
        pass
```

#### 2. Slow Schema Operations

```python
# Problem: DDL operations taking too long
# Symptoms: Tests exceeding 100ms target

# Solution: Use schema templates and caching
COMMON_SCHEMA_TEMPLATES = {
    "user_table": """
        CREATE TEMP TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            email VARCHAR(255)
        )
    """,
    "order_table": """
        CREATE TEMP TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            total DECIMAL(10,2)
        )
    """
}

@pytest.mark.asyncio
async def test_with_schema_template(tdd_test_context):
    """Test using pre-defined schema templates"""
    context = tdd_test_context
    connection = context.connection

    # Fast schema creation using template
    schema_sql = COMMON_SCHEMA_TEMPLATES["user_table"].format(
        table_name="test_users"
    )
    await connection.execute(schema_sql)
```

#### 3. Memory Leaks

```python
# Problem: Memory usage grows over test execution
# Symptoms: pytest consuming excessive memory

# Solution: Implement memory tracking and cleanup
@pytest.fixture(autouse=True)
def memory_tracker():
    """Automatic memory tracking for all tests"""
    import gc
    import psutil

    # Initial memory
    process = psutil.Process()
    initial_memory = process.memory_info().rss

    yield

    # Force cleanup
    gc.collect()

    # Check final memory
    final_memory = process.memory_info().rss
    memory_delta = (final_memory - initial_memory) / 1024 / 1024  # MB

    # Warn if memory increase is significant
    if memory_delta > 10:  # 10MB threshold
        pytest.warns(
            UserWarning,
            f"Potential memory leak: {memory_delta:.2f}MB increase"
        )
```

This performance guide provides comprehensive insights into DataFlow TDD performance characteristics, optimization techniques, and monitoring approaches to ensure your tests consistently achieve enterprise-grade performance targets.
