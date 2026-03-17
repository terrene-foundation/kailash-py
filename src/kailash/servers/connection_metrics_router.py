"""FastAPI router for connection pool metrics.

Exposes connection pool health, utilization, and alert data collected by the
:class:`~kailash.nodes.monitoring.connection_dashboard.ConnectionDashboardNode`
as REST endpoints that can be mounted on a :class:`WorkflowServer`.

Endpoints:
    GET /metrics        -- Current pool metrics (JSON)
    GET /pools          -- Per-pool status summary
    GET /alerts         -- Active alerts and rules

The router also contributes Prometheus-formatted gauge lines to the
server-level ``/metrics`` endpoint via :func:`get_prometheus_lines`.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)


class ConnectionMetricsProvider:
    """Aggregates connection pool metrics from registered pool sources.

    A *pool source* is any object with a ``get_pool_statistics`` async method
    that returns a dict with keys like ``health_score``, ``active_connections``,
    ``total_connections``, ``utilization``, etc.

    This provider is deliberately decoupled from
    :class:`ConnectionDashboardNode` so it can be used without the standalone
    aiohttp dashboard.
    """

    def __init__(self) -> None:
        self._sources: Dict[str, Any] = {}

    def register_source(self, name: str, source: Any) -> None:
        """Register a pool source.

        Args:
            name: Human-readable pool name.
            source: Object with an async ``get_pool_statistics()`` method.
        """
        self._sources[name] = source

    async def collect(self) -> Dict[str, Dict[str, Any]]:
        """Collect metrics from all registered pool sources.

        Returns:
            Mapping of pool name to stats dict.
        """
        results: Dict[str, Dict[str, Any]] = {}
        for name, source in self._sources.items():
            try:
                if hasattr(source, "get_pool_statistics"):
                    stats = await source.get_pool_statistics()
                    results[name] = {
                        "health_score": stats.get("health_score", 100),
                        "active_connections": stats.get("active_connections", 0),
                        "total_connections": stats.get("total_connections", 0),
                        "utilization": stats.get("utilization", 0.0),
                        "queries_per_second": stats.get("queries_per_second", 0.0),
                        "avg_query_time_ms": stats.get("avg_query_time_ms", 0.0),
                        "error_rate": stats.get("error_rate", 0.0),
                    }
            except Exception as e:
                logger.warning("Failed to collect metrics from pool %s: %s", name, e)
                results[name] = {
                    "health_score": 0,
                    "error": str(e),
                }
        return results

    def get_prometheus_lines(self, pool_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """Render pool metrics as Prometheus gauge lines.

        Args:
            pool_data: Result of :meth:`collect`.

        Returns:
            List of Prometheus text-format lines.
        """
        lines: List[str] = []
        for pool_name, stats in pool_data.items():
            safe_name = pool_name.replace("-", "_").replace(" ", "_")
            for key in (
                "health_score",
                "active_connections",
                "total_connections",
                "utilization",
                "queries_per_second",
                "avg_query_time_ms",
                "error_rate",
            ):
                value = stats.get(key)
                if value is not None and not isinstance(value, str):
                    metric_name = f"kailash_connection_{key}"
                    lines.append(f'{metric_name}{{pool="{safe_name}"}} {value}')
        return lines


def create_connection_metrics_router(
    provider: Optional[ConnectionMetricsProvider] = None,
) -> APIRouter:
    """Create a FastAPI router for connection metrics.

    Args:
        provider: Optional provider instance.  A default (empty) provider
            is created if none is supplied.

    Returns:
        Configured :class:`APIRouter`.
    """
    if provider is None:
        provider = ConnectionMetricsProvider()

    router = APIRouter(tags=["connections"])

    @router.get("/metrics")
    async def connection_metrics():
        """Current connection pool metrics."""
        pool_data = await provider.collect()
        return {
            "timestamp": time.time(),
            "pools": pool_data,
        }

    @router.get("/pools")
    async def connection_pools():
        """Per-pool status summary."""
        pool_data = await provider.collect()
        summary = {}
        for name, stats in pool_data.items():
            utilization = stats.get("utilization", 0.0)
            if utilization >= 0.95:
                status = "critical"
            elif utilization >= 0.8:
                status = "warning"
            else:
                status = "healthy"
            summary[name] = {
                "status": status,
                **stats,
            }
        return summary

    @router.get("/alerts")
    async def connection_alerts():
        """Active connection alerts based on pool thresholds."""
        pool_data = await provider.collect()
        alerts: List[Dict[str, Any]] = []
        for name, stats in pool_data.items():
            utilization = stats.get("utilization", 0.0)
            error_rate = stats.get("error_rate", 0.0)

            if utilization >= 0.95:
                alerts.append(
                    {
                        "pool": name,
                        "severity": "critical",
                        "message": f"Pool '{name}' near exhaustion: {utilization:.1%} utilization",
                        "metric": "utilization",
                        "value": utilization,
                    }
                )
            elif utilization >= 0.8:
                alerts.append(
                    {
                        "pool": name,
                        "severity": "warning",
                        "message": f"Pool '{name}' high utilization: {utilization:.1%}",
                        "metric": "utilization",
                        "value": utilization,
                    }
                )
            if error_rate >= 0.05:
                alerts.append(
                    {
                        "pool": name,
                        "severity": "error",
                        "message": f"Pool '{name}' high error rate: {error_rate:.2%}",
                        "metric": "error_rate",
                        "value": error_rate,
                    }
                )
        return {"active_alerts": alerts, "total": len(alerts)}

    # Stash provider on router for external access (e.g. Prometheus merge)
    router.provider = provider  # type: ignore[attr-defined]

    return router
