"""Discord alert node for the Kailash SDK.

This module implements Discord webhook integration for sending alerts and notifications
through Discord channels. It supports both simple text messages and rich embeds with
full customization options.

The Discord node provides:
- Webhook-based messaging (no bot token required)
- Rich embed support with colors and fields
- User and role mentions
- Thread support
- Rate limiting compliance
- Retry logic for failed requests
"""

import os
import re
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any, Optional

from kailash.nodes.alerts.base import AlertNode, AlertSeverity
from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.base import NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError


class DiscordRateLimiter:
    """Simple rate limiter for Discord webhooks.

    Discord limits webhooks to 30 requests per minute per webhook.
    This implements a sliding window rate limiter.
    """

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()

    def acquire(self) -> float:
        """Wait if necessary to comply with rate limits.

        Returns:
            Seconds waited (0 if no wait was needed)
        """
        now = time.time()

        # Remove old requests outside the window
        while self.requests and self.requests[0] < now - self.window_seconds:
            self.requests.popleft()

        # Check if we need to wait
        if len(self.requests) >= self.max_requests:
            # Calculate how long to wait
            oldest_request = self.requests[0]
            wait_time = (
                (oldest_request + self.window_seconds) - now + 0.1
            )  # Small buffer
            if wait_time > 0:
                time.sleep(wait_time)
                return wait_time

        # Record this request
        self.requests.append(now)
        return 0.0


@register_node()
class DiscordAlertNode(AlertNode):
    """
    Node for sending alerts to Discord channels via webhooks.

    This node provides a streamlined interface for sending notifications to Discord
    using webhook URLs. It supports Discord's rich embed format, allowing for
    visually appealing alerts with colors, fields, timestamps, and more.

    Design Philosophy:
        The DiscordAlertNode abstracts Discord's webhook API complexity while
        providing access to advanced features when needed. It handles rate limiting,
        retries, and formatting automatically, allowing users to focus on their
        alert content rather than Discord API specifics.

    Features:
        - Simple text messages or rich embeds
        - Automatic color coding based on alert severity
        - User/role/channel mentions with proper escaping
        - Thread support for organized discussions
        - Environment variable support for webhook URLs
        - Built-in rate limiting (30 requests/minute)
        - Retry logic with exponential backoff
        - Context data formatting as embed fields

    Webhook URL Security:
        Webhook URLs should be treated as secrets. This node supports:
        - Environment variable substitution (e.g., ${DISCORD_WEBHOOK})
        - Direct URL input (use with caution in production)
        - Configuration-based URLs via workflow parameters

    Examples:
        >>> # Simple text alert
        >>> node = DiscordAlertNode()
        >>> result = node.execute(
        ...     webhook_url="${DISCORD_ALERTS_WEBHOOK}",
        ...     title="Deployment Complete",
        ...     message="Version 1.2.3 deployed successfully",
        ...     alert_type="success"
        ... )
        >>>
        >>> # Rich embed with context
        >>> result = node.execute(
        ...     webhook_url=webhook_url,
        ...     title="Error in Data Pipeline",
        ...     message="Failed to process customer data",
        ...     alert_type="error",
        ...     context={
        ...         "Pipeline": "CustomerETL",
        ...         "Stage": "Transform",
        ...         "Error": "Invalid date format",
        ...         "Affected Records": 42
        ...     },
        ...     embed=True
        ... )
        >>>
        >>> # Mention users and post to thread
        >>> result = node.execute(
        ...     webhook_url=webhook_url,
        ...     title="Critical: Database Connection Lost",
        ...     alert_type="critical",
        ...     mentions=["@everyone"],
        ...     thread_id="1234567890",
        ...     embed=True
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the Discord alert node.

        Args:
            **kwargs: Node configuration parameters
        """
        super().__init__(**kwargs)
        self.http_client = HTTPRequestNode(id=f"{self.id}_http")
        self.rate_limiter = DiscordRateLimiter()

    def get_channel_parameters(self) -> dict[str, NodeParameter]:
        """Define Discord-specific parameters.

        Returns:
            Dictionary of Discord webhook parameters
        """
        return {
            "webhook_url": NodeParameter(
                name="webhook_url",
                type=str,
                required=True,
                description="Discord webhook URL (supports ${ENV_VAR} substitution)",
            ),
            "username": NodeParameter(
                name="username",
                type=str,
                required=False,
                default=None,
                description="Override webhook bot username",
            ),
            "avatar_url": NodeParameter(
                name="avatar_url",
                type=str,
                required=False,
                default=None,
                description="Override webhook bot avatar URL",
            ),
            "embed": NodeParameter(
                name="embed",
                type=bool,
                required=False,
                default=True,
                description="Send as rich embed (True) or plain text (False)",
            ),
            "color": NodeParameter(
                name="color",
                type=int,
                required=False,
                default=None,
                description="Override embed color (decimal color value)",
            ),
            "fields": NodeParameter(
                name="fields",
                type=list,
                required=False,
                default=[],
                description="Additional embed fields as list of {name, value, inline} dicts",
            ),
            "mentions": NodeParameter(
                name="mentions",
                type=list,
                required=False,
                default=[],
                description="List of mentions (@everyone, @here, user/role IDs)",
            ),
            "thread_id": NodeParameter(
                name="thread_id",
                type=str,
                required=False,
                default=None,
                description="Thread ID to post message in",
            ),
            "footer_text": NodeParameter(
                name="footer_text",
                type=str,
                required=False,
                default=None,
                description="Footer text for embeds",
            ),
            "timestamp": NodeParameter(
                name="timestamp",
                type=bool,
                required=False,
                default=True,
                description="Include timestamp in embed",
            ),
        }

    def resolve_webhook_url(self, webhook_url: str) -> str:
        """Resolve webhook URL, supporting environment variable substitution.

        Args:
            webhook_url: Raw webhook URL or environment variable reference

        Returns:
            Resolved webhook URL

        Raises:
            ValueError: If environment variable is not set
        """
        # Check for environment variable pattern ${VAR_NAME}
        env_pattern = r"\$\{([^}]+)\}"
        match = re.match(env_pattern, webhook_url.strip())

        if match:
            var_name = match.group(1)
            resolved_url = os.environ.get(var_name)
            if not resolved_url:
                raise ValueError(
                    f"Environment variable '{var_name}' is not set. "
                    f"Please set it or provide the webhook URL directly."
                )
            return resolved_url

        return webhook_url

    def format_mentions(self, mentions: list[str]) -> str:
        """Format mention list into Discord mention string.

        Args:
            mentions: List of mention strings

        Returns:
            Formatted mention string
        """
        if not mentions:
            return ""

        formatted_mentions = []
        for mention in mentions:
            # Handle special mentions
            if mention in ["@everyone", "@here"]:
                formatted_mentions.append(mention)
            # Handle user mentions (numeric IDs)
            elif mention.isdigit():
                formatted_mentions.append(f"<@{mention}>")
            # Handle role mentions (numeric IDs with & prefix)
            elif mention.startswith("&") and mention[1:].isdigit():
                formatted_mentions.append(f"<@{mention}>")
            # Pass through already formatted mentions
            elif mention.startswith("<@") and mention.endswith(">"):
                formatted_mentions.append(mention)
            else:
                # Assume it's a user ID
                formatted_mentions.append(f"<@{mention}>")

        return " ".join(formatted_mentions) + " "

    def build_embed(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        context: dict[str, Any],
        color: Optional[int],
        fields: list[dict[str, Any]],
        footer_text: Optional[str],
        timestamp: bool,
    ) -> dict[str, Any]:
        """Build a Discord embed object.

        Args:
            severity: Alert severity for color
            title: Embed title
            message: Embed description
            context: Context data to add as fields
            color: Override color
            fields: Additional fields
            footer_text: Footer text
            timestamp: Whether to include timestamp

        Returns:
            Discord embed object
        """
        embed = {
            "title": title,
            "color": color if color is not None else severity.get_color(),
        }

        if message:
            embed["description"] = message

        # Add context as fields
        embed_fields = []
        if context:
            for key, value in context.items():
                # Convert value to string, truncate if needed
                value_str = str(value)
                if len(value_str) > 1024:  # Discord field value limit
                    value_str = value_str[:1021] + "..."

                embed_fields.append({"name": key, "value": value_str, "inline": True})

        # Add custom fields
        for field in fields:
            if isinstance(field, dict) and "name" in field and "value" in field:
                embed_fields.append(
                    {
                        "name": str(field["name"]),
                        "value": str(field["value"]),
                        "inline": field.get("inline", True),
                    }
                )

        if embed_fields:
            embed["fields"] = embed_fields[:25]  # Discord limit: 25 fields

        # Add footer
        if footer_text:
            embed["footer"] = {"text": footer_text}

        # Add timestamp
        if timestamp:
            embed["timestamp"] = datetime.now(UTC).isoformat()

        return embed

    def send_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        context: dict[str, Any],
        **kwargs,
    ) -> dict[str, Any]:
        """Send alert to Discord via webhook.

        Args:
            severity: Alert severity
            title: Alert title
            message: Alert message
            context: Context data
            **kwargs: Discord-specific parameters

        Returns:
            Dictionary with response data

        Raises:
            NodeExecutionError: If webhook request fails after retries
        """
        # Extract Discord parameters
        webhook_url = self.resolve_webhook_url(kwargs["webhook_url"])
        username = kwargs.get("username")
        avatar_url = kwargs.get("avatar_url")
        use_embed = kwargs.get("embed", True)
        color = kwargs.get("color")
        fields = kwargs.get("fields", [])
        mentions = kwargs.get("mentions", [])
        thread_id = kwargs.get("thread_id")
        footer_text = kwargs.get("footer_text")
        timestamp = kwargs.get("timestamp", True)

        # Build payload
        payload = {}

        # Add username and avatar if provided
        if username:
            payload["username"] = username
        if avatar_url:
            payload["avatar_url"] = avatar_url

        # Format mentions
        mention_str = self.format_mentions(mentions)

        if use_embed:
            # Rich embed format
            embed = self.build_embed(
                severity, title, message, context, color, fields, footer_text, timestamp
            )
            payload["embeds"] = [embed]

            # Add mentions as content if present
            if mention_str:
                payload["content"] = mention_str.strip()
        else:
            # Plain text format
            content_parts = []
            if mention_str:
                content_parts.append(mention_str.strip())

            # Format as bold title with message
            content_parts.append(f"**{title}**")
            if message:
                content_parts.append(message)

            # Add context as formatted text
            if context:
                content_parts.append("\n" + self.format_context(context))

            payload["content"] = "\n".join(content_parts)

        # Handle thread posting
        url = webhook_url
        if thread_id:
            url = f"{webhook_url}?thread_id={thread_id}"

        # Apply rate limiting
        wait_time = self.rate_limiter.acquire()

        # Send with retry logic
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = self.http_client.execute(
                    url=url,
                    method="POST",
                    json_data=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                # Check response
                if response["status_code"] == 204:
                    # Success
                    return {
                        "success": True,
                        "status_code": response["status_code"],
                        "wait_time": wait_time,
                        "attempt": attempt + 1,
                        "webhook_url": webhook_url.split("?")[
                            0
                        ],  # Remove token for security
                        "thread_id": thread_id,
                    }
                elif response["status_code"] == 429:
                    # Rate limited - wait and retry
                    retry_after = float(
                        response.get("headers", {}).get(
                            "X-RateLimit-Reset-After", retry_delay
                        )
                    )
                    time.sleep(retry_after)
                    retry_delay *= 2
                else:
                    # Other error
                    error_msg = (
                        f"Discord webhook returned status {response['status_code']}"
                    )
                    if response.get("content"):
                        error_msg += f": {response['content']}"

                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        raise NodeExecutionError(error_msg)

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Discord webhook attempt {attempt + 1} failed: {e}"
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise NodeExecutionError(
                        f"Failed to send Discord alert after {max_retries} attempts: {e}"
                    ) from e

        # Should not reach here
        raise NodeExecutionError("Failed to send Discord alert: Max retries exceeded")
