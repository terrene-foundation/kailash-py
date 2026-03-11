#!/usr/bin/env python3
"""
Health Monitoring & Observability for DataFlow

Provides production-ready health monitoring for Kubernetes deployments:
- Health check endpoints (/health)
- Readiness probes (/ready)
- Component health validation
- Prometheus metrics integration

Critical for production deployments requiring orchestration, monitoring,
and observability.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels for components and overall system."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    """Health check result with status, details, and timestamp."""

    status: HealthStatus
    message: str
    details: Dict[str, Any]
    timestamp: datetime

    def to_json(self) -> str:
        """Serialize health check to JSON format."""

        def serialize_details(details: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively serialize details, converting HealthStatus enums."""
            result = {}
            for key, value in details.items():
                if isinstance(value, dict):
                    result[key] = serialize_details(value)
                elif isinstance(value, HealthStatus):
                    result[key] = value.value
                else:
                    result[key] = value
            return result

        return json.dumps(
            {
                "status": self.status.value,
                "message": self.message,
                "details": serialize_details(self.details),
                "timestamp": self.timestamp.isoformat(),
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert health check to dictionary."""
        return {
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class HealthMonitor:
    """
    Production health monitoring for DataFlow.

    Features:
    - Database connection health checks
    - Schema cache health monitoring
    - Connection pool health tracking
    - Overall system health aggregation
    - Kubernetes-compatible readiness checks

    Example:
        >>> monitor = HealthMonitor(dataflow)
        >>> health = await monitor.health_check()
        >>> print(f"Status: {health.status.value}")
        >>> is_ready = await monitor.readiness_check()
    """

    def __init__(self, dataflow: Any):
        """
        Initialize health monitor.

        Args:
            dataflow: DataFlow instance to monitor
        """
        self.dataflow = dataflow
        self._checks: Dict[str, Callable] = {
            "database": self._check_database,
            "schema_cache": self._check_schema_cache,
            "connection_pool": self._check_connection_pool,
        }

    async def health_check(self) -> HealthCheck:
        """
        Run all health checks and aggregate results.

        Returns:
            HealthCheck with overall status and component details

        Example:
            >>> health = await monitor.health_check()
            >>> if health.status == HealthStatus.UNHEALTHY:
            ...     logger.error(f"Unhealthy: {health.details}")
        """
        results = {}
        overall_status = HealthStatus.HEALTHY

        for name, check_fn in self._checks.items():
            try:
                result = await check_fn()
                results[name] = result

                # Downgrade overall status based on component status
                if result["status"] == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif (
                    result["status"] == HealthStatus.DEGRADED
                    and overall_status != HealthStatus.UNHEALTHY
                ):
                    overall_status = HealthStatus.DEGRADED

            except Exception as e:
                logger.error(f"Health check '{name}' failed with exception: {e}")
                results[name] = {"status": HealthStatus.UNHEALTHY, "error": str(e)}
                overall_status = HealthStatus.UNHEALTHY

        return HealthCheck(
            status=overall_status,
            message=f"Health check complete with status: {overall_status.value}",
            details=results,
            timestamp=datetime.now(),
        )

    async def readiness_check(self) -> bool:
        """
        Kubernetes readiness check.

        Returns:
            True if ready to serve traffic (healthy or degraded),
            False if unhealthy (should not receive traffic)

        Example:
            >>> is_ready = await monitor.readiness_check()
            >>> if not is_ready:
            ...     logger.warning("Not ready for traffic")
        """
        health = await self.health_check()
        return health.status != HealthStatus.UNHEALTHY

    async def _check_database(self) -> Dict[str, Any]:
        """
        Check database connection health.

        Returns:
            Dict with status and message

        Raises:
            Exception if database connection fails
        """
        try:
            # Try to get a connection and execute a simple query
            async with self.dataflow.get_connection() as conn:
                # SQLite uses execute(), PostgreSQL uses fetch()
                try:
                    # Try PostgreSQL-style query
                    await conn.fetch("SELECT 1")
                except AttributeError:
                    # Fall back to SQLite-style query
                    await conn.execute("SELECT 1")

            return {
                "status": HealthStatus.HEALTHY,
                "message": "Database connection healthy",
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": f"Database connection failed: {e}",
            }

    async def _check_schema_cache(self) -> Dict[str, Any]:
        """
        Check schema cache health.

        Returns:
            Dict with status and message based on cache hit rate
        """
        try:
            if not hasattr(self.dataflow, "_schema_cache"):
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": "Schema cache not enabled",
                }

            metrics = self.dataflow._schema_cache.get_metrics()
            hit_rate = metrics.get("hit_rate", 0)

            # Threshold: <50% hit rate is degraded
            if hit_rate < 0.5 and metrics.get("hits", 0) + metrics.get("misses", 0) > 0:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"Low cache hit rate: {hit_rate:.2%}",
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": f"Cache hit rate: {hit_rate:.2%}",
            }
        except Exception as e:
            logger.error(f"Schema cache health check failed: {e}")
            return {
                "status": HealthStatus.DEGRADED,
                "message": f"Schema cache check failed: {e}",
            }

    async def _check_connection_pool(self) -> Dict[str, Any]:
        """
        Check connection pool health.

        Returns:
            Dict with status and message based on pool utilization
        """
        try:
            # Check if connection pooling is enabled
            if (
                not hasattr(self.dataflow, "enable_connection_pooling")
                or not self.dataflow.enable_connection_pooling
            ):
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": "Connection pooling disabled",
                }

            # Check if pool manager exists
            if not hasattr(self.dataflow, "_pool_manager"):
                return {
                    "status": HealthStatus.HEALTHY,
                    "message": "Connection pool not initialized",
                }

            # Get pool metrics - use connection_url or database_config.url
            db_url = getattr(
                self.dataflow,
                "connection_url",
                getattr(
                    getattr(self.dataflow, "database_config", None),
                    "url",
                    None,
                ),
            )
            metrics = self.dataflow._pool_manager.get_pool_metrics(db_url)

            utilization = metrics.get("utilization", 0)

            # Threshold: >90% utilization is degraded
            if utilization > 0.9:
                return {
                    "status": HealthStatus.DEGRADED,
                    "message": f"High pool utilization: {utilization:.2%}",
                }

            return {
                "status": HealthStatus.HEALTHY,
                "message": f"Pool utilization: {utilization:.2%}",
            }
        except Exception as e:
            logger.error(f"Connection pool health check failed: {e}")
            return {
                "status": HealthStatus.DEGRADED,
                "message": f"Connection pool check failed: {e}",
            }


def add_health_endpoints(app: Any, dataflow: Any) -> None:
    """
    Add health monitoring endpoints to FastAPI application.

    Registers:
    - GET /health - Health check endpoint
    - GET /ready - Readiness probe for Kubernetes
    - GET /metrics - Prometheus metrics endpoint

    Args:
        app: FastAPI application instance
        dataflow: DataFlow instance to monitor

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> add_health_endpoints(app, dataflow)
        >>> # Endpoints available:
        >>> # GET /health
        >>> # GET /ready
        >>> # GET /metrics
    """
    from fastapi import Response

    health_monitor = HealthMonitor(dataflow)

    # Get configurable endpoint paths from environment
    health_path = os.environ.get("DATAFLOW_HEALTH_ENDPOINT", "/health")
    ready_path = os.environ.get("DATAFLOW_READY_ENDPOINT", "/ready")
    metrics_path = os.environ.get("DATAFLOW_METRICS_ENDPOINT", "/metrics")

    @app.get(health_path)
    async def health():
        """
        Health check endpoint.

        Returns:
            200: Healthy or degraded (still serving)
            503: Unhealthy (not serving)
        """
        health_check = await health_monitor.health_check()

        # Determine status code based on health
        status_code = 200
        if health_check.status == HealthStatus.UNHEALTHY:
            status_code = 503

        return Response(
            content=health_check.to_json(),
            status_code=status_code,
            media_type="application/json",
        )

    @app.get(ready_path)
    async def readiness():
        """
        Readiness check for Kubernetes.

        Returns:
            200: Ready to serve traffic
            503: Not ready (don't send traffic)
        """
        is_ready = await health_monitor.readiness_check()

        if is_ready:
            return {"status": "ready"}
        else:
            return Response(
                content='{"status": "not ready"}',
                status_code=503,
                media_type="application/json",
            )

    @app.get(metrics_path)
    async def metrics():
        """
        Prometheus metrics endpoint.

        Returns:
            Prometheus text format metrics
        """
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except ImportError:
            # Prometheus client not installed
            logger.warning("prometheus_client not installed, returning empty metrics")
            return Response(
                content="# Prometheus client not installed\n", media_type="text/plain"
            )


__all__ = [
    "HealthMonitor",
    "HealthStatus",
    "HealthCheck",
    "add_health_endpoints",
]
