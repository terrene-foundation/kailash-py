"""
Streaming analytics and performance monitoring for A2A systems.

This module provides real-time streaming capabilities and performance dashboards
for monitoring A2A agent interactions, task execution, and system health.
"""

import asyncio
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set
from uuid import uuid4

from kailash.nodes.base import Node, NodeParameter, register_node


class MetricType(Enum):
    """Types of metrics that can be collected."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"
    RATE = "rate"


class AlertSeverity(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MetricValue:
    """A single metric value with timestamp."""

    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


@dataclass
class StreamEvent:
    """A streaming event in the A2A system."""

    event_id: str
    event_type: str
    source: str
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": self.metadata,
        }


@dataclass
class Alert:
    """System alert based on metrics."""

    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    timestamp: datetime
    metric_name: str
    metric_value: float
    threshold: float
    resolved: bool = False
    resolved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "alert_id": self.alert_id,
            "name": self.name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class MetricsCollector:
    """Collects and manages metrics for streaming analytics."""

    def __init__(self, max_retention_hours: int = 24):
        self.max_retention_hours = max_retention_hours
        self.metrics: Dict[str, List[MetricValue]] = defaultdict(list)
        self.metric_types: Dict[str, MetricType] = {}
        self.alert_rules: Dict[str, Dict[str, Any]] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self._lock = asyncio.Lock()

    async def record_metric(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Record a metric value."""
        async with self._lock:
            metric_value = MetricValue(
                value=value, timestamp=datetime.now(), labels=labels or {}
            )

            self.metrics[name].append(metric_value)
            self.metric_types[name] = metric_type

            # Clean up old metrics
            await self._cleanup_old_metrics(name)

            # Check alert rules
            await self._check_alert_rules(name, value)

    async def increment_counter(
        self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None
    ):
        """Increment a counter metric."""
        await self.record_metric(name, value, MetricType.COUNTER, labels)

    async def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ):
        """Set a gauge metric."""
        await self.record_metric(name, value, MetricType.GAUGE, labels)

    async def record_timer(
        self, name: str, duration: float, labels: Optional[Dict[str, str]] = None
    ):
        """Record a timer metric."""
        await self.record_metric(name, duration, MetricType.TIMER, labels)

    async def get_metric_values(
        self,
        name: str,
        since: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> List[MetricValue]:
        """Get metric values with optional filtering."""
        async with self._lock:
            values = self.metrics.get(name, [])

            if since:
                values = [v for v in values if v.timestamp >= since]

            if labels:
                values = [
                    v
                    for v in values
                    if all(v.labels.get(k) == val for k, val in labels.items())
                ]

            return values

    async def get_metric_stats(
        self, name: str, since: Optional[datetime] = None
    ) -> Dict[str, float]:
        """Get statistical summary of a metric."""
        values = await self.get_metric_values(name, since)

        if not values:
            return {}

        numeric_values = [v.value for v in values]

        return {
            "count": len(numeric_values),
            "min": min(numeric_values),
            "max": max(numeric_values),
            "mean": statistics.mean(numeric_values),
            "median": statistics.median(numeric_values),
            "stddev": (
                statistics.stdev(numeric_values) if len(numeric_values) > 1 else 0.0
            ),
            "sum": sum(numeric_values),
        }

    async def add_alert_rule(
        self,
        name: str,
        metric_name: str,
        threshold: float,
        condition: str = "greater_than",
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        message: str = "",
    ):
        """Add an alert rule."""
        self.alert_rules[name] = {
            "metric_name": metric_name,
            "threshold": threshold,
            "condition": condition,
            "severity": severity,
            "message": message or f"{metric_name} {condition} {threshold}",
        }

    async def _cleanup_old_metrics(self, name: str):
        """Clean up old metric values."""
        cutoff_time = datetime.now() - timedelta(hours=self.max_retention_hours)
        self.metrics[name] = [
            v for v in self.metrics[name] if v.timestamp >= cutoff_time
        ]

    async def _check_alert_rules(self, metric_name: str, value: float):
        """Check if metric value triggers any alerts."""
        for rule_name, rule in self.alert_rules.items():
            if rule["metric_name"] != metric_name:
                continue

            condition = rule["condition"]
            threshold = rule["threshold"]
            triggered = False

            if condition == "greater_than" and value > threshold:
                triggered = True
            elif condition == "less_than" and value < threshold:
                triggered = True
            elif condition == "equals" and value == threshold:
                triggered = True

            if triggered:
                await self._trigger_alert(rule_name, rule, value)
            else:
                await self._resolve_alert(rule_name)

    async def _trigger_alert(self, rule_name: str, rule: Dict[str, Any], value: float):
        """Trigger an alert."""
        if rule_name not in self.active_alerts:
            alert = Alert(
                alert_id=str(uuid4()),
                name=rule_name,
                severity=rule["severity"],
                message=rule["message"],
                timestamp=datetime.now(),
                metric_name=rule["metric_name"],
                metric_value=value,
                threshold=rule["threshold"],
            )
            self.active_alerts[rule_name] = alert

    async def _resolve_alert(self, rule_name: str):
        """Resolve an alert."""
        if rule_name in self.active_alerts:
            alert = self.active_alerts[rule_name]
            alert.resolved = True
            alert.resolved_at = datetime.now()
            # Keep resolved alerts for a bit, then clean up
            # In production, you might want to send to external system

    async def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts."""
        return [alert for alert in self.active_alerts.values() if not alert.resolved]

    async def get_all_metrics(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all metrics as serializable data."""
        result = {}
        async with self._lock:
            for name, values in self.metrics.items():
                result[name] = [v.to_dict() for v in values]
        return result


class EventStreamer:
    """Streams events from the A2A system."""

    def __init__(self, buffer_size: int = 1000):
        self.buffer_size = buffer_size
        self.event_buffer: deque = deque(maxlen=buffer_size)
        self.subscribers: Set[asyncio.Queue] = set()
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish_event(self, event: StreamEvent):
        """Publish an event to all subscribers."""
        async with self._lock:
            # Add to buffer
            self.event_buffer.append(event)

            # Notify subscribers
            dead_queues = set()
            for queue in self.subscribers:
                try:
                    await queue.put(event)
                except asyncio.QueueEmpty:
                    # Queue is full, subscriber is slow
                    dead_queues.add(queue)
                except Exception:
                    # Subscriber is dead
                    dead_queues.add(queue)

            # Clean up dead subscribers
            self.subscribers -= dead_queues

            # Call event handlers
            for handler in self.event_handlers.get(event.event_type, []):
                try:
                    await handler(event)
                except Exception:
                    # Log error but continue
                    pass

    async def subscribe(
        self, queue_size: int = 100
    ) -> AsyncGenerator[StreamEvent, None]:
        """Subscribe to event stream."""
        queue = asyncio.Queue(maxsize=queue_size)
        self.subscribers.add(queue)

        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            self.subscribers.discard(queue)
            raise
        except Exception:
            self.subscribers.discard(queue)
            raise

    async def add_event_handler(
        self, event_type: str, handler: Callable[[StreamEvent], None]
    ):
        """Add an event handler for a specific event type."""
        self.event_handlers[event_type].append(handler)

    async def get_recent_events(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> List[StreamEvent]:
        """Get recent events from the buffer."""
        async with self._lock:
            events = list(self.event_buffer)

            if event_type:
                events = [e for e in events if e.event_type == event_type]

            return events[-limit:]


class PerformanceDashboard:
    """Real-time performance dashboard for A2A system."""

    def __init__(
        self, metrics_collector: MetricsCollector, event_streamer: EventStreamer
    ):
        self.metrics_collector = metrics_collector
        self.event_streamer = event_streamer
        self.dashboard_data: Dict[str, Any] = {}
        self._update_interval = 5  # seconds
        self._update_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the dashboard update loop."""
        if self._update_task is None:
            self._update_task = asyncio.create_task(self._update_loop())

    async def stop(self):
        """Stop the dashboard update loop."""
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

    async def _update_loop(self):
        """Main update loop for dashboard data."""
        while True:
            try:
                await self._update_dashboard_data()
                await asyncio.sleep(self._update_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue
                await asyncio.sleep(self._update_interval)

    async def _update_dashboard_data(self):
        """Update dashboard data with current metrics."""
        now = datetime.now()
        last_hour = now - timedelta(hours=1)

        # Get key metrics
        task_stats = await self.metrics_collector.get_metric_stats(
            "tasks_completed", last_hour
        )
        agent_stats = await self.metrics_collector.get_metric_stats(
            "agent_utilization", last_hour
        )
        insight_stats = await self.metrics_collector.get_metric_stats(
            "insight_quality", last_hour
        )

        # Get recent events
        recent_events = await self.event_streamer.get_recent_events(limit=50)

        # Get active alerts
        active_alerts = await self.metrics_collector.get_active_alerts()

        # Update dashboard data
        self.dashboard_data = {
            "timestamp": now.isoformat(),
            "overview": {
                "total_tasks": task_stats.get("sum", 0),
                "average_agent_utilization": agent_stats.get("mean", 0.0),
                "average_insight_quality": insight_stats.get("mean", 0.0),
                "active_alerts": len(active_alerts),
            },
            "task_performance": {
                "completed_last_hour": task_stats.get("count", 0),
                "completion_rate": task_stats.get("mean", 0.0),
                "peak_completion_rate": task_stats.get("max", 0.0),
            },
            "agent_performance": {
                "average_utilization": agent_stats.get("mean", 0.0),
                "peak_utilization": agent_stats.get("max", 0.0),
                "utilization_stddev": agent_stats.get("stddev", 0.0),
            },
            "insight_quality": {
                "average_quality": insight_stats.get("mean", 0.0),
                "quality_trend": "stable",  # Could be calculated from historical data
                "quality_distribution": {
                    "high": 0,  # Could be calculated from raw data
                    "medium": 0,
                    "low": 0,
                },
            },
            "recent_events": [e.to_dict() for e in recent_events[-10:]],
            "active_alerts": [a.to_dict() for a in active_alerts],
            "system_health": {
                "status": "healthy" if len(active_alerts) == 0 else "degraded",
                "uptime": "99.9%",  # Could be calculated from metrics
                "last_updated": now.isoformat(),
            },
        }

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get current dashboard data."""
        return self.dashboard_data.copy()

    async def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics summary."""
        now = datetime.now()
        last_minute = now - timedelta(minutes=1)

        # Get very recent metrics
        recent_tasks = await self.metrics_collector.get_metric_values(
            "tasks_completed", last_minute
        )
        recent_insights = await self.metrics_collector.get_metric_values(
            "insight_quality", last_minute
        )

        return {
            "timestamp": now.isoformat(),
            "tasks_per_minute": len(recent_tasks),
            "average_insight_quality": (
                statistics.mean([v.value for v in recent_insights])
                if recent_insights
                else 0.0
            ),
            "active_agents": len(
                await self.metrics_collector.get_metric_values(
                    "agent_active", last_minute
                )
            ),
            "system_load": 0.0,  # Could be calculated from various metrics
        }


@register_node()
class StreamingAnalyticsNode(Node):
    """Node for streaming analytics and real-time monitoring."""

    def __init__(self, name: str = "streaming_analytics", **kwargs):
        """Initialize streaming analytics node."""
        self.action = "start_monitoring"
        self.metrics_config = None
        self.alert_rules = None
        self.dashboard_config = None
        self.buffer_size = 1000
        self.retention_hours = 24
        self.update_interval = 5

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Initialize components
        self.metrics_collector = MetricsCollector(
            max_retention_hours=self.retention_hours
        )
        self.event_streamer = EventStreamer(buffer_size=self.buffer_size)
        self.dashboard = PerformanceDashboard(
            self.metrics_collector, self.event_streamer
        )

        # Track if monitoring is active
        self._monitoring_active = False

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                required=False,
                default="start_monitoring",
                description="Action to perform: start_monitoring, stop_monitoring, get_metrics, get_dashboard",
            ),
            "metrics_config": NodeParameter(
                name="metrics_config",
                type=dict,
                required=False,
                description="Configuration for metrics collection",
            ),
            "alert_rules": NodeParameter(
                name="alert_rules",
                type=list,
                required=False,
                description="Alert rules configuration",
            ),
            "dashboard_config": NodeParameter(
                name="dashboard_config",
                type=dict,
                required=False,
                description="Dashboard configuration",
            ),
            "buffer_size": NodeParameter(
                name="buffer_size",
                type=int,
                required=False,
                default=1000,
                description="Event buffer size",
            ),
            "retention_hours": NodeParameter(
                name="retention_hours",
                type=int,
                required=False,
                default=24,
                description="Metric retention period in hours",
            ),
            "update_interval": NodeParameter(
                name="update_interval",
                type=int,
                required=False,
                default=5,
                description="Dashboard update interval in seconds",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Execute streaming analytics action."""
        # Get parameters
        action = kwargs.get("action", self.action)
        metrics_config = kwargs.get("metrics_config", self.metrics_config)
        alert_rules = kwargs.get("alert_rules", self.alert_rules)
        dashboard_config = kwargs.get("dashboard_config", self.dashboard_config)

        if action == "start_monitoring":
            return await self._start_monitoring(
                metrics_config, alert_rules, dashboard_config
            )
        elif action == "stop_monitoring":
            return await self._stop_monitoring()
        elif action == "get_metrics":
            return await self._get_metrics()
        elif action == "get_dashboard":
            return await self._get_dashboard()
        elif action == "record_metric":
            return await self._record_metric(kwargs)
        elif action == "publish_event":
            return await self._publish_event(kwargs)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _start_monitoring(
        self,
        metrics_config: Optional[Dict[str, Any]],
        alert_rules: Optional[List[Dict[str, Any]]],
        dashboard_config: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Start monitoring with configuration."""
        # Configure alert rules
        if alert_rules:
            for rule in alert_rules:
                await self.metrics_collector.add_alert_rule(
                    name=rule["name"],
                    metric_name=rule["metric_name"],
                    threshold=rule["threshold"],
                    condition=rule.get("condition", "greater_than"),
                    severity=AlertSeverity(rule.get("severity", "medium")),
                    message=rule.get("message", ""),
                )

        # Configure dashboard
        if dashboard_config:
            self.dashboard._update_interval = dashboard_config.get("update_interval", 5)

        # Start dashboard
        await self.dashboard.start()
        self._monitoring_active = True

        return {
            "success": True,
            "message": "Monitoring started",
            "monitoring_active": self._monitoring_active,
            "alert_rules_configured": len(alert_rules) if alert_rules else 0,
            "dashboard_update_interval": self.dashboard._update_interval,
        }

    async def _stop_monitoring(self) -> Dict[str, Any]:
        """Stop monitoring."""
        await self.dashboard.stop()
        self._monitoring_active = False

        return {
            "success": True,
            "message": "Monitoring stopped",
            "monitoring_active": self._monitoring_active,
        }

    async def _get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        all_metrics = await self.metrics_collector.get_all_metrics()
        active_alerts = await self.metrics_collector.get_active_alerts()

        return {
            "success": True,
            "metrics": all_metrics,
            "active_alerts": [a.to_dict() for a in active_alerts],
            "monitoring_active": self._monitoring_active,
        }

    async def _get_dashboard(self) -> Dict[str, Any]:
        """Get dashboard data."""
        dashboard_data = await self.dashboard.get_dashboard_data()
        real_time_metrics = await self.dashboard.get_real_time_metrics()

        return {
            "success": True,
            "dashboard": dashboard_data,
            "real_time": real_time_metrics,
            "monitoring_active": self._monitoring_active,
        }

    async def _record_metric(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Record a metric value."""
        metric_name = params.get("metric_name")
        metric_value = params.get("metric_value")
        metric_type = params.get("metric_type", "gauge")
        labels = params.get("labels", {})

        if not metric_name or metric_value is None:
            raise ValueError("metric_name and metric_value are required")

        await self.metrics_collector.record_metric(
            name=metric_name,
            value=float(metric_value),
            metric_type=MetricType(metric_type),
            labels=labels,
        )

        return {
            "success": True,
            "message": f"Recorded metric {metric_name} = {metric_value}",
            "metric_name": metric_name,
            "metric_value": metric_value,
        }

    async def _publish_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Publish a stream event."""
        event_type = params.get("event_type")
        source = params.get("source", "unknown")
        data = params.get("data", {})
        metadata = params.get("metadata", {})

        if not event_type:
            raise ValueError("event_type is required")

        event = StreamEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            source=source,
            timestamp=datetime.now(),
            data=data,
            metadata=metadata,
        )

        await self.event_streamer.publish_event(event)

        return {
            "success": True,
            "message": f"Published event {event_type}",
            "event_id": event.event_id,
            "event_type": event_type,
        }


@register_node()
class A2AMonitoringNode(Node):
    """Specialized monitoring node for A2A systems."""

    def __init__(self, name: str = "a2a_monitoring", **kwargs):
        """Initialize A2A monitoring node."""
        self.coordinator_node = None
        self.streaming_node = None
        self.monitoring_interval = 10
        self.enable_auto_alerts = True

        # Set attributes from kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

        super().__init__(name=name, **kwargs)

        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "coordinator_node": NodeParameter(
                name="coordinator_node",
                type=object,
                required=True,
                description="A2A coordinator node to monitor",
            ),
            "streaming_node": NodeParameter(
                name="streaming_node",
                type=object,
                required=True,
                description="Streaming analytics node",
            ),
            "monitoring_interval": NodeParameter(
                name="monitoring_interval",
                type=int,
                required=False,
                default=10,
                description="Monitoring interval in seconds",
            ),
            "enable_auto_alerts": NodeParameter(
                name="enable_auto_alerts",
                type=bool,
                required=False,
                default=True,
                description="Enable automatic alert generation",
            ),
        }

    async def run(self, **kwargs) -> Dict[str, Any]:
        """Start A2A monitoring."""
        # Get parameters
        coordinator_node = kwargs.get("coordinator_node", self.coordinator_node)
        streaming_node = kwargs.get("streaming_node", self.streaming_node)
        monitoring_interval = kwargs.get(
            "monitoring_interval", self.monitoring_interval
        )
        enable_auto_alerts = kwargs.get("enable_auto_alerts", self.enable_auto_alerts)

        if not coordinator_node or not streaming_node:
            raise ValueError("coordinator_node and streaming_node are required")

        # Set up monitoring
        self.coordinator_node = coordinator_node
        self.streaming_node = streaming_node
        self.monitoring_interval = monitoring_interval

        # Configure default alert rules for A2A
        if enable_auto_alerts:
            await self._setup_default_alerts()

        # Start monitoring task
        if self._monitoring_task is None:
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())

        return {
            "success": True,
            "message": "A2A monitoring started",
            "monitoring_interval": self.monitoring_interval,
            "auto_alerts_enabled": enable_auto_alerts,
        }

    async def _setup_default_alerts(self):
        """Set up default alert rules for A2A monitoring."""
        default_rules = [
            {
                "name": "high_task_failure_rate",
                "metric_name": "task_failure_rate",
                "threshold": 0.1,
                "condition": "greater_than",
                "severity": "high",
                "message": "Task failure rate is above 10%",
            },
            {
                "name": "low_agent_utilization",
                "metric_name": "agent_utilization",
                "threshold": 0.3,
                "condition": "less_than",
                "severity": "medium",
                "message": "Agent utilization is below 30%",
            },
            {
                "name": "low_insight_quality",
                "metric_name": "insight_quality",
                "threshold": 0.6,
                "condition": "less_than",
                "severity": "medium",
                "message": "Average insight quality is below 60%",
            },
            {
                "name": "high_response_time",
                "metric_name": "response_time",
                "threshold": 5000,  # 5 seconds
                "condition": "greater_than",
                "severity": "high",
                "message": "Response time is above 5 seconds",
            },
        ]

        for rule in default_rules:
            await self.streaming_node.metrics_collector.add_alert_rule(
                name=rule["name"],
                metric_name=rule["metric_name"],
                threshold=rule["threshold"],
                condition=rule["condition"],
                severity=AlertSeverity(rule["severity"]),
                message=rule["message"],
            )

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while True:
            try:
                await self._collect_a2a_metrics()
                await asyncio.sleep(self.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue monitoring
                await asyncio.sleep(self.monitoring_interval)

    async def _collect_a2a_metrics(self):
        """Collect metrics from A2A coordinator."""
        if not self.coordinator_node:
            return

        # Get current state from coordinator
        active_tasks = len(getattr(self.coordinator_node, "active_tasks", {}))
        completed_tasks = len(getattr(self.coordinator_node, "completed_tasks", []))
        registered_agents = len(getattr(self.coordinator_node, "registered_agents", {}))

        # Calculate metrics
        total_tasks = active_tasks + completed_tasks
        agent_utilization = active_tasks / max(registered_agents, 1)

        # Record metrics
        await self.streaming_node.metrics_collector.set_gauge(
            "active_tasks", active_tasks
        )
        await self.streaming_node.metrics_collector.set_gauge(
            "completed_tasks", completed_tasks
        )
        await self.streaming_node.metrics_collector.set_gauge(
            "registered_agents", registered_agents
        )
        await self.streaming_node.metrics_collector.set_gauge(
            "agent_utilization", agent_utilization
        )

        # Calculate insight quality if available
        if hasattr(self.coordinator_node, "completed_tasks"):
            completed_tasks_list = getattr(self.coordinator_node, "completed_tasks", [])
            if completed_tasks_list:
                quality_scores = []
                for task in completed_tasks_list[-10:]:  # Last 10 tasks
                    if hasattr(task, "current_quality_score"):
                        # Handle both real values and mock objects
                        score = task.current_quality_score
                        if isinstance(score, (int, float)):
                            quality_scores.append(score)

                if quality_scores:
                    avg_quality = sum(quality_scores) / len(quality_scores)
                    await self.streaming_node.metrics_collector.set_gauge(
                        "insight_quality", avg_quality
                    )

        # Publish monitoring event
        event = StreamEvent(
            event_id=str(uuid4()),
            event_type="a2a_metrics_collected",
            source="a2a_monitoring",
            timestamp=datetime.now(),
            data={
                "active_tasks": active_tasks,
                "completed_tasks": completed_tasks,
                "registered_agents": registered_agents,
                "agent_utilization": agent_utilization,
            },
        )

        await self.streaming_node.event_streamer.publish_event(event)

    async def stop_monitoring(self):
        """Stop monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
