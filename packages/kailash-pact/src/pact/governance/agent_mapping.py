# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""AgentRoleMapping -- maps agent IDs to D/T/R role addresses.

Bridge between "agent X is running" and "agent X occupies role D1-R1-D2-R1-T1-R1".
Thread-safe for concurrent lookups per governance.md Rule 5.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pact.governance.compilation import CompiledOrg

logger = logging.getLogger(__name__)

__all__ = ["AgentRoleMapping"]


class AgentRoleMapping:
    """Maps agent IDs to D/T/R role addresses.

    Bridge between "agent X is running" and "agent X occupies role D1-R1-D2-R1-T1-R1".
    Thread-safe for concurrent lookups.

    All public methods acquire self._lock before reading or writing internal state,
    per governance.md Rule 5 (Thread-Safe Stores).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agent_to_address: dict[str, str] = {}
        self._address_to_agent: dict[str, str] = {}

    @classmethod
    def from_org(cls, compiled_org: CompiledOrg) -> AgentRoleMapping:
        """Build mapping from compiled org (roles with agent_id field).

        Iterates all nodes in the compiled organization. For each node that has a
        role_definition with an agent_id, registers the bidirectional mapping.

        Args:
            compiled_org: A compiled organization with positional addresses assigned.

        Returns:
            A new AgentRoleMapping populated from the org's role definitions.
        """
        mapping = cls()
        for address, node in compiled_org.nodes.items():
            if node.role_definition and node.role_definition.agent_id:
                mapping.register(node.role_definition.agent_id, address)
        return mapping

    def register(self, agent_id: str, role_address: str) -> None:
        """Register an agent-to-address mapping. Thread-safe.

        If the agent_id was previously registered to a different address, the old
        mapping is overwritten. The old address's reverse mapping is also removed.

        Args:
            agent_id: The unique identifier of the agent.
            role_address: The D/T/R positional address the agent occupies.
        """
        with self._lock:
            # Remove stale reverse mapping if agent was previously at a different address
            old_address = self._agent_to_address.get(agent_id)
            if old_address is not None and old_address != role_address:
                self._address_to_agent.pop(old_address, None)

            self._agent_to_address[agent_id] = role_address
            self._address_to_agent[role_address] = agent_id

    def get_address(self, agent_id: str) -> str | None:
        """Get the D/T/R address for an agent ID.

        Args:
            agent_id: The agent identifier to look up.

        Returns:
            The positional address, or None if the agent is not registered.
        """
        with self._lock:
            return self._agent_to_address.get(agent_id)

    def get_agent(self, role_address: str) -> str | None:
        """Get the agent ID occupying a role address.

        Args:
            role_address: The D/T/R positional address to look up.

        Returns:
            The agent ID, or None if no agent is registered at this address.
        """
        with self._lock:
            return self._address_to_agent.get(role_address)

    def resolve(self, agent_id_or_address: str) -> str:
        """Resolve to address: if it's an agent ID, look up; if it's already an address, return it.

        Resolution order:
        1. Check if the string is a registered agent ID -- return mapped address.
        2. Check if the string contains D/T/R address segments -- treat as passthrough.
        3. Otherwise, raise ValueError.

        Args:
            agent_id_or_address: Either an agent ID or a D/T/R positional address.

        Returns:
            The resolved D/T/R address.

        Raises:
            ValueError: If the string cannot be resolved to a role address.
        """
        with self._lock:
            # 1. Check if it's a registered agent ID
            if agent_id_or_address in self._agent_to_address:
                return self._agent_to_address[agent_id_or_address]

            # 2. Check if it looks like a D/T/R address (contains D, T, or R segments)
            if any(c in agent_id_or_address for c in ("D", "T", "R")):
                return agent_id_or_address

            # 3. Unresolvable
            raise ValueError(
                f"Cannot resolve '{agent_id_or_address}' to a role address. "
                f"It is not a registered agent ID and does not contain D/T/R segments. "
                f"Registered agent IDs: {sorted(self._agent_to_address.keys())}"
            )
