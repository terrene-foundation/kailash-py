"""Runtime monitoring and metrics collection.

This module provides comprehensive monitoring capabilities for the enhanced
LocalRuntime, including resource monitoring, health checks, performance
tracking, and enterprise integration.

Components:
- RuntimeMonitor: Overall runtime health and performance tracking
- ResourceMonitor: Resource usage and limits monitoring
- HealthChecker: Health check coordination and reporting
"""

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional, Union

import psutil

logger = logging.getLogger(__name__)


class ResourceMonitor:
    """Monitors resource usage and enforces limits."""

    def __init__(
        self,
        resource_limits: Optional[Dict[str, Any]] = None,
        monitoring_interval: float = 1.0,
        alert_thresholds: Optional[Dict[str, float]] = None,
        history_size: int = 100,
    ):
        """Initialize resource monitor.

        Args:
            resource_limits: Limits for various resources
            monitoring_interval: How often to check resources (seconds)
            alert_thresholds: Thresholds for triggering alerts (0.0-1.0)
            history_size: Number of historical samples to keep
        """
        self.resource_limits = resource_limits or {}
        self.monitoring_interval = monitoring_interval
        self.alert_thresholds = alert_thresholds or {
            "memory": 0.8,
            "connections": 0.9,
            "cpu": 0.85,
        }
        self.history_size = history_size

        # Current usage tracking
        self._current_usage: Dict[str, Any] = {}
        self._connections: Dict[str, Any] = {}
        self._usage_history: deque = deque(maxlen=history_size)

        # Monitoring state
        self._is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()

        # Validate limits
        self._validate_resource_limits()

        logger.info("ResourceMonitor initialized")

    def _validate_resource_limits(self) -> None:
        """Validate resource limits configuration."""
        for key, value in self.resource_limits.items():
            if isinstance(value, (int, float)) and value < 0:
                raise ValueError(f"Resource limit '{key}' cannot be negative: {value}")

    def get_current_memory_usage(self) -> float:
        """Get current memory usage in MB.

        Returns:
            Current memory usage in megabytes
        """
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except Exception as e:
            logger.warning(f"Failed to get memory usage: {e}")
            return 0.0

    def add_connection(self, connection_id: str) -> None:
        """Add a connection for tracking.

        Args:
            connection_id: Unique connection identifier
        """
        with self._lock:
            self._connections[connection_id] = {
                "created_at": datetime.now(UTC),
                "last_used": datetime.now(UTC),
            }

    def remove_connection(self, connection_id: str) -> None:
        """Remove a connection from tracking.

        Args:
            connection_id: Connection identifier to remove
        """
        with self._lock:
            self._connections.pop(connection_id, None)

    def get_connection_count(self) -> int:
        """Get current number of tracked connections.

        Returns:
            Number of active connections
        """
        with self._lock:
            return len(self._connections)

    def check_resource_limits(self) -> bool:
        """Check if current usage is within limits.

        Returns:
            True if within limits, False otherwise
        """
        violations = self.get_limit_violations()
        return len(violations) == 0

    def get_limit_violations(self) -> Dict[str, Any]:
        """Get current limit violations.

        Returns:
            Dictionary of violated limits with details
        """
        violations = {}

        # Check memory limit
        if "max_memory_mb" in self.resource_limits:
            current_memory = self.get_current_memory_usage()
            limit = self.resource_limits["max_memory_mb"]
            if current_memory > limit:
                violations["memory"] = {
                    "current": current_memory,
                    "limit": limit,
                    "violation_percent": (current_memory / limit - 1) * 100,
                }

        # Check connection limit
        if "max_connections" in self.resource_limits:
            current_connections = self.get_connection_count()
            limit = self.resource_limits["max_connections"]
            if current_connections > limit:
                violations["connections"] = {
                    "current": current_connections,
                    "limit": limit,
                    "violation_count": current_connections - limit,
                }

        return violations

    async def start_monitoring(self) -> None:
        """Start continuous resource monitoring."""
        if self._is_monitoring:
            return

        self._is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started resource monitoring")

    async def stop_monitoring(self) -> None:
        """Stop continuous resource monitoring."""
        if not self._is_monitoring:
            return

        self._is_monitoring = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped resource monitoring")

    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        while self._is_monitoring:
            try:
                # Collect current usage
                usage_sample = {
                    "timestamp": datetime.now(UTC),
                    "memory_mb": self.get_current_memory_usage(),
                    "connections": self.get_connection_count(),
                    "cpu_percent": self._get_cpu_usage(),
                }

                self._record_usage_sample(usage_sample)

                # Wait for next interval
                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(1)  # Brief pause before retry

    def _get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception as e:
            logger.warning(f"Failed to get CPU usage: {e}")
            return 0.0

    def _record_usage_sample(self, sample: Dict[str, Any]) -> None:
        """Record a usage sample in history.

        Args:
            sample: Usage sample to record
        """
        with self._lock:
            self._usage_history.append(sample)
            self._current_usage = sample.copy()

    def get_monitoring_metrics(self) -> List[Dict[str, Any]]:
        """Get monitoring metrics history.

        Returns:
            List of historical usage samples
        """
        with self._lock:
            return list(self._usage_history)

    def get_usage_history(self) -> List[Dict[str, Any]]:
        """Get usage history.

        Returns:
            List of historical usage samples
        """
        return self.get_monitoring_metrics()

    @property
    def is_monitoring(self) -> bool:
        """Check if monitoring is active."""
        return self._is_monitoring


class RuntimeMonitor:
    """Overall runtime monitoring and health tracking."""

    def __init__(
        self,
        runtime_id: str,
        enable_performance_tracking: bool = True,
        enable_health_checks: bool = True,
        metrics_collector: Optional[Any] = None,
        audit_logger: Optional[Any] = None,
        alert_manager: Optional[Any] = None,
        dashboard_client: Optional[Any] = None,
    ):
        """Initialize runtime monitor.

        Args:
            runtime_id: Unique runtime identifier
            enable_performance_tracking: Enable execution performance tracking
            enable_health_checks: Enable health check system
            metrics_collector: Enterprise metrics collector
            audit_logger: Enterprise audit logger
            alert_manager: Enterprise alert manager
            dashboard_client: Enterprise dashboard client
        """
        self.runtime_id = runtime_id
        self.enable_performance_tracking = enable_performance_tracking
        self.enable_health_checks = enable_health_checks

        # Enterprise integrations
        self.metrics_collector = metrics_collector
        self.audit_logger = audit_logger
        self.alert_manager = alert_manager
        self.dashboard_client = dashboard_client

        # Performance tracking
        self._execution_metrics: List[Dict[str, Any]] = []
        self._performance_benchmarks: List[Dict[str, Any]] = []
        self._active_executions: Dict[str, Dict[str, Any]] = {}

        # Health checks
        self._health_checks: Dict[str, Callable] = {}
        self._async_health_checks: Dict[str, Callable] = {}

        # Thread safety
        self._lock = threading.RLock()

        logger.info(f"RuntimeMonitor initialized for {runtime_id}")

    def start_execution_tracking(self, workflow_id: str) -> str:
        """Start tracking workflow execution.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Execution tracking ID
        """
        if not self.enable_performance_tracking:
            return ""

        execution_id = f"exec_{int(time.time() * 1000)}_{workflow_id}"

        with self._lock:
            self._active_executions[execution_id] = {
                "workflow_id": workflow_id,
                "start_time": time.time(),
                "start_timestamp": datetime.now(UTC),
            }

        return execution_id

    def end_execution_tracking(self, execution_id: str, success: bool) -> None:
        """End execution tracking.

        Args:
            execution_id: Execution tracking ID
            success: Whether execution was successful
        """
        if not self.enable_performance_tracking or not execution_id:
            return

        with self._lock:
            if execution_id in self._active_executions:
                execution_info = self._active_executions.pop(execution_id)

                end_time = time.time()
                duration_ms = (end_time - execution_info["start_time"]) * 1000

                metric = {
                    "execution_id": execution_id,
                    "workflow_id": execution_info["workflow_id"],
                    "start_time": execution_info["start_timestamp"],
                    "end_time": datetime.now(UTC),
                    "duration_ms": duration_ms,
                    "success": success,
                }

                self._execution_metrics.append(metric)

                # Report to enterprise metrics if available
                if self.metrics_collector:
                    try:
                        self.metrics_collector.record_metric(
                            "workflow_execution", metric
                        )
                    except Exception as e:
                        logger.warning(f"Failed to record enterprise metric: {e}")

    def get_execution_metrics(self) -> List[Dict[str, Any]]:
        """Get execution metrics.

        Returns:
            List of execution metrics
        """
        with self._lock:
            return self._execution_metrics.copy()

    def register_health_check(self, name: str, check_function: Callable) -> None:
        """Register a health check function.

        Args:
            name: Health check name
            check_function: Function that returns health status
        """
        self._health_checks[name] = check_function

    def register_async_health_check(self, name: str, check_function: Callable) -> None:
        """Register an async health check function.

        Args:
            name: Health check name
            check_function: Async function that returns health status
        """
        self._async_health_checks[name] = check_function

    def run_health_checks(self) -> Dict[str, Any]:
        """Run all registered health checks.

        Returns:
            Health check results
        """
        if not self.enable_health_checks:
            return {}

        results = {}

        for name, check_func in self._health_checks.items():
            try:
                result = check_func()
                results[name] = (
                    result if isinstance(result, dict) else {"status": str(result)}
                )
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                logger.warning(f"Health check '{name}' failed: {e}")

        return results

    async def run_async_health_checks(self) -> Dict[str, Any]:
        """Run all registered async health checks.

        Returns:
            Async health check results
        """
        if not self.enable_health_checks:
            return {}

        results = {}

        for name, check_func in self._async_health_checks.items():
            try:
                result = await check_func()
                results[name] = (
                    result if isinstance(result, dict) else {"status": str(result)}
                )
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                logger.warning(f"Async health check '{name}' failed: {e}")

        return results

    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """Get aggregated performance metrics.

        Returns:
            Aggregated metrics summary
        """
        with self._lock:
            if not self._execution_metrics:
                return {
                    "total_executions": 0,
                    "success_rate": 0.0,
                    "avg_execution_time_ms": 0.0,
                }

            total = len(self._execution_metrics)
            successful = sum(1 for m in self._execution_metrics if m["success"])
            success_rate = successful / total if total > 0 else 0.0

            avg_duration = (
                sum(m["duration_ms"] for m in self._execution_metrics) / total
            )

            return {
                "total_executions": total,
                "success_rate": success_rate,
                "avg_execution_time_ms": avg_duration,
                "successful_executions": successful,
                "failed_executions": total - successful,
            }

    def record_performance_benchmark(
        self,
        operation: str,
        duration_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a performance benchmark.

        Args:
            operation: Operation name
            duration_ms: Duration in milliseconds
            metadata: Additional metadata
        """
        benchmark = {
            "operation": operation,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(UTC),
            "metadata": metadata or {},
        }

        with self._lock:
            self._performance_benchmarks.append(benchmark)

    def get_performance_benchmarks(self) -> List[Dict[str, Any]]:
        """Get performance benchmarks.

        Returns:
            List of performance benchmarks
        """
        with self._lock:
            return self._performance_benchmarks.copy()

    def log_audit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Log an audit event.

        Args:
            event_type: Type of audit event
            details: Event details
        """
        if self.audit_logger:
            try:
                self.audit_logger.log_event(
                    {
                        "runtime_id": self.runtime_id,
                        "event_type": event_type,
                        "timestamp": datetime.now(UTC),
                        "details": details,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log audit event: {e}")

    def check_and_trigger_alerts(self, metrics: Dict[str, Any]) -> None:
        """Check metrics and trigger alerts if needed.

        Args:
            metrics: Current metrics to check
        """
        if not self.alert_manager:
            return

        try:
            # Check for alert conditions
            alerts = []

            if metrics.get("memory_usage_percent", 0) > 90:
                alerts.append(
                    {
                        "type": "high_memory_usage",
                        "severity": "warning",
                        "message": f"High memory usage: {metrics['memory_usage_percent']:.1f}%",
                    }
                )

            if metrics.get("error_rate", 0) > 0.1:
                alerts.append(
                    {
                        "type": "high_error_rate",
                        "severity": "critical",
                        "message": f"High error rate: {metrics['error_rate']:.1%}",
                    }
                )

            # Trigger alerts
            for alert in alerts:
                self.alert_manager.trigger_alert(alert)

        except Exception as e:
            logger.warning(f"Failed to check/trigger alerts: {e}")

    async def push_metrics_to_dashboard(self, metrics: Dict[str, Any]) -> None:
        """Push metrics to enterprise dashboard.

        Args:
            metrics: Metrics to push
        """
        if not self.dashboard_client:
            return

        try:
            await self.dashboard_client.push_metrics(metrics)
        except Exception as e:
            logger.warning(f"Failed to push metrics to dashboard: {e}")


class HealthChecker:
    """Coordinates health checks and status reporting."""

    def __init__(self):
        """Initialize health checker."""
        self._checks: Dict[str, Callable] = {}

    def register_check(self, name: str, check_func: Callable) -> None:
        """Register a health check.

        Args:
            name: Check name
            check_func: Function that returns health status
        """
        self._checks[name] = check_func

    def run_checks(self) -> Dict[str, Any]:
        """Run all health checks.

        Returns:
            Health check results
        """
        results = {}
        overall_status = "healthy"

        for name, check_func in self._checks.items():
            try:
                result = check_func()
                if isinstance(result, dict):
                    results[name] = result
                    if result.get("status") != "healthy":
                        overall_status = "degraded"
                else:
                    results[name] = {"status": "healthy" if result else "unhealthy"}
                    if not result:
                        overall_status = "degraded"
            except Exception as e:
                results[name] = {"status": "error", "error": str(e)}
                overall_status = "unhealthy"

        return {
            "status": overall_status,
            "details": results,
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Enterprise monitoring integration adapters
class PrometheusAdapter:
    """Adapter for Prometheus metrics integration."""

    def __init__(
        self, prefix: str = "kailash", labels: Optional[Dict[str, str]] = None
    ):
        """Initialize Prometheus adapter.

        Args:
            prefix: Metric name prefix
            labels: Default labels to add to all metrics
        """
        self.prefix = prefix
        self.default_labels = labels or {}
        self._metrics_cache = {}

        try:
            # Try to import prometheus_client if available
            import prometheus_client

            self.prometheus_client = prometheus_client
            self.enabled = True
            logger.info("Prometheus adapter initialized")
        except ImportError:
            self.prometheus_client = None
            self.enabled = False
            logger.warning(
                "Prometheus client not available - metrics will be logged only"
            )

    def counter(self, name: str, description: str, labels: List[str] = None) -> Any:
        """Get or create a counter metric."""
        full_name = f"{self.prefix}_{name}"

        if not self.enabled:
            return MockMetric(full_name, "counter")

        if full_name not in self._metrics_cache:
            self._metrics_cache[full_name] = self.prometheus_client.Counter(
                full_name, description, labels or []
            )

        return self._metrics_cache[full_name]

    def gauge(self, name: str, description: str, labels: List[str] = None) -> Any:
        """Get or create a gauge metric."""
        full_name = f"{self.prefix}_{name}"

        if not self.enabled:
            return MockMetric(full_name, "gauge")

        if full_name not in self._metrics_cache:
            self._metrics_cache[full_name] = self.prometheus_client.Gauge(
                full_name, description, labels or []
            )

        return self._metrics_cache[full_name]


class DataDogAdapter:
    """Adapter for DataDog metrics integration."""

    def __init__(self, prefix: str = "kailash", tags: List[str] = None):
        """Initialize DataDog adapter."""
        self.prefix = prefix
        self.default_tags = tags or []

        try:
            import datadog

            self.datadog = datadog
            self.enabled = True
            logger.info("DataDog adapter initialized")
        except ImportError:
            self.datadog = None
            self.enabled = False
            logger.warning("DataDog client not available - metrics will be logged only")

    def increment(self, metric: str, value: int = 1, tags: List[str] = None) -> None:
        """Increment a counter metric."""
        full_name = f"{self.prefix}.{metric}"
        all_tags = self.default_tags + (tags or [])

        if self.enabled:
            self.datadog.statsd.increment(full_name, value, tags=all_tags)
        else:
            logger.info(f"DataDog metric: {full_name} += {value} (tags: {all_tags})")

    def gauge(self, metric: str, value: float, tags: List[str] = None) -> None:
        """Set a gauge metric."""
        full_name = f"{self.prefix}.{metric}"
        all_tags = self.default_tags + (tags or [])

        if self.enabled:
            self.datadog.statsd.gauge(full_name, value, tags=all_tags)
        else:
            logger.info(f"DataDog metric: {full_name} = {value} (tags: {all_tags})")


class MockMetric:
    """Mock metric for when real monitoring is not available."""

    def __init__(self, name: str, metric_type: str):
        self.name = name
        self.metric_type = metric_type

    def inc(self, amount: float = 1, **kwargs) -> None:
        """Mock increment."""
        logger.debug(f"Mock {self.metric_type} {self.name} += {amount}")

    def set(self, value: float, **kwargs) -> None:
        """Mock set."""
        logger.debug(f"Mock {self.metric_type} {self.name} = {value}")

    def labels(self, **kwargs):
        """Mock labels."""
        return self


class EnterpriseMonitoringManager:
    """Manages enterprise monitoring integrations."""

    def __init__(self, runtime_id: str):
        """Initialize enterprise monitoring manager."""
        self.runtime_id = runtime_id
        self.adapters: Dict[str, Any] = {}

        # Initialize available adapters
        self.adapters["prometheus"] = PrometheusAdapter(
            prefix="kailash_runtime", labels={"runtime_id": runtime_id}
        )

        self.adapters["datadog"] = DataDogAdapter(
            prefix="kailash.runtime", tags=[f"runtime_id:{runtime_id}"]
        )

        logger.info(f"Enterprise monitoring initialized for runtime {runtime_id}")

    def record_workflow_execution(
        self, workflow_id: str, duration_ms: float, success: bool
    ) -> None:
        """Record workflow execution metrics."""
        # Prometheus
        if self.adapters["prometheus"].enabled:
            counter = self.adapters["prometheus"].counter(
                "workflows_total",
                "Total workflows executed",
                ["workflow_id", "success"],
            )
            counter.labels(workflow_id=workflow_id, success=str(success)).inc()

        # DataDog
        self.adapters["datadog"].increment(
            "workflow.executions",
            tags=[f"workflow_id:{workflow_id}", f"success:{success}"],
        )

    def record_resource_usage(self, resource_type: str, value: float) -> None:
        """Record resource usage metrics."""
        # Prometheus
        if self.adapters["prometheus"].enabled:
            gauge = self.adapters["prometheus"].gauge(
                f"resource_{resource_type}", f"{resource_type} usage", ["resource_type"]
            )
            gauge.labels(resource_type=resource_type).set(value)

        # DataDog
        self.adapters["datadog"].gauge(
            f"resource.{resource_type}", value, tags=[f"resource_type:{resource_type}"]
        )
