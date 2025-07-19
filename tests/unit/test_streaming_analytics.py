"""
Unit tests for streaming analytics functionality.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from kailash.nodes.ai.streaming_analytics import (
    A2AMonitoringNode,
    Alert,
    AlertSeverity,
    EventStreamer,
    MetricsCollector,
    MetricType,
    MetricValue,
    PerformanceDashboard,
    StreamEvent,
    StreamingAnalyticsNode,
)


class TestMetricValue:
    """Test MetricValue functionality."""

    def test_metric_value_creation(self):
        """Test creating a metric value."""
        timestamp = datetime.now()
        metric = MetricValue(value=42.5, timestamp=timestamp, labels={"agent": "test"})

        assert metric.value == 42.5
        assert metric.timestamp == timestamp
        assert metric.labels["agent"] == "test"

    def test_metric_value_to_dict(self):
        """Test converting metric value to dict."""
        timestamp = datetime.now()
        metric = MetricValue(value=42.5, timestamp=timestamp, labels={"agent": "test"})

        data = metric.to_dict()

        assert data["value"] == 42.5
        assert data["timestamp"] == timestamp.isoformat()
        assert data["labels"]["agent"] == "test"


class TestStreamEvent:
    """Test StreamEvent functionality."""

    def test_stream_event_creation(self):
        """Test creating a stream event."""
        timestamp = datetime.now()
        event = StreamEvent(
            event_id="test-id",
            event_type="test_event",
            source="test_source",
            timestamp=timestamp,
            data={"key": "value"},
            metadata={"meta": "data"},
        )

        assert event.event_id == "test-id"
        assert event.event_type == "test_event"
        assert event.source == "test_source"
        assert event.timestamp == timestamp
        assert event.data["key"] == "value"
        assert event.metadata["meta"] == "data"

    def test_stream_event_to_dict(self):
        """Test converting stream event to dict."""
        timestamp = datetime.now()
        event = StreamEvent(
            event_id="test-id",
            event_type="test_event",
            source="test_source",
            timestamp=timestamp,
            data={"key": "value"},
        )

        data = event.to_dict()

        assert data["event_id"] == "test-id"
        assert data["event_type"] == "test_event"
        assert data["source"] == "test_source"
        assert data["timestamp"] == timestamp.isoformat()
        assert data["data"]["key"] == "value"


class TestAlert:
    """Test Alert functionality."""

    def test_alert_creation(self):
        """Test creating an alert."""
        timestamp = datetime.now()
        alert = Alert(
            alert_id="alert-id",
            name="test_alert",
            severity=AlertSeverity.HIGH,
            message="Test alert message",
            timestamp=timestamp,
            metric_name="test_metric",
            metric_value=100.0,
            threshold=50.0,
        )

        assert alert.alert_id == "alert-id"
        assert alert.name == "test_alert"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.message == "Test alert message"
        assert alert.metric_name == "test_metric"
        assert alert.metric_value == 100.0
        assert alert.threshold == 50.0
        assert alert.resolved is False

    def test_alert_to_dict(self):
        """Test converting alert to dict."""
        timestamp = datetime.now()
        alert = Alert(
            alert_id="alert-id",
            name="test_alert",
            severity=AlertSeverity.HIGH,
            message="Test alert message",
            timestamp=timestamp,
            metric_name="test_metric",
            metric_value=100.0,
            threshold=50.0,
        )

        data = alert.to_dict()

        assert data["alert_id"] == "alert-id"
        assert data["name"] == "test_alert"
        assert data["severity"] == "high"
        assert data["message"] == "Test alert message"
        assert data["metric_name"] == "test_metric"
        assert data["metric_value"] == 100.0
        assert data["threshold"] == 50.0
        assert data["resolved"] is False


class TestMetricsCollector:
    """Test MetricsCollector functionality."""

    @pytest.mark.asyncio
    async def test_record_metric(self):
        """Test recording a metric."""
        collector = MetricsCollector(max_retention_hours=1)

        await collector.record_metric("test_metric", 42.5, MetricType.GAUGE)

        values = await collector.get_metric_values("test_metric")
        assert len(values) == 1
        assert values[0].value == 42.5
        assert collector.metric_types["test_metric"] == MetricType.GAUGE

    @pytest.mark.asyncio
    async def test_increment_counter(self):
        """Test incrementing a counter."""
        collector = MetricsCollector()

        await collector.increment_counter("requests", 1.0)
        await collector.increment_counter("requests", 2.0)

        values = await collector.get_metric_values("requests")
        assert len(values) == 2
        assert values[0].value == 1.0
        assert values[1].value == 2.0

    @pytest.mark.asyncio
    async def test_set_gauge(self):
        """Test setting a gauge metric."""
        collector = MetricsCollector()

        await collector.set_gauge("temperature", 23.5)

        values = await collector.get_metric_values("temperature")
        assert len(values) == 1
        assert values[0].value == 23.5

    @pytest.mark.asyncio
    async def test_record_timer(self):
        """Test recording a timer metric."""
        collector = MetricsCollector()

        await collector.record_timer("response_time", 150.0)

        values = await collector.get_metric_values("response_time")
        assert len(values) == 1
        assert values[0].value == 150.0
        assert collector.metric_types["response_time"] == MetricType.TIMER

    @pytest.mark.asyncio
    async def test_get_metric_stats(self):
        """Test getting metric statistics."""
        collector = MetricsCollector()

        # Record multiple values
        await collector.record_metric("test_metric", 10.0)
        await collector.record_metric("test_metric", 20.0)
        await collector.record_metric("test_metric", 30.0)

        stats = await collector.get_metric_stats("test_metric")

        assert stats["count"] == 3
        assert stats["min"] == 10.0
        assert stats["max"] == 30.0
        assert stats["mean"] == 20.0
        assert stats["median"] == 20.0
        assert stats["sum"] == 60.0

    @pytest.mark.asyncio
    async def test_get_metric_values_with_labels(self):
        """Test getting metric values with label filtering."""
        collector = MetricsCollector()

        await collector.record_metric("requests", 1.0, labels={"method": "GET"})
        await collector.record_metric("requests", 2.0, labels={"method": "POST"})

        get_values = await collector.get_metric_values(
            "requests", labels={"method": "GET"}
        )
        assert len(get_values) == 1
        assert get_values[0].value == 1.0

        post_values = await collector.get_metric_values(
            "requests", labels={"method": "POST"}
        )
        assert len(post_values) == 1
        assert post_values[0].value == 2.0

    @pytest.mark.asyncio
    async def test_alert_rules(self):
        """Test alert rule functionality."""
        collector = MetricsCollector()

        # Add alert rule
        await collector.add_alert_rule(
            name="high_cpu",
            metric_name="cpu_usage",
            threshold=80.0,
            condition="greater_than",
            severity=AlertSeverity.HIGH,
            message="CPU usage is too high",
        )

        # Record value below threshold
        await collector.record_metric("cpu_usage", 70.0)
        active_alerts = await collector.get_active_alerts()
        assert len(active_alerts) == 0

        # Record value above threshold
        await collector.record_metric("cpu_usage", 90.0)
        active_alerts = await collector.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].name == "high_cpu"
        assert active_alerts[0].metric_value == 90.0

        # Record value below threshold again
        await collector.record_metric("cpu_usage", 60.0)
        active_alerts = await collector.get_active_alerts()
        assert len(active_alerts) == 0  # Alert should be resolved

    @pytest.mark.asyncio
    async def test_get_all_metrics(self):
        """Test getting all metrics."""
        collector = MetricsCollector()

        await collector.record_metric("metric1", 10.0)
        await collector.record_metric("metric2", 20.0)

        all_metrics = await collector.get_all_metrics()

        assert "metric1" in all_metrics
        assert "metric2" in all_metrics
        assert len(all_metrics["metric1"]) == 1
        assert len(all_metrics["metric2"]) == 1
        assert all_metrics["metric1"][0]["value"] == 10.0
        assert all_metrics["metric2"][0]["value"] == 20.0


class TestEventStreamer:
    """Test EventStreamer functionality."""

    @pytest.mark.asyncio
    async def test_publish_event(self):
        """Test publishing an event."""
        streamer = EventStreamer(buffer_size=10)

        event = StreamEvent(
            event_id="test-id",
            event_type="test_event",
            source="test",
            timestamp=datetime.now(),
            data={"key": "value"},
        )

        await streamer.publish_event(event)

        recent_events = await streamer.get_recent_events()
        assert len(recent_events) == 1
        assert recent_events[0].event_id == "test-id"

    @pytest.mark.asyncio
    async def test_event_subscription(self):
        """Test event subscription."""
        streamer = EventStreamer(buffer_size=10)

        # Start subscription
        received_events = []

        async def collect_events():
            async for event in streamer.subscribe(queue_size=5):
                received_events.append(event)
                if len(received_events) >= 2:
                    break

        # Start collection task
        collection_task = asyncio.create_task(collect_events())

        # Wait a bit to ensure subscriber is ready
        await asyncio.sleep(0.01)

        # Publish events
        for i in range(2):
            event = StreamEvent(
                event_id=f"event-{i}",
                event_type="test_event",
                source="test",
                timestamp=datetime.now(),
                data={"index": i},
            )
            await streamer.publish_event(event)

        # Wait for collection to complete
        await asyncio.wait_for(collection_task, timeout=1.0)

        assert len(received_events) == 2
        assert received_events[0].event_id == "event-0"
        assert received_events[1].event_id == "event-1"

    @pytest.mark.asyncio
    async def test_event_handlers(self):
        """Test event handlers."""
        streamer = EventStreamer()

        handled_events = []

        async def event_handler(event):
            handled_events.append(event)

        await streamer.add_event_handler("test_event", event_handler)

        event = StreamEvent(
            event_id="test-id",
            event_type="test_event",
            source="test",
            timestamp=datetime.now(),
            data={},
        )

        await streamer.publish_event(event)

        assert len(handled_events) == 1
        assert handled_events[0].event_id == "test-id"

    @pytest.mark.asyncio
    async def test_get_recent_events_with_filter(self):
        """Test getting recent events with type filter."""
        streamer = EventStreamer(buffer_size=10)

        # Publish different types of events
        for i in range(3):
            event = StreamEvent(
                event_id=f"event-{i}",
                event_type="type_a" if i % 2 == 0 else "type_b",
                source="test",
                timestamp=datetime.now(),
                data={"index": i},
            )
            await streamer.publish_event(event)

        all_events = await streamer.get_recent_events()
        assert len(all_events) == 3

        type_a_events = await streamer.get_recent_events(event_type="type_a")
        assert len(type_a_events) == 2

        type_b_events = await streamer.get_recent_events(event_type="type_b")
        assert len(type_b_events) == 1


class TestPerformanceDashboard:
    """Test PerformanceDashboard functionality."""

    @pytest.mark.asyncio
    async def test_dashboard_creation(self):
        """Test creating a performance dashboard."""
        collector = MetricsCollector()
        streamer = EventStreamer()
        dashboard = PerformanceDashboard(collector, streamer)

        assert dashboard.metrics_collector == collector
        assert dashboard.event_streamer == streamer
        assert dashboard._update_task is None

    @pytest.mark.asyncio
    async def test_dashboard_start_stop(self):
        """Test starting and stopping the dashboard."""
        collector = MetricsCollector()
        streamer = EventStreamer()
        dashboard = PerformanceDashboard(collector, streamer)

        # Start dashboard
        await dashboard.start()
        assert dashboard._update_task is not None

        # Stop dashboard
        await dashboard.stop()
        assert dashboard._update_task is None

    @pytest.mark.asyncio
    async def test_get_dashboard_data(self):
        """Test getting dashboard data."""
        collector = MetricsCollector()
        streamer = EventStreamer()
        dashboard = PerformanceDashboard(collector, streamer)

        # Record some metrics
        await collector.record_metric("tasks_completed", 5.0)
        await collector.record_metric("agent_utilization", 0.8)
        await collector.record_metric("insight_quality", 0.9)

        # Update dashboard data
        await dashboard._update_dashboard_data()

        data = await dashboard.get_dashboard_data()

        assert "timestamp" in data
        assert "overview" in data
        assert "task_performance" in data
        assert "agent_performance" in data
        assert "insight_quality" in data
        assert "system_health" in data

    @pytest.mark.asyncio
    async def test_get_real_time_metrics(self):
        """Test getting real-time metrics."""
        collector = MetricsCollector()
        streamer = EventStreamer()
        dashboard = PerformanceDashboard(collector, streamer)

        # Record recent metrics
        await collector.record_metric("tasks_completed", 3.0)
        await collector.record_metric("insight_quality", 0.85)
        await collector.record_metric("agent_active", 1.0)

        real_time = await dashboard.get_real_time_metrics()

        assert "timestamp" in real_time
        assert "tasks_per_minute" in real_time
        assert "average_insight_quality" in real_time
        assert "active_agents" in real_time
        assert "system_load" in real_time


class TestStreamingAnalyticsNode:
    """Test StreamingAnalyticsNode functionality."""

    @pytest.mark.asyncio
    async def test_start_monitoring(self):
        """Test starting monitoring."""
        node = StreamingAnalyticsNode(name="test_analytics")

        result = await node.run(
            action="start_monitoring",
            alert_rules=[
                {
                    "name": "test_alert",
                    "metric_name": "test_metric",
                    "threshold": 10.0,
                    "severity": "high",
                }
            ],
        )

        assert result["success"] is True
        assert result["monitoring_active"] is True
        assert result["alert_rules_configured"] == 1

        # Stop monitoring
        await node.run(action="stop_monitoring")

    @pytest.mark.asyncio
    async def test_record_metric(self):
        """Test recording a metric."""
        node = StreamingAnalyticsNode(name="test_analytics")

        result = await node.run(
            action="record_metric",
            metric_name="test_metric",
            metric_value=42.5,
            metric_type="gauge",
        )

        assert result["success"] is True
        assert result["metric_name"] == "test_metric"
        assert result["metric_value"] == 42.5

    @pytest.mark.asyncio
    async def test_publish_event(self):
        """Test publishing an event."""
        node = StreamingAnalyticsNode(name="test_analytics")

        result = await node.run(
            action="publish_event",
            event_type="test_event",
            source="test_source",
            data={"key": "value"},
        )

        assert result["success"] is True
        assert result["event_type"] == "test_event"
        assert "event_id" in result

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting metrics."""
        node = StreamingAnalyticsNode(name="test_analytics")

        # Record a metric first
        await node.run(
            action="record_metric", metric_name="test_metric", metric_value=42.5
        )

        result = await node.run(action="get_metrics")

        assert result["success"] is True
        assert "metrics" in result
        assert "active_alerts" in result
        assert "monitoring_active" in result
        assert "test_metric" in result["metrics"]

    @pytest.mark.asyncio
    async def test_get_dashboard(self):
        """Test getting dashboard data."""
        node = StreamingAnalyticsNode(name="test_analytics")

        result = await node.run(action="get_dashboard")

        assert result["success"] is True
        assert "dashboard" in result
        assert "real_time" in result
        assert "monitoring_active" in result

    @pytest.mark.asyncio
    async def test_invalid_action(self):
        """Test invalid action."""
        node = StreamingAnalyticsNode(name="test_analytics")

        with pytest.raises(ValueError, match="Unknown action"):
            await node.run(action="invalid_action")

    def test_get_parameters(self):
        """Test getting node parameters."""
        node = StreamingAnalyticsNode(name="test_analytics")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "action" in param_names
        assert "metrics_config" in param_names
        assert "alert_rules" in param_names
        assert "dashboard_config" in param_names
        assert "buffer_size" in param_names
        assert "retention_hours" in param_names
        assert "update_interval" in param_names


class TestA2AMonitoringNode:
    """Test A2AMonitoringNode functionality."""

    @pytest.mark.asyncio
    async def test_a2a_monitoring_start(self):
        """Test starting A2A monitoring."""
        # Create mock coordinator and streaming nodes
        coordinator_node = Mock()
        coordinator_node.active_tasks = {}
        coordinator_node.completed_tasks = []
        coordinator_node.registered_agents = {}

        streaming_node = Mock()
        streaming_node.metrics_collector = MetricsCollector()
        streaming_node.event_streamer = EventStreamer()

        node = A2AMonitoringNode(name="test_a2a_monitoring")

        result = await node.run(
            coordinator_node=coordinator_node,
            streaming_node=streaming_node,
            monitoring_interval=5,
            enable_auto_alerts=True,
        )

        assert result["success"] is True
        assert result["monitoring_interval"] == 5
        assert result["auto_alerts_enabled"] is True

        # Stop monitoring
        await node.stop_monitoring()

    @pytest.mark.asyncio
    async def test_a2a_monitoring_collect_metrics(self):
        """Test collecting A2A metrics."""
        # Create mock coordinator
        coordinator_node = Mock()
        coordinator_node.active_tasks = {"task1": Mock(), "task2": Mock()}

        # Create mock tasks with quality scores
        task1 = Mock()
        task1.current_quality_score = 0.8
        task2 = Mock()
        task2.current_quality_score = 0.9
        task3 = Mock()
        task3.current_quality_score = 0.7

        coordinator_node.completed_tasks = [task1, task2, task3]
        coordinator_node.registered_agents = {"agent1": Mock(), "agent2": Mock()}

        streaming_node = Mock()
        streaming_node.metrics_collector = MetricsCollector()
        streaming_node.event_streamer = EventStreamer()

        node = A2AMonitoringNode(name="test_a2a_monitoring")
        node.coordinator_node = coordinator_node
        node.streaming_node = streaming_node

        # Collect metrics
        await node._collect_a2a_metrics()

        # Check that metrics were recorded
        active_tasks = await streaming_node.metrics_collector.get_metric_values(
            "active_tasks"
        )
        assert len(active_tasks) == 1
        assert active_tasks[0].value == 2

        completed_tasks = await streaming_node.metrics_collector.get_metric_values(
            "completed_tasks"
        )
        assert len(completed_tasks) == 1
        assert completed_tasks[0].value == 3

        registered_agents = await streaming_node.metrics_collector.get_metric_values(
            "registered_agents"
        )
        assert len(registered_agents) == 1
        assert registered_agents[0].value == 2

        agent_utilization = await streaming_node.metrics_collector.get_metric_values(
            "agent_utilization"
        )
        assert len(agent_utilization) == 1
        assert agent_utilization[0].value == 1.0  # 2 active tasks / 2 agents

    @pytest.mark.asyncio
    async def test_a2a_monitoring_missing_parameters(self):
        """Test error when required parameters are missing."""
        node = A2AMonitoringNode(name="test_a2a_monitoring")

        with pytest.raises(
            ValueError, match="coordinator_node and streaming_node are required"
        ):
            await node.run()

    def test_get_parameters(self):
        """Test getting A2A monitoring node parameters."""
        node = A2AMonitoringNode(name="test_a2a_monitoring")
        parameters = node.get_parameters()

        param_names = list(parameters.keys())
        assert "coordinator_node" in param_names
        assert "streaming_node" in param_names
        assert "monitoring_interval" in param_names
        assert "enable_auto_alerts" in param_names
