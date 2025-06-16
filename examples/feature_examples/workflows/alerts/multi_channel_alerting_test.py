"""
Feature Test: Multi-Channel Alert Routing Workflow with Discord
Tests intelligent alert routing based on severity, time, and business rules
"""

from kailash import Workflow
from kailash.nodes import PythonCodeNode
from kailash.nodes.alerts import DiscordAlertNode
from kailash.nodes.transform import FilterNode


def test_severity_based_routing():
    """Test routing alerts to different Discord channels based on severity"""

    workflow = Workflow(workflow_id="severity_based_alert_routing")

    # Generate alerts with different severities
    alert_generator = PythonCodeNode.from_function(
        name="GenerateAlertsNode",
        func=lambda: [
            {
                "id": "ALT-001",
                "severity": "critical",
                "title": "Database connection lost",
                "message": "Primary database unreachable",
                "timestamp": "2024-01-13T10:30:00Z",
            },
            {
                "id": "ALT-002",
                "severity": "warning",
                "title": "High memory usage",
                "message": "Memory usage at 85%",
                "timestamp": "2024-01-13T10:31:00Z",
            },
            {
                "id": "ALT-003",
                "severity": "info",
                "title": "Backup completed",
                "message": "Daily backup successful",
                "timestamp": "2024-01-13T10:32:00Z",
            },
        ],
        inputs=[],
        outputs=["alerts"],
    )
    workflow.add_node("alert_generator", alert_generator)

    # Route critical alerts to Discord with @everyone mention
    critical_filter = FilterNode(
        name="CriticalFilterNode", filter_expression="alert['severity'] == 'critical'"
    )
    workflow.add_node(critical_filter)
    workflow.connect(alert_generator, critical_filter, mapping={"alerts": "items"})

    critical_discord = DiscordAlertNode(name="CriticalDiscordAlertNode")
    workflow.add_node(critical_discord)
    workflow.connect(
        critical_filter, critical_discord, mapping={"filtered_items": "alerts"}
    )

    # Route warnings to Discord warnings channel
    warning_filter = FilterNode(
        name="WarningFilterNode", filter_expression="alert['severity'] == 'warning'"
    )
    workflow.add_node(warning_filter)
    workflow.connect(alert_generator, warning_filter, mapping={"alerts": "items"})

    warning_discord = DiscordAlertNode(name="WarningDiscordAlertNode")
    workflow.add_node(warning_discord)
    workflow.connect(
        warning_filter, warning_discord, mapping={"filtered_items": "alerts"}
    )

    # Route info alerts to Discord info channel
    info_filter = FilterNode(
        name="InfoFilterNode", filter_expression="alert['severity'] == 'info'"
    )
    workflow.add_node(info_filter)
    workflow.connect(alert_generator, info_filter, mapping={"alerts": "items"})

    info_discord = DiscordAlertNode(name="InfoDiscordAlertNode")
    workflow.add_node(info_discord)
    workflow.connect(info_filter, info_discord, mapping={"filtered_items": "alerts"})

    return workflow


def test_time_based_routing():
    """Test routing alerts to different Discord channels based on time"""

    workflow = Workflow(workflow_id="time_based_alert_routing")

    # Check current time and generate alert
    time_checker = PythonCodeNode.from_function(
        name="TimeCheckerNode",
        func=lambda: {
            "current_hour": 22,  # 10 PM
            "is_business_hours": False,
            "is_weekend": False,
            "alert": {
                "title": "Server maintenance required",
                "message": "Non-critical updates available",
                "severity": "medium",
            },
        },
        inputs=[],
        outputs=["current_hour", "is_business_hours", "is_weekend", "alert"],
    )
    workflow.add_node(time_checker)

    # During business hours: Send to ops Discord channel
    business_hours_discord = DiscordAlertNode(name="BusinessHoursDiscordNode")
    workflow.add_node(business_hours_discord)
    workflow.connect(
        time_checker,
        business_hours_discord,
        mapping={"alert": "context", "is_business_hours": "context.is_business_hours"},
    )

    # After hours: Send to on-call Discord channel
    after_hours_discord = DiscordAlertNode(name="AfterHoursDiscordNode")
    workflow.add_node(after_hours_discord)
    workflow.connect(
        time_checker,
        after_hours_discord,
        mapping={
            "alert": "context",
            "is_business_hours": "context.is_business_hours",
            "current_hour": "context.current_hour",
        },
    )

    # Weekend: Send to weekend Discord channel
    weekend_discord = DiscordAlertNode(name="WeekendDiscordNode")
    workflow.add_node(weekend_discord)
    workflow.connect(
        time_checker,
        weekend_discord,
        mapping={"alert": "context", "is_weekend": "context.is_weekend"},
    )

    return workflow


def test_escalation_chain():
    """Test alert escalation through multiple Discord channels"""

    workflow = Workflow(workflow_id="alert_escalation_chain")

    # Initial incident detection
    incident_detector = PythonCodeNode.from_function(
        name="IncidentDetectorNode",
        func=lambda: {
            "incident_id": "INC-2024-001",
            "type": "API Gateway Down",
            "impact": "All external API calls failing",
            "start_time": "2024-01-13T10:00:00Z",
            "escalation_level": 0,
        },
        inputs=[],
        outputs=["incident_id", "type", "impact", "start_time", "escalation_level"],
    )
    workflow.add_node(incident_detector)

    # Level 0: Discord notification to ops channel
    level0_discord = DiscordAlertNode(name="Level0DiscordNode")
    workflow.add_node(level0_discord)
    workflow.connect(
        incident_detector,
        level0_discord,
        mapping={
            "incident_id": "context.incident_id",
            "type": "title",
            "impact": "message",
            "escalation_level": "context.escalation_level",
        },
    )

    # Wait for response and escalate if needed
    response_checker = PythonCodeNode.from_function(
        name="ResponseCheckerNode",
        func=lambda incident_id, escalation_level: {
            "acknowledged": False,  # Simulate no acknowledgment
            "elapsed_minutes": 10,
            "escalation_level": escalation_level + 1 if not False else escalation_level,
        },
        inputs=["incident_id", "escalation_level"],
        outputs=["acknowledged", "elapsed_minutes", "escalation_level"],
    )
    workflow.add_node(response_checker)
    workflow.connect(
        level0_discord,
        response_checker,
        mapping={"incident_id": "incident_id", "escalation_level": "escalation_level"},
    )

    # Level 1: Discord ping to on-call channel
    level1_discord = DiscordAlertNode(name="Level1DiscordNode")
    workflow.add_node(level1_discord)
    workflow.connect(
        response_checker,
        level1_discord,
        mapping={
            "type": "title",
            "elapsed_minutes": "context.elapsed_minutes",
            "incident_id": "context.incident_id",
            "escalation_level": "context.escalation_level",
            "acknowledged": "context.acknowledged",
        },
    )

    # Level 2: Discord alert to management channel
    level2_discord = DiscordAlertNode(name="Level2DiscordNode")
    workflow.add_node(level2_discord)
    workflow.connect(
        level1_discord,
        level2_discord,
        mapping={
            "incident_id": "context.incident_id",
            "type": "context.type",
            "impact": "context.impact",
            "elapsed_minutes": "context.elapsed_minutes",
            "escalation_level": "context.escalation_level",
            "acknowledged": "context.acknowledged",
        },
    )

    return workflow


def validate_examples():
    """Validate that all examples create valid workflows"""

    examples = [
        ("Severity Based Routing", test_severity_based_routing),
        ("Time Based Routing", test_time_based_routing),
        ("Escalation Chain", test_escalation_chain),
    ]

    print("Discord Alert Routing Examples Validation")
    print("=" * 50)

    for name, example_func in examples:
        try:
            workflow = example_func()
            # Count alert nodes by type
            alert_types = {}
            for node in workflow.nodes:
                if "Alert" in node.name:
                    node_type = node.__class__.__name__
                    alert_types[node_type] = alert_types.get(node_type, 0) + 1

            print(f"✓ {name}: {len(workflow.nodes)} nodes")
            for alert_type, count in alert_types.items():
                print(f"  - {count} {alert_type}")
        except Exception as e:
            print(f"✗ {name}: Failed - {str(e)}")


if __name__ == "__main__":
    validate_examples()
