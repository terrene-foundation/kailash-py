"""Connection pool metrics endpoints.

Exposes connection pool health, utilization, and alert data collected by the
:class:`~kailash.nodes.monitoring.connection_dashboard.ConnectionDashboardNode`
as REST endpoints that can be registered on a :class:`WorkflowServer`.

Endpoints registered at *prefix* (default ``/connections``):
    GET {prefix}/metrics  -- Current pool metrics (JSON)
    GET {prefix}/pools    -- Per-pool status summary
    GET {prefix}/alerts   -- Active alerts and rules

The provider also contributes Prometheus-formatted gauge lines to the
server-level ``/metrics`` endpoint via :func:`get_prometheus_lines`.

Migration note
--------------
Prior revisions of this module exposed ``create_connection_metrics_router``
which returned a FastAPI ``APIRouter``. As part of the FastAPI -> Nexus
migration (#445 Wave 1), the router factory has been replaced with
:func:`register_connection_metrics` which registers handlers directly via
the ``add_api_route`` method present on both FastAPI apps and Nexus apps.
This keeps engine-level code free of raw FastAPI imports while preserving
the external HTTP contract.
"""

import logging
import time
from typing import Any, Dict, List, Optional

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


def _build_endpoint_handlers(provider: ConnectionMetricsProvider):
    """Construct the three endpoint coroutines bound to *provider*.

    Extracted so :func:`register_connection_metrics` stays simple and so
    tests can exercise the handler logic independently of any HTTP app.
    """

    async def connection_metrics() -> Dict[str, Any]:
        """Current connection pool metrics."""
        pool_data = await provider.collect()
        return {
            "timestamp": time.time(),
            "pools": pool_data,
        }

    async def connection_pools() -> Dict[str, Dict[str, Any]]:
        """Per-pool status summary."""
        pool_data = await provider.collect()
        summary: Dict[str, Dict[str, Any]] = {}
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

    async def connection_alerts() -> Dict[str, Any]:
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

    return connection_metrics, connection_pools, connection_alerts


def register_connection_metrics(
    app: Any,
    provider: Optional[ConnectionMetricsProvider] = None,
    *,
    prefix: str = "/connections",
    tags: Optional[List[str]] = None,
) -> ConnectionMetricsProvider:
    """Register connection metrics endpoints on *app*.

    The *app* argument is duck-typed: any object with an ``add_api_route``
    method (FastAPI ``FastAPI`` / ``APIRouter`` instances, Nexus apps) will
    work. This keeps engine-level code free of FastAPI-specific imports.

    Args:
        app: Application/router object exposing
            ``add_api_route(path, endpoint, methods=[...], tags=[...])``.
        provider: Optional provider instance. A default (empty) provider
            is created if none is supplied.
        prefix: URL prefix for the endpoints (default ``/connections``).
        tags: Optional OpenAPI tags (default ``["connections"]``).

    Returns:
        The :class:`ConnectionMetricsProvider` bound to the endpoints, so
        callers can register pool sources and later generate Prometheus
        lines from the same provider instance.
    """
    if provider is None:
        provider = ConnectionMetricsProvider()
    effective_tags = tags if tags is not None else ["connections"]

    metrics_handler, pools_handler, alerts_handler = _build_endpoint_handlers(provider)

    app.add_api_route(
        f"{prefix}/metrics",
        metrics_handler,
        methods=["GET"],
        tags=effective_tags,
    )
    app.add_api_route(
        f"{prefix}/pools",
        pools_handler,
        methods=["GET"],
        tags=effective_tags,
    )
    app.add_api_route(
        f"{prefix}/alerts",
        alerts_handler,
        methods=["GET"],
        tags=effective_tags,
    )

    return provider


__all__ = [
    "ConnectionMetricsProvider",
    "register_connection_metrics",
]
