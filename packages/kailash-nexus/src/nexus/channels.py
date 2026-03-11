"""Channel configuration for Nexus.

This module provides convenience configuration helpers for the SDK's
enterprise channels. The actual channel implementations are provided
by the Kailash SDK.

NOTE: This module is kept minimal - the enterprise gateway handles
most channel functionality automatically.
"""

import asyncio
import logging
import socket
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ChannelConfig:
    """Configuration for a single channel."""

    enabled: bool = True
    port: Optional[int] = None
    host: str = "0.0.0.0"
    additional_config: Dict[str, Any] = None

    def __post_init__(self):
        if self.additional_config is None:
            self.additional_config = {}


class ChannelManager:
    """Manages configuration and initialization of all channels."""

    # Default ports for channels
    DEFAULT_PORTS = {
        "api": 8000,
        "mcp": 3001,
        "cli": None,  # CLI doesn't need a port
    }

    def __init__(self):
        """Initialize channel manager."""
        self._channels: Dict[str, ChannelConfig] = {}
        self._initialize_defaults()
        self._session_manager = None

    def _initialize_defaults(self):
        """Initialize default channel configurations."""
        self._channels["api"] = ChannelConfig(
            port=self.DEFAULT_PORTS["api"],
            additional_config={
                "docs_enabled": True,
                "cors_enabled": True,
            },
        )

        self._channels["cli"] = ChannelConfig(
            port=None,  # CLI doesn't use ports
            additional_config={
                "interactive": True,
                "color": True,
            },
        )

        self._channels["mcp"] = ChannelConfig(
            port=self.DEFAULT_PORTS["mcp"],
            additional_config={
                "transport": "stdio",
                "version": "1.0",
            },
        )

    def configure_api(self, **kwargs) -> ChannelConfig:
        """Configure API channel.

        Args:
            **kwargs: Configuration overrides

        Returns:
            Updated API channel configuration
        """
        config = self._channels["api"]

        # Apply overrides
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.additional_config[key] = value

        # Ensure port is available
        if config.port:
            config.port = find_available_port(config.port)

        logger.info(f"API channel configured on port {config.port}")
        return config

    def configure_cli(self, **kwargs) -> ChannelConfig:
        """Configure CLI channel.

        Args:
            **kwargs: Configuration overrides

        Returns:
            Updated CLI channel configuration
        """
        config = self._channels["cli"]

        # Apply overrides
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.additional_config[key] = value

        logger.info("CLI channel configured")
        return config

    def configure_mcp(self, **kwargs) -> ChannelConfig:
        """Configure MCP channel.

        Args:
            **kwargs: Configuration overrides

        Returns:
            Updated MCP channel configuration
        """
        config = self._channels["mcp"]

        # Apply overrides
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
            else:
                config.additional_config[key] = value

        # Ensure port is available if using network transport
        if config.port and config.additional_config.get("transport") != "stdio":
            config.port = find_available_port(config.port)

        logger.info(f"MCP channel configured on port {config.port}")
        return config

    def get_channel_config(self, channel: str) -> Optional[ChannelConfig]:
        """Get configuration for a specific channel.

        Args:
            channel: Channel name (api, cli, mcp)

        Returns:
            Channel configuration or None
        """
        return self._channels.get(channel)

    def create_unified_channels(self) -> Dict[str, Any]:
        """Create unified channel configuration for gateway.

        Returns:
            Unified configuration dictionary
        """
        unified = {
            "channels": {},
            "health_endpoint": "/health",
            "enable_docs": True,
        }

        # Add API channel
        if self._channels["api"].enabled:
            unified["channels"]["api"] = {
                "enabled": True,
                "port": self._channels["api"].port,
                "host": self._channels["api"].host,
                **self._channels["api"].additional_config,
            }

        # Add CLI channel
        if self._channels["cli"].enabled:
            unified["channels"]["cli"] = {
                "enabled": True,
                **self._channels["cli"].additional_config,
            }

        # Add MCP channel
        if self._channels["mcp"].enabled:
            unified["channels"]["mcp"] = {
                "enabled": True,
                "port": self._channels["mcp"].port,
                **self._channels["mcp"].additional_config,
            }

        return unified

    # NOTE: initialize_channels() method removed - redundant with gateway initialization
    # Channels are initialized automatically by:
    # - Enterprise gateway (API channel) - see Nexus._initialize_gateway()
    # - MCPServer/MCPChannel (MCP channel) - see Nexus._initialize_mcp_server()
    # - CLI doesn't need server initialization (local command execution)

    def configure_health_endpoint(self, endpoint: str = "/health") -> Dict[str, Any]:
        """Configure health check endpoint.

        Args:
            endpoint: Health endpoint path

        Returns:
            Health endpoint configuration
        """
        return {
            "path": endpoint,
            "methods": ["GET"],
            "response": {
                "status": "healthy",
                "channels": self._get_channel_status(),
            },
        }

    def _get_channel_status(self) -> Dict[str, bool]:
        """Get status of all channels.

        Returns:
            Dictionary of channel status
        """
        return {channel: config.enabled for channel, config in self._channels.items()}

    # NOTE: register_workflow_on_channels() method removed - duplicate of Nexus.register() logic
    # Workflow registration across channels is handled by Nexus.register() which calls:
    # - gateway.register_workflow() for API channel (REST endpoints)
    # - mcp_channel.register_workflow() for MCP channel (MCP tools)
    # - CLI access is automatic via gateway's workflow registry

    def create_session_manager(self) -> "SessionManager":
        """Create a session manager for cross-channel sync.

        Returns:
            SessionManager instance
        """
        if not self._session_manager:
            self._session_manager = SessionManager()
        return self._session_manager


class SessionManager:
    """Manages sessions across channels for synchronization."""

    def __init__(self):
        """Initialize session manager."""
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._sync_enabled = True

    def create_session(self, session_id: str, channel: str) -> Dict[str, Any]:
        """Create a new session.

        Args:
            session_id: Unique session identifier
            channel: Channel that created the session

        Returns:
            Session data
        """
        session = {
            "id": session_id,
            "created_by": channel,
            "data": {},
            "channels": [channel],
        }
        self._sessions[session_id] = session
        return session

    def sync_session(self, session_id: str, channel: str) -> Optional[Dict[str, Any]]:
        """Sync session data across channels.

        Args:
            session_id: Session to sync
            channel: Channel requesting sync

        Returns:
            Session data or None
        """
        if not self._sync_enabled:
            return None

        session = self._sessions.get(session_id)
        if session and channel not in session["channels"]:
            session["channels"].append(channel)

        return session

    def update_session(self, session_id: str, data: Dict[str, Any]) -> None:
        """Update session data.

        Args:
            session_id: Session to update
            data: Data to merge into session
        """
        if session_id in self._sessions:
            self._sessions[session_id]["data"].update(data)


def find_available_port(preferred_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from preferred port.

    Args:
        preferred_port: Preferred port number
        max_attempts: Maximum number of ports to try

    Returns:
        Available port number
    """
    for offset in range(max_attempts):
        port = preferred_port + offset
        if is_port_available(port):
            if offset > 0:
                logger.info(f"Port {preferred_port} unavailable, using {port}")
            return port

    raise RuntimeError(f"No available ports found starting from {preferred_port}")


def is_port_available(port: int) -> bool:
    """Check if a port is available.

    Args:
        port: Port number to check

    Returns:
        True if port is available
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("", port))
            return True
        except (OSError, socket.error):
            return False


# Global channel manager
_channel_manager = None


def get_channel_manager() -> ChannelManager:
    """Get or create the global channel manager.

    Returns:
        Global ChannelManager instance
    """
    global _channel_manager
    if _channel_manager is None:
        _channel_manager = ChannelManager()
    return _channel_manager


# Convenience functions for direct access
def configure_api(**kwargs) -> ChannelConfig:
    """Configure API channel."""
    return get_channel_manager().configure_api(**kwargs)


def configure_cli(**kwargs) -> ChannelConfig:
    """Configure CLI channel."""
    return get_channel_manager().configure_cli(**kwargs)


def configure_mcp(**kwargs) -> ChannelConfig:
    """Configure MCP channel."""
    return get_channel_manager().configure_mcp(**kwargs)


def create_unified_channels() -> Dict[str, Any]:
    """Create unified channel configuration."""
    return get_channel_manager().create_unified_channels()


# NOTE: initialize_channels() module function removed - redundant with gateway initialization
# See ChannelManager class for explanation


def configure_health_endpoint(endpoint: str = "/health") -> Dict[str, Any]:
    """Configure health endpoint."""
    return get_channel_manager().configure_health_endpoint(endpoint)


# NOTE: register_workflow_on_channels() module function removed - duplicate logic
# See ChannelManager class for explanation


def create_session_manager() -> SessionManager:
    """Create session manager."""
    return get_channel_manager().create_session_manager()
