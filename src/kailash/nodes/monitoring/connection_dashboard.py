"""Real-time monitoring dashboard for connection pools.

This module provides a web-based dashboard for monitoring connection pool
health, performance metrics, and alerts. It integrates with the metrics
collection system to provide real-time visualization.

Features:
- Real-time pool statistics with WebSocket updates
- Health score visualization with history
- Alert configuration and notifications
- Historical trend analysis with charts
- Export capabilities for reports

Example:
    >>> dashboard = ConnectionDashboardNode(
    ...     name="pool_monitor",
    ...     port=8080,
    ...     update_interval=1.0,
    ...     retention_hours=24
    ... )
    >>>
    >>> # Start dashboard server
    >>> await dashboard.start()
    >>>
    >>> # Access at http://localhost:8080
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import aiohttp_cors
from aiohttp import web
from kailash.nodes.base import Node, NodeParameter, register_node

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """Alert rule configuration."""

    id: str
    name: str
    condition: str  # e.g., "pool_utilization > 0.9"
    threshold: float
    duration_seconds: int = 60  # How long condition must be true
    cooldown_seconds: int = 300  # Prevent alert spam
    severity: str = "warning"  # info, warning, error, critical
    enabled: bool = True
    last_triggered: Optional[float] = None

    def is_in_cooldown(self) -> bool:
        """Check if alert is in cooldown period."""
        if not self.last_triggered:
            return False
        return (time.time() - self.last_triggered) < self.cooldown_seconds


@dataclass
class Alert:
    """Active alert instance."""

    rule_id: str
    triggered_at: float
    severity: str
    message: str
    metric_value: float
    resolved: bool = False
    resolved_at: Optional[float] = None

    def duration(self) -> float:
        """Get alert duration in seconds."""
        end_time = self.resolved_at or time.time()
        return end_time - self.triggered_at


class MetricsCache:
    """Cache for metrics data with time-based expiration."""

    def __init__(self, retention_hours: int = 24):
        """Initialize metrics cache."""
        self.retention_hours = retention_hours
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self._last_cleanup = time.time()

    def add(self, metric_name: str, value: Dict[str, Any]):
        """Add metric value to cache."""
        if metric_name not in self._data:
            self._data[metric_name] = []

        value["timestamp"] = time.time()
        self._data[metric_name].append(value)

        # Periodic cleanup
        if time.time() - self._last_cleanup > 3600:  # Every hour
            self._cleanup()

    def get_recent(self, metric_name: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """Get recent metric values."""
        if metric_name not in self._data:
            return []

        cutoff = time.time() - (minutes * 60)
        return [v for v in self._data[metric_name] if v["timestamp"] >= cutoff]

    def _cleanup(self):
        """Remove old data."""
        cutoff = time.time() - (self.retention_hours * 3600)

        for metric_name in list(self._data.keys()):
            self._data[metric_name] = [
                v for v in self._data[metric_name] if v["timestamp"] >= cutoff
            ]

            # Remove empty metrics
            if not self._data[metric_name]:
                del self._data[metric_name]

        self._last_cleanup = time.time()


@register_node()
class ConnectionDashboardNode(Node):
    """Web-based monitoring dashboard for connection pools.

    Provides real-time visualization of connection pool metrics,
    health scores, and alerts through a web interface.
    """

    def __init__(self, **config):
        """Initialize dashboard node.

        Args:
            port: Web server port (default: 8080)
            host: Web server host (default: localhost)
            update_interval: Metric update interval in seconds (default: 1.0)
            retention_hours: How long to keep historical data (default: 24)
            enable_alerts: Enable alert system (default: True)
        """
        self.port = config.get("port", 8080)
        self.host = config.get("host", "localhost")
        self.update_interval = config.get("update_interval", 1.0)
        self.retention_hours = config.get("retention_hours", 24)
        self.enable_alerts = config.get("enable_alerts", True)

        super().__init__(**config)

        # Web server
        self.app = None
        self.runner = None
        self.site = None

        # WebSocket connections
        self._websockets: Set[web.WebSocketResponse] = set()

        # Metrics cache
        self._cache = MetricsCache(self.retention_hours)

        # Alert system
        self._alert_rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Alert] = {}
        self._alert_history: List[Alert] = []

        # Update task
        self._update_task: Optional[asyncio.Task] = None

        # Initialize default alert rules
        self._init_default_alerts()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "port": NodeParameter(
                name="port", type=int, default=8080, description="Web server port"
            ),
            "host": NodeParameter(
                name="host",
                type=str,
                default="localhost",
                description="Web server host",
            ),
            "update_interval": NodeParameter(
                name="update_interval",
                type=float,
                default=1.0,
                description="Metric update interval in seconds",
            ),
            "retention_hours": NodeParameter(
                name="retention_hours",
                type=int,
                default=24,
                description="Historical data retention in hours",
            ),
            "enable_alerts": NodeParameter(
                name="enable_alerts",
                type=bool,
                default=True,
                description="Enable alert system",
            ),
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                description="Dashboard action",
                choices=["start", "stop", "status"],
            ),
        }

    async def execute(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute dashboard action.

        Actions:
        - start: Start the dashboard server
        - stop: Stop the dashboard server
        - status: Get dashboard status
        """
        action = input_data.get("action", "status")

        if action == "start":
            await self.start()
            return {
                "status": "started",
                "url": f"http://{self.host}:{self.port}",
                "websocket": f"ws://{self.host}:{self.port}/ws",
            }

        elif action == "stop":
            await self.stop()
            return {"status": "stopped"}

        else:
            return self.get_status()

    async def start(self):
        """Start the dashboard web server."""
        if self.app:
            logger.warning("Dashboard already running")
            return

        # Create web app
        self.app = web.Application()

        # Setup CORS
        cors = aiohttp_cors.setup(
            self.app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True, expose_headers="*", allow_headers="*"
                )
            },
        )

        # Add routes
        self.app.router.add_get("/", self._handle_index)
        self.app.router.add_get("/api/metrics", self._handle_metrics)
        self.app.router.add_get("/api/pools", self._handle_pools)
        self.app.router.add_get("/api/alerts", self._handle_alerts)
        self.app.router.add_post("/api/alerts", self._handle_create_alert)
        self.app.router.add_delete("/api/alerts/{alert_id}", self._handle_delete_alert)
        self.app.router.add_get("/api/history/{metric_name}", self._handle_history)
        self.app.router.add_get("/ws", self._handle_websocket)

        # Configure CORS for all routes
        for route in list(self.app.router.routes()):
            cors.add(route)

        # Start server
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()

        # Start update task
        self._update_task = asyncio.create_task(self._update_loop())

        logger.info(f"Dashboard started at http://{self.host}:{self.port}")

    async def stop(self):
        """Stop the dashboard web server."""
        # Stop update task
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket connections
        for ws in list(self._websockets):
            await ws.close()

        # Stop web server
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()

        self.app = None
        self.runner = None
        self.site = None

        logger.info("Dashboard stopped")

    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve dashboard HTML."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>Connection Pool Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .pool-card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric { display: inline-block; margin: 10px 20px 10px 0; }
        .metric-label { color: #666; font-size: 12px; }
        .metric-value { font-size: 24px; font-weight: bold; }
        .health-bar { width: 100%; height: 20px; background: #ddd; border-radius: 10px; overflow: hidden; }
        .health-fill { height: 100%; transition: width 0.3s, background-color 0.3s; }
        .health-good { background: #4caf50; }
        .health-warning { background: #ff9800; }
        .health-critical { background: #f44336; }
        .alert { padding: 10px; margin: 5px 0; border-radius: 4px; }
        .alert-warning { background: #fff3cd; border: 1px solid #ffeeba; }
        .alert-error { background: #f8d7da; border: 1px solid #f5c6cb; }
        .alert-critical { background: #d1ecf1; border: 1px solid #bee5eb; }
        .chart { width: 100%; height: 200px; margin: 20px 0; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <h1>Connection Pool Dashboard</h1>

        <div id="alerts"></div>

        <h2>Connection Pools</h2>
        <div id="pools"></div>

        <h2>Metrics History</h2>
        <canvas id="metricsChart" class="chart"></canvas>
    </div>

    <script>
        // WebSocket connection
        const ws = new WebSocket(`ws://${window.location.host}/ws`);

        // Chart setup
        const ctx = document.getElementById('metricsChart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Pool Utilization',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 1
                    }
                }
            }
        });

        // Update functions
        function updatePools(pools) {
            const container = document.getElementById('pools');
            container.innerHTML = '';

            for (const [name, pool] of Object.entries(pools)) {
                const healthClass = pool.health_score > 80 ? 'health-good' :
                                  pool.health_score > 60 ? 'health-warning' : 'health-critical';

                container.innerHTML += `
                    <div class="pool-card">
                        <h3>${name}</h3>

                        <div class="health-bar">
                            <div class="health-fill ${healthClass}" style="width: ${pool.health_score}%"></div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Active Connections</div>
                            <div class="metric-value">${pool.active_connections}</div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Total Connections</div>
                            <div class="metric-value">${pool.total_connections}</div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Utilization</div>
                            <div class="metric-value">${(pool.utilization * 100).toFixed(1)}%</div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Queries/sec</div>
                            <div class="metric-value">${pool.queries_per_second.toFixed(1)}</div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Avg Query Time</div>
                            <div class="metric-value">${pool.avg_query_time_ms.toFixed(1)}ms</div>
                        </div>

                        <div class="metric">
                            <div class="metric-label">Error Rate</div>
                            <div class="metric-value">${(pool.error_rate * 100).toFixed(2)}%</div>
                        </div>
                    </div>
                `;
            }
        }

        function updateAlerts(alerts) {
            const container = document.getElementById('alerts');
            container.innerHTML = '';

            if (alerts.length === 0) return;

            container.innerHTML = '<h2>Active Alerts</h2>';

            for (const alert of alerts) {
                const alertClass = `alert-${alert.severity}`;
                container.innerHTML += `
                    <div class="alert ${alertClass}">
                        <strong>${alert.message}</strong> -
                        ${new Date(alert.triggered_at * 1000).toLocaleTimeString()}
                    </div>
                `;
            }
        }

        function updateChart(data) {
            // Update chart with latest data
            if (data.timestamp && data.utilization !== undefined) {
                const time = new Date(data.timestamp * 1000).toLocaleTimeString();

                chart.data.labels.push(time);
                chart.data.datasets[0].data.push(data.utilization);

                // Keep only last 60 points
                if (chart.data.labels.length > 60) {
                    chart.data.labels.shift();
                    chart.data.datasets[0].data.shift();
                }

                chart.update('none');  // No animation for real-time
            }
        }

        // WebSocket handlers
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'pools') {
                updatePools(data.pools);
            } else if (data.type === 'alerts') {
                updateAlerts(data.alerts);
            } else if (data.type === 'metrics') {
                updateChart(data.data);
            }
        };

        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        // Initial load
        fetch('/api/pools').then(r => r.json()).then(data => updatePools(data));
        fetch('/api/alerts').then(r => r.json()).then(data => updateAlerts(data.active));
    </script>
</body>
</html>
"""
        return web.Response(text=html, content_type="text/html")

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Get current metrics."""
        metrics = await self._collect_metrics()
        return web.json_response(metrics)

    async def _handle_pools(self, request: web.Request) -> web.Response:
        """Get pool information."""
        pools = await self._get_pool_info()
        return web.json_response(pools)

    async def _handle_alerts(self, request: web.Request) -> web.Response:
        """Get alerts."""
        return web.json_response(
            {
                "active": [
                    {
                        "rule_id": alert.rule_id,
                        "triggered_at": alert.triggered_at,
                        "severity": alert.severity,
                        "message": alert.message,
                        "duration": alert.duration(),
                    }
                    for alert in self._active_alerts.values()
                    if not alert.resolved
                ],
                "rules": [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "condition": rule.condition,
                        "threshold": rule.threshold,
                        "severity": rule.severity,
                        "enabled": rule.enabled,
                    }
                    for rule in self._alert_rules.values()
                ],
                "history": [
                    {
                        "rule_id": alert.rule_id,
                        "triggered_at": alert.triggered_at,
                        "resolved_at": alert.resolved_at,
                        "severity": alert.severity,
                        "message": alert.message,
                        "duration": alert.duration(),
                    }
                    for alert in self._alert_history[-20:]  # Last 20 alerts
                ],
            }
        )

    async def _handle_create_alert(self, request: web.Request) -> web.Response:
        """Create new alert rule."""
        data = await request.json()

        rule = AlertRule(
            id=f"rule_{len(self._alert_rules)}",
            name=data["name"],
            condition=data["condition"],
            threshold=data["threshold"],
            duration_seconds=data.get("duration_seconds", 60),
            severity=data.get("severity", "warning"),
        )

        self._alert_rules[rule.id] = rule

        return web.json_response({"id": rule.id})

    async def _handle_delete_alert(self, request: web.Request) -> web.Response:
        """Delete alert rule."""
        alert_id = request.match_info["alert_id"]

        if alert_id in self._alert_rules:
            del self._alert_rules[alert_id]
            return web.json_response({"deleted": True})

        return web.json_response({"error": "Alert not found"}, status=404)

    async def _handle_history(self, request: web.Request) -> web.Response:
        """Get metric history."""
        metric_name = request.match_info["metric_name"]
        minutes = int(request.query.get("minutes", 60))

        history = self._cache.get_recent(metric_name, minutes)

        return web.json_response(history)

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._websockets.add(ws)

        try:
            # Send initial data
            pools = await self._get_pool_info()
            await ws.send_json({"type": "pools", "pools": pools})

            # Keep connection alive
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # Handle client messages if needed
                    pass
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")

        finally:
            self._websockets.discard(ws)

        return ws

    async def _update_loop(self):
        """Periodically update metrics and check alerts."""
        while True:
            try:
                # Collect metrics
                metrics = await self._collect_metrics()
                pools = await self._get_pool_info()

                # Update cache
                for pool_name, pool_data in pools.items():
                    self._cache.add(
                        f"{pool_name}_utilization",
                        {"value": pool_data["utilization"], "pool": pool_name},
                    )

                # Check alerts
                if self.enable_alerts:
                    await self._check_alerts(pools)

                # Broadcast to WebSocket clients
                await self._broadcast({"type": "pools", "pools": pools})

                # Send sample metrics for chart
                if pools:
                    first_pool = next(iter(pools.values()))
                    await self._broadcast(
                        {
                            "type": "metrics",
                            "data": {
                                "timestamp": time.time(),
                                "utilization": first_pool["utilization"],
                            },
                        }
                    )

                # Send active alerts
                active_alerts = [
                    {
                        "rule_id": alert.rule_id,
                        "triggered_at": alert.triggered_at,
                        "severity": alert.severity,
                        "message": alert.message,
                    }
                    for alert in self._active_alerts.values()
                    if not alert.resolved
                ]

                if active_alerts:
                    await self._broadcast({"type": "alerts", "alerts": active_alerts})

            except Exception as e:
                logger.error(f"Error in update loop: {e}")

            await asyncio.sleep(self.update_interval)

    async def _collect_metrics(self) -> Dict[str, Any]:
        """Collect metrics from all pools."""
        # This would integrate with the MetricsAggregator
        # For now, return sample data
        return {"timestamp": time.time(), "pools": await self._get_pool_info()}

    async def _get_pool_info(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all pools."""
        # This would get real data from connection pools
        # For now, return sample data

        # Try to get real pools from resource registry
        pools_info = {}

        if hasattr(self, "runtime") and hasattr(self.runtime, "resource_registry"):
            resources = self.runtime.resource_registry.list_resources()

            for name, resource in resources.items():
                if hasattr(resource, "get_pool_statistics"):
                    try:
                        stats = await resource.get_pool_statistics()
                        pools_info[name] = {
                            "health_score": stats.get("health_score", 100),
                            "active_connections": stats.get("active_connections", 0),
                            "total_connections": stats.get("total_connections", 0),
                            "utilization": stats.get("utilization", 0.0),
                            "queries_per_second": stats.get("queries_per_second", 0.0),
                            "avg_query_time_ms": stats.get("avg_query_time_ms", 0.0),
                            "error_rate": stats.get("error_rate", 0.0),
                        }
                    except Exception as e:
                        logger.error(f"Error getting stats for pool {name}: {e}")

        # If no real pools, return sample data
        if not pools_info:
            pools_info = {
                "main_pool": {
                    "health_score": 85,
                    "active_connections": 8,
                    "total_connections": 10,
                    "utilization": 0.8,
                    "queries_per_second": 150.5,
                    "avg_query_time_ms": 12.3,
                    "error_rate": 0.002,
                }
            }

        return pools_info

    async def _check_alerts(self, pools: Dict[str, Dict[str, Any]]):
        """Check alert conditions."""
        for rule in self._alert_rules.values():
            if not rule.enabled or rule.is_in_cooldown():
                continue

            # Simple condition evaluation (in production, use proper parser)
            triggered = False
            metric_value = 0.0

            for pool_name, pool_data in pools.items():
                if (
                    "utilization" in rule.condition
                    and pool_data["utilization"] > rule.threshold
                ):
                    triggered = True
                    metric_value = pool_data["utilization"]
                    break
                elif (
                    "error_rate" in rule.condition
                    and pool_data["error_rate"] > rule.threshold
                ):
                    triggered = True
                    metric_value = pool_data["error_rate"]
                    break

            # Check if alert should be triggered
            alert_key = f"{rule.id}_{int(time.time() / rule.duration_seconds)}"

            if triggered:
                if alert_key not in self._active_alerts:
                    alert = Alert(
                        rule_id=rule.id,
                        triggered_at=time.time(),
                        severity=rule.severity,
                        message=f"{rule.name}: {rule.condition} (value: {metric_value:.2f})",
                        metric_value=metric_value,
                    )

                    self._active_alerts[alert_key] = alert
                    self._alert_history.append(alert)
                    rule.last_triggered = time.time()

                    logger.warning(f"Alert triggered: {alert.message}")
            else:
                # Resolve alert if condition no longer met
                if alert_key in self._active_alerts:
                    alert = self._active_alerts[alert_key]
                    alert.resolved = True
                    alert.resolved_at = time.time()

                    logger.info(f"Alert resolved: {rule.name}")

    async def _broadcast(self, data: Dict[str, Any]):
        """Broadcast data to all WebSocket clients."""
        if not self._websockets:
            return

        # Send to all connected clients
        disconnected = set()

        for ws in self._websockets:
            try:
                await ws.send_json(data)
            except ConnectionResetError:
                disconnected.add(ws)

        # Remove disconnected clients
        self._websockets -= disconnected

    def _init_default_alerts(self):
        """Initialize default alert rules."""
        default_rules = [
            AlertRule(
                id="high_utilization",
                name="High Pool Utilization",
                condition="pool_utilization > 0.9",
                threshold=0.9,
                duration_seconds=60,
                severity="warning",
            ),
            AlertRule(
                id="high_error_rate",
                name="High Error Rate",
                condition="error_rate > 0.05",
                threshold=0.05,
                duration_seconds=30,
                severity="error",
            ),
            AlertRule(
                id="pool_exhausted",
                name="Pool Exhausted",
                condition="pool_utilization >= 1.0",
                threshold=1.0,
                duration_seconds=10,
                severity="critical",
            ),
        ]

        for rule in default_rules:
            self._alert_rules[rule.id] = rule

    def get_status(self) -> Dict[str, Any]:
        """Get dashboard status."""
        return {
            "running": self.app is not None,
            "url": f"http://{self.host}:{self.port}" if self.app else None,
            "websocket_clients": len(self._websockets),
            "active_alerts": len(
                [a for a in self._active_alerts.values() if not a.resolved]
            ),
            "alert_rules": len(self._alert_rules),
            "cached_metrics": len(self._cache._data),
            "update_interval": self.update_interval,
            "retention_hours": self.retention_hours,
        }
