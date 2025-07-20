"""Edge monitoring node for comprehensive edge observability.

This node integrates edge monitoring capabilities into workflows,
providing metrics collection, health monitoring, alerting, and analytics.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.edge.monitoring.edge_monitor import (
    AlertSeverity,
    EdgeMetric,
    EdgeMonitor,
    HealthStatus,
    MetricType,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class EdgeMonitoringNode(AsyncNode):
    """Node for edge monitoring and observability operations.

    This node provides comprehensive monitoring capabilities for edge nodes
    including metrics collection, health checks, alerting, and analytics.

    Example:
        >>> # Record a metric
        >>> result = await monitoring_node.execute_async(
        ...     operation="record_metric",
        ...     edge_node="edge-west-1",
        ...     metric_type="latency",
        ...     value=0.250,
        ...     tags={"region": "us-west", "service": "api"}
        ... )

        >>> # Get health status
        >>> result = await monitoring_node.execute_async(
        ...     operation="get_health",
        ...     edge_node="edge-west-1"
        ... )

        >>> # Query metrics
        >>> result = await monitoring_node.execute_async(
        ...     operation="query_metrics",
        ...     edge_node="edge-west-1",
        ...     metric_type="latency",
        ...     time_range_minutes=60
        ... )

        >>> # Get analytics
        >>> result = await monitoring_node.execute_async(
        ...     operation="get_analytics",
        ...     edge_node="edge-west-1"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize edge monitoring node."""
        super().__init__(**kwargs)

        # Extract configuration
        retention_period = kwargs.get("retention_period", 24 * 60 * 60)
        alert_cooldown = kwargs.get("alert_cooldown", 300)
        health_check_interval = kwargs.get("health_check_interval", 30)
        anomaly_detection = kwargs.get("anomaly_detection", True)

        # Initialize monitor
        self.monitor = EdgeMonitor(
            retention_period=retention_period,
            alert_cooldown=alert_cooldown,
            health_check_interval=health_check_interval,
            anomaly_detection=anomaly_detection,
        )

        self._monitor_started = False

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform (record_metric, query_metrics, get_health, get_alerts, get_analytics, set_threshold, get_summary, start_monitor, stop_monitor)",
            ),
            # For record_metric
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Edge node identifier",
            ),
            "metric_type": NodeParameter(
                name="metric_type",
                type=str,
                required=False,
                description="Type of metric (latency, throughput, error_rate, resource_usage, availability, cache_hit_rate)",
            ),
            "value": NodeParameter(
                name="value", type=float, required=False, description="Metric value"
            ),
            "tags": NodeParameter(
                name="tags",
                type=dict,
                required=False,
                default={},
                description="Metric tags for filtering",
            ),
            # For query_metrics
            "time_range_minutes": NodeParameter(
                name="time_range_minutes",
                type=int,
                required=False,
                default=60,
                description="Time range in minutes for queries",
            ),
            # For get_alerts
            "severity": NodeParameter(
                name="severity",
                type=str,
                required=False,
                description="Alert severity filter (info, warning, error, critical)",
            ),
            "active_only": NodeParameter(
                name="active_only",
                type=bool,
                required=False,
                default=False,
                description="Only return active alerts",
            ),
            # For set_threshold
            "threshold_value": NodeParameter(
                name="threshold_value",
                type=float,
                required=False,
                description="Threshold value to set",
            ),
            # Configuration
            "retention_period": NodeParameter(
                name="retention_period",
                type=int,
                required=False,
                default=24 * 60 * 60,
                description="Metrics retention period (seconds)",
            ),
            "alert_cooldown": NodeParameter(
                name="alert_cooldown",
                type=int,
                required=False,
                default=300,
                description="Alert cooldown period (seconds)",
            ),
            "health_check_interval": NodeParameter(
                name="health_check_interval",
                type=int,
                required=False,
                default=30,
                description="Health check interval (seconds)",
            ),
            "anomaly_detection": NodeParameter(
                name="anomaly_detection",
                type=bool,
                required=False,
                default=True,
                description="Enable anomaly detection",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "metrics": NodeParameter(
                name="metrics", type=list, required=False, description="List of metrics"
            ),
            "health": NodeParameter(
                name="health",
                type=dict,
                required=False,
                description="Health status information",
            ),
            "alerts": NodeParameter(
                name="alerts", type=list, required=False, description="List of alerts"
            ),
            "analytics": NodeParameter(
                name="analytics",
                type=dict,
                required=False,
                description="Analytics summary",
            ),
            "summary": NodeParameter(
                name="summary",
                type=dict,
                required=False,
                description="Overall monitoring summary",
            ),
            "metric_recorded": NodeParameter(
                name="metric_recorded",
                type=bool,
                required=False,
                description="Whether metric was recorded",
            ),
            "monitor_active": NodeParameter(
                name="monitor_active",
                type=bool,
                required=False,
                description="Whether monitor is active",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all node parameters for compatibility."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute monitoring operation."""
        operation = kwargs["operation"]

        try:
            if operation == "record_metric":
                return await self._record_metric(kwargs)
            elif operation == "query_metrics":
                return await self._query_metrics(kwargs)
            elif operation == "get_health":
                return await self._get_health(kwargs)
            elif operation == "get_alerts":
                return await self._get_alerts(kwargs)
            elif operation == "get_analytics":
                return await self._get_analytics(kwargs)
            elif operation == "set_threshold":
                return await self._set_threshold(kwargs)
            elif operation == "get_summary":
                return await self._get_summary()
            elif operation == "start_monitor":
                return await self._start_monitor()
            elif operation == "stop_monitor":
                return await self._stop_monitor()
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Edge monitoring operation failed: {str(e)}")
            return {"status": "error", "error": str(e)}

    async def _record_metric(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Record a metric."""
        # Create metric
        try:
            metric_type = MetricType(kwargs.get("metric_type", "latency"))
        except ValueError:
            metric_type = MetricType.LATENCY

        metric = EdgeMetric(
            timestamp=datetime.now(),
            edge_node=kwargs.get("edge_node", "unknown"),
            metric_type=metric_type,
            value=kwargs.get("value", 0.0),
            tags=kwargs.get("tags", {}),
        )

        # Record metric
        await self.monitor.record_metric(metric)

        return {
            "status": "success",
            "metric_recorded": True,
            "metric": metric.to_dict(),
        }

    async def _query_metrics(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Query metrics."""
        # Parse parameters
        edge_node = kwargs.get("edge_node")
        metric_type_str = kwargs.get("metric_type")
        time_range_minutes = kwargs.get("time_range_minutes", 60)
        tags = kwargs.get("tags")

        # Parse metric type
        metric_type = None
        if metric_type_str:
            try:
                metric_type = MetricType(metric_type_str)
            except ValueError:
                pass

        # Calculate time range
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=time_range_minutes)

        # Query metrics
        metrics = await self.monitor.get_metrics(
            edge_node=edge_node,
            metric_type=metric_type,
            start_time=start_time,
            end_time=end_time,
            tags=tags,
        )

        # Format results
        return {
            "status": "success",
            "metrics": [m.to_dict() for m in metrics],
            "count": len(metrics),
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        }

    async def _get_health(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get health status."""
        edge_node = kwargs.get("edge_node", "unknown")

        health = await self.monitor.get_edge_health(edge_node)

        return {"status": "success", "health": health.to_dict()}

    async def _get_alerts(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get alerts."""
        # Parse parameters
        edge_node = kwargs.get("edge_node")
        severity_str = kwargs.get("severity")
        active_only = kwargs.get("active_only", False)
        time_range_minutes = kwargs.get("time_range_minutes", 60)

        # Parse severity
        severity = None
        if severity_str:
            try:
                severity = AlertSeverity(severity_str)
            except ValueError:
                pass

        # Calculate time range
        start_time = datetime.now() - timedelta(minutes=time_range_minutes)

        # Get alerts
        alerts = await self.monitor.get_alerts(
            edge_node=edge_node,
            severity=severity,
            start_time=start_time,
            active_only=active_only,
        )

        # Format results
        return {
            "status": "success",
            "alerts": [a.to_dict() for a in alerts],
            "count": len(alerts),
            "active_count": len(
                [a for a in alerts if active_only or True]
            ),  # TODO: proper active check
        }

    async def _get_analytics(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Get analytics for an edge node."""
        edge_node = kwargs.get("edge_node", "unknown")

        analytics = self.monitor.get_analytics(edge_node)

        return {"status": "success", "analytics": analytics}

    async def _set_threshold(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Set alert threshold."""
        metric_type_str = kwargs.get("metric_type", "latency")
        severity = kwargs.get("severity", "warning")
        value = kwargs.get("threshold_value", 1.0)

        # Parse metric type
        try:
            metric_type = MetricType(metric_type_str)
        except ValueError:
            return {
                "status": "error",
                "error": f"Invalid metric type: {metric_type_str}",
            }

        # Set threshold
        self.monitor.set_threshold(metric_type, severity, value)

        return {
            "status": "success",
            "threshold_set": True,
            "metric_type": metric_type.value,
            "severity": severity,
            "value": value,
        }

    async def _get_summary(self) -> Dict[str, Any]:
        """Get monitoring summary."""
        summary = self.monitor.get_summary()

        return {"status": "success", "summary": summary}

    async def _start_monitor(self) -> Dict[str, Any]:
        """Start monitoring service."""
        if not self._monitor_started:
            await self.monitor.start()
            self._monitor_started = True

        return {"status": "success", "monitor_active": True}

    async def _stop_monitor(self) -> Dict[str, Any]:
        """Stop monitoring service."""
        if self._monitor_started:
            await self.monitor.stop()
            self._monitor_started = False

        return {"status": "success", "monitor_active": False}

    async def cleanup(self):
        """Clean up resources."""
        if self._monitor_started:
            await self.monitor.stop()
