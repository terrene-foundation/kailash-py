"""
Kaizen MCP Integration

This package contains MCP (Model Context Protocol) server implementations
for Kaizen framework.

Sub-packages:
- builtin_server: MCP server providing Kaizen's 12 builtin tools
"""

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EnterpriseFeatures:
    """Enterprise MCP server features configuration."""

    authentication: str = "none"
    audit_trail: bool = False
    monitoring_enabled: bool = False
    security_level: str = "standard"
    multi_tenant: bool = False
    load_balancing: str = "none"
    encryption: Optional[Dict[str, Any]] = None
    compliance: List[str] = field(default_factory=list)


@dataclass
class MCPServerConfig:
    """Configuration for MCP server exposure.

    Attributes:
        server_name: Name of the MCP server
        port: Port to run server on
        server_id: Unique server identifier (auto-generated)
        exposed_tools: List of tools to expose
        capabilities: List of capabilities
        auth_type: Authentication type
        auth_config: Authentication configuration
        auto_discovery: Enable auto-discovery
        enterprise_features: Enterprise features configuration
        server_state: Current server state
        error_message: Error message if server failed
    """

    server_name: str = "kaizen-mcp-server"
    port: int = 8080
    server_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    exposed_tools: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    auth_type: str = "none"
    auth_config: Dict[str, Any] = field(default_factory=dict)
    auto_discovery: bool = False
    enterprise_features: Optional[EnterpriseFeatures] = None
    server_state: str = "initialized"
    error_message: Optional[str] = None

    def start_server(self) -> bool:
        """Start the MCP server (state tracking).

        This method updates the server state to "running". The actual MCP server
        is run as an external process (e.g., `python -m kaizen.mcp.builtin_server`).
        This configuration object tracks the intended state for management purposes.

        Returns:
            True if state updated successfully
        """
        self.server_state = "running"
        return True

    def stop_server(self) -> bool:
        """Stop the MCP server (state tracking).

        This method updates the server state to "stopped". If an external MCP
        server process is running, it should be terminated separately.

        Returns:
            True if state updated successfully
        """
        self.server_state = "stopped"
        return True


__all__ = [
    "EnterpriseFeatures",
    "MCPServerConfig",
]
