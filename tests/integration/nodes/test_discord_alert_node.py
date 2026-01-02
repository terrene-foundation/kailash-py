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
        discord_node.http_client.execute = Mock(return_value=mock_http_response)

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
        discord_node.http_client.execute.assert_called_once()
        call_args = discord_node.http_client.execute.call_args[1]
        assert call_args["method"] == "POST"
        assert "json_data" in call_args

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_plain_text(self, mock_sleep, discord_node, mock_http_response):
        """Test plain text alert sending."""
        discord_node.http_client.execute = Mock(return_value=mock_http_response)

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
        call_args = discord_node.http_client.execute.call_args[1]
        payload = call_args["json_data"]
        assert "content" in payload
        assert "@here" in payload["content"]
        assert "**Error Alert**" in payload["content"]
        assert "embeds" not in payload

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_with_thread(self, mock_sleep, discord_node, mock_http_response):
        """Test alert sending to a thread."""
        discord_node.http_client.execute = Mock(return_value=mock_http_response)

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
        call_args = discord_node.http_client.execute.call_args[1]
        assert "thread_id=9876543210" in call_args["url"]

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_rate_limited(self, mock_sleep, discord_node):
        """Test handling of rate limit responses."""
        # First call returns 429 (rate limited)
        # Second call succeeds
        discord_node.http_client.execute = Mock(
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
        discord_node.http_client.execute = Mock(
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
        assert discord_node.http_client.execute.call_count == 3

    @patch("kailash.nodes.alerts.discord.time.sleep")
    def test_send_alert_max_retries_exceeded(self, mock_sleep, discord_node):
        """Test failure after max retries."""
        discord_node.http_client.execute = Mock(
            side_effect=Exception("Persistent error")
        )

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

        assert discord_node.http_client.execute.call_count == 3

    def test_run_method_integration(self, discord_node, mock_http_response):
        """Test the run method integration."""
        discord_node.http_client.execute = Mock(return_value=mock_http_response)

        with patch.dict(
            os.environ, {"TEST_WEBHOOK": "https://discord.com/api/webhooks/123/abc"}
        ):
            result = discord_node.execute(
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
        call_args = discord_node.http_client.execute.call_args[1]
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
