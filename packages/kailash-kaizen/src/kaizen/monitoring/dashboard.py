"""
PerformanceDashboard: Real-time performance visualization with <1s refresh.

This module provides a FastAPI-based web dashboard with WebSocket
support for real-time metric updates and Plotly.js visualizations.

FastAPI is an optional dependency (the ``server`` extra). This module imports
cleanly without it — ``import kaizen.monitoring`` succeeds on a bare install —
and the FastAPI surface (the ``app`` object and ``create_dashboard_app()``) is
built lazily, raising a clear, actionable error only when it is actually used.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from .analytics_aggregator import AnalyticsAggregator

if TYPE_CHECKING:  # analyzer-only; never imported at runtime on a bare install
    from fastapi import FastAPI, WebSocket

# NOTE: this module deliberately does NOT use ``from __future__ import
# annotations``. FastAPI resolves a route handler's parameter annotations via
# ``typing.get_type_hints`` against the handler's *module globals*. The ``/ws``
# handler is defined inside ``create_dashboard_app`` where ``WebSocket`` is a
# local import, so under PEP 563 the annotation would be the unresolvable string
# ``"WebSocket"`` (module globals never see it) and FastAPI would fail to inject
# the socket. Without PEP 563 the annotation captures the real class at def
# time. The only module/class-scope annotations that reference the optional
# ``FastAPI`` / ``WebSocket`` names are quoted forward references (never
# evaluated at runtime), so import stays FastAPI-free.

logger = logging.getLogger(__name__)

_MISSING_FASTAPI_MSG = (
    "The Kaizen performance dashboard requires FastAPI, which is not installed. "
    "Install the server extra to enable it: pip install 'kailash-kaizen[server]'"
)


class MonitoringDependencyError(ImportError):
    """Raised when the monitoring dashboard is used without its optional deps.

    Subclasses :class:`ImportError` so existing ``except ImportError`` handlers
    still catch it, while carrying an actionable remedy in the message.
    """


def _require_fastapi():
    """Import and return the ``fastapi`` module, or raise a typed, actionable error.

    Called at the point the dashboard's FastAPI surface is actually built, so a
    bare ``import kaizen.monitoring`` never trips it — only an explicit attempt
    to construct/serve the dashboard does.
    """
    try:
        import fastapi
    except ImportError as exc:
        raise MonitoringDependencyError(_MISSING_FASTAPI_MSG) from exc
    return fastapi


# Lazily-built singleton FastAPI app, exposed as module attribute ``app`` via
# ``__getattr__`` below so accessing it (not importing this module) is what
# requires FastAPI.
_app: Optional["FastAPI"] = None


class PerformanceDashboard:
    """
    Real-time performance dashboard with <1s refresh.

    Features:
    - Live metric charts (latency, throughput, errors)
    - Historical trends (1h, 24h, 7d)
    - Drill-down views (per-agent, per-signature)
    - Anomaly highlighting
    """

    _instance: Optional["PerformanceDashboard"] = None

    def __init__(self, aggregator: AnalyticsAggregator):
        """
        Initialize dashboard.

        Args:
            aggregator: AnalyticsAggregator instance
        """
        self.aggregator = aggregator
        # Quoted forward ref: no runtime WebSocket needed (FastAPI-free import).
        self._clients: "List[WebSocket]" = []
        PerformanceDashboard._instance = self

    @classmethod
    def get_instance(cls) -> Optional["PerformanceDashboard"]:
        """Get dashboard singleton instance."""
        return cls._instance

    async def _get_dashboard_data(self) -> Dict:
        """
        Get current metrics for dashboard.

        Returns:
            Dictionary containing Plotly traces for visualization
        """
        # Latency metrics
        latency_stats = self.aggregator.get_stats("signature.resolution.latency", "1m")

        # Cache metrics for different tiers
        cache_stats = {
            "hot": self.aggregator.get_stats("cache.access.latency", "1m"),
            "warm": self.aggregator.get_stats("cache.access.latency", "1m"),
            "cold": self.aggregator.get_stats("cache.access.latency", "1m"),
        }

        # Error metrics
        error_stats = self.aggregator.get_stats("agent.execution.latency", "1m")

        # Build Plotly traces
        return {
            "latency_traces": self._build_latency_traces(latency_stats),
            "cache_traces": self._build_cache_traces(cache_stats),
            "error_traces": self._build_error_traces(error_stats),
        }

    def _build_latency_traces(self, stats: Dict) -> List[Dict]:
        """
        Build Plotly traces for latency chart.

        Args:
            stats: Statistics dictionary

        Returns:
            List of Plotly trace dictionaries
        """
        if not stats:
            return []

        samples = stats.get("samples", [])
        p95 = stats.get("p95", 0)

        traces = [
            {
                "x": list(range(len(samples))),
                "y": samples,
                "type": "scatter",
                "mode": "lines",
                "name": "Latency",
                "line": {"color": "blue"},
            }
        ]

        # Add p95 threshold line if we have samples
        if samples:
            traces.append(
                {
                    "x": list(range(len(samples))),
                    "y": [p95] * len(samples),
                    "type": "scatter",
                    "mode": "lines",
                    "name": "p95",
                    "line": {"color": "red", "dash": "dash"},
                }
            )

        return traces

    def _build_cache_traces(self, cache_stats: Dict) -> List[Dict]:
        """
        Build Plotly traces for cache hit rate chart.

        Args:
            cache_stats: Cache statistics by tier

        Returns:
            List of Plotly trace dictionaries
        """
        traces = []

        for tier, stats in cache_stats.items():
            if stats:
                samples = stats.get("samples", [])
                if samples:
                    traces.append(
                        {
                            "x": list(range(len(samples))),
                            "y": samples,
                            "type": "scatter",
                            "mode": "lines",
                            "name": f"{tier.capitalize()} Tier",
                        }
                    )

        return traces

    def _build_error_traces(self, error_stats: Dict) -> List[Dict]:
        """
        Build Plotly traces for error rate chart.

        Args:
            error_stats: Error statistics

        Returns:
            List of Plotly trace dictionaries
        """
        if not error_stats:
            return []

        samples = error_stats.get("samples", [])

        if not samples:
            return []

        return [
            {
                "x": list(range(len(samples))),
                "y": samples,
                "type": "scatter",
                "mode": "lines",
                "name": "Error Rate",
                "line": {"color": "orange"},
            }
        ]


def create_dashboard_app(
    aggregator: Optional[AnalyticsAggregator] = None,
) -> "FastAPI":
    """Build and return the dashboard's FastAPI application.

    This is the canonical constructor for the dashboard's HTTP surface. FastAPI
    is imported here (not at module load), so a bare ``import kaizen.monitoring``
    never requires the ``server`` extra; calling this without FastAPI installed
    raises :class:`MonitoringDependencyError` naming the remedy.

    Args:
        aggregator: If provided, a :class:`PerformanceDashboard` is constructed
            and registered as the singleton the routes serve from. If omitted,
            the routes serve from whatever instance was constructed elsewhere
            (via :meth:`PerformanceDashboard.get_instance`).

    Returns:
        A configured ``fastapi.FastAPI`` instance with the dashboard routes.

    Raises:
        MonitoringDependencyError: If FastAPI is not installed.
    """
    _require_fastapi()
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, PlainTextResponse

    app = FastAPI(title="Kaizen Performance Dashboard")

    if aggregator is not None:
        PerformanceDashboard(aggregator)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_ui():
        """Serve dashboard HTML."""
        return HTMLResponse(
            """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Kaizen Performance Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
            }
            h1 {
                color: #333;
                text-align: center;
            }
            .chart-container {
                background-color: white;
                padding: 20px;
                margin: 20px 0;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .status {
                text-align: center;
                padding: 10px;
                background-color: #e8f5e9;
                border-radius: 4px;
                margin-bottom: 20px;
            }
            .status.disconnected {
                background-color: #ffebee;
            }
        </style>
    </head>
    <body>
        <h1>Kaizen Performance Dashboard</h1>
        <div id="status" class="status">Connecting...</div>

        <div class="chart-container">
            <div id="latency-chart" style="width:100%;height:400px"></div>
        </div>

        <div class="chart-container">
            <div id="cache-hit-rate-chart" style="width:100%;height:400px"></div>
        </div>

        <div class="chart-container">
            <div id="error-rate-chart" style="width:100%;height:400px"></div>
        </div>

        <script>
            // Use current host for WebSocket (works in any deployment)
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsHost = window.location.host || 'localhost:8000';
            const ws = new WebSocket(`${wsProtocol}//${wsHost}/ws`);
            const statusDiv = document.getElementById('status');

            ws.onopen = function() {
                statusDiv.textContent = 'Connected - Real-time updates active';
                statusDiv.className = 'status';
            };

            ws.onclose = function() {
                statusDiv.textContent = 'Disconnected - Attempting to reconnect...';
                statusDiv.className = 'status disconnected';
            };

            ws.onerror = function(error) {
                console.error('WebSocket error:', error);
                statusDiv.textContent = 'Connection error';
                statusDiv.className = 'status disconnected';
            };

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                updateCharts(data);
            };

            function updateCharts(data) {
                // Update latency chart
                if (data.latency_traces && data.latency_traces.length > 0) {
                    Plotly.react('latency-chart', data.latency_traces, {
                        title: 'Signature Resolution Latency',
                        xaxis: {title: 'Sample'},
                        yaxis: {title: 'Latency (ms)'}
                    });
                }

                // Update cache hit rate chart
                if (data.cache_traces && data.cache_traces.length > 0) {
                    Plotly.react('cache-hit-rate-chart', data.cache_traces, {
                        title: 'Cache Performance by Tier',
                        xaxis: {title: 'Sample'},
                        yaxis: {title: 'Latency (ms)'}
                    });
                }

                // Update error rate chart
                if (data.error_traces && data.error_traces.length > 0) {
                    Plotly.react('error-rate-chart', data.error_traces, {
                        title: 'Agent Execution Metrics',
                        xaxis: {title: 'Sample'},
                        yaxis: {title: 'Latency (ms)'}
                    });
                }
            }

            // Initialize empty charts
            Plotly.newPlot('latency-chart', [], {
                title: 'Signature Resolution Latency',
                xaxis: {title: 'Sample'},
                yaxis: {title: 'Latency (ms)'}
            });

            Plotly.newPlot('cache-hit-rate-chart', [], {
                title: 'Cache Performance by Tier',
                xaxis: {title: 'Sample'},
                yaxis: {title: 'Latency (ms)'}
            });

            Plotly.newPlot('error-rate-chart', [], {
                title: 'Agent Execution Metrics',
                xaxis: {title: 'Sample'},
                yaxis: {title: 'Latency (ms)'}
            });
        </script>
    </body>
    </html>
    """
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time metric streaming."""
        await websocket.accept()

        # Get dashboard instance
        dashboard = PerformanceDashboard.get_instance()
        if dashboard:
            dashboard._clients.append(websocket)

        try:
            while True:
                # Send metrics every 1s
                await asyncio.sleep(1)

                if dashboard:
                    metrics_data = await dashboard._get_dashboard_data()
                    await websocket.send_json(metrics_data)
        except WebSocketDisconnect:
            if dashboard:
                dashboard._clients.remove(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if dashboard:
                dashboard._clients.remove(websocket)

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics():
        """Prometheus metrics endpoint.

        Returns the Prometheus exposition format as ``text/plain`` — scrapers
        reject the default ``application/json`` FastAPI would otherwise apply to
        a bare ``str`` return.
        """
        dashboard = PerformanceDashboard.get_instance()

        if not dashboard:
            return "# No metrics available\n"

        metrics_text = []

        # Get all metrics from aggregator
        for window in ["1s", "1m", "5m", "1h"]:
            all_metrics = dashboard.aggregator.get_all_metrics(window)

            for metric_name, stats in all_metrics.items():
                if stats:
                    # Export in Prometheus format
                    clean_name = metric_name.replace(".", "_")

                    metrics_text.append(
                        f"# HELP {clean_name}_p95 95th percentile of {metric_name}"
                    )
                    metrics_text.append(f"# TYPE {clean_name}_p95 gauge")
                    metrics_text.append(
                        f'{clean_name}_p95{{window="{window}"}} {stats["p95"]}'
                    )

                    metrics_text.append(
                        f"# HELP {clean_name}_mean Mean of {metric_name}"
                    )
                    metrics_text.append(f"# TYPE {clean_name}_mean gauge")
                    metrics_text.append(
                        f'{clean_name}_mean{{window="{window}"}} {stats["mean"]}'
                    )

        return "\n".join(metrics_text)

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        dashboard = PerformanceDashboard.get_instance()

        return {
            "status": "healthy",
            "dashboard_active": dashboard is not None,
            "connected_clients": len(dashboard._clients) if dashboard else 0,
        }

    return app


def __getattr__(name: str):
    """Lazily build the singleton ``app`` on first access (PEP 562).

    Keeps ``import kaizen.monitoring.dashboard`` FastAPI-free while preserving
    the historical ``dashboard.app`` / ``kaizen.monitoring.app`` public symbol.
    Accessing ``app`` without FastAPI installed raises the typed, actionable
    :class:`MonitoringDependencyError`.
    """
    if name == "app":
        global _app
        if _app is None:
            _app = create_dashboard_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
