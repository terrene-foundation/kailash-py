"""
DataFlow TDD Performance Optimization Module

Advanced performance optimizations for DataFlow TDD infrastructure to achieve
consistent <100ms test execution times. Implements connection pooling optimization,
schema caching, parallel execution support, and performance monitoring.

Key Features:
- Session-level connection pools with preheating
- Schema caching and lazy loading
- Thread-safe parallel execution support
- Real-time performance monitoring
- Memory optimization and leak prevention
- Performance regression detection

Performance Targets:
- Individual test execution: <100ms consistently
- Connection acquisition: <5ms (pool preheating)
- Schema operations: <10ms (caching)
- Parallel test isolation: 100% success rate
- Memory overhead: <2MB per test context
"""

import asyncio
import logging
import os
import threading
import time
import uuid
import weakref
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

import asyncpg
import psutil

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics for TDD operations."""

    operation_id: str
    operation_type: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    connection_reused: bool = False
    schema_cached: bool = False
    memory_delta_mb: float = 0.0
    thread_id: int = field(default_factory=threading.get_ident)
    savepoint_count: int = 0
    sql_queries: int = 0
    target_achieved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def complete(self):
        """Mark the operation as complete and calculate duration."""
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.target_achieved = self.duration_ms < 100.0


class ConnectionPoolManager:
    """
    Advanced connection pool manager with preheating and optimization.

    Features:
    - Session-level connection pools
    - Connection preheating to eliminate cold starts
    - Pool size optimization based on test patterns
    - Connection health monitoring
    - Automatic cleanup and resource management
    """

    def __init__(self):
        self.pools: Dict[str, asyncpg.Pool] = {}
        self.pool_configs: Dict[str, Dict[str, Any]] = {}
        self.connection_metrics: Dict[str, List[float]] = defaultdict(list)
        self.preheated_connections: Set[str] = set()
        self.cleanup_callbacks: List[Callable] = []
        self._lock = threading.Lock()

    async def create_optimized_pool(
        self,
        pool_id: str,
        connection_string: str,
        min_size: int = 2,
        max_size: int = 10,
        preheat: bool = True,
    ) -> asyncpg.Pool:
        """
        Create an optimized connection pool with preheating.

        Args:
            pool_id: Unique identifier for the pool
            connection_string: PostgreSQL connection string
            min_size: Minimum pool size
            max_size: Maximum pool size
            preheat: Whether to preheat connections

        Returns:
            asyncpg.Pool: Optimized connection pool
        """
        with self._lock:
            if pool_id in self.pools:
                return self.pools[pool_id]

        # Optimize pool configuration for TDD
        pool_config = {
            "min_size": min_size,
            "max_size": max_size,
            "command_timeout": 10,  # Fast timeout for tests
            "server_settings": {
                "application_name": f"dataflow_tdd_{pool_id}",
                "tcp_keepalives_idle": "60",
                "tcp_keepalives_interval": "10",
                "tcp_keepalives_count": "3",
            },
        }

        start_time = time.time()
        pool = await asyncpg.create_pool(connection_string, **pool_config)
        creation_time = (time.time() - start_time) * 1000

        with self._lock:
            self.pools[pool_id] = pool
            self.pool_configs[pool_id] = pool_config
            self.connection_metrics[pool_id].append(creation_time)

        if preheat:
            await self._preheat_pool(pool_id, pool)

        logger.debug(f"Created optimized pool {pool_id}: {creation_time:.2f}ms")
        return pool

    async def _preheat_pool(self, pool_id: str, pool: asyncpg.Pool):
        """Preheat pool connections to eliminate cold start delays."""
        preheat_start = time.time()

        # Acquire and release connections to warm them up
        connections = []
        try:
            for _ in range(pool._minsize):
                conn = await pool.acquire()
                # Perform a simple query to ensure connection is ready
                await conn.fetchval("SELECT 1")
                connections.append(conn)

            # Release all connections back to pool
            for conn in connections:
                await pool.release(conn)

            preheat_time = (time.time() - preheat_start) * 1000
            self.preheated_connections.add(pool_id)

            logger.debug(f"Preheated pool {pool_id}: {preheat_time:.2f}ms")

        except Exception as e:
            logger.error(f"Failed to preheat pool {pool_id}: {e}")
            # Release any acquired connections
            for conn in connections:
                try:
                    await pool.release(conn)
                except:
                    pass

    async def get_optimized_connection(self, pool_id: str) -> asyncpg.Connection:
        """
        Get an optimized connection from the pool.

        Args:
            pool_id: Pool identifier

        Returns:
            asyncpg.Connection: Database connection
        """
        start_time = time.time()

        if pool_id not in self.pools:
            raise ValueError(f"Pool {pool_id} not found")

        pool = self.pools[pool_id]
        connection = await pool.acquire()

        acquisition_time = (time.time() - start_time) * 1000
        self.connection_metrics[pool_id].append(acquisition_time)

        # Log slow acquisitions
        if acquisition_time > 10.0:  # 10ms threshold
            logger.warning(f"Slow connection acquisition: {acquisition_time:.2f}ms")

        return connection

    async def release_connection(self, pool_id: str, connection: asyncpg.Connection):
        """Release a connection back to the pool."""
        if pool_id in self.pools:
            await self.pools[pool_id].release(connection)

    def get_pool_statistics(self, pool_id: str) -> Dict[str, Any]:
        """Get performance statistics for a pool."""
        if pool_id not in self.pools:
            return {}

        pool = self.pools[pool_id]
        metrics = self.connection_metrics[pool_id]

        return {
            "pool_id": pool_id,
            "size": pool.get_size(),
            "min_size": pool._minsize,
            "max_size": pool._maxsize,
            "idle_connections": pool.get_idle_size(),
            "preheated": pool_id in self.preheated_connections,
            "avg_acquisition_time_ms": sum(metrics) / len(metrics) if metrics else 0,
            "total_acquisitions": len(metrics),
            "config": self.pool_configs.get(pool_id, {}),
        }

    async def cleanup_pool(self, pool_id: str):
        """Clean up a specific pool."""
        with self._lock:
            if pool_id in self.pools:
                pool = self.pools[pool_id]
                await pool.close()
                del self.pools[pool_id]
                del self.pool_configs[pool_id]
                self.preheated_connections.discard(pool_id)
                logger.debug(f"Cleaned up pool {pool_id}")

    async def cleanup_all_pools(self):
        """Clean up all pools."""
        for callback in self.cleanup_callbacks:
            try:
                await callback()
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")

        pool_ids = list(self.pools.keys())
        for pool_id in pool_ids:
            await self.cleanup_pool(pool_id)

        self.connection_metrics.clear()


class SchemaCache:
    """
    Schema caching system for fast test execution.

    Features:
    - Pre-created test schemas in session setup
    - Cached table definitions to avoid repeated DDL
    - Lazy loading for models only used in specific tests
    - Schema versioning and invalidation
    - Memory-efficient storage
    """

    def __init__(self):
        self.cached_schemas: Dict[str, Dict[str, Any]] = {}
        self.table_definitions: Dict[str, str] = {}
        self.schema_versions: Dict[str, int] = {}
        self.lazy_loaded_models: Set[str] = set()
        self._cache_lock = threading.Lock()

    def cache_schema(self, schema_id: str, tables: Dict[str, str], version: int = 1):
        """
        Cache a schema definition.

        Args:
            schema_id: Unique schema identifier
            tables: Dictionary of table_name -> DDL
            version: Schema version for invalidation
        """
        with self._cache_lock:
            self.cached_schemas[schema_id] = {
                "tables": tables,
                "cached_at": time.time(),
                "version": version,
                "access_count": 0,
            }
            self.schema_versions[schema_id] = version

        logger.debug(f"Cached schema {schema_id} with {len(tables)} tables")

    def get_cached_schema(self, schema_id: str) -> Optional[Dict[str, Any]]:
        """Get a cached schema definition."""
        with self._cache_lock:
            if schema_id in self.cached_schemas:
                schema = self.cached_schemas[schema_id]
                schema["access_count"] += 1
                schema["last_accessed"] = time.time()
                return schema
        return None

    def is_schema_cached(self, schema_id: str, version: int = None) -> bool:
        """Check if a schema is cached and up-to-date."""
        with self._cache_lock:
            if schema_id not in self.cached_schemas:
                return False

            if version is not None:
                return self.schema_versions.get(schema_id, 0) >= version

            return True

    def get_table_ddl(self, table_name: str) -> Optional[str]:
        """Get cached DDL for a specific table."""
        with self._cache_lock:
            return self.table_definitions.get(table_name)

    def cache_table_ddl(self, table_name: str, ddl: str):
        """Cache DDL for a specific table."""
        with self._cache_lock:
            self.table_definitions[table_name] = ddl

    def mark_lazy_loaded(self, model_name: str):
        """Mark a model as lazy loaded."""
        with self._cache_lock:
            self.lazy_loaded_models.add(model_name)

    def is_lazy_loaded(self, model_name: str) -> bool:
        """Check if a model is lazy loaded."""
        with self._cache_lock:
            return model_name in self.lazy_loaded_models

    def invalidate_schema(self, schema_id: str):
        """Invalidate a cached schema."""
        with self._cache_lock:
            if schema_id in self.cached_schemas:
                del self.cached_schemas[schema_id]
                del self.schema_versions[schema_id]
                logger.debug(f"Invalidated schema cache for {schema_id}")

    def clear_cache(self):
        """Clear all cached schemas."""
        with self._cache_lock:
            self.cached_schemas.clear()
            self.table_definitions.clear()
            self.schema_versions.clear()
            self.lazy_loaded_models.clear()

    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        with self._cache_lock:
            total_schemas = len(self.cached_schemas)
            total_tables = len(self.table_definitions)
            total_access = sum(s["access_count"] for s in self.cached_schemas.values())

            return {
                "cached_schemas": total_schemas,
                "cached_tables": total_tables,
                "lazy_loaded_models": len(self.lazy_loaded_models),
                "total_access_count": total_access,
                "cache_hit_rate": total_access / max(total_schemas, 1),
                "schemas": list(self.cached_schemas.keys()),
            }


class ParallelExecutionManager:
    """
    Thread-safe parallel execution support for TDD tests.

    Features:
    - Database-level isolation for parallel runners
    - Connection pool management for high concurrency
    - Thread safety across concurrent tests
    - Deadlock detection and prevention
    - Resource allocation optimization
    """

    def __init__(self):
        self.active_tests: Dict[str, Dict[str, Any]] = {}
        self.thread_pools: Dict[str, ThreadPoolExecutor] = {}
        self.isolation_levels: Dict[str, str] = {}
        self.deadlock_detection: bool = True
        self._parallel_lock = threading.RLock()

    def register_parallel_test(
        self, test_id: str, thread_id: int, isolation_level: str = "SERIALIZABLE"
    ):
        """
        Register a test for parallel execution.

        Args:
            test_id: Unique test identifier
            thread_id: Thread identifier
            isolation_level: Database isolation level
        """
        with self._parallel_lock:
            self.active_tests[test_id] = {
                "thread_id": thread_id,
                "start_time": time.time(),
                "isolation_level": isolation_level,
                "status": "running",
                "resources": set(),
            }
            self.isolation_levels[test_id] = isolation_level

    def unregister_parallel_test(self, test_id: str):
        """Unregister a test from parallel execution."""
        with self._parallel_lock:
            if test_id in self.active_tests:
                self.active_tests[test_id]["status"] = "completed"
                self.active_tests[test_id]["end_time"] = time.time()
                # Keep for statistics, remove after cleanup

    def allocate_resource(self, test_id: str, resource_name: str) -> bool:
        """
        Allocate a resource to a test (for deadlock prevention).

        Args:
            test_id: Test identifier
            resource_name: Resource identifier

        Returns:
            bool: True if allocated successfully
        """
        with self._parallel_lock:
            # Check if resource is already allocated
            for tid, test_info in self.active_tests.items():
                if tid != test_id and resource_name in test_info["resources"]:
                    return False  # Resource busy

            if test_id in self.active_tests:
                self.active_tests[test_id]["resources"].add(resource_name)
                return True

            return False

    def release_resource(self, test_id: str, resource_name: str):
        """Release a resource from a test."""
        with self._parallel_lock:
            if test_id in self.active_tests:
                self.active_tests[test_id]["resources"].discard(resource_name)

    def get_isolation_level(self, test_id: str) -> str:
        """Get the isolation level for a test."""
        return self.isolation_levels.get(test_id, "READ COMMITTED")

    def detect_potential_deadlock(self, test_id: str, requested_resource: str) -> bool:
        """
        Detect potential deadlock scenarios.

        Args:
            test_id: Test requesting resource
            requested_resource: Resource being requested

        Returns:
            bool: True if potential deadlock detected
        """
        if not self.deadlock_detection:
            return False

        with self._parallel_lock:
            # Simple deadlock detection: circular dependency check
            for tid, test_info in self.active_tests.items():
                if tid != test_id and requested_resource in test_info["resources"]:
                    # Check if we have resources that the other test might need
                    our_resources = self.active_tests.get(test_id, {}).get(
                        "resources", set()
                    )
                    if our_resources:
                        return True  # Potential deadlock

            return False

    def get_parallel_statistics(self) -> Dict[str, Any]:
        """Get parallel execution statistics."""
        with self._parallel_lock:
            active_count = sum(
                1 for t in self.active_tests.values() if t["status"] == "running"
            )
            completed_count = sum(
                1 for t in self.active_tests.values() if t["status"] == "completed"
            )

            return {
                "active_tests": active_count,
                "completed_tests": completed_count,
                "total_tests": len(self.active_tests),
                "isolation_levels": dict(self.isolation_levels),
                "deadlock_detection_enabled": self.deadlock_detection,
            }


class PerformanceMonitor:
    """
    Real-time performance monitoring and regression detection.

    Features:
    - Real-time performance tracking during test runs
    - Automatic regression detection (tests getting slower)
    - Performance reporting and optimization suggestions
    - Alerting for performance degradation
    - Historical trend analysis
    """

    def __init__(self):
        self.metrics_history: List[PerformanceMetrics] = []
        self.performance_baselines: Dict[str, float] = {}
        self.regression_threshold: float = 1.5  # 50% slower
        self.alert_callbacks: List[Callable] = []
        self.monitoring_enabled: bool = True
        self._monitor_lock = threading.Lock()

    def record_metrics(self, metrics: PerformanceMetrics):
        """Record performance metrics."""
        if not self.monitoring_enabled:
            return

        with self._monitor_lock:
            self.metrics_history.append(metrics)

            # Check for regression
            if self._detect_regression(metrics):
                self._trigger_regression_alert(metrics)

    def _detect_regression(self, metrics: PerformanceMetrics) -> bool:
        """Detect performance regression."""
        operation_type = metrics.operation_type

        if operation_type not in self.performance_baselines:
            # Establish baseline
            self.performance_baselines[operation_type] = metrics.duration_ms
            return False

        baseline = self.performance_baselines[operation_type]
        current = metrics.duration_ms

        if current > baseline * self.regression_threshold:
            return True

        # Update baseline with rolling average
        recent_metrics = [
            m
            for m in self.metrics_history[-10:]  # Last 10 measurements
            if m.operation_type == operation_type
        ]

        if len(recent_metrics) >= 3:
            avg_duration = sum(m.duration_ms for m in recent_metrics) / len(
                recent_metrics
            )
            self.performance_baselines[operation_type] = avg_duration

        return False

    def _trigger_regression_alert(self, metrics: PerformanceMetrics):
        """Trigger performance regression alert."""
        baseline = self.performance_baselines.get(metrics.operation_type, 0)
        degradation = (metrics.duration_ms / baseline - 1) * 100 if baseline > 0 else 0

        alert_data = {
            "operation_type": metrics.operation_type,
            "operation_id": metrics.operation_id,
            "current_duration_ms": metrics.duration_ms,
            "baseline_duration_ms": baseline,
            "degradation_percent": degradation,
            "timestamp": time.time(),
        }

        logger.warning(
            f"Performance regression detected: {metrics.operation_type} "
            f"({metrics.duration_ms:.2f}ms vs {baseline:.2f}ms baseline, "
            f"{degradation:.1f}% slower)"
        )

        for callback in self.alert_callbacks:
            try:
                callback(alert_data)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def add_alert_callback(self, callback: Callable):
        """Add a callback for performance alerts."""
        self.alert_callbacks.append(callback)

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report."""
        with self._monitor_lock:
            if not self.metrics_history:
                return {"message": "No metrics recorded"}

            # Group metrics by operation type
            by_operation = defaultdict(list)
            for metric in self.metrics_history:
                by_operation[metric.operation_type].append(metric)

            report = {
                "total_operations": len(self.metrics_history),
                "monitoring_enabled": self.monitoring_enabled,
                "regression_threshold": self.regression_threshold,
                "baselines": dict(self.performance_baselines),
                "operations": {},
            }

            for op_type, metrics in by_operation.items():
                durations = [
                    m.duration_ms for m in metrics if m.duration_ms is not None
                ]
                target_achieved = [m.target_achieved for m in metrics]

                if durations:
                    report["operations"][op_type] = {
                        "count": len(metrics),
                        "avg_duration_ms": sum(durations) / len(durations),
                        "min_duration_ms": min(durations),
                        "max_duration_ms": max(durations),
                        "target_achievement_rate": sum(target_achieved)
                        / len(target_achieved)
                        * 100,
                        "connection_reuse_rate": sum(
                            m.connection_reused for m in metrics
                        )
                        / len(metrics)
                        * 100,
                        "schema_cache_rate": sum(m.schema_cached for m in metrics)
                        / len(metrics)
                        * 100,
                    }

            return report

    def clear_history(self, keep_baselines: bool = True):
        """Clear metrics history."""
        with self._monitor_lock:
            self.metrics_history.clear()
            if not keep_baselines:
                self.performance_baselines.clear()


class MemoryOptimizer:
    """
    Memory optimization for connection reuse and efficient cleanup.

    Features:
    - Connection reuse without memory leaks
    - Efficient cleanup of test contexts
    - Garbage collection optimization for long test suites
    - Memory usage monitoring and alerts
    - Weak reference management for cleanup
    """

    def __init__(self):
        self.tracked_objects: weakref.WeakSet = weakref.WeakSet()
        self.memory_snapshots: List[Dict[str, Any]] = []
        self.cleanup_callbacks: List[Callable] = []
        self.gc_optimization: bool = True
        self.memory_threshold_mb: float = 100.0  # Alert threshold

    def track_object(self, obj: Any, obj_type: str = None):
        """Track an object for memory monitoring."""
        self.tracked_objects.add(obj)

        if obj_type:
            # Store metadata about the object
            if not hasattr(obj, "_memory_metadata"):
                obj._memory_metadata = {
                    "type": obj_type,
                    "created_at": time.time(),
                    "tracked": True,
                }

    def take_memory_snapshot(self, label: str = None) -> Dict[str, Any]:
        """Take a memory usage snapshot."""
        process = psutil.Process()
        memory_info = process.memory_info()

        snapshot = {
            "label": label or f"snapshot_{len(self.memory_snapshots)}",
            "timestamp": time.time(),
            "rss_mb": memory_info.rss / 1024 / 1024,
            "vms_mb": memory_info.vms / 1024 / 1024,
            "tracked_objects": len(self.tracked_objects),
            "process_id": process.pid,
        }

        self.memory_snapshots.append(snapshot)

        # Check threshold
        if snapshot["rss_mb"] > self.memory_threshold_mb:
            logger.warning(
                f"Memory usage exceeded threshold: {snapshot['rss_mb']:.2f}MB"
            )

        return snapshot

    def optimize_memory(self):
        """Perform memory optimization."""
        if not self.gc_optimization:
            return

        import gc

        # Force garbage collection
        collected = gc.collect()

        # Take snapshot after GC
        snapshot = self.take_memory_snapshot("post_gc")

        logger.debug(
            f"Memory optimization: collected {collected} objects, "
            f"current usage: {snapshot['rss_mb']:.2f}MB"
        )

    def register_cleanup_callback(self, callback: Callable):
        """Register a cleanup callback."""
        self.cleanup_callbacks.append(callback)

    def cleanup_tracked_objects(self):
        """Clean up tracked objects."""
        cleaned_count = 0

        for callback in self.cleanup_callbacks:
            try:
                callback()
                cleaned_count += 1
            except Exception as e:
                logger.warning(f"Cleanup callback failed: {e}")

        # Force cleanup of tracked objects
        self.tracked_objects.clear()

        # Optimize memory after cleanup
        self.optimize_memory()

        logger.debug(f"Cleaned up {cleaned_count} objects")

    def get_memory_report(self) -> Dict[str, Any]:
        """Get memory usage report."""
        if not self.memory_snapshots:
            return {"message": "No memory snapshots available"}

        current = self.memory_snapshots[-1]
        initial = (
            self.memory_snapshots[0] if len(self.memory_snapshots) > 1 else current
        )

        return {
            "current_usage_mb": current["rss_mb"],
            "initial_usage_mb": initial["rss_mb"],
            "memory_delta_mb": current["rss_mb"] - initial["rss_mb"],
            "tracked_objects": len(self.tracked_objects),
            "snapshots_taken": len(self.memory_snapshots),
            "threshold_mb": self.memory_threshold_mb,
            "gc_optimization_enabled": self.gc_optimization,
        }


# Global optimization manager instances
_pool_manager: Optional[ConnectionPoolManager] = None
_schema_cache: Optional[SchemaCache] = None
_parallel_manager: Optional[ParallelExecutionManager] = None
_performance_monitor: Optional[PerformanceMonitor] = None
_memory_optimizer: Optional[MemoryOptimizer] = None


def get_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager."""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()
    return _pool_manager


def get_schema_cache() -> SchemaCache:
    """Get the global schema cache."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = SchemaCache()
    return _schema_cache


def get_parallel_manager() -> ParallelExecutionManager:
    """Get the global parallel execution manager."""
    global _parallel_manager
    if _parallel_manager is None:
        _parallel_manager = ParallelExecutionManager()
    return _parallel_manager


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor


def get_memory_optimizer() -> MemoryOptimizer:
    """Get the global memory optimizer."""
    global _memory_optimizer
    if _memory_optimizer is None:
        _memory_optimizer = MemoryOptimizer()
    return _memory_optimizer


@asynccontextmanager
async def optimized_test_context(
    test_id: str = None,
    enable_pooling: bool = True,
    enable_caching: bool = True,
    enable_parallel: bool = True,
    enable_monitoring: bool = True,
    enable_memory_optimization: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Create an optimized test context with all performance features enabled.

    Args:
        test_id: Unique test identifier
        enable_pooling: Enable connection pooling optimization
        enable_caching: Enable schema caching
        enable_parallel: Enable parallel execution support
        enable_monitoring: Enable performance monitoring
        enable_memory_optimization: Enable memory optimization

    Yields:
        Dict containing all optimization managers and metrics
    """
    if test_id is None:
        test_id = f"opt_test_{uuid.uuid4().hex[:8]}"

    metrics = PerformanceMetrics(
        operation_id=test_id, operation_type="optimized_test_execution"
    )

    # Get all managers
    managers = {}

    if enable_pooling:
        managers["pool_manager"] = get_pool_manager()

    if enable_caching:
        managers["schema_cache"] = get_schema_cache()

    if enable_parallel:
        managers["parallel_manager"] = get_parallel_manager()
        managers["parallel_manager"].register_parallel_test(
            test_id, threading.get_ident(), "SERIALIZABLE"
        )

    if enable_monitoring:
        managers["performance_monitor"] = get_performance_monitor()

    if enable_memory_optimization:
        managers["memory_optimizer"] = get_memory_optimizer()
        managers["memory_optimizer"].take_memory_snapshot(f"start_{test_id}")

    try:
        context = {"test_id": test_id, "metrics": metrics, **managers}

        yield context

    except Exception as e:
        logger.error(f"Error in optimized test context {test_id}: {e}")
        raise

    finally:
        # Complete metrics and cleanup
        metrics.complete()

        if enable_monitoring and "performance_monitor" in managers:
            managers["performance_monitor"].record_metrics(metrics)

        if enable_parallel and "parallel_manager" in managers:
            managers["parallel_manager"].unregister_parallel_test(test_id)

        if enable_memory_optimization and "memory_optimizer" in managers:
            managers["memory_optimizer"].take_memory_snapshot(f"end_{test_id}")
            managers["memory_optimizer"].optimize_memory()


async def cleanup_optimization_infrastructure():
    """Clean up all optimization infrastructure."""
    global _pool_manager, _schema_cache, _parallel_manager, _performance_monitor, _memory_optimizer

    try:
        if _pool_manager:
            await _pool_manager.cleanup_all_pools()

        if _schema_cache:
            _schema_cache.clear_cache()

        if _memory_optimizer:
            _memory_optimizer.cleanup_tracked_objects()

    except Exception as e:
        logger.error(f"Error during optimization cleanup: {e}")

    finally:
        # Reset global instances
        _pool_manager = None
        _schema_cache = None
        _parallel_manager = None
        _performance_monitor = None
        _memory_optimizer = None


def is_optimization_enabled() -> bool:
    """Check if performance optimization is enabled."""
    return os.getenv("DATAFLOW_PERFORMANCE_OPTIMIZATION", "true").lower() in (
        "true",
        "yes",
        "1",
        "on",
    )
