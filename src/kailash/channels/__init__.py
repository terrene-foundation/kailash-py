"""Channel abstractions for Nexus multi-channel architecture.

This module provides the core channel abstractions for the Kailash Nexus framework,
enabling unified management of API, CLI, and MCP interfaces through a common channel abstraction.
"""

from .api_channel import APIChannel
from .base import Channel, ChannelConfig, ChannelType
from .cli_channel import CLIChannel
from .mcp_channel import MCPChannel
from .session import CrossChannelSession, SessionManager

__all__ = [
    "Channel",
    "ChannelConfig",
    "ChannelType",
    "APIChannel",
    "CLIChannel",
    "MCPChannel",
    "SessionManager",
    "CrossChannelSession",
]
