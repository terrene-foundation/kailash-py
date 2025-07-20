"""Connection health monitoring system for enterprise resilience.

This module provides comprehensive health monitoring for database connections,
Redis connections, and other external services. It integrates with circuit
breakers and bulkhead patterns to provide enterprise-grade observability.

Features:
- Real-time health status monitoring
- Automatic health checks with configurable intervals
- Integration with circuit breakers and bulkheads
- Health-based routing and failover
- Comprehensive metrics collection
- Alert generation for critical failures

Example:
    >>> monitor = HealthMonitor()
    >>> monitor.register_check("database", DatabaseHealthCheck(...))
    >>> status = await monitor.get_health_status("database")
    >>> if status.is_healthy:
    ...     # Proceed with operation
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""

    check_id: str
    service_name: str
    status: HealthStatus
    response_time_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    is_healthy: bool = field(init=False)

    # Additional attributes for compatibility
    check_name: str = field(default="", init=False)
    message: str = field(default="", init=False)
    error: Optional[str] = field(default=None, init=False)
    metadata: Dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self):
        """Calculate health status and initialize compatibility fields."""
        self.is_healthy = self.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

        # Initialize compatibility fields
        self.check_name = self.service_name
        self.error = self.error_message
        self.metadata = self.details.copy()

        # Set message based on status
        if self.status == HealthStatus.HEALTHY:
            self.message = "Service is healthy"
        elif self.status == HealthStatus.DEGRADED:
            self.message = "Service is degraded but functional"
        elif self.status == HealthStatus.UNHEALTHY:
            self.message = (
                f"Service is unhealthy: {self.error_message or 'Unknown error'}"
            )
        else:
            self.message = "Service status unknown"


@dataclass
class HealthMetrics:
    """Health monitoring metrics."""

    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    avg_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    uptime_percentage: float = 100.0
    consecutive_failures: int = 0
    last_successful_check: Optional[datetime] = None
    last_failed_check: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class HealthAlert:
    """Health monitoring alert."""

    alert_id: str = field(default_factory=lambda: str(uuid4()))
    service_name: str = ""
    level: AlertLevel = AlertLevel.INFO
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class HealthCheck(ABC):
    """Abstract base class for health checks."""

    def __init__(self, name: str, timeout: float = 5.0, critical: bool = True):
        """Initialize health check.

        Args:
            name: Name of the service being checked
            timeout: Timeout for health check in seconds
            critical: Whether this check is critical for overall health
        """
        self.name = name
        self.timeout = timeout
        self.critical = critical

    @abstractmethod
    async def check_health(self) -> HealthCheckResult:
        """Perform health check and return result."""
        pass


class DatabaseHealthCheck(HealthCheck):
    """Health check for database connections."""

    def __init__(self, name: str, database_node_or_connection_string, **kwargs):
        """Initialize database health check."""
        super().__init__(name, **kwargs)
        self.check_name = name  # Required by HealthCheckManager

        # Handle both database node objects and connection strings
        if hasattr(database_node_or_connection_string, "execute"):
            # It's a database node object
            self.database_node = database_node_or_connection_string
            self.connection_string = None
        else:
            # It's a connection string
            self.connection_string = database_node_or_connection_string
            self.database_node = None

    async def check_health(self) -> HealthCheckResult:
        """Check database health."""
        start_time = time.time()
        check_id = str(uuid4())

        try:
            if self.database_node:
                # Use database node object directly
                result = await self.database_node.execute(
                    "SELECT 1 as health_check", "dict"
                )

                response_time = (time.time() - start_time) * 1000

                if result and result.get("success"):
                    return HealthCheckResult(
                        check_id=check_id,
                        service_name=self.name,
                        status=HealthStatus.HEALTHY,
                        response_time_ms=response_time,
                        details={
                            "query_executed": True,
                            "query_result": result.get("data", []),
                        },
                    )
                else:
                    return HealthCheckResult(
                        check_id=check_id,
                        service_name=self.name,
                        status=HealthStatus.DEGRADED,
                        response_time_ms=response_time,
                        details={"query_executed": True, "query_result": []},
                        error_message="Query returned no success result",
                    )
            else:
                # Use connection string with SQL node
                from src.kailash.nodes.data.sql import SQLDatabaseNode

                sql_node = SQLDatabaseNode(connection_string=self.connection_string)

                # Execute simple health check query
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        sql_node.execute, query="SELECT 1 as health_check"
                    ),
                    timeout=self.timeout,
                )

                response_time = (time.time() - start_time) * 1000

                if "data" in result and len(result["data"]) > 0:
                    return HealthCheckResult(
                        check_id=check_id,
                        service_name=self.name,
                        status=HealthStatus.HEALTHY,
                        response_time_ms=response_time,
                        details={
                            "query_executed": True,
                            "rows_returned": len(result["data"]),
                            "execution_time": result.get("execution_time", 0),
                        },
                    )
                else:
                    return HealthCheckResult(
                        check_id=check_id,
                        service_name=self.name,
                        status=HealthStatus.DEGRADED,
                        response_time_ms=response_time,
                        details={"query_executed": True, "rows_returned": 0},
                        error_message="Query returned no data",
                    )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=f"Health check timed out after {self.timeout}s",
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )


class RedisHealthCheck(HealthCheck):
    """Health check for Redis connections."""

    def __init__(self, name: str, redis_config: Dict[str, Any], **kwargs):
        """Initialize Redis health check."""
        super().__init__(name, **kwargs)
        self.redis_config = redis_config
        self.check_name = name  # Required by HealthCheckManager

    async def check_health(self) -> HealthCheckResult:
        """Check Redis health."""
        start_time = time.time()
        check_id = str(uuid4())

        try:
            import redis

            # Create Redis client
            client = redis.Redis(**self.redis_config)

            # Execute ping command
            await asyncio.wait_for(asyncio.to_thread(client.ping), timeout=self.timeout)

            # Get Redis info
            info = await asyncio.to_thread(client.info)

            response_time = (time.time() - start_time) * 1000

            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.HEALTHY,
                response_time_ms=response_time,
                details={
                    "ping_successful": True,
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "redis_version": info.get("redis_version", "unknown"),
                },
            )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=f"Redis health check timed out after {self.timeout}s",
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )


class MemoryHealthCheck(HealthCheck):
    """Health check for system memory usage."""

    def __init__(
        self,
        name: str,
        warning_threshold: float = 80.0,
        critical_threshold: float = 95.0,
        **kwargs,
    ):
        """Initialize memory health check."""
        super().__init__(name, **kwargs)
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.check_name = name  # Required by HealthCheckManager

    async def check_health(self) -> HealthCheckResult:
        """Check system memory health."""
        start_time = time.time()
        check_id = str(uuid4())

        try:
            import psutil

            memory = psutil.virtual_memory()
            response_time = (time.time() - start_time) * 1000

            # Determine status based on memory usage
            if memory.percent >= self.critical_threshold:
                status = HealthStatus.UNHEALTHY
                message = f"Critical memory usage: {memory.percent:.1f}%"
            elif memory.percent >= self.warning_threshold:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory.percent:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage normal: {memory.percent:.1f}%"

            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=status,
                response_time_ms=response_time,
                details={
                    "memory_percent": memory.percent,
                    "total_memory": memory.total,
                    "available_memory": memory.available,
                    "used_memory": memory.used,
                },
                error_message=message if status != HealthStatus.HEALTHY else None,
            )

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )


class CustomHealthCheck(HealthCheck):
    """Custom health check that executes user-defined check function."""

    def __init__(self, name: str, check_function: Callable, **kwargs):
        """Initialize custom health check."""
        super().__init__(name, **kwargs)
        self.check_function = check_function
        self.check_name = name  # Required by HealthCheckManager

    async def check_health(self) -> HealthCheckResult:
        """Execute custom health check function."""
        start_time = time.time()
        check_id = str(uuid4())

        try:
            # Execute the custom check function
            if asyncio.iscoroutinefunction(self.check_function):
                result = await asyncio.wait_for(
                    self.check_function(), timeout=self.timeout
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.check_function), timeout=self.timeout
                )

            response_time = (time.time() - start_time) * 1000

            # Handle different result formats
            if isinstance(result, bool):
                status = HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY
                message = "Check passed" if result else "Check failed"
                details = {"result": result}
            elif isinstance(result, dict):
                # Expect dict with status, message, metadata
                status_str = result.get("status", "healthy").lower()
                if status_str == "healthy":
                    status = HealthStatus.HEALTHY
                elif status_str == "degraded":
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.UNHEALTHY

                message = result.get("message", "Custom check completed")
                details = result.get("metadata", {})
            else:
                # Assume success if we get any non-false result
                status = HealthStatus.HEALTHY
                message = "Custom check completed"
                details = {"result": str(result)}

            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=status,
                response_time_ms=response_time,
                details=details,
                error_message=None if status == HealthStatus.HEALTHY else message,
            )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=f"Custom health check timeout after {self.timeout}s",
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )


class HTTPHealthCheck(HealthCheck):
    """Health check for HTTP endpoints."""

    def __init__(self, name: str, url: str, expected_status: int = 200, **kwargs):
        """Initialize HTTP health check."""
        super().__init__(name, **kwargs)
        self.url = url
        self.expected_status = expected_status
        self.check_name = name  # Required by HealthCheckManager

    async def check_health(self) -> HealthCheckResult:
        """Check HTTP endpoint health."""
        start_time = time.time()
        check_id = str(uuid4())

        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.url)

            response_time = (time.time() - start_time) * 1000

            if response.status_code == self.expected_status:
                status = HealthStatus.HEALTHY
            elif 200 <= response.status_code < 300:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.UNHEALTHY

            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=status,
                response_time_ms=response_time,
                details={
                    "status_code": response.status_code,
                    "expected_status": self.expected_status,
                    "content_length": len(response.content),
                },
            )

        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=f"HTTP health check timed out after {self.timeout}s",
            )
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return HealthCheckResult(
                check_id=check_id,
                service_name=self.name,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time,
                error_message=str(e),
            )


class HealthMonitor:
    """Enterprise health monitoring system."""

    def __init__(self, check_interval: float = 30.0, alert_threshold: int = 3):
        """Initialize health monitor.

        Args:
            check_interval: Interval between health checks in seconds
            alert_threshold: Number of consecutive failures before alerting
        """
        self.check_interval = check_interval
        self.alert_threshold = alert_threshold
        self.health_checks: Dict[str, HealthCheck] = {}
        self.metrics: Dict[str, HealthMetrics] = {}
        self.alerts: List[HealthAlert] = []
        self.alert_callbacks: List[Callable[[HealthAlert], None]] = []
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

        logger.info("Initialized HealthMonitor")

    def register_check(self, service_name: str, health_check: HealthCheck):
        """Register a health check."""
        self.health_checks[service_name] = health_check
        self.metrics[service_name] = HealthMetrics()
        logger.info(f"Registered health check for service: {service_name}")

    def register_alert_callback(self, callback: Callable[[HealthAlert], None]):
        """Register callback for health alerts."""
        self.alert_callbacks.append(callback)

    async def check_service_health(self, service_name: str) -> HealthCheckResult:
        """Perform health check for specific service."""
        if service_name not in self.health_checks:
            raise ValueError(f"No health check registered for service: {service_name}")

        health_check = self.health_checks[service_name]
        result = await health_check.check_health()

        # Update metrics
        await self._update_metrics(service_name, result)

        # Check for alerts
        await self._check_alerts(service_name, result)

        return result

    async def get_health_status(self, service_name: str) -> Optional[HealthCheckResult]:
        """Get latest health status for service."""
        return await self.check_service_health(service_name)

    async def get_all_health_status(self) -> Dict[str, HealthCheckResult]:
        """Get health status for all registered services."""
        results = {}
        for service_name in self.health_checks:
            try:
                results[service_name] = await self.check_service_health(service_name)
            except Exception as e:
                logger.error(f"Failed to check health for {service_name}: {e}")
                results[service_name] = HealthCheckResult(
                    check_id=str(uuid4()),
                    service_name=service_name,
                    status=HealthStatus.UNKNOWN,
                    response_time_ms=0.0,
                    error_message=str(e),
                )
        return results

    async def get_overall_health(self) -> HealthStatus:
        """Get overall system health status."""
        all_status = await self.get_all_health_status()

        if not all_status:
            return HealthStatus.UNKNOWN

        critical_services = [
            name for name, check in self.health_checks.items() if check.critical
        ]

        # Check critical services first
        critical_unhealthy = any(
            all_status[name].status == HealthStatus.UNHEALTHY
            for name in critical_services
            if name in all_status
        )

        if critical_unhealthy:
            return HealthStatus.UNHEALTHY

        # Check if any service is degraded
        any_degraded = any(
            result.status == HealthStatus.DEGRADED for result in all_status.values()
        )

        if any_degraded:
            return HealthStatus.DEGRADED

        # Check if all are healthy
        all_healthy = all(
            result.status == HealthStatus.HEALTHY for result in all_status.values()
        )

        return HealthStatus.HEALTHY if all_healthy else HealthStatus.UNKNOWN

    async def get_metrics(self, service_name: str) -> Optional[HealthMetrics]:
        """Get metrics for specific service."""
        return self.metrics.get(service_name)

    async def get_all_metrics(self) -> Dict[str, HealthMetrics]:
        """Get metrics for all services."""
        return self.metrics.copy()

    async def get_alerts(self, resolved: Optional[bool] = None) -> List[HealthAlert]:
        """Get health alerts."""
        if resolved is None:
            return self.alerts.copy()
        return [alert for alert in self.alerts if alert.resolved == resolved]

    async def start_monitoring(self):
        """Start continuous health monitoring."""
        if self._running:
            logger.warning("Health monitoring already running")
            return

        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started health monitoring")

    async def stop_monitoring(self):
        """Stop continuous health monitoring."""
        if not self._running:
            return

        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped health monitoring")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                # Check all services
                await self.get_all_health_status()

                # Wait for next check interval
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(min(self.check_interval, 10))  # Fallback interval

    async def _update_metrics(self, service_name: str, result: HealthCheckResult):
        """Update metrics for service."""
        async with self._lock:
            metrics = self.metrics[service_name]

            metrics.total_checks += 1

            if result.is_healthy:
                metrics.successful_checks += 1
                metrics.consecutive_failures = 0
                metrics.last_successful_check = result.timestamp
            else:
                metrics.failed_checks += 1
                metrics.consecutive_failures += 1
                metrics.last_failed_check = result.timestamp

            # Update response time metrics
            if metrics.total_checks == 1:
                metrics.avg_response_time_ms = result.response_time_ms
            else:
                metrics.avg_response_time_ms = (
                    metrics.avg_response_time_ms * (metrics.total_checks - 1)
                    + result.response_time_ms
                ) / metrics.total_checks

            if result.response_time_ms > metrics.max_response_time_ms:
                metrics.max_response_time_ms = result.response_time_ms

            # Update uptime percentage
            metrics.uptime_percentage = (
                metrics.successful_checks / metrics.total_checks
            ) * 100

    async def _check_alerts(self, service_name: str, result: HealthCheckResult):
        """Check if alerts should be generated."""
        metrics = self.metrics[service_name]

        # Check for consecutive failure threshold
        if metrics.consecutive_failures >= self.alert_threshold:
            await self._generate_alert(
                service_name,
                AlertLevel.CRITICAL,
                f"Service {service_name} has {metrics.consecutive_failures} consecutive failures",
                {
                    "consecutive_failures": metrics.consecutive_failures,
                    "last_error": result.error_message,
                    "health_status": result.status.value,
                },
            )

        # Check for high response times
        if result.response_time_ms > 5000:  # 5 seconds
            await self._generate_alert(
                service_name,
                AlertLevel.WARNING,
                f"High response time for {service_name}: {result.response_time_ms:.2f}ms",
                {
                    "response_time_ms": result.response_time_ms,
                    "avg_response_time_ms": metrics.avg_response_time_ms,
                },
            )

    async def _generate_alert(
        self,
        service_name: str,
        level: AlertLevel,
        message: str,
        details: Dict[str, Any],
    ):
        """Generate health alert."""
        alert = HealthAlert(
            service_name=service_name, level=level, message=message, details=details
        )

        self.alerts.append(alert)

        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")

        logger.warning(f"Health alert generated: {message}")


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get global health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor


async def quick_health_check(service_name: str) -> bool:
    """Quick health check for a service."""
    monitor = get_health_monitor()
    try:
        result = await monitor.get_health_status(service_name)
        return result.is_healthy if result else False
    except Exception:
        return False


@dataclass
class HealthSummary:
    """Health summary for all checks."""

    total_checks: int
    healthy_checks: int
    degraded_checks: int
    unhealthy_checks: int
    overall_status: HealthStatus
    details: List[HealthCheckResult]


class HealthCheckManager:
    """Manager for orchestrating multiple health checks with configuration."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize health check manager with configuration."""
        self.config = config
        self.enabled = config.get("enabled", True)
        self.default_interval = config.get("default_interval", 30.0)
        self.parallel_checks = config.get("parallel_checks", True)
        self.max_concurrent_checks = config.get("max_concurrent_checks", 10)

        self.health_checks: Dict[str, HealthCheck] = {}
        self.check_intervals: Dict[str, float] = {}
        self.last_results: Dict[str, HealthCheckResult] = {}
        self.history: Dict[str, List[HealthCheckResult]] = {}
        self.status_change_callbacks: List[Callable] = []
        self._running = False

    def register_health_check(self, health_check: HealthCheck, interval: float = None):
        """Register a health check with optional interval."""
        check_name = health_check.check_name
        self.health_checks[check_name] = health_check
        self.check_intervals[check_name] = interval or self.default_interval
        self.history[check_name] = []

    async def run_health_check(self, check_name: str) -> HealthCheckResult:
        """Run a specific health check."""
        if check_name not in self.health_checks:
            raise ValueError(f"Health check '{check_name}' not found")

        health_check = self.health_checks[check_name]
        result = await health_check.check_health()

        # Check for status changes before storing new result
        await self._check_status_change(check_name, result)

        # Store result
        self.last_results[check_name] = result
        self.history[check_name].append(result)

        return result

    async def run_all_health_checks(self) -> List[HealthCheckResult]:
        """Run all registered health checks."""
        if not self.health_checks:
            return []

        if self.parallel_checks:
            # Run checks in parallel
            tasks = [
                self.run_health_check(check_name)
                for check_name in self.health_checks.keys()
            ]

            # Limit concurrency
            semaphore = asyncio.Semaphore(self.max_concurrent_checks)

            async def run_with_semaphore(task):
                async with semaphore:
                    return await task

            results = await asyncio.gather(
                *[run_with_semaphore(task) for task in tasks]
            )
        else:
            # Run checks sequentially
            results = []
            for check_name in self.health_checks.keys():
                result = await self.run_health_check(check_name)
                results.append(result)

        return results

    async def get_health_summary(self) -> HealthSummary:
        """Get summary of all health checks."""
        results = await self.run_all_health_checks()

        healthy_count = sum(1 for r in results if r.status == HealthStatus.HEALTHY)
        degraded_count = sum(1 for r in results if r.status == HealthStatus.DEGRADED)
        unhealthy_count = sum(1 for r in results if r.status == HealthStatus.UNHEALTHY)

        # Determine overall status
        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = HealthStatus.DEGRADED
        elif healthy_count > 0:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN

        return HealthSummary(
            total_checks=len(results),
            healthy_checks=healthy_count,
            degraded_checks=degraded_count,
            unhealthy_checks=unhealthy_count,
            overall_status=overall_status,
            details=results,
        )

    def add_status_change_callback(self, callback: Callable):
        """Add callback for status changes."""
        self.status_change_callbacks.append(callback)

    def get_health_history(
        self, check_name: str, limit: int = None
    ) -> List[HealthCheckResult]:
        """Get health check history for a specific check."""
        history = self.history.get(check_name, [])
        if limit:
            return history[-limit:]
        return history

    async def _check_status_change(self, check_name: str, result: HealthCheckResult):
        """Check if status has changed and notify callbacks."""
        if check_name in self.last_results:
            previous = self.last_results[check_name]
            if previous.status != result.status:
                # Status changed, notify callbacks
                for callback in self.status_change_callbacks:
                    try:
                        await callback(check_name, result)
                    except Exception as e:
                        logger.error(f"Error in status change callback: {e}")

    async def shutdown(self):
        """Shutdown the health check manager."""
        self._running = False
        # Any cleanup logic here


# Global health manager instance for convenience functions
_global_health_manager: Optional[HealthCheckManager] = None


def get_health_manager() -> HealthCheckManager:
    """Get the global health manager instance."""
    global _global_health_manager
    if _global_health_manager is None:
        config = {
            "enabled": True,
            "default_interval": 30.0,
            "parallel_checks": True,
            "max_concurrent_checks": 10,
        }
        _global_health_manager = HealthCheckManager(config)
    return _global_health_manager


# Add convenience functions for registering health checks
async def register_database_health_check(
    name: str, database_node, interval: float = 30.0
):
    """Register a database health check with global manager."""
    health_check = DatabaseHealthCheck(name, database_node)
    manager = get_health_manager()
    manager.register_health_check(health_check, interval)


async def register_memory_health_check(
    name: str,
    warning_threshold: float = 80.0,
    critical_threshold: float = 95.0,
    interval: float = 30.0,
):
    """Register a memory health check with global manager."""
    health_check = MemoryHealthCheck(name, warning_threshold, critical_threshold)
    manager = get_health_manager()
    manager.register_health_check(health_check, interval)


async def register_custom_health_check(
    name: str, check_func: Callable, interval: float = 30.0, timeout: float = 10.0
):
    """Register a custom health check with global manager."""
    health_check = CustomHealthCheck(name, check_func, timeout=timeout)
    manager = get_health_manager()
    manager.register_health_check(health_check, interval)
