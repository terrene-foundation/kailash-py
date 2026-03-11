# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Kaizen Trust Registry Module - Agent Discovery & Registration.

This module provides the AgentRegistry for discovering and registering
trusted agents across a multi-agent system.

Key Components:
- AgentRegistry: Central registry for agent discovery and registration
- AgentMetadata: Metadata about registered agents
- AgentStatus: Enum for agent status (ACTIVE, INACTIVE, REVOKED, SUSPENDED)
- DiscoveryQuery: Query builder for complex agent discovery
- AgentHealthMonitor: Background health monitoring for agents
- PostgresAgentRegistryStore: PostgreSQL persistence for registry

Example:
    from eatp.registry import (
        AgentRegistry,
        AgentMetadata,
        AgentStatus,
        RegistrationRequest,
        DiscoveryQuery,
        PostgresAgentRegistryStore,
    )

    # Initialize registry
    store = PostgresAgentRegistryStore(connection_string)
    registry = AgentRegistry(store, trust_operations)

    # Register an agent
    request = RegistrationRequest(
        agent_id="agent-001",
        agent_type="worker",
        capabilities=["analyze_data", "query_database"],
        constraints=["read_only"],
        trust_chain_hash=chain.compute_hash(),
    )
    metadata = await registry.register(request)

    # Discover agents by capability
    agents = await registry.find_by_capability("analyze_data")

    # Complex discovery
    query = DiscoveryQuery(
        capabilities=["analyze_data"],
        agent_type="worker",
        status=AgentStatus.ACTIVE,
    )
    results = await registry.discover(query)
"""

from eatp.registry.agent_registry import AgentRegistry, DiscoveryQuery
from eatp.registry.exceptions import (
    AgentAlreadyRegisteredError,
    AgentNotFoundError,
    RegistryError,
    TrustVerificationError,
    ValidationError,
)
from eatp.registry.health import AgentHealthMonitor, HealthStatus
from eatp.registry.models import AgentMetadata, AgentStatus, RegistrationRequest
from eatp.registry.store import AgentRegistryStore, PostgresAgentRegistryStore

__all__ = [
    # Models
    "AgentMetadata",
    "AgentStatus",
    "RegistrationRequest",
    # Store
    "AgentRegistryStore",
    "PostgresAgentRegistryStore",
    # Registry
    "AgentRegistry",
    "DiscoveryQuery",
    # Health
    "AgentHealthMonitor",
    "HealthStatus",
    # Exceptions
    "RegistryError",
    "AgentNotFoundError",
    "AgentAlreadyRegisteredError",
    "ValidationError",
    "TrustVerificationError",
]
