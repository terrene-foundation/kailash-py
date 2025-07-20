"""Edge monitoring service for comprehensive edge observability.

This service provides real-time monitoring, alerting, and analytics
for edge node operations, performance, and health.
"""

import asyncio
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class MetricType(Enum):
    """Types of metrics collected."""

    LATENCY = "latency"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    RESOURCE_USAGE = "resource_usage"
    AVAILABILITY = "availability"
    CACHE_HIT_RATE = "cache_hit_rate"
    MIGRATION_TIME = "migration_time"
    COORDINATION_OVERHEAD = "coordination_overhead"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class HealthStatus(Enum):
    """Edge node health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class EdgeMetric:
    """Represents a single metric measurement."""

    timestamp: datetime
    edge_node: str
    metric_type: MetricType
    value: float
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "edge_node": self.edge_node,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "tags": self.tags,
        }


@dataclass
class EdgeAlert:
    """Represents an alert for edge issues."""

    alert_id: str
    timestamp: datetime
    edge_node: str
    severity: AlertSeverity
    metric_type: MetricType
    message: str
    current_value: float
    threshold: float
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "timestamp": self.timestamp.isoformat(),
            "edge_node": self.edge_node,
            "severity": self.severity.value,
            "metric_type": self.metric_type.value,
            "message": self.message,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "tags": self.tags,
        }


@dataclass
class EdgeHealth:
    """Edge node health information."""

    edge_node: str
    status: HealthStatus
    last_check: datetime
    uptime_seconds: float
    metrics_summary: Dict[str, float]
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "edge_node": self.edge_node,
            "status": self.status.value,
            "last_check": self.last_check.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "metrics_summary": self.metrics_summary,
            "issues": self.issues,
        }


class EdgeMonitor:
    """Edge monitoring service for observability and alerting.

    Provides comprehensive monitoring of edge nodes including:
    - Real-time metrics collection
    - Health monitoring
    - Alerting based on thresholds
    - Performance analytics
    - Anomaly detection
    """

    def __init__(
        self,
        retention_period: int = 24 * 60 * 60,  # 24 hours
        alert_cooldown: int = 300,  # 5 minutes
        health_check_interval: int = 30,  # 30 seconds
        anomaly_detection: bool = True,
    ):
        """Initialize edge monitor.

        Args:
            retention_period: How long to retain metrics (seconds)
            alert_cooldown: Cooldown between alerts for same issue
            health_check_interval: Interval between health checks
            anomaly_detection: Enable anomaly detection
        """
        self.retention_period = retention_period
        self.alert_cooldown = alert_cooldown
        self.health_check_interval = health_check_interval
        self.anomaly_detection = anomaly_detection

        # Metrics storage
        self.metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self.aggregated_metrics: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: defaultdict(list)
        )

        # Health tracking
        self.health_status: Dict[str, EdgeHealth] = {}
        self.node_start_times: Dict[str, datetime] = {}

        # Alerting
        self.alerts: List[EdgeAlert] = []
        self.alert_history: Dict[str, datetime] = {}
        self.alert_thresholds: Dict[MetricType, Dict[str, float]] = {
            MetricType.LATENCY: {"warning": 0.5, "error": 1.0, "critical": 2.0},
            MetricType.ERROR_RATE: {"warning": 0.05, "error": 0.1, "critical": 0.2},
            MetricType.RESOURCE_USAGE: {
                "warning": 0.7,
                "error": 0.85,
                "critical": 0.95,
            },
            MetricType.AVAILABILITY: {"warning": 0.99, "error": 0.95, "critical": 0.9},
            MetricType.CACHE_HIT_RATE: {"warning": 0.7, "error": 0.5, "critical": 0.3},
        }

        # Analytics
        self.baseline_metrics: Dict[str, Dict[MetricType, float]] = defaultdict(dict)

        # Background tasks
        self._running = False
        self._health_check_task = None
        self._cleanup_task = None
        self._analytics_task = None

    async def start(self):
        """Start monitoring service."""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        if self.anomaly_detection:
            self._analytics_task = asyncio.create_task(self._analytics_loop())

    async def stop(self):
        """Stop monitoring service."""
        self._running = False

        tasks = [self._health_check_task, self._cleanup_task, self._analytics_task]
        for task in tasks:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def record_metric(self, metric: EdgeMetric):
        """Record a metric measurement.

        Args:
            metric: Metric to record
        """
        # Store in time-series
        key = f"{metric.edge_node}:{metric.metric_type.value}"
        self.metrics[key].append(metric)

        # Update aggregated metrics for fast queries
        self.aggregated_metrics[metric.edge_node][metric.metric_type].append(
            metric.value
        )

        # Check thresholds and generate alerts
        await self._check_thresholds(metric)

        # Update node tracking
        if metric.edge_node not in self.node_start_times:
            self.node_start_times[metric.edge_node] = datetime.now()

    async def get_metrics(
        self,
        edge_node: Optional[str] = None,
        metric_type: Optional[MetricType] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[EdgeMetric]:
        """Query metrics with filters.

        Args:
            edge_node: Filter by edge node
            metric_type: Filter by metric type
            start_time: Start of time range
            end_time: End of time range
            tags: Filter by tags

        Returns:
            List of matching metrics
        """
        results = []

        # Determine keys to search
        if edge_node and metric_type:
            keys = [f"{edge_node}:{metric_type.value}"]
        elif edge_node:
            keys = [k for k in self.metrics.keys() if k.startswith(f"{edge_node}:")]
        elif metric_type:
            keys = [
                k for k in self.metrics.keys() if k.endswith(f":{metric_type.value}")
            ]
        else:
            keys = list(self.metrics.keys())

        # Filter metrics
        for key in keys:
            for metric in self.metrics[key]:
                # Time range filter
                if start_time and metric.timestamp < start_time:
                    continue
                if end_time and metric.timestamp > end_time:
                    continue

                # Tag filter
                if tags:
                    if not all(metric.tags.get(k) == v for k, v in tags.items()):
                        continue

                results.append(metric)

        return sorted(results, key=lambda m: m.timestamp)

    async def get_edge_health(self, edge_node: str) -> EdgeHealth:
        """Get health status for an edge node.

        Args:
            edge_node: Edge node identifier

        Returns:
            Health status
        """
        if edge_node in self.health_status:
            return self.health_status[edge_node]

        # Create new health entry
        health = EdgeHealth(
            edge_node=edge_node,
            status=HealthStatus.UNKNOWN,
            last_check=datetime.now(),
            uptime_seconds=0,
            metrics_summary={},
        )

        self.health_status[edge_node] = health
        return health

    async def get_alerts(
        self,
        edge_node: Optional[str] = None,
        severity: Optional[AlertSeverity] = None,
        start_time: Optional[datetime] = None,
        active_only: bool = False,
    ) -> List[EdgeAlert]:
        """Get alerts with filters.

        Args:
            edge_node: Filter by edge node
            severity: Filter by severity
            start_time: Filter alerts after this time
            active_only: Only return active alerts

        Returns:
            List of matching alerts
        """
        results = []

        for alert in self.alerts:
            # Edge node filter
            if edge_node and alert.edge_node != edge_node:
                continue

            # Severity filter
            if severity and alert.severity != severity:
                continue

            # Time filter
            if start_time and alert.timestamp < start_time:
                continue

            # Active filter
            if active_only:
                # Check if alert is still active (within cooldown)
                key = f"{alert.edge_node}:{alert.metric_type.value}"
                if key in self.alert_history:
                    if (
                        datetime.now() - self.alert_history[key]
                    ).total_seconds() > self.alert_cooldown:
                        continue

            results.append(alert)

        return sorted(results, key=lambda a: a.timestamp, reverse=True)

    def get_analytics(self, edge_node: str) -> Dict[str, Any]:
        """Get analytics for an edge node.

        Args:
            edge_node: Edge node identifier

        Returns:
            Analytics summary
        """
        analytics = {
            "edge_node": edge_node,
            "metrics_summary": {},
            "trends": {},
            "anomalies": [],
            "recommendations": [],
        }

        # Calculate summaries for each metric type
        for metric_type, values in self.aggregated_metrics[edge_node].items():
            if not values:
                continue

            # Basic statistics
            analytics["metrics_summary"][metric_type.value] = {
                "count": len(values),
                "mean": statistics.mean(values),
                "median": statistics.median(values),
                "std_dev": statistics.stdev(values) if len(values) > 1 else 0,
                "min": min(values),
                "max": max(values),
                "p95": sorted(values)[int(len(values) * 0.95)] if values else 0,
                "p99": sorted(values)[int(len(values) * 0.99)] if values else 0,
            }

            # Trend analysis (simple moving average)
            if len(values) > 10:
                recent = values[-10:]
                older = values[-20:-10] if len(values) > 20 else values[:10]

                recent_avg = statistics.mean(recent)
                older_avg = statistics.mean(older)

                trend = "stable"
                if recent_avg > older_avg * 1.1:
                    trend = "increasing"
                elif recent_avg < older_avg * 0.9:
                    trend = "decreasing"

                analytics["trends"][metric_type.value] = {
                    "direction": trend,
                    "change_percent": (
                        ((recent_avg - older_avg) / older_avg * 100) if older_avg else 0
                    ),
                }

        # Detect anomalies
        if self.anomaly_detection:
            anomalies = self._detect_anomalies(edge_node)
            analytics["anomalies"] = [a.to_dict() for a in anomalies]

        # Generate recommendations
        analytics["recommendations"] = self._generate_recommendations(
            edge_node, analytics
        )

        return analytics

    async def _check_thresholds(self, metric: EdgeMetric):
        """Check if metric violates thresholds and create alerts."""
        if metric.metric_type not in self.alert_thresholds:
            return

        thresholds = self.alert_thresholds[metric.metric_type]
        alert_key = f"{metric.edge_node}:{metric.metric_type.value}"

        # Check cooldown
        if alert_key in self.alert_history:
            if (
                datetime.now() - self.alert_history[alert_key]
            ).total_seconds() < self.alert_cooldown:
                return

        # Determine severity
        severity = None
        threshold_value = None

        # For availability and cache hit rate, lower is worse
        if metric.metric_type in [MetricType.AVAILABILITY, MetricType.CACHE_HIT_RATE]:
            if metric.value <= thresholds.get("critical", 0):
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds["critical"]
            elif metric.value <= thresholds.get("error", 0):
                severity = AlertSeverity.ERROR
                threshold_value = thresholds["error"]
            elif metric.value <= thresholds.get("warning", 0):
                severity = AlertSeverity.WARNING
                threshold_value = thresholds["warning"]
        else:
            # For other metrics, higher is worse
            if metric.value >= thresholds.get("critical", float("inf")):
                severity = AlertSeverity.CRITICAL
                threshold_value = thresholds["critical"]
            elif metric.value >= thresholds.get("error", float("inf")):
                severity = AlertSeverity.ERROR
                threshold_value = thresholds["error"]
            elif metric.value >= thresholds.get("warning", float("inf")):
                severity = AlertSeverity.WARNING
                threshold_value = thresholds["warning"]

        # Create alert if threshold violated
        if severity:
            alert = EdgeAlert(
                alert_id=f"{alert_key}:{int(time.time())}",
                timestamp=datetime.now(),
                edge_node=metric.edge_node,
                severity=severity,
                metric_type=metric.metric_type,
                message=f"{metric.metric_type.value} threshold exceeded on {metric.edge_node}",
                current_value=metric.value,
                threshold=threshold_value,
                tags=metric.tags,
            )

            self.alerts.append(alert)
            self.alert_history[alert_key] = datetime.now()

    async def _health_check_loop(self):
        """Background task for health monitoring."""
        while self._running:
            try:
                # Check health of all known nodes
                for edge_node in list(self.node_start_times.keys()):
                    await self._check_node_health(edge_node)

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                print(f"Health check error: {e}")
                await asyncio.sleep(0.1)  # Fast retry for tests

    async def _check_node_health(self, edge_node: str):
        """Check health of a specific node."""
        health = await self.get_edge_health(edge_node)

        # Calculate uptime
        if edge_node in self.node_start_times:
            uptime = (datetime.now() - self.node_start_times[edge_node]).total_seconds()
            health.uptime_seconds = uptime

        # Analyze recent metrics
        issues = []
        metrics_summary = {}

        for metric_type in MetricType:
            key = f"{edge_node}:{metric_type.value}"
            if key in self.metrics:
                recent_metrics = [
                    m
                    for m in self.metrics[key]
                    if (datetime.now() - m.timestamp).total_seconds() < 300
                ]  # Last 5 min

                if recent_metrics:
                    values = [m.value for m in recent_metrics]
                    metrics_summary[metric_type.value] = {
                        "current": values[-1],
                        "avg": statistics.mean(values),
                        "min": min(values),
                        "max": max(values),
                    }

        health.metrics_summary = metrics_summary

        # Determine overall status
        recent_alerts = await self.get_alerts(
            edge_node=edge_node,
            start_time=datetime.now() - timedelta(minutes=5),
            active_only=True,
        )

        critical_alerts = [
            a for a in recent_alerts if a.severity == AlertSeverity.CRITICAL
        ]
        error_alerts = [a for a in recent_alerts if a.severity == AlertSeverity.ERROR]

        if critical_alerts:
            health.status = HealthStatus.UNHEALTHY
            issues.extend([a.message for a in critical_alerts])
        elif error_alerts:
            health.status = HealthStatus.DEGRADED
            issues.extend([a.message for a in error_alerts])
        elif metrics_summary:
            health.status = HealthStatus.HEALTHY
        else:
            health.status = HealthStatus.UNKNOWN
            issues.append("No recent metrics received")

        health.issues = issues
        health.last_check = datetime.now()

    async def _cleanup_loop(self):
        """Background task for cleaning old data."""
        while self._running:
            try:
                cutoff_time = datetime.now() - timedelta(seconds=self.retention_period)

                # Clean metrics
                for key in list(self.metrics.keys()):
                    self.metrics[key] = deque(
                        (m for m in self.metrics[key] if m.timestamp > cutoff_time),
                        maxlen=10000,
                    )

                # Clean alerts
                self.alerts = [a for a in self.alerts if a.timestamp > cutoff_time]

                # Clean aggregated metrics (keep recent window)
                for node in self.aggregated_metrics:
                    for metric_type in self.aggregated_metrics[node]:
                        # Keep last 1000 values
                        if len(self.aggregated_metrics[node][metric_type]) > 1000:
                            self.aggregated_metrics[node][metric_type] = (
                                self.aggregated_metrics[node][metric_type][-1000:]
                            )

                await asyncio.sleep(1)  # Fast cleanup for tests

            except Exception as e:
                print(f"Cleanup error: {e}")
                await asyncio.sleep(0.1)  # Fast retry for tests

    async def _analytics_loop(self):
        """Background task for analytics and anomaly detection."""
        while self._running:
            try:
                # Update baselines
                for edge_node in self.aggregated_metrics:
                    self._update_baseline(edge_node)

                await asyncio.sleep(300)  # Run every 5 minutes

            except Exception as e:
                print(f"Analytics error: {e}")
                await asyncio.sleep(300)

    def _update_baseline(self, edge_node: str):
        """Update baseline metrics for anomaly detection."""
        for metric_type, values in self.aggregated_metrics[edge_node].items():
            if len(values) > 100:
                # Use median as baseline (more robust to outliers)
                self.baseline_metrics[edge_node][metric_type] = statistics.median(
                    values
                )

    def _detect_anomalies(self, edge_node: str) -> List[EdgeAlert]:
        """Detect anomalies in metrics."""
        anomalies = []

        if edge_node not in self.baseline_metrics:
            return anomalies

        for metric_type, baseline in self.baseline_metrics[edge_node].items():
            recent_values = self.aggregated_metrics[edge_node][metric_type][-10:]

            if not recent_values:
                continue

            current = statistics.mean(recent_values)

            # Simple anomaly detection: significant deviation from baseline
            deviation = abs(current - baseline) / baseline if baseline else 0

            if deviation > 0.5:  # 50% deviation
                anomaly = EdgeAlert(
                    alert_id=f"anomaly:{edge_node}:{metric_type.value}:{int(time.time())}",
                    timestamp=datetime.now(),
                    edge_node=edge_node,
                    severity=AlertSeverity.WARNING,
                    metric_type=metric_type,
                    message=f"Anomaly detected: {metric_type.value} deviates {deviation*100:.1f}% from baseline",
                    current_value=current,
                    threshold=baseline,
                    tags={"type": "anomaly", "deviation": str(deviation)},
                )
                anomalies.append(anomaly)

        return anomalies

    def _generate_recommendations(
        self, edge_node: str, analytics: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on analytics."""
        recommendations = []

        # Check metrics
        metrics = analytics.get("metrics_summary", {})

        # High latency
        if MetricType.LATENCY.value in metrics:
            latency = metrics[MetricType.LATENCY.value]
            if latency["p95"] > 1.0:
                recommendations.append(
                    f"Consider scaling {edge_node} - p95 latency is {latency['p95']:.2f}s"
                )

        # High error rate
        if MetricType.ERROR_RATE.value in metrics:
            error_rate = metrics[MetricType.ERROR_RATE.value]
            if error_rate["mean"] > 0.05:
                recommendations.append(
                    f"Investigate errors on {edge_node} - error rate is {error_rate['mean']*100:.1f}%"
                )

        # Resource usage
        if MetricType.RESOURCE_USAGE.value in metrics:
            resources = metrics[MetricType.RESOURCE_USAGE.value]
            if resources["p95"] > 0.8:
                recommendations.append(
                    f"Resource usage high on {edge_node} - consider scaling or optimization"
                )

        # Cache performance
        if MetricType.CACHE_HIT_RATE.value in metrics:
            cache = metrics[MetricType.CACHE_HIT_RATE.value]
            if cache["mean"] < 0.7:
                recommendations.append(
                    f"Low cache hit rate ({cache['mean']*100:.1f}%) - review caching strategy"
                )

        # Check trends
        trends = analytics.get("trends", {})

        for metric, trend in trends.items():
            if trend["direction"] == "increasing" and trend["change_percent"] > 20:
                if metric in [MetricType.LATENCY.value, MetricType.ERROR_RATE.value]:
                    recommendations.append(
                        f"{metric} increasing by {trend['change_percent']:.1f}% - investigate cause"
                    )

        return recommendations

    def set_threshold(self, metric_type: MetricType, severity: str, value: float):
        """Update alert threshold.

        Args:
            metric_type: Type of metric
            severity: Severity level (warning, error, critical)
            value: Threshold value
        """
        if metric_type not in self.alert_thresholds:
            self.alert_thresholds[metric_type] = {}

        self.alert_thresholds[metric_type][severity] = value

    def get_summary(self) -> Dict[str, Any]:
        """Get overall monitoring summary."""
        # Count nodes by health status
        health_counts = defaultdict(int)
        for health in self.health_status.values():
            health_counts[health.status.value] += 1

        # Recent alerts by severity
        recent_alerts = defaultdict(int)
        cutoff = datetime.now() - timedelta(hours=1)
        for alert in self.alerts:
            if alert.timestamp > cutoff:
                recent_alerts[alert.severity.value] += 1

        # Active nodes
        active_nodes = []
        cutoff = datetime.now() - timedelta(minutes=5)
        for node, metrics_dict in self.aggregated_metrics.items():
            if any(metrics_dict.values()):  # Has recent metrics
                active_nodes.append(node)

        return {
            "monitoring_active": self._running,
            "total_nodes": len(self.health_status),
            "active_nodes": len(active_nodes),
            "health_summary": dict(health_counts),
            "recent_alerts": dict(recent_alerts),
            "total_metrics": sum(len(m) for m in self.metrics.values()),
            "retention_period": self.retention_period,
            "anomaly_detection": self.anomaly_detection,
        }
