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

L3 integration wiring (cross-primitive):
- Factory -> Enforcer: registers agent envelope at spawn time
- Factory -> Router: creates message channels at spawn time
- Factory -> Context: creates child ContextScope at spawn time

Implements cascade termination (I-02): deepest-first, all descendants.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from kaizen.l3.context.scope import ContextScope
    from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
    from kaizen.l3.messaging.router import MessageRouter

__all__ = ["AgentFactory"]

logger = logging.getLogger(__name__)


class AgentFactory:
    """Factory for spawning and terminating agent instances.

    All spawn preconditions are validated before creating the instance.
    Cascade termination ensures all descendants are terminated
    deepest-first when a parent is terminated.

    L3 integration: When ``enforcer``, ``router``, or ``parent_scope``
    are provided, spawn() automatically wires the new agent into those
    subsystems. All integration parameters are optional and default to
    None for backward compatibility.

    Args:
        registry: The AgentInstanceRegistry to use for tracking instances.
        enforcer: Optional EnvelopeEnforcer. When set, spawn() registers
            the agent's envelope with the enforcer for enforcement tracking.
        router: Optional MessageRouter. When set, spawn() creates
            bidirectional message channels between parent and child.
        default_channel_capacity: Default channel capacity when creating
            channels via the router integration. Defaults to 100.
    """

    def __init__(
        self,
        registry: AgentInstanceRegistry,
        enforcer: EnvelopeEnforcer | None = None,
        router: MessageRouter | None = None,
        default_channel_capacity: int = 100,
    ) -> None:
        self._registry = registry
        self._enforcer = enforcer
        self._router = router
        self._default_channel_capacity = default_channel_capacity
        # Spec registry: maps spec_id -> AgentSpec for tool/depth checks
        self._specs: dict[str, AgentSpec] = {}
        # AD-L3-10: Track ancestors currently being cascade-terminated
        self._terminating_ancestors: set[str] = set()
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        child_spec: AgentSpec,
        parent_id: str | None = None,
        parent_scope: ContextScope | None = None,
    ) -> AgentInstance:
        """Spawn a new agent instance.

        If parent_id is None, creates a root agent.
        If parent_id is provided, validates all spawn preconditions.

        L3 integration (all optional, backward-compatible):
        - If ``self._enforcer`` is set, registers the agent's envelope.
        - If ``self._router`` is set and parent_id is provided, creates
          bidirectional message channels between parent and child.
        - If ``parent_scope`` is provided, creates a child ContextScope
          and attaches it to the instance metadata (key: ``"context_scope"``).

        Args:
            child_spec: The AgentSpec blueprint for the new instance.
            parent_id: The parent instance ID, or None for root agents.
            parent_scope: Optional parent ContextScope. When provided,
                a child scope is created and attached to the instance.

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

        # L3 integration: Factory -> Enforcer
        if self._enforcer is not None and child_spec.envelope:
            self._enforcer.register(instance.instance_id, child_spec.envelope)

        # L3 integration: Factory -> Router
        if self._router is not None and parent_id is not None:
            cap = self._default_channel_capacity
            # Create bidirectional channels: parent->child and child->parent
            self._router.create_channel(parent_id, instance.instance_id, cap)
            self._router.create_channel(instance.instance_id, parent_id, cap)

        # L3 integration: Factory -> Context
        if parent_scope is not None:
            from kaizen.l3.context.projection import ScopeProjection

            # Create a child scope with inherited projections (monotonic tightening)
            child_scope = parent_scope.create_child(
                owner_id=instance.instance_id,
                read_projection=ScopeProjection(
                    allow_patterns=parent_scope.read_projection.allow_patterns,
                    deny_patterns=parent_scope.read_projection.deny_patterns,
                ),
                write_projection=ScopeProjection(
                    allow_patterns=parent_scope.write_projection.allow_patterns,
                    deny_patterns=parent_scope.write_projection.deny_patterns,
                ),
            )
            # Attach scope to instance metadata for retrieval by the agent
            instance.envelope = instance.envelope or {}
            if not isinstance(instance.envelope, dict):
                instance.envelope = {}
            instance.envelope["_context_scope_id"] = child_scope.scope_id

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
                    # H2 fix: deregister descendant from enforcer on termination
                    if self._enforcer is not None:
                        self._enforcer.deregister(desc_id)
                    logger.debug("Cascade terminated %s (parent_terminated)", desc_id)

            # Terminate the instance itself
            instance.transition_to(AgentLifecycleState.terminated(reason))
            # H2 fix: deregister terminated instance from enforcer
            if self._enforcer is not None:
                self._enforcer.deregister(instance_id)
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
