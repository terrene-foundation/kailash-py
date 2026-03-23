# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""AgentLifecycleManager — bridge between local agent specs and SDK AgentFactory.

Manages agent spawning and termination via the real SDK AgentFactory,
converting local kaizen-agents types (AgentSpec, ConstraintEnvelope,
MemoryConfig) to their SDK equivalents at the integration boundary.

All lifecycle operations (spawn, terminate, state transitions) delegate
to the SDK factory/registry, providing proper agent hierarchy management
with cascade termination.
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    TerminationReason,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec as SdkAgentSpec

from kaizen_agents._sdk_compat import envelope_to_dict
from kaizen_agents.types import AgentSpec as LocalAgentSpec

__all__ = ["AgentLifecycleManager"]

logger = logging.getLogger(__name__)


class AgentLifecycleManager:
    """Manages agent spawning and termination via SDK AgentFactory.

    Converts local kaizen-agents AgentSpec instances to SDK AgentSpec
    instances and delegates all lifecycle operations to the SDK factory.

    Args:
        factory: The SDK AgentFactory for spawn/terminate operations.
        registry: The SDK AgentInstanceRegistry for instance tracking.
    """

    def __init__(self, factory: AgentFactory, registry: AgentInstanceRegistry) -> None:
        self._factory = factory
        self._registry = registry

    async def spawn_agent(
        self,
        local_spec: LocalAgentSpec,
        parent_id: str | None = None,
    ) -> AgentInstance:
        """Spawn an agent from a local AgentSpec.

        Converts the local spec to an SDK spec via _convert_spec, then
        spawns via the SDK AgentFactory. The returned instance is in
        Pending state.

        Args:
            local_spec: The local AgentSpec blueprint.
            parent_id: The parent instance ID, or None for root agents.

        Returns:
            The newly created SDK AgentInstance in Pending state.

        Raises:
            InstanceNotFound: If parent_id does not exist.
            ValueError: If parent is not in Running or Waiting state.
            MaxChildrenExceeded: If parent's max_children limit is reached.
            MaxDepthExceeded: If any ancestor's max_depth limit would be exceeded.
            ToolNotInParent: If child requests a tool not in parent's spec.
        """
        sdk_spec = self._convert_spec(local_spec)
        instance = await self._factory.spawn(sdk_spec, parent_id=parent_id)

        logger.info(
            "Spawned agent instance %s (spec=%s, parent=%s)",
            instance.instance_id,
            local_spec.spec_id,
            parent_id,
        )
        return instance

    async def terminate_agent(self, instance_id: str, reason: str = "explicit_termination") -> None:
        """Terminate an agent and cascade to all descendants.

        Converts the reason string to an SDK TerminationReason enum.
        If the reason is not a valid TerminationReason value, falls back
        to EXPLICIT_TERMINATION.

        Args:
            instance_id: The instance to terminate.
            reason: Termination reason string (must match a TerminationReason value).

        Raises:
            InstanceNotFound: If the instance does not exist.
        """
        termination_reason = self._resolve_termination_reason(reason)

        await self._factory.terminate(instance_id, termination_reason)

        logger.info(
            "Terminated agent instance %s (reason=%s)",
            instance_id,
            termination_reason.value,
        )

    async def mark_running(self, instance_id: str) -> None:
        """Transition an agent to Running state.

        Args:
            instance_id: The instance to transition.

        Raises:
            InstanceNotFound: If the instance does not exist.
            InvalidStateTransitionError: If the transition is invalid.
        """
        await self._factory.update_state(instance_id, AgentLifecycleState.running())

    async def mark_completed(self, instance_id: str, result: Any = None) -> None:
        """Transition an agent to Completed state.

        Args:
            instance_id: The instance to transition.
            result: Optional result payload for the completed state.

        Raises:
            InstanceNotFound: If the instance does not exist.
            InvalidStateTransitionError: If the transition is invalid.
        """
        await self._factory.update_state(instance_id, AgentLifecycleState.completed(result=result))

    async def get_children(self, parent_id: str) -> list[AgentInstance]:
        """Return direct children of a parent instance.

        Args:
            parent_id: The parent instance ID.

        Returns:
            List of child AgentInstance objects.
        """
        return await self._factory.children_of(parent_id)

    async def get_lineage(self, instance_id: str) -> list[str]:
        """Return the root-to-instance ancestry path.

        Args:
            instance_id: The instance to trace lineage for.

        Returns:
            List of instance_ids from root to the given instance.

        Raises:
            InstanceNotFound: If the instance does not exist.
        """
        return await self._factory.lineage(instance_id)

    def _convert_spec(self, local: LocalAgentSpec) -> SdkAgentSpec:
        """Convert a local AgentSpec to an SDK AgentSpec.

        Conversions:
            - ConstraintEnvelope -> dict via envelope_to_dict()
            - MemoryConfig -> dict with session/shared/persistent keys
            - timedelta max_lifetime -> float seconds (or None)
            - All other fields map directly

        Args:
            local: The local AgentSpec to convert.

        Returns:
            The equivalent SDK AgentSpec (frozen dataclass).
        """
        return SdkAgentSpec(
            spec_id=local.spec_id,
            name=local.name,
            description=local.description,
            capabilities=local.capabilities,
            tool_ids=local.tool_ids,
            envelope=envelope_to_dict(local.envelope),
            memory_config={
                "session": local.memory_config.session,
                "shared": local.memory_config.shared,
                "persistent": local.memory_config.persistent,
            },
            max_lifetime=(
                local.max_lifetime.total_seconds() if local.max_lifetime is not None else None
            ),
            max_children=local.max_children,
            max_depth=local.max_depth,
            required_context_keys=local.required_context_keys,
            produced_context_keys=local.produced_context_keys,
            metadata=local.metadata,
        )

    @staticmethod
    def _resolve_termination_reason(reason: str) -> TerminationReason:
        """Resolve a reason string to a TerminationReason enum.

        If the reason string matches a valid TerminationReason value,
        returns that variant. Otherwise falls back to EXPLICIT_TERMINATION.

        Args:
            reason: The termination reason string.

        Returns:
            The corresponding TerminationReason enum variant.
        """
        valid_values = {r.value for r in TerminationReason}
        if reason in valid_values:
            return TerminationReason(reason)

        logger.warning(
            "Unknown termination reason '%s', falling back to EXPLICIT_TERMINATION",
            reason,
        )
        return TerminationReason.EXPLICIT_TERMINATION
