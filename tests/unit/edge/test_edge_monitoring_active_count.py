"""Regression tests for issue #1406 gap #1 — edge monitoring active_count.

The ``_get_alerts`` handler used ``len([a for a in alerts if active_only or True])``
to compute ``active_count``. The ``or True`` made the comprehension a no-op, so
``active_count`` always equalled the total alert count regardless of which alerts
were actually active. The fix introduces ``EdgeMonitor.is_alert_active`` (the
cooldown-window predicate, previously inline in ``get_alerts``) and computes
``active_count`` from it.
"""

from datetime import datetime, timedelta

import pytest

from kailash.edge.monitoring.edge_monitor import (
    AlertSeverity,
    EdgeAlert,
    EdgeMonitor,
    MetricType,
)
from kailash.nodes.edge.edge_monitoring_node import EdgeMonitoringNode


def _alert(edge_node: str, metric_type: MetricType, alert_id: str) -> EdgeAlert:
    return EdgeAlert(
        alert_id=alert_id,
        timestamp=datetime.now(),
        edge_node=edge_node,
        severity=AlertSeverity.WARNING,
        metric_type=metric_type,
        message="threshold exceeded",
        current_value=1.0,
        threshold=0.5,
    )


def test_is_alert_active_true_within_cooldown():
    monitor = EdgeMonitor(alert_cooldown=300)
    alert = _alert("n1", MetricType.LATENCY, "a1")
    monitor.alert_history["n1:latency"] = datetime.now()
    assert monitor.is_alert_active(alert) is True


def test_is_alert_active_false_outside_cooldown():
    monitor = EdgeMonitor(alert_cooldown=300)
    alert = _alert("n1", MetricType.LATENCY, "a1")
    monitor.alert_history["n1:latency"] = datetime.now() - timedelta(seconds=600)
    assert monitor.is_alert_active(alert) is False


def test_is_alert_active_false_without_history():
    monitor = EdgeMonitor(alert_cooldown=300)
    alert = _alert("n1", MetricType.LATENCY, "a1")
    # No alert_history entry for this key → not active.
    assert monitor.is_alert_active(alert) is False


@pytest.mark.regression
async def test_active_count_excludes_inactive_alerts():
    """active_count must count ONLY active alerts, not every alert.

    The pre-fix `or True` short-circuit made active_count == count
    unconditionally. With one active and one inactive alert returned,
    active_count MUST be 1, not 2.
    """
    node = EdgeMonitoringNode()

    active = _alert("n1", MetricType.LATENCY, "active")
    inactive = _alert("n2", MetricType.ERROR_RATE, "inactive")
    node.monitor.alerts = [active, inactive]
    node.monitor.alert_history["n1:latency"] = datetime.now()
    node.monitor.alert_history["n2:error_rate"] = datetime.now() - timedelta(
        seconds=10_000
    )

    result = await node._get_alerts({"active_only": False})

    assert result["count"] == 2
    assert result["active_count"] == 1


@pytest.mark.regression
async def test_active_count_zero_when_no_history():
    """When no alert has a live cooldown entry, active_count is 0 even though
    alerts are returned — the no-op filter would have reported the full count."""
    node = EdgeMonitoringNode()
    node.monitor.alerts = [
        _alert("n1", MetricType.LATENCY, "a1"),
        _alert("n2", MetricType.THROUGHPUT, "a2"),
    ]

    result = await node._get_alerts({"active_only": False})

    assert result["count"] == 2
    assert result["active_count"] == 0
