"""Integration tests for Discord alerts with real webhook.

⚠️  WARNING: These tests send real messages to your Discord channel!

To run these tests:
1. Set DISCORD_TEST_WEBHOOK environment variable to a valid webhook URL
2. Run: pytest tests/integration/nodes/test_discord_alert_integration.py -v

Note: These tests are skipped by default to prevent accidental messages.
"""

import asyncio
import os
from datetime import datetime
from typing import Dict
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.ai.a2a import A2AAgentNode
from kailash.nodes.alerts.discord import DiscordAlertNode
from kailash.nodes.base import NodeParameter
from kailash.nodes.code.python import PythonCodeNode
from kailash.nodes.data.readers import CSVReaderNode, JSONReaderNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("DISCORD_TEST_WEBHOOK"),
    reason="DISCORD_TEST_WEBHOOK environment variable not set",
)
class TestDiscordAlertIntegration:
    """Integration tests for Discord alerts with real webhook.

    ⚠️  WARNING: These tests send real messages to your Discord channel!

    To run these tests:
    1. Set DISCORD_TEST_WEBHOOK environment variable to a valid webhook URL
    2. Run: pytest tests/integration/nodes/test_discord_alert_integration.py -v

    Note: These tests are skipped by default to prevent accidental messages.
    """

    @pytest.fixture
    def webhook_url(self) -> str:
        """Get Discord webhook URL from environment or use mock."""
        real_webhook = os.getenv("DISCORD_TEST_WEBHOOK")
        if real_webhook:
            return real_webhook
        else:
            # Use a mock webhook URL for testing when real one isn't available
            return "https://discord.com/api/webhooks/123456789/mock-webhook-for-testing"

    def test_simple_alert(self, webhook_url: str):
        """Test sending a simple alert to Discord."""
        # Create node
        node = DiscordAlertNode(name="discord_test")

        # Execute
        result = node.execute(
            webhook_url=webhook_url,
            title="Test Alert",
            message="Hello from integration test!",
            alert_type="info",
        )

        # Verify based on actual return fields from DiscordAlertNode
        assert result["success"] is True
        assert result["alert_type"] == "info"
        assert result["title"] == "Test Alert"
        assert "webhook_url" in result
        assert "status_code" in result

    def test_workflow_with_alert(self, webhook_url: str):
        """Test Discord alert in a workflow context."""

        self._run_workflow_test(webhook_url)

    def _run_workflow_test(self, webhook_url: str):
        """Helper method to run the actual workflow test."""
        # Build workflow
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node(
            "PythonCodeNode",
            "generate_data",
            config={
                "code": """
import random
from datetime import datetime
metrics = {
    'cpu_usage': random.randint(50, 100),
    'memory_usage': random.randint(60, 95),
    'error_count': random.randint(0, 10),
    'timestamp': str(datetime.now())
}
result = {'metrics': metrics}
                """
            },
        )

        # DiscordAlertNode doesn't support templates, so we'll format the message in Python
        builder.add_node(
            "PythonCodeNode",
            "format_message",
            config={
                "code": """
# PythonCodeNode passes inputs directly as variables
cpu = metrics.get('cpu_usage', 0)
mem = metrics.get('memory_usage', 0)
err = metrics.get('error_count', 0)
ts = metrics.get('timestamp', 'N/A')

message = f'''📊 **Metrics Report:**
- CPU Usage: {cpu}%
- Memory Usage: {mem}%
- Error Count: {err}
- Timestamp: {ts}

Status: {'⚠️ Warning' if err > 5 else '✅ Normal'}'''

result = {'title': '🚨 System Alert 🚨', 'message': message}
                """
            },
        )

        builder.add_node(
            "DiscordAlertNode",
            "send_alert",
            config={
                "webhook_url": webhook_url,
                "embed": True,
                "color": 0xFF0000,  # Red
                "footer_text": "Kailash SDK Integration Test",
            },
        )

        # Connect nodes
        builder.add_connection(
            "generate_data", "result.metrics", "format_message", "metrics"
        )
        builder.add_connection("format_message", "result.title", "send_alert", "title")
        builder.add_connection(
            "format_message", "result.message", "send_alert", "message"
        )

        # Execute workflow
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify - result can be a tuple (outputs, workflow_id) or just outputs dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        assert isinstance(outputs, dict)
        assert "send_alert" in outputs

        alert_result = outputs["send_alert"]

        # Check if the alert succeeded
        assert (
            "error" not in alert_result
        ), f"Alert failed: {alert_result.get('error', 'Unknown error')}"
        assert alert_result["success"] is True
        assert alert_result["alert_type"] == "info"  # Default
        assert "webhook_url" in alert_result

    def test_conditional_alerts(self, webhook_url: str):
        """Test conditional Discord alerts based on conditions."""
        # Build workflow with conditional logic
        builder = WorkflowBuilder()

        # Data generation node
        builder.add_node(
            "PythonCodeNode",
            "check_system",
            config={
                "code": """
import random
status = random.choice(['healthy', 'warning', 'critical'])
metrics = {
    'status': status,
    'cpu': random.randint(0, 100),
    'memory': random.randint(0, 100),
    'disk': random.randint(0, 100)
}
result = {'system_status': status, 'metrics': metrics}
                """
            },
        )

        # Switch node for conditional routing
        builder.add_node(
            "SwitchNode",
            "status_router",
            config={
                "condition_field": "system_status",
                "cases": ["critical", "warning", "healthy"],
            },
        )

        # Format critical message
        builder.add_node(
            "PythonCodeNode",
            "format_critical",
            config={
                "code": """
# When coming from SwitchNode, we get the full data object
data = metrics if isinstance(metrics, dict) else {}
actual_metrics = data.get('metrics', data) if 'metrics' in data else data
title = "🔴 CRITICAL ALERT"
message = f"System is in critical state! CPU: {actual_metrics.get('cpu', 0)}%, Memory: {actual_metrics.get('memory', 0)}%"
result = {'title': title, 'message': message}
                """
            },
        )

        # Format warning message
        builder.add_node(
            "PythonCodeNode",
            "format_warning",
            config={
                "code": """
# When coming from SwitchNode, we get the full data object
data = metrics if isinstance(metrics, dict) else {}
actual_metrics = data.get('metrics', data) if 'metrics' in data else data
title = "🟡 Warning"
message = f"System needs attention. CPU: {actual_metrics.get('cpu', 0)}%, Memory: {actual_metrics.get('memory', 0)}%"
result = {'title': title, 'message': message}
                """
            },
        )

        # Different alerts for different conditions
        builder.add_node(
            "DiscordAlertNode",
            "critical_alert",
            config={
                "webhook_url": webhook_url,
                "embed": True,
                "color": 0xFF0000,  # Red
            },
        )

        builder.add_node(
            "DiscordAlertNode",
            "warning_alert",
            config={
                "webhook_url": webhook_url,
                "embed": True,
                "color": 0xFFFF00,  # Yellow
            },
        )

        # Connect nodes
        builder.add_connection(
            "check_system", "result.system_status", "status_router", "system_status"
        )
        builder.add_connection(
            "check_system", "result.metrics", "status_router", "metrics"
        )

        # Conditional connections for formatting
        builder.add_connection(
            "status_router", "case_critical", "format_critical", "metrics"
        )
        builder.add_connection(
            "status_router", "case_warning", "format_warning", "metrics"
        )

        # Connect formatters to alerts
        builder.add_connection(
            "format_critical", "result.title", "critical_alert", "title"
        )
        builder.add_connection(
            "format_critical", "result.message", "critical_alert", "message"
        )
        builder.add_connection(
            "format_warning", "result.title", "warning_alert", "title"
        )
        builder.add_connection(
            "format_warning", "result.message", "warning_alert", "message"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()

        # Mock HTTP clients if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            for node_id, node in workflow.nodes.items():
                if isinstance(node, DiscordAlertNode):
                    node.http_client = mock_http_client

        result = runtime.execute(workflow)

        # Verify - result can be a tuple (outputs, workflow_id) or just outputs dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        assert isinstance(outputs, dict)
        # One of the alerts should have been triggered (or neither if status was 'healthy')
        has_critical = "critical_alert" in outputs
        has_warning = "warning_alert" in outputs
        # At least we should have run the check
        assert "check_system" in outputs

    def test_rate_limiting(self, webhook_url: str):
        """Test rate limiting functionality."""
        # Skip this test if using real webhook to avoid rate limits
        if "mock-webhook-for-testing" not in webhook_url:
            pytest.skip("Skipping rate limit test with real webhook")

        # Create node
        node = DiscordAlertNode(name="rate_limited")

        # Mock the rate limiter's window to be very small for testing
        node.rate_limiter.max_requests = 2
        node.rate_limiter.window_seconds = 1

        # Set up mock to simulate rate limiting on third request
        mock_http_client.run.side_effect = [
            {"status_code": 204, "content": "", "headers": {}},  # First request OK
            {"status_code": 204, "content": "", "headers": {}},  # Second request OK
            {
                "status_code": 429,  # Third request rate limited
                "content": "Rate limited",
                "headers": {"X-RateLimit-Reset-After": "0.1"},
            },
            {"status_code": 204, "content": "", "headers": {}},  # Retry succeeds
        ]
        node.http_client = mock_http_client

        # Send multiple messages quickly
        results = []
        for i in range(3):
            result = node.execute(
                webhook_url=webhook_url,
                title=f"Rate Test {i + 1}",
                message=f"Rate limit test message {i + 1}",
                alert_type="info",
            )
            results.append(result)

        # All should eventually succeed (with retry logic)
        assert all(r["success"] is True for r in results)
        # Check that we hit the rate limit and retried
        assert mock_http_client.run.call_count == 4  # 3 initial + 1 retry

    def test_complex_embeds(self, webhook_url: str):
        """Test sending complex embeds with multiple fields."""
        node = DiscordAlertNode(name="embed_test")

        # Mock HTTP client if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            node.http_client = mock_http_client

        # Create custom fields for the embed
        fields = [
            {
                "name": "Total Workflows",
                "value": "1,234",
                "inline": True,
            },
            {
                "name": "Success Rate",
                "value": "98.5%",
                "inline": True,
            },
            {
                "name": "Avg Duration",
                "value": "245ms",
                "inline": True,
            },
            {
                "name": "Most Used Nodes",
                "value": "PythonCodeNode (45%), CSVReaderNode (22%), LLMAgentNode (18%)",
                "inline": False,
            },
        ]

        result = node.execute(
            webhook_url=webhook_url,
            title="📊 Kailash SDK Performance Report",
            message="Daily performance metrics for the SDK",
            alert_type="success",
            embed=True,
            color=0x00FF00,  # Green
            fields=fields,
            footer_text=f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            context={"report_type": "daily", "generated_by": "test_suite"},
        )

        assert result["success"] is True
        assert result["alert_type"] == "success"
        assert "webhook_url" in result

    def test_error_reporting_workflow(self, webhook_url: str):
        """Test a complete error reporting workflow."""
        builder = WorkflowBuilder()

        # Simulate error detection
        builder.add_node(
            "PythonCodeNode",
            "detect_errors",
            config={
                "code": """
from datetime import datetime
errors = [
    {'level': 'ERROR', 'message': 'Database connection failed', 'count': 5},
    {'level': 'WARNING', 'message': 'API rate limit approaching', 'count': 12},
    {'level': 'ERROR', 'message': 'Memory usage exceeded threshold', 'count': 1}
]
error_summary = {
    'total_errors': sum(e['count'] for e in errors if e['level'] == 'ERROR'),
    'total_warnings': sum(e['count'] for e in errors if e['level'] == 'WARNING'),
    'critical_errors': [e for e in errors if e['level'] == 'ERROR'],
    'timestamp': str(datetime.now())
}
result = {'error_summary': error_summary}
                """
            },
        )

        # Format error report
        builder.add_node(
            "PythonCodeNode",
            "format_error_report",
            config={
                "code": """
summary = error_summary
timestamp = summary.get('timestamp', 'N/A')
total_errors = summary.get('total_errors', 0)
total_warnings = summary.get('total_warnings', 0)
critical_errors = summary.get('critical_errors', [])

title = f"🚨 Error Report - {timestamp}"
message_parts = [
    "**Summary:**",
    f"- Total Errors: {total_errors}",
    f"- Total Warnings: {total_warnings}",
    "",
    "**Critical Errors:**"
]

for error in critical_errors:
    message_parts.append(f"• {error['message']} ({error['count']} occurrences)")

message_parts.append("")
message_parts.append("Please investigate immediately!")

result = {'title': title, 'message': '\\n'.join(message_parts)}
                """
            },
        )

        # Discord alert node
        builder.add_node(
            "DiscordAlertNode",
            "error_report",
            config={
                "webhook_url": webhook_url,
                "alert_type": "error",
                "embed": True,
                "color": 0xFF0000,
                "fields": [
                    {
                        "name": "Action Required",
                        "value": "Check system logs and database connections",
                        "inline": False,
                    }
                ],
            },
        )

        # Connect
        builder.add_connection(
            "detect_errors",
            "result.error_summary",
            "format_error_report",
            "error_summary",
        )
        builder.add_connection(
            "format_error_report", "result.title", "error_report", "title"
        )
        builder.add_connection(
            "format_error_report", "result.message", "error_report", "message"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify - result can be a tuple (outputs, workflow_id) or just outputs dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        assert isinstance(outputs, dict)
        assert "error_report" in outputs
        assert outputs["error_report"]["success"] is True
        assert outputs["error_report"]["alert_type"] == "error"

    @pytest.mark.asyncio
    async def test_async_workflow_alerts(self, webhook_url: str):
        """Test Discord alerts in async workflow context."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.async_builder import AsyncWorkflowBuilder

        # Build async workflow
        builder = AsyncWorkflowBuilder()

        # Add async monitoring node
        builder.add_async_code(
            "monitor_services",
            code="""
import asyncio
services = ['api', 'database', 'cache', 'queue']
status_checks = []

for service in services:
    # Simulate async health check
    await asyncio.sleep(0.01)
    status = 'healthy' if hash(service) % 3 != 0 else 'degraded'
    status_checks.append({
        'service': service,
        'status': status,
        'response_time': hash(service) % 100 + 50
    })

unhealthy = [s for s in status_checks if s['status'] != 'healthy']
result = {'all_services': status_checks, 'unhealthy_services': unhealthy, 'alert_needed': len(unhealthy) > 0}
            """,
        )

        # Format alert message
        builder.add_node(
            "PythonCodeNode",
            "format_alert",
            config={
                "code": """
# When coming from SwitchNode's true_output, we get the full data object
# Extract unhealthy_services from the data
if isinstance(unhealthy_services, dict) and 'unhealthy_services' in unhealthy_services:
    unhealthy = unhealthy_services['unhealthy_services']
elif isinstance(unhealthy_services, list):
    unhealthy = unhealthy_services
else:
    unhealthy = []

title = "⚠️ Service Health Alert"
message_parts = ["The following services are experiencing issues:"]

for service in unhealthy:
    message_parts.append(f"• **{service['service']}**: {service['status']} ({service['response_time']}ms response time)")

message_parts.append(f"\\nTotal affected services: {len(unhealthy)}")
message = '\\n'.join(message_parts)

result = {'title': title, 'message': message}
                """
            },
        )

        # Conditional alert - using operator for boolean check
        builder.add_node(
            "SwitchNode",
            "alert_switch",
            config={
                "condition_field": "alert_needed",
                "operator": "==",
                "value": True,
            },
        )

        builder.add_node(
            "DiscordAlertNode",
            "service_alert",
            config={
                "webhook_url": webhook_url,
                "alert_type": "warning",
                "embed": True,
            },
        )

        # Connect nodes
        builder.add_connection(
            "monitor_services", "alert_needed", "alert_switch", "alert_needed"
        )
        builder.add_connection(
            "monitor_services",
            "unhealthy_services",
            "alert_switch",
            "unhealthy_services",
        )

        # Route to formatter when alert is needed (using true_output for boolean mode)
        builder.add_connection(
            "alert_switch", "true_output", "format_alert", "unhealthy_services"
        )

        # Connect formatter to alert
        builder.add_connection("format_alert", "result.title", "service_alert", "title")
        builder.add_connection(
            "format_alert", "result.message", "service_alert", "message"
        )

        # Execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime()

        # Mock HTTP client if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            for node_id, node in workflow.nodes.items():
                if isinstance(node, DiscordAlertNode):
                    node.http_client = mock_http_client

        result = await runtime.execute_async(workflow)

        # Verify - result can be a tuple (outputs, workflow_id) or just outputs dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        assert isinstance(outputs, dict)
        # Alert may or may not trigger based on hash-based health checks

    def test_a2a_coordination_alerts(self, webhook_url: str):
        """Test Discord alerts with A2A agent coordination."""
        builder = WorkflowBuilder()

        # Mock coordination result (in real scenario, this would come from A2A)
        builder.add_node(
            "PythonCodeNode",
            "mock_coordination",
            config={
                "code": """
result = {
    'agents_used': 'monitor, analyzer, reporter',
    'total_time': 1250,
    'summary': 'System analysis completed. Minor anomalies detected in API response times.',
    'recommendations': [
        'Scale API servers during peak hours',
        'Implement caching for frequent queries',
        'Monitor database connection pool'
    ]
}
result = {'coordination_result': result}
                """
            },
        )

        # Format coordination report
        builder.add_node(
            "PythonCodeNode",
            "format_coordination",
            config={
                "code": """
result = coordination_result
agents = result.get('agents_used', 'Unknown')
time_ms = result.get('total_time', 0)
summary = result.get('summary', 'No summary available')
recommendations = result.get('recommendations', [])

title = "🤖 A2A Coordination Report"
message_parts = [
    f"**Agents Involved:** {agents}",
    f"**Coordination Time:** {time_ms}ms",
    "",
    "**Key Findings:**",
    summary,
    "",
    "**Recommendations:**"
]

for rec in recommendations:
    message_parts.append(f"• {rec}")

result = {'title': title, 'message': '\\n'.join(message_parts)}
                """
            },
        )

        # Discord alert for coordination results
        builder.add_node(
            "DiscordAlertNode",
            "coordination_alert",
            config={
                "webhook_url": webhook_url,
                "alert_type": "info",
                "embed": True,
                "color": 0x9B59B6,  # Purple
                "footer_text": "Powered by Kailash A2A Framework",
            },
        )

        # Connect
        builder.add_connection(
            "mock_coordination",
            "result.coordination_result",
            "format_coordination",
            "coordination_result",
        )
        builder.add_connection(
            "format_coordination", "result.title", "coordination_alert", "title"
        )
        builder.add_connection(
            "format_coordination", "result.message", "coordination_alert", "message"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()

        # Mock HTTP client if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            for node_id, node in workflow.nodes.items():
                if isinstance(node, DiscordAlertNode):
                    node.http_client = mock_http_client

        result = runtime.execute(workflow)

        # Verify - result can be a tuple (outputs, workflow_id) or just outputs dict
        if isinstance(result, tuple):
            outputs, workflow_id = result
        else:
            outputs = result

        assert isinstance(outputs, dict)
        assert outputs["coordination_alert"]["success"] is True
        assert outputs["coordination_alert"]["alert_type"] == "info"

    def test_batch_alerts(self, webhook_url: str):
        """Test batching multiple alerts into one message."""
        # Collect multiple events
        events = []
        for i in range(5):
            events.append(
                {
                    "id": f"event_{i}",
                    "type": ["info", "warning", "error"][i % 3],
                    "message": f"Test event {i}",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        # Format batch message
        message_parts = [f"📋 **Batch Alert Summary** - {len(events)} events", ""]

        for event in events:
            icon = (
                "🔴"
                if event["type"] == "error"
                else "🟡" if event["type"] == "warning" else "🟢"
            )
            message_parts.append(f"{icon} [{event['type']}] {event['message']}")

        message_parts.append("")
        message_parts.append(f"Generated at: {datetime.now().strftime('%H:%M:%S')}")

        # Create batched alert
        node = DiscordAlertNode(name="batch_alert")

        # Mock HTTP client if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            node.http_client = mock_http_client

        result = node.execute(
            webhook_url=webhook_url,
            title="Batch Alert",
            message="\n".join(message_parts),
            alert_type="info",
            embed=True,
            context={"event_count": len(events)},
        )

        assert result["success"] is True
        assert result["alert_type"] == "info"

    def test_validation_and_sanitization(self, webhook_url: str):
        """Test input validation and sanitization."""
        node = DiscordAlertNode(name="validation_test")

        # Mock HTTP client if using mock webhook
        if "mock-webhook-for-testing" in webhook_url:
            node.http_client = mock_http_client

        # Test with potentially problematic input
        test_inputs = [
            ("Normal message", True),
            ("Message with @everyone", True),  # Discord handles escaping
            ("Message with ```code blocks```", True),
            ("Very " + "long " * 100 + "message", True),  # Discord handles truncation
            ("", True),  # Empty message but with title should work
        ]

        for inp, should_succeed in test_inputs:
            try:
                result = node.execute(
                    webhook_url=webhook_url,
                    title="Validation Test",
                    message=inp,
                    alert_type="info",
                )
                # Check if it succeeded as expected
                assert result["success"] is should_succeed
                if should_succeed:
                    assert result["alert_type"] == "info"
            except Exception as e:
                # If we expected failure, this is fine
                if should_succeed:
                    raise e
