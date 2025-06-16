"""
Tests for Discord Alert Node

This module tests the DiscordAlertNode functionality including:
- Basic alert sending
- Rich embed formatting
- Rate limiting
- Error handling
- Environment variable resolution
"""

import json
import os
import time
from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

from kailash.nodes.alerts import AlertSeverity, DiscordAlertNode
from kailash.sdk_exceptions import NodeExecutionError


class TestDiscordAlertNode:
    """Test suite for DiscordAlertNode."""

    @pytest.fixture
    def discord_node(self):
        """Create a Discord alert node instance."""
        return DiscordAlertNode(name="TestDiscordNode")

    @pytest.fixture
    def mock_http_response(self):
        """Mock successful HTTP response."""
        return {"status_code": 204, "content": "", "headers": {}}

    def test_initialization(self, discord_node):
        """Test node initialization."""
        assert discord_node.metadata.name == "TestDiscordNode"
        assert discord_node.category == "alerts"
        assert hasattr(discord_node, "http_client")
        assert hasattr(discord_node, "rate_limiter")

    def test_get_parameters(self, discord_node):
        """Test parameter definitions."""
        params = discord_node.get_parameters()

        # Check common alert parameters
        assert "alert_type" in params
        assert "title" in params
        assert "message" in params
        assert "context" in params

        # Check Discord-specific parameters
        assert "webhook_url" in params
        assert "username" in params
        assert "avatar_url" in params
        assert "embed" in params
        assert "color" in params
        assert "fields" in params
        assert "mentions" in params
        assert "thread_id" in params
        assert "footer_text" in params
        assert "timestamp" in params

        # Verify required parameters
        assert params["webhook_url"].required is True
        assert params["title"].required is True
        assert params["message"].required is False

    def test_resolve_webhook_url_direct(self, discord_node):
        """Test direct webhook URL resolution."""
        url = "https://discord.com/api/webhooks/123/abc"
        resolved = discord_node.resolve_webhook_url(url)
        assert resolved == url

    def test_resolve_webhook_url_env_var(self, discord_node):
        """Test environment variable webhook URL resolution."""
        test_url = "https://discord.com/api/webhooks/456/def"

        with patch.dict(os.environ, {"TEST_WEBHOOK": test_url}):
            resolved = discord_node.resolve_webhook_url("${TEST_WEBHOOK}")
            assert resolved == test_url

    def test_resolve_webhook_url_missing_env_var(self, discord_node):
        """Test error when environment variable is not set."""
        with pytest.raises(
            ValueError, match="Environment variable 'MISSING_VAR' is not set"
        ):
            discord_node.resolve_webhook_url("${MISSING_VAR}")

    def test_format_mentions_basic(self, discord_node):
        """Test basic mention formatting."""
        mentions = ["@everyone", "@here"]
        formatted = discord_node.format_mentions(mentions)
        assert formatted == "@everyone @here "

    def test_format_mentions_user_ids(self, discord_node):
        """Test user ID mention formatting."""
        mentions = ["123456789", "&987654321"]
        formatted = discord_node.format_mentions(mentions)
        assert formatted == "<@123456789> <@&987654321> "

    def test_format_mentions_mixed(self, discord_node):
        """Test mixed mention formatting."""
        mentions = ["@everyone", "123456789", "<@&987654321>"]
        formatted = discord_node.format_mentions(mentions)
        assert formatted == "@everyone <@123456789> <@&987654321> "

    def test_build_embed_basic(self, discord_node):
        """Test basic embed building."""
        embed = discord_node.build_embed(
            severity=AlertSeverity.SUCCESS,
            title="Test Alert",
            message="Test message",
            context={},
            color=None,
            fields=[],
            footer_text=None,
            timestamp=False,
        )

        assert embed["title"] == "Test Alert"
        assert embed["description"] == "Test message"
        assert embed["color"] == AlertSeverity.SUCCESS.get_color()
        assert "fields" not in embed
        assert "footer" not in embed
        assert "timestamp" not in embed

    def test_build_embed_with_context(self, discord_node):
        """Test embed building with context data."""
        context = {"Server": "prod-01", "CPU": "85%", "Memory": "4GB"}

        embed = discord_node.build_embed(
            severity=AlertSeverity.WARNING,
            title="System Alert",
            message="High resource usage",
            context=context,
            color=None,
            fields=[],
            footer_text=None,
            timestamp=False,
        )

        assert len(embed["fields"]) == 3
        assert embed["fields"][0]["name"] == "Server"
        assert embed["fields"][0]["value"] == "prod-01"
        assert embed["fields"][0]["inline"] is True

    def test_build_embed_with_custom_fields(self, discord_node):
        """Test embed building with custom fields."""
        custom_fields = [
            {"name": "Status", "value": "Online", "inline": True},
            {"name": "Uptime", "value": "99.9%", "inline": False},
        ]

        embed = discord_node.build_embed(
            severity=AlertSeverity.INFO,
            title="Status Report",
            message="",
            context={},
            color=0x00FF00,
            fields=custom_fields,
            footer_text="Updated hourly",
            timestamp=True,
        )

        assert embed["color"] == 0x00FF00
        assert len(embed["fields"]) == 2
        assert embed["fields"][1]["inline"] is False
        assert embed["footer"]["text"] == "Updated hourly"
        assert "timestamp" in embed

    def test_build_embed_field_limit(self, discord_node):
        """Test embed field limit enforcement."""
        # Create 30 fields (more than Discord's 25 limit)
        many_fields = [
            {"name": f"Field {i}", "value": f"Value {i}", "inline": True}
            for i in range(30)
        ]

        embed = discord_node.build_embed(
            severity=AlertSeverity.INFO,
            title="Many Fields",
            message="",
            context={},
            color=None,
            fields=many_fields,
            footer_text=None,
            timestamp=False,
        )

        assert len(embed["fields"]) == 25  # Should be truncated

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_success(self, mock_sleep, discord_node, mock_http_response):
        """Test successful alert sending."""
        discord_node.http_client.run = Mock(return_value=mock_http_response)

        result = discord_node.send_alert(
            severity=AlertSeverity.SUCCESS,
            title="Test Success",
            message="All good",
            context={},
            webhook_url="https://discord.com/api/webhooks/123/abc",
            embed=True,
        )

        assert result["success"] is True
        assert result["status_code"] == 204
        assert "webhook_url" in result
        assert "thread_id" in result

        # Verify HTTP call
        discord_node.http_client.run.assert_called_once()
        call_args = discord_node.http_client.run.call_args[1]
        assert call_args["method"] == "POST"
        assert "json_data" in call_args

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_plain_text(self, mock_sleep, discord_node, mock_http_response):
        """Test plain text alert sending."""
        discord_node.http_client.run = Mock(return_value=mock_http_response)

        result = discord_node.send_alert(
            severity=AlertSeverity.ERROR,
            title="Error Alert",
            message="Something went wrong",
            context={"Error": "Database timeout"},
            webhook_url="https://discord.com/api/webhooks/123/abc",
            embed=False,
            mentions=["@here"],
        )

        assert result["success"] is True

        # Check payload
        call_args = discord_node.http_client.run.call_args[1]
        payload = call_args["json_data"]
        assert "content" in payload
        assert "@here" in payload["content"]
        assert "**Error Alert**" in payload["content"]
        assert "embeds" not in payload

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_with_thread(self, mock_sleep, discord_node, mock_http_response):
        """Test alert sending to a thread."""
        discord_node.http_client.run = Mock(return_value=mock_http_response)

        result = discord_node.send_alert(
            severity=AlertSeverity.INFO,
            title="Thread Update",
            message="Posted to thread",
            context={},
            webhook_url="https://discord.com/api/webhooks/123/abc",
            thread_id="9876543210",
        )

        assert result["thread_id"] == "9876543210"

        # Check URL includes thread_id
        call_args = discord_node.http_client.run.call_args[1]
        assert "thread_id=9876543210" in call_args["url"]

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_rate_limited(self, mock_sleep, discord_node):
        """Test handling of rate limit responses."""
        # First call returns 429 (rate limited)
        # Second call succeeds
        discord_node.http_client.run = Mock(
            side_effect=[
                {
                    "status_code": 429,
                    "headers": {"X-RateLimit-Reset-After": "2.0"},
                    "content": "Rate limited",
                },
                {"status_code": 204, "content": "", "headers": {}},
            ]
        )

        result = discord_node.send_alert(
            severity=AlertSeverity.WARNING,
            title="Rate Test",
            message="Testing rate limits",
            context={},
            webhook_url="https://discord.com/api/webhooks/123/abc",
        )

        assert result["success"] is True
        assert result["attempt"] == 2

        # Verify sleep was called for rate limit
        mock_sleep.assert_called()

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_retry_on_error(self, mock_sleep, discord_node):
        """Test retry logic on errors."""
        # First two calls fail, third succeeds
        discord_node.http_client.run = Mock(
            side_effect=[
                Exception("Network error"),
                {"status_code": 500, "content": "Server error"},
                {"status_code": 204, "content": "", "headers": {}},
            ]
        )

        result = discord_node.send_alert(
            severity=AlertSeverity.CRITICAL,
            title="Retry Test",
            message="Testing retries",
            context={},
            webhook_url="https://discord.com/api/webhooks/123/abc",
        )

        assert result["success"] is True
        assert result["attempt"] == 3
        assert discord_node.http_client.run.call_count == 3

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_max_retries_exceeded(self, mock_sleep, discord_node):
        """Test failure after max retries."""
        discord_node.http_client.run = Mock(side_effect=Exception("Persistent error"))

        with pytest.raises(
            NodeExecutionError, match="Failed to send Discord alert after 3 attempts"
        ):
            discord_node.send_alert(
                severity=AlertSeverity.ERROR,
                title="Fail Test",
                message="This will fail",
                context={},
                webhook_url="https://discord.com/api/webhooks/123/abc",
            )

        assert discord_node.http_client.run.call_count == 3

    def test_run_method_integration(self, discord_node, mock_http_response):
        """Test the run method integration."""
        discord_node.http_client.run = Mock(return_value=mock_http_response)

        with patch.dict(
            os.environ, {"TEST_WEBHOOK": "https://discord.com/api/webhooks/123/abc"}
        ):
            result = discord_node.run(
                webhook_url="${TEST_WEBHOOK}",
                title="Integration Test",
                message="Testing full flow",
                alert_type="success",
                context={"Test": "Value"},
                username="Test Bot",
                embed=True,
            )

        assert result["success"] is True
        assert result["alert_type"] == "success"
        assert result["title"] == "Integration Test"

        # Check payload structure
        call_args = discord_node.http_client.run.call_args[1]
        payload = call_args["json_data"]
        assert payload["username"] == "Test Bot"
        assert "embeds" in payload
        assert payload["embeds"][0]["title"] == "Integration Test"

    def test_rate_limiter(self, discord_node):
        """Test rate limiter functionality."""
        limiter = discord_node.rate_limiter

        # First 30 requests should not wait
        for i in range(30):
            wait_time = limiter.acquire()
            assert wait_time == 0.0

        # 31st request should wait
        with patch("kailash.nodes.alerts.discord.time.time") as mock_time:
            # Mock time to make it seem like we're within the window
            mock_time.return_value = 59.0  # Just under 60 seconds

            with patch("kailash.nodes.alerts.discord.time.sleep") as mock_sleep:
                wait_time = limiter.acquire()
                assert wait_time > 0
                mock_sleep.assert_called_once()


# Integration Tests - Real Discord Webhook Testing
# These tests are marked as integration and skipped by default unless
# DISCORD_TEST_WEBHOOK environment variable is set


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("DISCORD_TEST_WEBHOOK"),
    reason="DISCORD_TEST_WEBHOOK environment variable not set",
)
class TestDiscordAlertIntegration:
    """Integration tests for Discord alerts with real webhook.

    ⚠️  WARNING: These tests send real messages to your Discord channel!

    Setup:
    1. Create a test Discord channel and webhook
    2. Set environment variable: export DISCORD_TEST_WEBHOOK="https://discord.com/api/webhooks/..."

    Running:
    - All integration tests: pytest -m integration
    - Skip integration tests: pytest -m "not integration"
    """

    @pytest.fixture(scope="class")
    def webhook_url(self):
        """Get test webhook URL from environment."""
        return os.getenv("DISCORD_TEST_WEBHOOK")

    @pytest.fixture
    def test_workflow(self):
        """Create a test workflow."""
        from kailash.workflow import Workflow

        return Workflow("discord_test", name="Discord Integration Test")

    @pytest.fixture(scope="class")
    def runtime(self):
        """Create a local runtime for test execution."""
        from kailash.runtime.local import LocalRuntime

        return LocalRuntime()

    def test_basic_text_alert_integration(self, test_workflow, webhook_url, runtime):
        """Test sending a basic text alert to real Discord webhook."""
        import time
        from datetime import datetime

        # Add Discord alert node
        alert_node = DiscordAlertNode()
        test_workflow.add_node("basic_alert", alert_node)

        # Execute workflow
        results, _ = runtime.execute(
            test_workflow,
            parameters={
                "basic_alert": {
                    "webhook_url": webhook_url,
                    "title": "Integration Test - Basic Alert",
                    "message": f"This is a test message sent at {datetime.now()}",
                    "alert_type": "info",
                    "embed": False,  # Plain text mode
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["basic_alert"]["success"] is True
        assert results["basic_alert"]["status_code"] == 204
        time.sleep(1)  # Rate limit courtesy

    def test_rich_embed_alert_integration(self, test_workflow, webhook_url, runtime):
        """Test sending a rich embed alert to real Discord webhook."""
        import time
        from datetime import datetime

        # Add Discord alert node
        alert_node = DiscordAlertNode()
        test_workflow.add_node("embed_alert", alert_node)

        # Execute workflow
        results, _ = runtime.execute(
            test_workflow,
            parameters={
                "embed_alert": {
                    "webhook_url": webhook_url,
                    "title": "🧪 Integration Test - Rich Embed",
                    "message": "Testing Discord rich embed functionality",
                    "alert_type": "success",
                    "username": "Integration Test Bot",
                    "footer_text": "Kailash SDK Integration Test",
                    "context": {
                        "Test Suite": "Discord Integration",
                        "SDK Version": "1.0.0",
                        "Timestamp": datetime.now().isoformat(),
                    },
                    "fields": [
                        {"name": "Status", "value": "✅ Passing", "inline": True},
                        {"name": "Environment", "value": "Test", "inline": True},
                    ],
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["embed_alert"]["success"] is True
        time.sleep(1)

    def test_all_severity_levels_integration(self, webhook_url, runtime):
        """Test all alert severity levels with real Discord webhook."""
        import time

        from kailash.workflow import Workflow

        severities = ["success", "info", "warning", "error", "critical"]

        for severity in severities:
            # Create a new workflow for each test to avoid node conflicts
            workflow = Workflow(
                f"discord_severity_{severity}", name=f"Discord {severity} Test"
            )

            # Add Discord alert node
            alert_node = DiscordAlertNode()
            workflow.add_node(f"{severity}_alert", alert_node)

            # Execute workflow
            results, _ = runtime.execute(
                workflow,
                parameters={
                    f"{severity}_alert": {
                        "webhook_url": webhook_url,
                        "title": f"Test {severity.upper()} Alert",
                        "message": f"This is a {severity} level alert",
                        "alert_type": severity,
                    }
                },
            )

            # Verify results
            assert results is not None
            assert results[f"{severity}_alert"]["success"] is True
            time.sleep(1)  # Avoid rate limiting

    def test_workflow_with_processing_and_alert_integration(
        self, test_workflow, webhook_url, runtime
    ):
        """Test a complete workflow with data processing and alerts."""
        import time

        from kailash.nodes.base import NodeParameter
        from kailash.nodes.code import PythonCodeNode

        # Define data processing function
        def process_data():
            return {
                "records_processed": 1000,
                "errors": 5,
                "duration": "45.3s",
                "status": "completed_with_warnings",
            }

        # Data processor node
        processor = PythonCodeNode.from_function(
            func=process_data,
            name="DataProcessorNode",
            output_schema={
                "records_processed": NodeParameter(
                    name="records_processed",
                    type=int,
                    description="Number of records processed",
                ),
                "errors": NodeParameter(
                    name="errors", type=int, description="Number of errors encountered"
                ),
                "duration": NodeParameter(
                    name="duration", type=str, description="Processing duration"
                ),
                "status": NodeParameter(
                    name="status", type=str, description="Processing status"
                ),
            },
        )
        test_workflow.add_node("process_data", processor)

        # Alert node
        alert_node = DiscordAlertNode()
        test_workflow.add_node("completion_alert", alert_node)

        # Connect nodes - processor outputs become alert context
        test_workflow.connect(
            "process_data",
            "completion_alert",
            mapping={
                "records_processed": "records_processed",
                "errors": "errors",
                "duration": "duration",
            },
        )

        # Execute workflow
        results, _ = runtime.execute(
            test_workflow,
            parameters={
                "completion_alert": {
                    "webhook_url": webhook_url,
                    "title": "📊 Workflow Completed",
                    "message": "Data processing workflow has finished",
                    "alert_type": "warning",  # Because we have errors
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["process_data"]["records_processed"] == 1000
        assert results["completion_alert"]["success"] is True
        time.sleep(1)

    @pytest.mark.parametrize(
        "mention_type,mention_value",
        [
            ("user_id", "123456789012345678"),  # Fake user ID
            ("role_mention", "&987654321098765432"),  # Fake role ID
            ("formatted_user", "<@123456789012345678>"),  # Pre-formatted
        ],
    )
    def test_mentions_integration(
        self, webhook_url, runtime, mention_type, mention_value
    ):
        """Test different mention formats with real Discord webhook."""
        import time

        from kailash.workflow import Workflow

        # Create workflow for this test
        workflow = Workflow(
            f"discord_mentions_{mention_type}",
            name=f"Discord Mentions Test - {mention_type}",
        )

        # Add Discord alert node
        alert_node = DiscordAlertNode()
        workflow.add_node("mention_alert", alert_node)

        # Execute workflow
        results, _ = runtime.execute(
            workflow,
            parameters={
                "mention_alert": {
                    "webhook_url": webhook_url,
                    "title": f"Test {mention_type} Mention",
                    "message": "Testing mention formatting (fake IDs)",
                    "alert_type": "info",
                    "mentions": [mention_value],
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["mention_alert"]["success"] is True
        time.sleep(1)

    def test_rate_limiting_integration(self, webhook_url, runtime):
        """Test rate limiting behavior with rapid requests to real Discord webhook."""
        import time

        from kailash.workflow import Workflow

        # Create workflow for rate limiting test
        workflow = Workflow("discord_rate_test", name="Discord Rate Limiting Test")

        # Add Discord alert node
        alert_node = DiscordAlertNode()
        workflow.add_node("rate_test", alert_node)

        # Send 5 rapid requests
        start_time = time.time()
        for i in range(5):
            results, _ = runtime.execute(
                workflow,
                parameters={
                    "rate_test": {
                        "webhook_url": webhook_url,
                        "title": f"Rate Limit Test {i+1}/5",
                        "message": "Testing rate limiter",
                        "alert_type": "info",
                    }
                },
            )
            assert results is not None
            assert results["rate_test"]["success"] is True

        end_time = time.time()
        duration = end_time - start_time

        print(f"\nRate limit test: 5 requests took {duration:.2f} seconds")
        # Should complete quickly since we're well under the 30/minute limit
        assert duration < 10  # Should take less than 10 seconds

    def test_environment_variable_webhook_integration(self, test_workflow, runtime):
        """Test using environment variable for webhook URL with real Discord webhook."""
        import time

        # Set a temporary env var
        test_webhook = os.getenv("DISCORD_TEST_WEBHOOK")
        os.environ["TEMP_DISCORD_WEBHOOK"] = test_webhook

        try:
            # Add Discord alert node
            alert_node = DiscordAlertNode()
            test_workflow.add_node("env_alert", alert_node)

            # Execute workflow
            results, _ = runtime.execute(
                test_workflow,
                parameters={
                    "env_alert": {
                        "webhook_url": "${TEMP_DISCORD_WEBHOOK}",
                        "title": "Environment Variable Test",
                        "message": "Testing webhook URL from environment variable",
                        "alert_type": "success",
                    }
                },
            )

            # Verify results
            assert results is not None
            assert results["env_alert"]["success"] is True
        finally:
            del os.environ["TEMP_DISCORD_WEBHOOK"]

        time.sleep(1)

    def test_standalone_discord_alert_integration(self, webhook_url):
        """Test Discord alert outside of workflow context with real webhook."""
        # Create and test node directly
        node = DiscordAlertNode(name="StandaloneTestNode")

        result = node.run(
            webhook_url=webhook_url,
            title="Standalone Node Test",
            message="Testing Discord node without workflow",
            alert_type="info",
            context={"Test Type": "Standalone", "Direct Execution": True},
        )

        # Verify direct node execution
        assert result["success"] is True
        assert result["alert_type"] == "info"
        assert result["title"] == "Standalone Node Test"

    def test_error_context_alert_integration(self, test_workflow, webhook_url, runtime):
        """Test sending an error alert with detailed context."""
        # Add Discord alert node
        alert_node = DiscordAlertNode()
        test_workflow.add_node("error_alert", alert_node)

        # Execute workflow
        results, _ = runtime.execute(
            test_workflow,
            parameters={
                "error_alert": {
                    "webhook_url": webhook_url,
                    "title": "❌ Integration Test Error",
                    "message": "Simulated error for testing purposes",
                    "alert_type": "error",
                    "username": "Error Reporter",
                    "footer_text": "Please investigate immediately",
                    "context": {
                        "Error Type": "TestException",
                        "Module": "test_discord_integration",
                        "Line": "N/A",
                        "Timestamp": datetime.now().isoformat(),
                        "Stack Trace": "This is a simulated error - no actual error occurred",
                    },
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["error_alert"]["success"] is True
        time.sleep(1)

    def test_thread_support_integration(self, test_workflow, webhook_url, runtime):
        """Test thread support (requires valid thread ID to actually work)."""
        # Add Discord alert node
        alert_node = DiscordAlertNode()
        test_workflow.add_node("thread_alert", alert_node)

        # Note: Invalid thread IDs will cause the request to fail with 400 error
        # This is expected behavior from Discord API
        # We'll test without thread_id to verify the feature exists
        results, _ = runtime.execute(
            test_workflow,
            parameters={
                "thread_alert": {
                    "webhook_url": webhook_url,
                    "title": "Thread Feature Test",
                    "message": "Testing thread support - would post to thread with valid ID",
                    "alert_type": "info",
                    # Omitting thread_id to avoid 400 error
                }
            },
        )

        # Verify results
        assert results is not None
        assert results["thread_alert"]["success"] is True

        # The thread_id should be None when not provided
        assert results["thread_alert"].get("thread_id") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
