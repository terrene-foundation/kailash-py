"""Alert and notification nodes for the Kailash SDK.

This module provides specialized nodes for sending alerts and notifications
through various channels. Each alert node follows a consistent interface while
providing channel-specific features and optimizations.

The module includes:
- Base alert node infrastructure
- Discord webhook integration
- (Future) Slack, email, webhook, and other integrations

Design Philosophy:
- Provide purpose-built nodes for common alert patterns
- Abstract channel-specific complexity
- Support both simple and advanced use cases
- Enable consistent alert formatting across channels
"""

from .base import AlertNode, AlertSeverity
from .discord import DiscordAlertNode

__all__ = [
    "AlertNode",
    "AlertSeverity",
    "DiscordAlertNode",
]
