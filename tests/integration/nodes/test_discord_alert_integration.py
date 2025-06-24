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
        """Get Discord webhook URL from environment."""
        return os.getenv("DISCORD_TEST_WEBHOOK", "")

    def test_simple_alert(self, webhook_url: str):
        """Test sending a simple alert to Discord."""
        # Create node
        node = DiscordAlertNode(
            name="discord_test",
            webhook_url=webhook_url,
            message_template="Test message from Kailash SDK: {{message}}",
        )

        # Execute
        result = node.execute(message="Hello from integration test!")

        # Verify
        assert result["success"] is True
        assert result["webhook_used"] == webhook_url
        assert (
            "Test message from Kailash SDK: Hello from integration test!"
            in result["message_sent"]
        )

    def test_workflow_with_alert(self, webhook_url: str):
        """Test Discord alert in a workflow context."""
        # Build workflow
        builder = WorkflowBuilder()

        # Add nodes
        builder.add_node(
            "PythonCodeNode",
            "generate_data",
            code="""
import random
metrics = {
    'cpu_usage': random.randint(50, 100),
    'memory_usage': random.randint(60, 95),
    'error_count': random.randint(0, 10),
    'timestamp': str(datetime.now())
}
{'metrics': metrics}
            """,
        )

        builder.add_node(
            "DiscordAlertNode",
            "send_alert",
            webhook_url=webhook_url,
            message_template="""
🚨 **System Alert** 🚨

📊 **Metrics Report:**
- CPU Usage: {{metrics.cpu_usage}}%
- Memory Usage: {{metrics.memory_usage}}%
- Error Count: {{metrics.error_count}}
- Timestamp: {{metrics.timestamp}}

Status: {{#if (gt metrics.error_count 5)}}⚠️ Warning{{else}}✅ Normal{{/if}}
            """,
            embed_config={
                "title": "Kailash System Metrics",
                "color": "0xFF0000",  # Red
                "footer": {"text": "Kailash SDK Integration Test"},
            },
        )

        # Connect nodes
        builder.add_connection("generate_data", "send_alert", "metrics", "metrics")

        # Execute workflow
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify
        assert result.success is True
        alert_result = result.outputs["send_alert"]
        assert alert_result["success"] is True
        assert "System Alert" in alert_result["message_sent"]

    def test_conditional_alerts(self, webhook_url: str):
        """Test conditional Discord alerts based on conditions."""
        # Build workflow with conditional logic
        builder = WorkflowBuilder()

        # Data generation node
        builder.add_node(
            "PythonCodeNode",
            "check_system",
            code="""
import random
status = random.choice(['healthy', 'warning', 'critical'])
metrics = {
    'status': status,
    'cpu': random.randint(0, 100),
    'memory': random.randint(0, 100),
    'disk': random.randint(0, 100)
}
{'system_status': status, 'metrics': metrics}
            """,
        )

        # Switch node for conditional routing
        builder.add_node(
            "SwitchNode",
            "status_router",
            condition_field="system_status",
        )

        # Different alerts for different conditions
        builder.add_node(
            "DiscordAlertNode",
            "critical_alert",
            webhook_url=webhook_url,
            message_template="🔴 **CRITICAL ALERT**: System is in critical state! CPU: {{metrics.cpu}}%, Memory: {{metrics.memory}}%",
            embed_config={"color": "0xFF0000"},  # Red
        )

        builder.add_node(
            "DiscordAlertNode",
            "warning_alert",
            webhook_url=webhook_url,
            message_template="🟡 **Warning**: System needs attention. CPU: {{metrics.cpu}}%, Memory: {{metrics.memory}}%",
            embed_config={"color": "0xFFFF00"},  # Yellow
        )

        # Connect nodes
        builder.add_connection(
            "check_system", "status_router", "system_status", "system_status"
        )
        builder.add_connection("check_system", "status_router", "metrics", "metrics")

        # Conditional connections
        builder.add_connection(
            "status_router",
            "critical_alert",
            "metrics",
            "metrics",
            condition="critical",
        )
        builder.add_connection(
            "status_router", "warning_alert", "metrics", "metrics", condition="warning"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        # Verify
        assert result.success is True
        # One of the alerts should have been triggered
        assert "critical_alert" in result.outputs or "warning_alert" in result.outputs

    def test_rate_limiting(self, webhook_url: str):
        """Test rate limiting functionality with real webhook."""
        # Create node with rate limiting
        node = DiscordAlertNode(
            name="rate_limited",
            webhook_url=webhook_url,
            rate_limit_per_minute=2,  # Only 2 messages per minute
        )

        # Send multiple messages
        results = []
        for i in range(3):
            result = node.execute(message=f"Rate limit test message {i + 1}")
            results.append(result)

        # First two should succeed
        assert results[0]["success"] is True
        assert results[1]["success"] is True

        # Third should be rate limited
        assert results[2]["success"] is False
        assert results[2]["error"] == "Rate limit exceeded"

    def test_complex_embeds(self, webhook_url: str):
        """Test sending complex embeds with multiple fields."""
        node = DiscordAlertNode(
            name="embed_test",
            webhook_url=webhook_url,
            message_template="Check out this detailed report:",
            embed_config={
                "title": "📊 Kailash SDK Performance Report",
                "description": "Daily performance metrics for the SDK",
                "color": "0x00FF00",  # Green
                "fields": [
                    {
                        "name": "Total Workflows",
                        "value": "{{total_workflows}}",
                        "inline": True,
                    },
                    {
                        "name": "Success Rate",
                        "value": "{{success_rate}}%",
                        "inline": True,
                    },
                    {
                        "name": "Avg Duration",
                        "value": "{{avg_duration}}ms",
                        "inline": True,
                    },
                    {
                        "name": "Most Used Nodes",
                        "value": "{{top_nodes}}",
                        "inline": False,
                    },
                ],
                "footer": {"text": "Generated at {{timestamp}}"},
                "thumbnail": {"url": "https://via.placeholder.com/100"},
            },
        )

        result = node.execute(
            total_workflows="1,234",
            success_rate="98.5",
            avg_duration="245",
            top_nodes="PythonCodeNode (45%), CSVReaderNode (22%), LLMAgentNode (18%)",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

        assert result["success"] is True
        assert "embed" in result  # Should have created an embed

    def test_error_reporting_workflow(self, webhook_url: str):
        """Test a complete error reporting workflow."""
        builder = WorkflowBuilder()

        # Simulate error detection
        builder.add_node(
            "PythonCodeNode",
            "detect_errors",
            code="""
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
{'error_summary': error_summary}
            """,
        )

        # Format error report
        builder.add_node(
            "DiscordAlertNode",
            "error_report",
            webhook_url=webhook_url,
            message_template="""
🚨 **Error Report** - {{error_summary.timestamp}}

**Summary:**
- Total Errors: {{error_summary.total_errors}}
- Total Warnings: {{error_summary.total_warnings}}

**Critical Errors:**
{{#each error_summary.critical_errors}}
• {{this.message}} ({{this.count}} occurrences)
{{/each}}

Please investigate immediately!
            """,
            embed_config={
                "title": "System Error Details",
                "color": "0xFF0000",
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
            "detect_errors", "error_report", "error_summary", "error_summary"
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        assert result.success is True
        assert result.outputs["error_report"]["success"] is True

    @pytest.mark.asyncio
    async def test_async_workflow_alerts(self, webhook_url: str):
        """Test Discord alerts in async workflow context."""
        from kailash.runtime.async_local import AsyncLocalRuntime
        from kailash.workflow.async_builder import AsyncWorkflowBuilder

        # Build async workflow
        builder = AsyncWorkflowBuilder()

        # Add async monitoring node
        builder.add_async_node(
            "PythonCodeNode",
            "monitor_services",
            code="""
import asyncio
services = ['api', 'database', 'cache', 'queue']
status_checks = []

for service in services:
    # Simulate async health check
    await asyncio.sleep(0.1)
    status = 'healthy' if hash(service) % 3 != 0 else 'degraded'
    status_checks.append({
        'service': service,
        'status': status,
        'response_time': hash(service) % 100 + 50
    })

unhealthy = [s for s in status_checks if s['status'] != 'healthy']
{'all_services': status_checks, 'unhealthy_services': unhealthy, 'alert_needed': len(unhealthy) > 0}
            """,
        )

        # Conditional alert
        builder.add_node(
            "SwitchNode",
            "alert_switch",
            condition_field="alert_needed",
        )

        builder.add_node(
            "DiscordAlertNode",
            "service_alert",
            webhook_url=webhook_url,
            message_template="""
⚠️ **Service Health Alert**

The following services are experiencing issues:
{{#each unhealthy_services}}
• **{{this.service}}**: {{this.status}} ({{this.response_time}}ms response time)
{{/each}}

Total affected services: {{unhealthy_services.length}}
            """,
        )

        # Connect nodes
        builder.add_connection(
            "monitor_services", "alert_switch", "alert_needed", "alert_needed"
        )
        builder.add_connection(
            "monitor_services",
            "alert_switch",
            "unhealthy_services",
            "unhealthy_services",
        )
        builder.add_connection(
            "alert_switch",
            "service_alert",
            "unhealthy_services",
            "unhealthy_services",
            condition=True,
        )

        # Execute
        workflow = builder.build()
        runtime = AsyncLocalRuntime()
        result = await runtime.execute_async(workflow)

        assert result.success is True
        # Alert may or may not trigger based on random health checks

    def test_a2a_coordination_alerts(self, webhook_url: str):
        """Test Discord alerts with A2A agent coordination."""
        builder = WorkflowBuilder()

        # A2A Coordinator
        builder.add_node(
            "A2AAgentNode",
            "coordinator",
            agent_configs={
                "monitor": {"role": "Monitor system metrics", "model": "gpt-3.5-turbo"},
                "analyzer": {"role": "Analyze anomalies", "model": "gpt-3.5-turbo"},
                "reporter": {"role": "Generate reports", "model": "gpt-3.5-turbo"},
            },
            coordination_strategy="round_robin",
        )

        # Discord alert for coordination results
        builder.add_node(
            "DiscordAlertNode",
            "coordination_alert",
            webhook_url=webhook_url,
            message_template="""
🤖 **A2A Coordination Report**

**Agents Involved:** {{coordination_result.agents_used}}
**Coordination Time:** {{coordination_result.total_time}}ms

**Key Findings:**
{{coordination_result.summary}}

**Recommendations:**
{{#each coordination_result.recommendations}}
• {{this}}
{{/each}}
            """,
            embed_config={
                "title": "Multi-Agent Analysis Complete",
                "color": "0x9B59B6",  # Purple
                "footer": {"text": "Powered by Kailash A2A Framework"},
            },
        )

        # Mock coordination result (in real scenario, this would come from A2A)
        builder.add_node(
            "PythonCodeNode",
            "mock_coordination",
            code="""
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
{'coordination_result': result}
            """,
        )

        # Connect
        builder.add_connection(
            "mock_coordination",
            "coordination_alert",
            "coordination_result",
            "coordination_result",
        )

        # Execute
        workflow = builder.build()
        runtime = LocalRuntime()
        result = runtime.execute(workflow)

        assert result.success is True
        assert result.outputs["coordination_alert"]["success"] is True

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

        # Create batched alert
        node = DiscordAlertNode(
            name="batch_alert",
            webhook_url=webhook_url,
            message_template="""
📋 **Batch Alert Summary** - {{events.length}} events

{{#each events}}
{{#if (eq this.type "error")}}🔴{{else if (eq this.type "warning")}}🟡{{else}}🟢{{/if}} [{{this.type}}] {{this.message}}
{{/each}}

Generated at: {{timestamp}}
            """,
        )

        result = node.execute(
            events=events, timestamp=datetime.now().strftime("%H:%M:%S")
        )

        assert result["success"] is True
        assert "5 events" in result["message_sent"]

    def test_validation_and_sanitization(self, webhook_url: str):
        """Test input validation and sanitization."""
        node = DiscordAlertNode(
            name="validation_test",
            webhook_url=webhook_url,
            message_template="User input: {{user_input}}",
        )

        # Test with potentially problematic input
        test_inputs = [
            "Normal message",
            "Message with @everyone",  # Should be escaped
            "Message with ```code blocks```",
            "Very " + "long " * 100 + "message",  # Should be truncated
            "",  # Empty message
        ]

        for inp in test_inputs:
            result = node.execute(user_input=inp)
            # All should succeed but be properly sanitized
            assert result["success"] is True or (inp == "" and not result["success"])
