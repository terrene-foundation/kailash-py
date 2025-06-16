"""
Feature Test: Alert Aggregation and Batching Workflow
Tests intelligent alert batching, deduplication, and summary generation
"""

from kailash import Workflow
from kailash.nodes import PythonCodeNode
from kailash.nodes.alerts import DiscordAlertNode


def test_alert_aggregation_workflow():
    """Test aggregating multiple alerts into summary notifications"""

    workflow = Workflow(
        workflow_id="alert_aggregation_workflow", name="Alert Aggregation Workflow"
    )

    # Simulate multiple monitoring checks
    monitors = []
    for service in [
        "auth-service",
        "payment-api",
        "user-db",
        "cache-cluster",
        "queue-system",
    ]:
        monitor = PythonCodeNode.from_function(
            name=f"Monitor{service.replace('-', '_').title()}Node",
            func=lambda svc=service: {
                "service": svc,
                "status": (
                    "degraded" if svc in ["payment-api", "cache-cluster"] else "healthy"
                ),
                "response_time": 450 if svc == "payment-api" else 50,
                "error_rate": 5.2 if svc == "payment-api" else 0.1,
                "issues": (
                    ["High latency", "Connection timeouts"]
                    if svc == "payment-api"
                    else []
                ),
            },
            inputs=[],
            outputs=["service", "status", "response_time", "error_rate", "issues"],
        )
        workflow.add_node(f"monitor_{service}", monitor)
        monitors.append(monitor)

    # Aggregate all monitoring results
    aggregator = PythonCodeNode.from_function(
        name="AlertAggregatorNode",
        func=aggregate_monitoring_results,
        inputs=[f"result_{i}" for i in range(len(monitors))],
        outputs=[
            "summary",
            "alert_count",
            "services_affected",
            "should_alert",
            "severity",
        ],
    )
    workflow.add_node("aggregator", aggregator)

    # Connect monitors to aggregator
    for i, monitor in enumerate(monitors):
        service = [
            "auth-service",
            "payment-api",
            "user-db",
            "cache-cluster",
            "queue-system",
        ][i]
        workflow.connect(
            f"monitor_{service}",
            "aggregator",
            mapping={
                "service": f"result_{i}.service",
                "status": f"result_{i}.status",
                "response_time": f"result_{i}.response_time",
                "error_rate": f"result_{i}.error_rate",
                "issues": f"result_{i}.issues",
            },
        )

    # Send aggregated alert only if threshold met
    summary_alert = DiscordAlertNode(name="AggregatedSummaryAlertNode")
    workflow.add_node("summary_alert", summary_alert)
    workflow.connect(
        "aggregator",
        "summary_alert",
        mapping={
            "summary": "message",
            "alert_count": "context.alert_count",
            "services_affected": "context.services_affected",
            "should_alert": "context.should_alert",
            "severity": "context.severity",
        },
    )

    return workflow


def test_deduplication_workflow():
    """Test alert deduplication to prevent spam"""

    workflow = Workflow(
        workflow_id="alert_deduplication_workflow", name="Alert Deduplication Workflow"
    )

    # Generate stream of similar alerts
    alert_stream = PythonCodeNode.from_function(
        name="AlertStreamNode",
        func=lambda: [
            {
                "id": "ERR-001",
                "type": "connection_timeout",
                "source": "db-01",
                "count": 1,
            },
            {
                "id": "ERR-001",
                "type": "connection_timeout",
                "source": "db-01",
                "count": 2,
            },
            {
                "id": "ERR-001",
                "type": "connection_timeout",
                "source": "db-01",
                "count": 3,
            },
            {"id": "ERR-002", "type": "memory_high", "source": "app-03", "count": 1},
            {
                "id": "ERR-001",
                "type": "connection_timeout",
                "source": "db-01",
                "count": 4,
            },
        ],
        inputs=[],
        outputs=["alerts"],
    )
    workflow.add_node("alert_stream", alert_stream)

    # Deduplicate alerts
    deduplicator = PythonCodeNode.from_function(
        name="AlertDeduplicatorNode",
        func=deduplicate_alerts,
        inputs=["alerts"],
        outputs=["unique_alerts", "duplicate_counts", "dedup_summary"],
    )
    workflow.add_node("deduplicator", deduplicator)
    workflow.connect("alert_stream", "deduplicator", mapping={"alerts": "alerts"})

    # Send deduplicated alerts with occurrence count
    dedup_alert = DiscordAlertNode(name="DeduplicatedAlertNode")
    workflow.add_node("dedup_alert", dedup_alert)
    workflow.connect(
        "deduplicator",
        "dedup_alert",
        mapping={
            "unique_alerts": "context.unique_alerts",
            "duplicate_counts": "context.duplicate_counts",
            "dedup_summary": "message",
        },
    )

    return workflow


def test_smart_batching_workflow():
    """Test intelligent alert batching based on type and urgency"""

    workflow = Workflow(workflow_id="smart_alert_batching", name="Smart Alert Batching")

    # Generate various alert types
    alert_generator = PythonCodeNode.from_function(
        name="GenerateVariousAlertsNode",
        func=lambda: {
            "security_alerts": [
                {"type": "failed_login", "ip": "192.168.1.100", "attempts": 5},
                {"type": "failed_login", "ip": "192.168.1.101", "attempts": 3},
            ],
            "performance_alerts": [
                {"type": "slow_query", "query": "SELECT * FROM users", "time": "2.5s"},
                {"type": "high_cpu", "server": "web-01", "usage": "85%"},
            ],
            "business_alerts": [
                {"type": "low_inventory", "product": "SKU-123", "remaining": 10},
                {"type": "payment_failed", "order": "ORD-456", "amount": "$150"},
            ],
        },
        inputs=[],
        outputs=["security_alerts", "performance_alerts", "business_alerts"],
    )
    workflow.add_node("alert_generator", alert_generator)

    # Batch processor for each category
    batch_processor = PythonCodeNode.from_function(
        name="BatchProcessorNode",
        func=process_alert_batches,
        inputs=["security_alerts", "performance_alerts", "business_alerts"],
        outputs=["batched_alerts", "batch_priorities", "send_immediately"],
    )
    workflow.add_node("batch_processor", batch_processor)
    workflow.connect(
        "alert_generator",
        "batch_processor",
        mapping={
            "security_alerts": "security_alerts",
            "performance_alerts": "performance_alerts",
            "business_alerts": "business_alerts",
        },
    )

    # Immediate alerts for high priority
    immediate_alert = DiscordAlertNode(name="ImmediateAlertNode")
    workflow.add_node("immediate_alert", immediate_alert)
    workflow.connect(
        "batch_processor",
        "immediate_alert",
        mapping={"send_immediately": "context.send_immediately"},
    )

    # Batched alerts for lower priority
    # NOTE: WebhookAlertNode will be implemented in a future release
    # For now, using DiscordAlertNode for demonstration
    batched_alert = DiscordAlertNode(name="BatchedDiscordAlertNode")
    workflow.add_node("batched_alert", batched_alert)
    workflow.connect(
        "batch_processor",
        "batched_alert",
        mapping={
            "batched_alerts": "context",
            "batch_priorities": "context.priorities",
        },
    )

    return workflow


def test_periodic_digest_workflow():
    """Test periodic alert digest generation"""

    workflow = Workflow(
        workflow_id="periodic_alert_digest", name="Periodic Alert Digest"
    )

    # Collect alerts over time window
    alert_collector = PythonCodeNode.from_function(
        name="AlertCollectorNode",
        func=lambda: {
            "time_window": "Last 24 hours",
            "total_alerts": 142,
            "by_severity": {"critical": 3, "warning": 28, "info": 111},
            "by_service": {"api-gateway": 45, "database": 23, "cache": 18, "other": 56},
            "top_issues": [
                {"issue": "Connection timeouts", "count": 34},
                {"issue": "High memory usage", "count": 21},
                {"issue": "Slow queries", "count": 15},
            ],
            "trends": {"vs_yesterday": "+15%", "vs_last_week": "-5%"},
        },
        inputs=[],
        outputs=[
            "time_window",
            "total_alerts",
            "by_severity",
            "by_service",
            "top_issues",
            "trends",
        ],
    )
    workflow.add_node("alert_collector", alert_collector)

    # Generate digest report
    digest_generator = PythonCodeNode.from_function(
        name="DigestGeneratorNode",
        func=generate_alert_digest,
        inputs=[
            "time_window",
            "total_alerts",
            "by_severity",
            "by_service",
            "top_issues",
            "trends",
        ],
        outputs=["digest_html", "digest_summary", "chart_url"],
    )
    workflow.add_node("digest_generator", digest_generator)
    workflow.connect("alert_collector", "digest_generator")

    # Send digest via Discord
    digest_discord = DiscordAlertNode(name="DigestDiscordAlertNode")
    workflow.add_node("digest_discord", digest_discord)
    workflow.connect(
        "digest_generator",
        "digest_discord",
        mapping={
            "digest_summary": "message",
            "time_window": "context.time_window",
            "total_alerts": "context.total_alerts",
            "by_severity": "context.by_severity",
            "trends": "context.trends",
        },
    )

    return workflow


# Helper functions that would be implemented
def aggregate_monitoring_results(*results):
    """Aggregate monitoring results from multiple services"""
    issues = []
    affected = []

    for result in results:
        if result.get("status") != "healthy":
            affected.append(result["service"])
            issues.extend(result.get("issues", []))

    return {
        "summary": f"Found issues in {len(affected)} services: "
        + ", ".join(issues[:3]),
        "alert_count": len(issues),
        "services_affected": affected,
        "should_alert": len(affected) > 0,
        "severity": "critical" if len(affected) > 3 else "warning",
    }


def deduplicate_alerts(alerts):
    """Deduplicate alerts and count occurrences"""
    unique = {}
    for alert in alerts:
        key = f"{alert['type']}:{alert['source']}"
        if key not in unique:
            unique[key] = {"alert": alert, "count": 0}
        unique[key]["count"] += 1

    return {
        "unique_alerts": list(unique.keys()),
        "duplicate_counts": {k: v["count"] for k, v in unique.items()},
        "dedup_summary": f"Reduced {len(alerts)} alerts to {len(unique)} unique issues",
    }


def process_alert_batches(security_alerts, performance_alerts, business_alerts):
    """Process and batch alerts by priority"""
    immediate = []
    batched = []

    # Security alerts are high priority
    if len(security_alerts) > 3:
        immediate.extend(security_alerts)
    else:
        batched.extend(security_alerts)

    # Performance and business alerts are batched
    batched.extend(performance_alerts)
    batched.extend(business_alerts)

    return {
        "batched_alerts": batched,
        "batch_priorities": {
            "security": "high",
            "performance": "medium",
            "business": "low",
        },
        "send_immediately": immediate,
    }


def generate_alert_digest(
    time_window, total_alerts, by_severity, by_service, top_issues, trends
):
    """Generate alert digest report"""
    return {
        "digest_html": "<html>...</html>",  # Full HTML report
        "digest_summary": f"Total alerts: {total_alerts}. Top issue: {top_issues[0]['issue']}",
        "chart_url": "https://example.com/charts/alert-digest.png",
    }


def generate_dedup_fields(unique_alerts, counts):
    """Generate Discord fields for deduplicated alerts"""
    return [
        {"name": alert, "value": f"Occurred {counts[alert]} times", "inline": True}
        for alert in unique_alerts[:10]  # Limit to 10 fields
    ]


def format_immediate_alerts(alerts):
    """Format immediate alerts for Discord"""
    return [
        {
            "name": f"⚠️ {alert['type']}",
            "value": f"Source: {alert.get('ip', alert.get('source', 'Unknown'))}",
            "inline": False,
        }
        for alert in alerts[:5]
    ]


def validate_examples():
    """Validate that all examples create valid workflows"""

    examples = [
        ("Alert Aggregation", test_alert_aggregation_workflow),
        ("Alert Deduplication", test_deduplication_workflow),
        ("Smart Batching", test_smart_batching_workflow),
        ("Periodic Digest", test_periodic_digest_workflow),
    ]

    print("Alert Aggregation and Batching Examples Validation")
    print("=" * 50)

    for name, example_func in examples:
        try:
            workflow = example_func()
            print(f"✓ {name}: {len(workflow.nodes)} nodes")

            # Check for aggregation patterns
            has_aggregator = any("Aggregator" in node_id for node_id in workflow.nodes)
            has_batching = any("batch" in node_id.lower() for node_id in workflow.nodes)

            if has_aggregator:
                print("  - Has aggregation logic")
            if has_batching:
                print("  - Has batching configuration")

        except Exception as e:
            print(f"✗ {name}: Failed - {str(e)}")


if __name__ == "__main__":
    validate_examples()
