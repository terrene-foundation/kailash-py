"""
Enhanced TDD Fixtures with Performance Optimization

High-performance test fixtures that integrate with the performance optimization
module to achieve consistent <100ms execution times. These fixtures build upon
the basic TDD support with advanced connection pooling, schema caching, and
parallel execution capabilities.

Key Features:
- Integration with performance optimization managers
- Connection pool preheating and reuse
- Schema caching and lazy loading
- Thread-safe parallel execution
- Real-time performance monitoring
- Memory optimization and leak prevention

Performance Targets:
- Individual test execution: <100ms consistently
- Fixture setup: <5ms (using preheated pools)
- Schema operations: <10ms (using cache)
- Parallel isolation: 100% success rate
- Memory overhead: <2MB per test context
"""

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import asyncpg
import pytest
from dataflow.testing.performance_optimization import (
    PerformanceMetrics,
    get_memory_optimizer,
    get_parallel_manager,
    get_performance_monitor,
    get_pool_manager,
    get_schema_cache,
    is_optimization_enabled,
    optimized_test_context,
)
from dataflow.testing.tdd_support import (
    TDDTestContext,
    get_database_manager,
    get_transaction_manager,
    is_tdd_mode,
)

logger = logging.getLogger(__name__)


@dataclass
class EnhancedTestContext:
    """Enhanced test context with performance optimization."""

    test_id: str
    base_context: TDDTestContext
    optimization_context: Dict[str, Any]
    metrics: PerformanceMetrics
    preheated_pool: bool = False
    cached_schema: bool = False
    parallel_safe: bool = False
    memory_optimized: bool = False


class OptimizedModelFactory:
    """Model factory with schema caching and lazy loading."""

    def __init__(self, test_id: str, schema_cache=None):
        self.test_id = test_id
        self.schema_cache = schema_cache or get_schema_cache()
        self.created_models = []
        self.lazy_models = {}

    def create_cached_user_model(self) -> type:
        """Create User model with schema caching."""
        model_key = f"User_{self.test_id}"

        if self.schema_cache.is_schema_cached(model_key):
            # Use cached schema
            cached = self.schema_cache.get_cached_schema(model_key)
            logger.debug(f"Using cached schema for User model: {model_key}")

        class User:
            id: int = None
            name: str
            email: str
            active: bool = True
            created_at: str = None
            updated_at: str = None
            profile_data: Dict[str, Any] = None

        User.__name__ = f"OptimizedUser_{self.test_id}"
        User.__tablename__ = f"opt_users_{self.test_id}"
        User.__cached__ = True

        # Cache the schema
        self.schema_cache.cache_schema(
            model_key,
            {
                "users": f"CREATE TABLE opt_users_{self.test_id} (id SERIAL PRIMARY KEY, name VARCHAR(255), email VARCHAR(255), active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP, updated_at TIMESTAMP, profile_data JSONB)"
            },
        )

        self.created_models.append(User)
        return User

    def create_lazy_product_model(self) -> type:
        """Create Product model with lazy loading."""
        model_key = f"Product_{self.test_id}"

        if not self.schema_cache.is_lazy_loaded(model_key):
            self.schema_cache.mark_lazy_loaded(model_key)

        class Product:
            id: int = None
            name: str
            price: float
            category: str = "general"
            in_stock: bool = True
            sku: str = None
            attributes: Dict[str, Any] = None

        Product.__name__ = f"LazyProduct_{self.test_id}"
        Product.__tablename__ = f"lazy_products_{self.test_id}"
        Product.__lazy_loaded__ = True

        self.lazy_models[model_key] = Product
        return Product

    def get_model_statistics(self) -> Dict[str, Any]:
        """Get model creation statistics."""
        return {
            "created_models": len(self.created_models),
            "lazy_models": len(self.lazy_models),
            "total_models": len(self.created_models) + len(self.lazy_models),
            "cache_enabled": self.schema_cache is not None,
        }


@pytest.fixture
async def enhanced_tdd_context():
    """
    Enhanced TDD context with full performance optimization.

    Provides a complete test environment with:
    - Preheated connection pools
    - Schema caching
    - Parallel execution support
    - Performance monitoring
    - Memory optimization

    Example:
        async def test_optimized_operation(enhanced_tdd_context):
            context = enhanced_tdd_context
            # All optimizations are automatically enabled
            # Connection is preheated and ready
            # Schema operations use cache
            # Performance is monitored
    """
    if not is_tdd_mode():
        pytest.skip("TDD mode not enabled (set DATAFLOW_TDD_MODE=true)")

    if not is_optimization_enabled():
        pytest.skip("Performance optimization not enabled")

    test_id = f"enhanced_{uuid.uuid4().hex[:8]}"

    async with optimized_test_context(
        test_id=test_id,
        enable_pooling=True,
        enable_caching=True,
        enable_parallel=True,
        enable_monitoring=True,
        enable_memory_optimization=True,
    ) as opt_context:

        # Create base TDD context with optimized settings
        from dataflow.testing.tdd_support import tdd_test_context

        async with tdd_test_context(test_id=test_id) as base_context:
            enhanced_context = EnhancedTestContext(
                test_id=test_id,
                base_context=base_context,
                optimization_context=opt_context,
                metrics=opt_context["metrics"],
                preheated_pool=True,
                cached_schema=True,
                parallel_safe=True,
                memory_optimized=True,
            )

            yield enhanced_context


@pytest.fixture
async def preheated_dataflow():
    """
    DataFlow instance with preheated connection pool.

    Provides a DataFlow instance that uses preheated connections for
    maximum performance. Connection acquisition time is <5ms.

    Example:
        async def test_fast_database_ops(preheated_dataflow):
            df, pool_stats = preheated_dataflow
            # Connection is immediately available
            # No cold start delays
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"preheated_{uuid.uuid4().hex[:8]}"
    pool_manager = get_pool_manager()

    # Create optimized pool with preheating
    connection_string = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql://dataflow_test:dataflow_test_password@localhost:5434/dataflow_test",
    )

    pool = await pool_manager.create_optimized_pool(
        pool_id=test_id,
        connection_string=connection_string,
        min_size=2,
        max_size=5,
        preheat=True,
    )

    from dataflow import DataFlow

    # Create DataFlow with optimized pool settings
    df = DataFlow(
        database_url=connection_string,
        existing_schema_mode=True,
        auto_migrate=False,
        cache_enabled=False,
        pool_size=2,  # Match pool size
        pool_max_overflow=3,
        pool_timeout=5,
        echo=False,
        tdd_mode=True,
    )

    try:
        pool_stats = pool_manager.get_pool_statistics(test_id)
        yield df, pool_stats

    finally:
        df.close()
        await pool_manager.cleanup_pool(test_id)


@pytest.fixture
async def cached_schema_models():
    """
    Pre-cached test models for immediate use.

    Provides standard test models with pre-cached schemas to eliminate
    DDL overhead. Schema operations complete in <10ms.

    Example:
        async def test_with_cached_models(cached_schema_models):
            User, Product, Order, cache_stats = cached_schema_models
            # Models are immediately available
            # No table creation delays
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"cached_{uuid.uuid4().hex[:8]}"
    factory = OptimizedModelFactory(test_id)

    # Create models with caching
    User = factory.create_cached_user_model()
    Product = factory.create_lazy_product_model()

    # Create a simple Order model
    class Order:
        id: int = None
        user_id: int
        product_id: int
        quantity: int = 1
        total_price: float = 0.0
        status: str = "pending"

    Order.__name__ = f"CachedOrder_{test_id}"
    Order.__tablename__ = f"cached_orders_{test_id}"

    # Cache Order schema
    schema_cache = get_schema_cache()
    schema_cache.cache_schema(
        f"Order_{test_id}",
        {
            "orders": f"CREATE TABLE cached_orders_{test_id} (id SERIAL PRIMARY KEY, user_id INTEGER, product_id INTEGER, quantity INTEGER DEFAULT 1, total_price DECIMAL(10,2) DEFAULT 0.0, status VARCHAR(50) DEFAULT 'pending')"
        },
    )

    cache_stats = schema_cache.get_cache_statistics()

    yield User, Product, Order, cache_stats


@pytest.fixture
async def parallel_test_execution():
    """
    Thread-safe parallel test execution support.

    Provides isolation and resource management for parallel test execution.
    Ensures 100% success rate for concurrent tests.

    Example:
        async def test_parallel_operations(parallel_test_execution):
            context, isolation_id, resource_manager = parallel_test_execution
            # Safe for parallel execution
            # No race conditions
            # Proper resource isolation
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"parallel_{uuid.uuid4().hex[:12]}"
    parallel_manager = get_parallel_manager()

    # Register for parallel execution
    parallel_manager.register_parallel_test(
        test_id,
        threading.get_ident(),
        "SERIALIZABLE",  # Highest isolation for parallel tests
    )

    # Create isolation identifier
    isolation_id = f"iso_{uuid.uuid4().hex[:8]}"

    # Resource manager for deadlock prevention
    class ResourceManager:
        def __init__(self, test_id: str, parallel_manager):
            self.test_id = test_id
            self.parallel_manager = parallel_manager
            self.allocated_resources = set()

        def allocate(self, resource_name: str) -> bool:
            if self.parallel_manager.allocate_resource(self.test_id, resource_name):
                self.allocated_resources.add(resource_name)
                return True
            return False

        def release(self, resource_name: str):
            if resource_name in self.allocated_resources:
                self.parallel_manager.release_resource(self.test_id, resource_name)
                self.allocated_resources.remove(resource_name)

        def release_all(self):
            for resource in list(self.allocated_resources):
                self.release(resource)

    resource_manager = ResourceManager(test_id, parallel_manager)

    try:
        # Create test context with parallel isolation
        async with optimized_test_context(
            test_id=test_id, enable_parallel=True
        ) as context:
            yield context, isolation_id, resource_manager

    finally:
        # Cleanup
        resource_manager.release_all()
        parallel_manager.unregister_parallel_test(test_id)


@pytest.fixture
async def performance_monitored_test():
    """
    Test execution with real-time performance monitoring.

    Provides comprehensive performance monitoring with regression detection
    and alerting for performance degradation.

    Example:
        async def test_monitored_operation(performance_monitored_test):
            monitor, metrics_collector, alert_handler = performance_monitored_test

            with metrics_collector.measure("operation"):
                # Perform test operations
                pass

            # Performance is automatically monitored
            # Regressions are detected and reported
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"monitored_{uuid.uuid4().hex[:8]}"
    monitor = get_performance_monitor()

    # Create metrics collector
    class MetricsCollector:
        def __init__(self, test_id: str, monitor):
            self.test_id = test_id
            self.monitor = monitor
            self.current_metrics = None

        def measure(self, operation_name: str):
            return self._measure_context(operation_name)

        def _measure_context(self, operation_name: str):
            return MetricsContext(self, operation_name)

        def record_operation(self, operation_name: str, duration_ms: float, **metadata):
            metrics = PerformanceMetrics(
                operation_id=f"{self.test_id}_{operation_name}",
                operation_type=operation_name,
                duration_ms=duration_ms,
                **metadata,
            )
            metrics.target_achieved = duration_ms < 100.0
            self.monitor.record_metrics(metrics)
            self.current_metrics = metrics

    class MetricsContext:
        def __init__(self, collector: MetricsCollector, operation_name: str):
            self.collector = collector
            self.operation_name = operation_name
            self.start_time = 0.0

        def __enter__(self):
            self.start_time = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration_ms = (time.time() - self.start_time) * 1000
            self.collector.record_operation(self.operation_name, duration_ms)

    # Alert handler for performance issues
    class AlertHandler:
        def __init__(self):
            self.alerts = []

        def handle_alert(self, alert_data: Dict[str, Any]):
            self.alerts.append(alert_data)
            logger.warning(f"Performance alert: {alert_data}")

        def get_alerts(self) -> List[Dict[str, Any]]:
            return self.alerts.copy()

    metrics_collector = MetricsCollector(test_id, monitor)
    alert_handler = AlertHandler()

    # Register alert handler
    monitor.add_alert_callback(alert_handler.handle_alert)

    yield monitor, metrics_collector, alert_handler


@pytest.fixture
async def memory_optimized_test():
    """
    Test execution with memory optimization and leak detection.

    Provides memory optimization features to prevent leaks and ensure
    efficient resource utilization during test execution.

    Example:
        async def test_memory_efficient(memory_optimized_test):
            optimizer, tracker, cleanup_manager = memory_optimized_test

            # Memory usage is automatically tracked
            # Objects are cleaned up efficiently
            # Memory leaks are detected
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"memory_{uuid.uuid4().hex[:8]}"
    optimizer = get_memory_optimizer()

    # Take initial memory snapshot
    initial_snapshot = optimizer.take_memory_snapshot(f"start_{test_id}")

    # Memory tracker
    class MemoryTracker:
        def __init__(self, optimizer):
            self.optimizer = optimizer
            self.tracked_objects = []

        def track(self, obj, obj_type: str = None):
            self.optimizer.track_object(obj, obj_type)
            self.tracked_objects.append((obj, obj_type))

        def get_memory_delta(self) -> float:
            current = self.optimizer.take_memory_snapshot(f"current_{test_id}")
            return current["rss_mb"] - initial_snapshot["rss_mb"]

        def check_leak_threshold(self, threshold_mb: float = 5.0) -> bool:
            delta = self.get_memory_delta()
            return delta > threshold_mb

    # Cleanup manager
    class CleanupManager:
        def __init__(self, optimizer):
            self.optimizer = optimizer
            self.cleanup_callbacks = []

        def register_cleanup(self, callback):
            self.cleanup_callbacks.append(callback)
            self.optimizer.register_cleanup_callback(callback)

        def force_cleanup(self):
            for callback in self.cleanup_callbacks:
                try:
                    callback()
                except Exception as e:
                    logger.warning(f"Cleanup callback failed: {e}")

            self.optimizer.optimize_memory()

    tracker = MemoryTracker(optimizer)
    cleanup_manager = CleanupManager(optimizer)

    try:
        yield optimizer, tracker, cleanup_manager

    finally:
        # Final cleanup and memory check
        cleanup_manager.force_cleanup()
        final_snapshot = optimizer.take_memory_snapshot(f"end_{test_id}")

        memory_delta = final_snapshot["rss_mb"] - initial_snapshot["rss_mb"]
        if memory_delta > 5.0:  # 5MB threshold
            logger.warning(f"Memory leak detected: {memory_delta:.2f}MB increase")


@pytest.fixture
async def comprehensive_tdd_benchmark():
    """
    Comprehensive benchmark test environment.

    Combines all performance optimizations for complete benchmarking
    of TDD infrastructure. Validates <100ms execution target.

    Example:
        async def test_complete_benchmark(comprehensive_tdd_benchmark):
            benchmark_context = comprehensive_tdd_benchmark

            # All optimizations are enabled
            # Complete performance monitoring
            # Comprehensive statistics
    """
    if not is_tdd_mode() or not is_optimization_enabled():
        pytest.skip("TDD mode and optimization not enabled")

    test_id = f"benchmark_{uuid.uuid4().hex[:8]}"

    # Comprehensive benchmark context
    class BenchmarkContext:
        def __init__(self):
            self.test_id = test_id
            self.start_time = time.time()
            self.metrics = {}
            self.optimizations_enabled = {
                "connection_pooling": True,
                "schema_caching": True,
                "parallel_execution": True,
                "performance_monitoring": True,
                "memory_optimization": True,
            }

        def record_metric(self, name: str, value: float, unit: str = "ms"):
            self.metrics[name] = {"value": value, "unit": unit}

        def get_total_time(self) -> float:
            return (time.time() - self.start_time) * 1000

        def validate_performance_target(self, target_ms: float = 100.0) -> bool:
            total_time = self.get_total_time()
            return total_time <= target_ms

        def get_comprehensive_report(self) -> Dict[str, Any]:
            pool_manager = get_pool_manager()
            schema_cache = get_schema_cache()
            parallel_manager = get_parallel_manager()
            performance_monitor = get_performance_monitor()
            memory_optimizer = get_memory_optimizer()

            return {
                "test_id": self.test_id,
                "total_execution_time_ms": self.get_total_time(),
                "target_achieved": self.validate_performance_target(),
                "optimizations": self.optimizations_enabled,
                "recorded_metrics": self.metrics,
                "pool_statistics": (
                    pool_manager.get_pool_statistics(self.test_id)
                    if hasattr(pool_manager, "get_pool_statistics")
                    else {}
                ),
                "cache_statistics": schema_cache.get_cache_statistics(),
                "parallel_statistics": parallel_manager.get_parallel_statistics(),
                "performance_report": performance_monitor.get_performance_report(),
                "memory_report": memory_optimizer.get_memory_report(),
            }

    async with optimized_test_context(
        test_id=test_id,
        enable_pooling=True,
        enable_caching=True,
        enable_parallel=True,
        enable_monitoring=True,
        enable_memory_optimization=True,
    ) as opt_context:

        benchmark_context = BenchmarkContext()

        # Record initial metrics
        benchmark_context.record_metric(
            "setup_time", (time.time() - benchmark_context.start_time) * 1000
        )

        yield benchmark_context


# Backward compatibility and convenience fixtures
@pytest.fixture
async def fast_optimized_dataflow():
    """Alias for preheated_dataflow for convenience."""
    async for result in preheated_dataflow():
        yield result[0]  # Just the DataFlow instance


@pytest.fixture
async def optimized_models():
    """Alias for cached_schema_models returning just the models."""
    async for result in cached_schema_models():
        yield result[:3]  # User, Product, Order models only


# Performance validation hooks
def pytest_runtest_call(pyfuncitem):
    """Validate enhanced TDD performance targets."""
    if hasattr(pyfuncitem, "start_time"):
        duration_ms = (time.time() - pyfuncitem.start_time) * 1000

        # Check for enhanced TDD markers
        enhanced_markers = ["enhanced_tdd", "optimized_test", "performance_test"]
        if any(marker.name in enhanced_markers for marker in pyfuncitem.iter_markers()):
            target_ms = 50.0  # Stricter target for enhanced tests
            if duration_ms > target_ms:
                logger.warning(
                    f"Enhanced TDD test {pyfuncitem.name} exceeded {target_ms}ms target: {duration_ms:.2f}ms"
                )


def pytest_runtest_setup(item):
    """Enhanced setup with performance tracking."""
    item.start_time = time.time()

    # Enable detailed logging for performance tests
    if any(
        marker.name in ["performance_test", "benchmark"]
        for marker in item.iter_markers()
    ):
        logging.getLogger("dataflow.testing").setLevel(logging.DEBUG)
