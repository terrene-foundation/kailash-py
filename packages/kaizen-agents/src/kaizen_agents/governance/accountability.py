# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""D/T/R Accountability -- positional addressing for agent hierarchies.

Maps each spawned agent to a PACT D/T/R positional address based on its
lineage. The root agent gets D1-R1; children get parent_address-T{n}-R1
where n is the child sequence number under that parent.

This bridges the kailash-kaizen AgentFactory hierarchy with PACT's
accountability grammar, enabling governance queries like:
  "Who defined the envelope that governs this action?"
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from pact.governance.addressing import Address

logger = logging.getLogger(__name__)

__all__ = [
    "AccountabilityTracker",
    "AccountabilityRecord",
]


@dataclass(frozen=True)
class AccountabilityRecord:
    """Maps an agent instance to its positional address and governance lineage.

    Attributes:
        instance_id: The agent's unique instance ID.
        address: The D/T/R positional address.
        parent_id: Parent instance ID, or None for root.
        envelope_snapshot: The envelope assigned at spawn time (for audit).
        policy_source: Who defined the governing envelope (human role address).
    """

    instance_id: str
    address: Address
    parent_id: str | None
    envelope_snapshot: dict[str, Any] = field(default_factory=dict)
    policy_source: str = ""


class AccountabilityTracker:
    """Tracks D/T/R positional addresses for all agents in a hierarchy.

    Thread-safe. All public methods acquire self._lock.

    Usage:
        tracker = AccountabilityTracker()
        root = tracker.register_root("root-001", envelope={...})
        child = tracker.register_child("child-001", parent_id="root-001", envelope={...})
        addr = tracker.get_address("child-001")  # Address("D1-R1-T1-R1")
    """

    def __init__(self, max_agents: int = 100_000) -> None:
        self._lock = threading.Lock()
        self._max_agents = max_agents
        self._records: dict[str, AccountabilityRecord] = {}
        self._child_counters: dict[str, int] = {}  # parent_id -> next child seq

    def register_root(
        self,
        instance_id: str,
        envelope: dict[str, Any] | None = None,
        policy_source: str = "",
    ) -> AccountabilityRecord:
        """Register the root agent with address D1-R1.

        Args:
            instance_id: The root agent's instance ID.
            envelope: The envelope assigned to the root agent.
            policy_source: Who defined the root envelope (human role address).

        Returns:
            The AccountabilityRecord for the root agent.

        Raises:
            ValueError: If instance_id is already registered.
        """
        with self._lock:
            if instance_id in self._records:
                raise ValueError(f"Agent '{instance_id}' is already registered")
            if len(self._records) >= self._max_agents:
                raise ValueError(
                    f"Agent registration limit ({self._max_agents}) reached. "
                    f"Cannot register '{instance_id}'."
                )

            address = Address.parse("D1-R1")
            record = AccountabilityRecord(
                instance_id=instance_id,
                address=address,
                parent_id=None,
                envelope_snapshot=envelope or {},
                policy_source=policy_source,
            )
            self._records[instance_id] = record
            self._child_counters[instance_id] = 0

            logger.info(
                "Registered root agent %s at address %s",
                instance_id,
                address,
            )
            return record

    def register_child(
        self,
        instance_id: str,
        parent_id: str,
        envelope: dict[str, Any] | None = None,
        policy_source: str = "",
    ) -> AccountabilityRecord:
        """Register a child agent with address parent_address-T{n}-R1.

        Args:
            instance_id: The child agent's instance ID.
            parent_id: The parent agent's instance ID.
            envelope: The envelope assigned to the child.
            policy_source: Who defined the child's envelope.

        Returns:
            The AccountabilityRecord for the child agent.

        Raises:
            ValueError: If instance_id already registered or parent_id unknown.
        """
        with self._lock:
            if instance_id in self._records:
                raise ValueError(f"Agent '{instance_id}' is already registered")
            if parent_id not in self._records:
                raise ValueError(f"Parent '{parent_id}' is not registered")
            if len(self._records) >= self._max_agents:
                raise ValueError(
                    f"Agent registration limit ({self._max_agents}) reached. "
                    f"Cannot register '{instance_id}'."
                )

            # Increment child counter for parent
            self._child_counters.setdefault(parent_id, 0)
            self._child_counters[parent_id] += 1
            seq = self._child_counters[parent_id]

            # Build child address: parent_address-T{seq}-R1
            parent_addr = self._records[parent_id].address
            child_addr_str = f"{parent_addr}-T{seq}-R1"
            child_address = Address.parse(child_addr_str)

            # If no explicit policy_source, inherit from parent
            if not policy_source:
                policy_source = self._records[parent_id].policy_source

            record = AccountabilityRecord(
                instance_id=instance_id,
                address=child_address,
                parent_id=parent_id,
                envelope_snapshot=envelope or {},
                policy_source=policy_source,
            )
            self._records[instance_id] = record
            self._child_counters[instance_id] = 0

            logger.info(
                "Registered child agent %s at address %s (parent=%s)",
                instance_id,
                child_address,
                parent_id,
            )
            return record

    def get_address(self, instance_id: str) -> Address | None:
        """Get the D/T/R address for an agent.

        Args:
            instance_id: The agent's instance ID.

        Returns:
            The Address, or None if not registered.
        """
        with self._lock:
            record = self._records.get(instance_id)
            return record.address if record is not None else None

    def get_record(self, instance_id: str) -> AccountabilityRecord | None:
        """Get the full accountability record for an agent.

        Args:
            instance_id: The agent's instance ID.

        Returns:
            The AccountabilityRecord, or None if not registered.
        """
        with self._lock:
            return self._records.get(instance_id)

    def get_siblings(self, instance_id: str) -> list[AccountabilityRecord]:
        """Find siblings -- agents with the same parent.

        Args:
            instance_id: The agent to find siblings for.

        Returns:
            List of sibling AccountabilityRecords (excluding self).
        """
        with self._lock:
            record = self._records.get(instance_id)
            if record is None or record.parent_id is None:
                return []

            return [
                r
                for r in self._records.values()
                if r.parent_id == record.parent_id and r.instance_id != instance_id
            ]

    def trace_accountability(self, instance_id: str) -> list[AccountabilityRecord]:
        """Trace the accountability chain from root to the given agent.

        Returns the ordered list of records from root → ... → agent.

        Args:
            instance_id: The agent to trace.

        Returns:
            Ordered list of AccountabilityRecords from root to agent.
            Empty list if instance_id is not registered.
        """
        with self._lock:
            chain: list[AccountabilityRecord] = []
            current_id: str | None = instance_id
            visited: set[str] = set()

            while current_id is not None:
                if current_id in visited:
                    break  # R1-08: Cycle detected, stop traversal
                visited.add(current_id)
                record = self._records.get(current_id)
                if record is None:
                    break
                chain.append(record)
                current_id = record.parent_id

            chain.reverse()
            return chain

    def query_policy_source(self, instance_id: str) -> str:
        """Given an agent, identify who defined the governing envelope.

        Walks up the accountability chain to find the nearest policy_source.

        Args:
            instance_id: The agent to query.

        Returns:
            The policy_source string, or "" if no source found.
        """
        with self._lock:
            current_id: str | None = instance_id
            visited: set[str] = set()
            while current_id is not None:
                if current_id in visited:
                    break  # R1-08: Cycle detected, stop traversal
                visited.add(current_id)
                record = self._records.get(current_id)
                if record is None:
                    break
                if record.policy_source:
                    return record.policy_source
                current_id = record.parent_id
            return ""

    def unregister(self, instance_id: str) -> None:
        """Remove an agent from tracking (e.g., on termination).

        Args:
            instance_id: The agent to unregister.
        """
        with self._lock:
            self._records.pop(instance_id, None)
            self._child_counters.pop(instance_id, None)

    @property
    def agent_count(self) -> int:
        """Number of currently tracked agents."""
        with self._lock:
            return len(self._records)
