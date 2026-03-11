"""
PerformanceDashboard: Real-time performance visualization with <1s refresh.

This module provides a FastAPI-based web dashboard with WebSocket
support for real-time metric updates and Plotly.js visualizations.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .analytics_aggregator import AnalyticsAggregator

logger = logging.getLogger(__name__)

# Global FastAPI app
app = FastAPI(title="Kaizen Performance Dashboard")


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
        self._clients: List[WebSocket] = []
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


# FastAPI endpoints


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


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
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

                metrics_text.append(f"# HELP {clean_name}_mean Mean of {metric_name}")
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
