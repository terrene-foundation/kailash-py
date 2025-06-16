"""Base alert node class for the Kailash SDK.

This module provides the foundation for all alert and notification nodes in the system.
It defines common parameters, severity levels, and formatting utilities that are shared
across different alert implementations.

The alert system is designed to provide:
- Consistent interface across different notification channels
- Severity-based formatting and colors
- Structured context data support
- Easy extensibility for new alert types
"""

from abc import abstractmethod
from enum import Enum
from typing import Any

from kailash.nodes.base import Node, NodeParameter


class AlertSeverity(str, Enum):
    """Standard alert severity levels with associated colors."""

    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    INFO = "info"

    def get_color(self) -> int:
        """Get the color code for this severity level (Discord/Slack compatible)."""
        colors = {
            AlertSeverity.SUCCESS: 0x28A745,  # Green
            AlertSeverity.WARNING: 0xFFC107,  # Yellow/Amber
            AlertSeverity.ERROR: 0xDC3545,  # Red
            AlertSeverity.CRITICAL: 0x8B0000,  # Dark Red
            AlertSeverity.INFO: 0x007BFF,  # Blue
        }
        return colors.get(self, 0x808080)  # Default to gray


class AlertNode(Node):
    """
    Base class for all alert and notification nodes in the Kailash SDK.

    This abstract base class provides common functionality for sending alerts
    through various channels (Discord, Slack, email, webhooks, etc.). It defines
    standard parameters that all alert nodes should support and provides utilities
    for formatting messages consistently.

    Design Philosophy:
        Alert nodes should provide a simple, consistent interface for sending
        notifications while allowing channel-specific features when needed.
        The base class handles common concerns like severity levels, titles,
        and context data, while subclasses implement channel-specific logic.

    Common Parameters:
        - alert_type: Severity level (success, warning, error, critical, info)
        - title: Alert title/subject
        - message: Main alert message body
        - context: Additional structured data

    Subclasses must implement:
        - get_channel_parameters(): Define channel-specific parameters
        - send_alert(): Implement the actual alert sending logic
    """

    category = "alerts"

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define common parameters for all alert nodes.

        Returns:
            Dictionary of common alert parameters merged with channel-specific ones
        """
        common_params = {
            "alert_type": NodeParameter(
                name="alert_type",
                type=str,
                required=False,
                default="info",
                description="Alert severity level: success, warning, error, critical, info",
            ),
            "title": NodeParameter(
                name="title",
                type=str,
                required=True,
                description="Alert title or subject",
            ),
            "message": NodeParameter(
                name="message",
                type=str,
                required=False,
                default="",
                description="Main alert message body",
            ),
            "context": NodeParameter(
                name="context",
                type=dict,
                required=False,
                default={},
                description="Additional context data to include in the alert",
            ),
        }

        # Merge with channel-specific parameters
        channel_params = self.get_channel_parameters()
        return {**common_params, **channel_params}

    @abstractmethod
    def get_channel_parameters(self) -> dict[str, NodeParameter]:
        """Define channel-specific parameters.

        Subclasses must implement this to add their specific parameters
        like webhook URLs, authentication tokens, formatting options, etc.

        Returns:
            Dictionary of channel-specific parameters
        """
        pass

    def validate_alert_type(self, alert_type: str) -> AlertSeverity:
        """Validate and normalize the alert type.

        Args:
            alert_type: String representation of alert severity

        Returns:
            Normalized AlertSeverity enum value

        Raises:
            ValueError: If alert_type is not valid
        """
        try:
            return AlertSeverity(alert_type.lower())
        except ValueError:
            valid_types = [s.value for s in AlertSeverity]
            raise ValueError(
                f"Invalid alert_type '{alert_type}'. Must be one of: {', '.join(valid_types)}"
            )

    def format_context(self, context: dict[str, Any]) -> str:
        """Format context dictionary for display.

        Args:
            context: Dictionary of context data

        Returns:
            Formatted string representation of context
        """
        if not context:
            return ""

        lines = []
        for key, value in context.items():
            # Handle nested dictionaries and lists
            if isinstance(value, (dict, list)):
                import json

                value_str = json.dumps(value)  # No indent for single-line format
            else:
                value_str = str(value)

            lines.append(f"**{key}**: {value_str}")

        return "\n".join(lines)

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute the alert node.

        This method validates common parameters, normalizes the alert type,
        and delegates to the subclass's send_alert method.

        Args:
            **kwargs: Alert parameters including common and channel-specific ones

        Returns:
            Dictionary with alert execution results
        """
        # Validate and normalize alert type
        alert_type_str = kwargs.get("alert_type", "info")
        alert_severity = self.validate_alert_type(alert_type_str)

        # Extract common parameters
        title = kwargs["title"]
        message = kwargs.get("message", "")
        context = kwargs.get("context", {})

        # Extract channel-specific parameters only
        channel_params = {
            k: v
            for k, v in kwargs.items()
            if k not in ["alert_type", "title", "message", "context"]
        }

        # Call subclass implementation
        result = self.send_alert(
            severity=alert_severity,
            title=title,
            message=message,
            context=context,
            **channel_params,  # Pass only channel-specific params
        )

        # Add standard metadata to result
        result["alert_type"] = alert_severity.value
        result["title"] = title

        return result

    @abstractmethod
    def send_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        context: dict[str, Any],
        **kwargs,
    ) -> dict[str, Any]:
        """Send the alert through the specific channel.

        Subclasses must implement this method to handle the actual alert delivery.

        Args:
            severity: Normalized alert severity
            title: Alert title
            message: Alert message body
            context: Additional context data
            **kwargs: Channel-specific parameters

        Returns:
            Dictionary with channel-specific response data
        """
        pass
