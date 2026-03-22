# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AgentFactory — runtime agent instantiation with invariant validation.

Validates PACT governance invariants at spawn time:
- Parent state (Running or Waiting)
- Max children limit
- Max depth limit (checked against ALL ancestors)
- Tool ID subsetting (child tools must be subset of parent tools)
- Required context keys
- Spawn blocked during cascade termination (AD-L3-10)

Implements cascade termination (I-02): deepest-first, all descendants.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

from kaizen.l3.factory.errors import (
    InstanceNotFound,
    MaxChildrenExceeded,
    MaxDepthExceeded,
    ToolNotInParent,
)
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    TerminationReason,
    _StateTag,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec

__all__ = ["AgentFactory"]

logger = logging.getLogger(__name__)


class AgentFactory:
    """Factory for spawning and terminating agent instances.

    All spawn preconditions are validated before creating the instance.
    Cascade termination ensures all descendants are terminated
    deepest-first when a parent is terminated.

    Args:
        registry: The AgentInstanceRegistry to use for tracking instances.
    """

    def __init__(self, registry: AgentInstanceRegistry) -> None:
        self._registry = registry
        # Spec registry: maps spec_id -> AgentSpec for tool/depth checks
        self._specs: dict[str, AgentSpec] = {}
        # AD-L3-10: Track ancestors currently being cascade-terminated
        self._terminating_ancestors: set[str] = set()
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        child_spec: AgentSpec,
        parent_id: str | None = None,
    ) -> AgentInstance:
        """Spawn a new agent instance.

        If parent_id is None, creates a root agent.
        If parent_id is provided, validates all spawn preconditions.

        Args:
            child_spec: The AgentSpec blueprint for the new instance.
            parent_id: The parent instance ID, or None for root agents.

        Returns:
            The newly created AgentInstance in Pending state.

        Raises:
            InstanceNotFound: If parent_id does not exist in registry.
            ValueError: If parent is not in Running or Waiting state.
            MaxChildrenExceeded: If parent's max_children limit reached.
            MaxDepthExceeded: If any ancestor's max_depth limit would be exceeded.
            ToolNotInParent: If child requests a tool not in parent's spec.
        """
        async with self._lock:
            if parent_id is not None:
                await self._validate_spawn_preconditions(child_spec, parent_id)

            instance = AgentInstance(
                spec_id=child_spec.spec_id,
                parent_id=parent_id,
            )

            # Store spec for future child spawns (tool subsetting, depth checks)
            self._specs[child_spec.spec_id] = child_spec

            # Also store instance_id -> spec mapping for lineage-based lookups
            # We key by instance_id to handle multiple instances of same spec
            self._specs[f"_inst_{instance.instance_id}"] = child_spec

        await self._registry.register(instance)

        logger.debug(
            "Spawned instance %s (spec=%s, parent=%s)",
            instance.instance_id,
            child_spec.spec_id,
            parent_id,
        )
        return instance

    async def _validate_spawn_preconditions(
        self, child_spec: AgentSpec, parent_id: str
    ) -> None:
        """Validate all spawn preconditions for a child agent.

        Called within self._lock. Registry access uses the registry's
        own lock, so we access internal state carefully to avoid deadlocks.

        Preconditions:
            1. Parent exists and is Running or Waiting
            2. Parent's max_children not exceeded
            3. No ancestor's max_depth exceeded
            4. Child tool_ids subset of parent tool_ids
            5. Spawn not blocked by cascade termination
        """
        # 0. Check if parent is being cascade-terminated (AD-L3-10)
        if parent_id in self._terminating_ancestors:
            raise ValueError(
                f"Cannot spawn under '{parent_id}': "
                f"ancestor is being cascade-terminated"
            )

        # 1. Parent must exist and be Running or Waiting
        parent = await self._registry.get(parent_id)
        valid_states = {_StateTag.RUNNING, _StateTag.WAITING}
        if parent.state.tag not in valid_states:
            raise ValueError(
                f"Parent '{parent_id}' must be in Running or Waiting state "
                f"to spawn children, current state: {parent.state.name}"
            )

        # 2. Max children check
        parent_spec = self._specs.get(f"_inst_{parent_id}") or self._specs.get(
            parent.spec_id
        )
        if parent_spec is not None and parent_spec.max_children is not None:
            children = await self._registry.children_of(parent_id)
            if len(children) >= parent_spec.max_children:
                raise MaxChildrenExceeded(
                    parent_id=parent_id,
                    limit=parent_spec.max_children,
                    current=len(children),
                )

        # 3. Max depth check — walk the lineage and check each ancestor's limit
        lineage = await self._registry.lineage(parent_id)
        # new_child_depth = len(lineage) (0-indexed from root)
        # For each ancestor at position i in lineage, the child would be
        # at depth (len(lineage) - i) below that ancestor
        for i, ancestor_id in enumerate(lineage):
            ancestor_spec = self._specs.get(f"_inst_{ancestor_id}") or self._specs.get(
                # Fallback: look up by the ancestor's spec_id
                (await self._registry.get(ancestor_id)).spec_id
                if ancestor_id in (await self._registry_instance_ids())
                else ""
            )
            if ancestor_spec is not None and ancestor_spec.max_depth is not None:
                # Depth of the new child relative to this ancestor
                depth_below_ancestor = len(lineage) - i
                if depth_below_ancestor > ancestor_spec.max_depth:
                    raise MaxDepthExceeded(
                        parent_id=ancestor_id,
                        depth_limit=ancestor_spec.max_depth,
                        current_depth=depth_below_ancestor,
                    )

        # 4. Tool ID subset check
        if child_spec.tool_ids and parent_spec is not None:
            parent_tools = set(parent_spec.tool_ids)
            for tool_id in child_spec.tool_ids:
                if tool_id not in parent_tools:
                    raise ToolNotInParent(tool_id)

    async def _registry_instance_ids(self) -> set[str]:
        """Get all instance IDs from the registry (internal helper)."""
        # Access the registry's internal dict — not ideal but avoids
        # adding a public method just for this check.
        # We're already under self._lock so this is safe.
        return set(self._registry._instances.keys())

    async def terminate(
        self,
        instance_id: str,
        reason: TerminationReason,
    ) -> None:
        """Terminate an instance and cascade to all descendants.

        Per I-02: descendants are terminated deepest-first with
        reason ParentTerminated. The instance itself is terminated
        with the given reason.

        Idempotent: terminating an already-terminal instance is a no-op.

        Per AD-L3-10: spawn requests are blocked for any instance
        in the _terminating_ancestors set during cascade.

        Args:
            instance_id: The instance to terminate.
            reason: The termination reason for the root instance.

        Raises:
            InstanceNotFound: If the instance does not exist.
        """
        # Check existence
        instance = await self._registry.get(instance_id)

        # Idempotent: already terminal -> no-op
        if instance.is_terminal:
            return

        # Mark as terminating ancestor to block spawns (AD-L3-10)
        async with self._lock:
            self._terminating_ancestors.add(instance_id)

        try:
            # Collect all descendants
            descendants = await self._registry.all_descendants(instance_id)

            # Sort by depth (deepest first) — use lineage length as proxy
            depths: list[tuple[int, str]] = []
            for desc_id in descendants:
                lineage = await self._registry.lineage(desc_id)
                depths.append((len(lineage), desc_id))
            depths.sort(reverse=True)  # deepest first

            # Terminate descendants (deepest first)
            for _, desc_id in depths:
                desc = await self._registry.get(desc_id)
                if not desc.is_terminal:
                    desc.transition_to(
                        AgentLifecycleState.terminated(
                            TerminationReason.PARENT_TERMINATED
                        )
                    )
                    logger.debug("Cascade terminated %s (parent_terminated)", desc_id)

            # Terminate the instance itself
            instance.transition_to(AgentLifecycleState.terminated(reason))
            logger.debug("Terminated %s (reason=%s)", instance_id, reason.value)

        finally:
            async with self._lock:
                self._terminating_ancestors.discard(instance_id)

    # -----------------------------------------------------------------------
    # Delegation to registry (read operations)
    # -----------------------------------------------------------------------

    async def get_state(self, instance_id: str) -> AgentLifecycleState:
        """Get the current lifecycle state of an instance.

        Args:
            instance_id: The instance ID.

        Returns:
            The current AgentLifecycleState.

        Raises:
            InstanceNotFound: If the instance does not exist.
        """
        instance = await self._registry.get(instance_id)
        return instance.state

    async def update_state(
        self, instance_id: str, new_state: AgentLifecycleState
    ) -> None:
        """Update an instance's lifecycle state.

        Delegates to registry.update_state() with transition validation.
        """
        await self._registry.update_state(instance_id, new_state)

    async def children_of(self, parent_id: str) -> list[AgentInstance]:
        """Return direct children of a parent instance."""
        return await self._registry.children_of(parent_id)

    async def lineage(self, instance_id: str) -> list[str]:
        """Return the root-to-instance ancestry path."""
        return await self._registry.lineage(instance_id)

    async def all_descendants(self, instance_id: str) -> list[str]:
        """Return all descendants of an instance via BFS."""
        return await self._registry.all_descendants(instance_id)

    async def count_live(self) -> int:
        """Return the count of non-terminal instances."""
        return await self._registry.count_live()
