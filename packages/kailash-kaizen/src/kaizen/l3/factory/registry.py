# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AgentInstanceRegistry — thread-safe registry for agent instance tracking.

Uses asyncio.Lock per AD-L3-04-AMENDED (L3 primitives are exclusively
called from async code paths). Maintains three internal indexes for
efficient lookup by instance_id, parent_id, and spec_id.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from kaizen.l3.factory.errors import InstanceNotFound, RegistryError
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
)

__all__ = ["AgentInstanceRegistry"]

logger = logging.getLogger(__name__)


class AgentInstanceRegistry:
    """Thread-safe registry tracking all agent instances.

    Internal indexes (implementation-private):
        _instances: dict[str, AgentInstance] — primary index by instance_id
        _children: dict[str, list[str]] — parent_id -> child instance_ids
        _by_spec: dict[str, list[str]] — spec_id -> instance_ids

    All mutations are serialized behind an asyncio.Lock.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._instances: dict[str, AgentInstance] = {}
        self._children: dict[str, list[str]] = {}
        self._by_spec: dict[str, list[str]] = {}

    async def register(self, instance: AgentInstance) -> None:
        """Register a new instance. Fails if instance_id already exists.

        Args:
            instance: The AgentInstance to register.

        Raises:
            RegistryError: If an instance with the same ID already exists.
        """
        async with self._lock:
            if instance.instance_id in self._instances:
                raise RegistryError(
                    f"Duplicate instance_id: '{instance.instance_id}' "
                    f"already exists in registry"
                )
            self._instances[instance.instance_id] = instance

            # Update children index
            if instance.parent_id is not None:
                if instance.parent_id not in self._children:
                    self._children[instance.parent_id] = []
                self._children[instance.parent_id].append(instance.instance_id)

            # Update spec index
            if instance.spec_id not in self._by_spec:
                self._by_spec[instance.spec_id] = []
            self._by_spec[instance.spec_id].append(instance.instance_id)

            logger.debug(
                "Registered instance %s (spec=%s, parent=%s)",
                instance.instance_id,
                instance.spec_id,
                instance.parent_id,
            )

    async def deregister(self, instance_id: str) -> AgentInstance:
        """Remove a terminal instance from the registry.

        Args:
            instance_id: The ID of the instance to deregister.

        Returns:
            The removed AgentInstance.

        Raises:
            InstanceNotFound: If no instance with the ID exists.
            RegistryError: If the instance is not in a terminal state.
        """
        async with self._lock:
            if instance_id not in self._instances:
                raise InstanceNotFound(instance_id)

            instance = self._instances[instance_id]
            if not instance.is_terminal:
                raise RegistryError(
                    f"Cannot deregister instance '{instance_id}': "
                    f"not in a terminal state (current: {instance.state.name})"
                )

            del self._instances[instance_id]

            # Remove from children index
            if instance.parent_id is not None:
                children_list = self._children.get(instance.parent_id, [])
                if instance_id in children_list:
                    children_list.remove(instance_id)
                    if not children_list:
                        del self._children[instance.parent_id]

            # Remove from spec index
            spec_list = self._by_spec.get(instance.spec_id, [])
            if instance_id in spec_list:
                spec_list.remove(instance_id)
                if not spec_list:
                    del self._by_spec[instance.spec_id]

            # Clean up children index entry for this instance
            if instance_id in self._children:
                del self._children[instance_id]

            logger.debug("Deregistered instance %s", instance_id)
            return instance

    async def get(self, instance_id: str) -> AgentInstance:
        """Look up an instance by ID.

        Args:
            instance_id: The instance ID to look up.

        Returns:
            The AgentInstance.

        Raises:
            InstanceNotFound: If no instance with the ID exists.
        """
        async with self._lock:
            if instance_id not in self._instances:
                raise InstanceNotFound(instance_id)
            return self._instances[instance_id]

    async def children_of(self, parent_id: str) -> list[AgentInstance]:
        """Return direct children of a parent instance.

        Args:
            parent_id: The parent instance ID.

        Returns:
            List of child AgentInstance objects. Empty if no children
            or parent does not exist.
        """
        async with self._lock:
            child_ids = self._children.get(parent_id, [])
            return [self._instances[cid] for cid in child_ids if cid in self._instances]

    async def lineage(self, instance_id: str) -> list[str]:
        """Return the root-to-instance ancestry path.

        Args:
            instance_id: The instance to trace lineage for.

        Returns:
            List of instance_ids from root to the given instance.

        Raises:
            InstanceNotFound: If the instance does not exist.
        """
        async with self._lock:
            if instance_id not in self._instances:
                raise InstanceNotFound(instance_id)

            path: list[str] = []
            current_id: str | None = instance_id
            while current_id is not None:
                if current_id not in self._instances:
                    break
                path.append(current_id)
                current_id = self._instances[current_id].parent_id

            path.reverse()
            return path

    async def all_descendants(self, instance_id: str) -> list[str]:
        """Return all descendants of an instance via BFS.

        Args:
            instance_id: The root instance to find descendants of.

        Returns:
            List of descendant instance_ids (not including the root).
        """
        async with self._lock:
            result: list[str] = []
            queue: deque[str] = deque()

            # Seed with direct children
            for child_id in self._children.get(instance_id, []):
                if child_id in self._instances:
                    queue.append(child_id)

            while queue:
                current = queue.popleft()
                result.append(current)
                for child_id in self._children.get(current, []):
                    if child_id in self._instances:
                        queue.append(child_id)

            return result

    async def count_live(self) -> int:
        """Return the count of non-terminal instances.

        Returns:
            Number of instances not in a terminal state.
        """
        async with self._lock:
            return sum(1 for inst in self._instances.values() if not inst.is_terminal)

    async def update_state(
        self, instance_id: str, new_state: AgentLifecycleState
    ) -> None:
        """Update an instance's lifecycle state with transition validation.

        Delegates to instance.transition_to() which validates the transition
        against the state machine rules.

        Args:
            instance_id: The instance to update.
            new_state: The target state.

        Raises:
            InstanceNotFound: If no instance with the ID exists.
            InvalidStateTransitionError: If the transition is not valid.
        """
        async with self._lock:
            if instance_id not in self._instances:
                raise InstanceNotFound(instance_id)
            self._instances[instance_id].transition_to(new_state)
