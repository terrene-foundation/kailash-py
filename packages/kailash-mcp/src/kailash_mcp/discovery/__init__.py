# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""MCP service discovery -- registry, health checking, load balancing."""

from kailash_mcp.discovery.discovery import (
    DiscoveryBackend,
    FileBasedDiscovery,
    HealthChecker,
    LoadBalancer,
    NetworkDiscovery,
    ServerInfo,
    ServiceMesh,
    ServiceRegistry,
    create_default_registry,
    discover_mcp_servers,
    get_mcp_client,
)
from kailash_mcp.discovery.registry_integration import (
    NetworkAnnouncer,
    ServerRegistrar,
    enable_auto_discovery,
    register_server_manually,
)

__all__ = [
    "ServiceRegistry",
    "ServerInfo",
    "DiscoveryBackend",
    "FileBasedDiscovery",
    "NetworkDiscovery",
    "HealthChecker",
    "LoadBalancer",
    "ServiceMesh",
    "create_default_registry",
    "discover_mcp_servers",
    "get_mcp_client",
    "ServerRegistrar",
    "NetworkAnnouncer",
    "enable_auto_discovery",
    "register_server_manually",
]
