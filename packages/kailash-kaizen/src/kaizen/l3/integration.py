# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3Runtime — wired integration layer connecting all 5 L3 subsystems.

Provides a convenience class that creates and wires together all L3
primitives (envelope, context, messaging, factory, plan) into a single
cohesive runtime. This eliminates the boilerplate of manually connecting
the cross-primitive integration points.

Cross-primitive wiring:
    Factory -> Enforcer: spawn() registers agent envelopes
    Factory -> Router:   spawn() creates bidirectional channels
    Factory -> Context:  spawn() creates child ContextScope
    Enforcer -> Plan:    executor checks budget before node execution

Usage:
    runtime = L3Runtime(root_envelope={"financial_limit": 100.0})
    instance = await runtime.spawn_agent(spec, parent_id="root")
"""

from __future__ import annotations

import logging
from typing import Any

from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import DataClassification
from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
from kaizen.l3.envelope.tracker import EnvelopeTracker
from kaizen.l3.envelope.types import PlanGradient
from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import AgentInstance
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec
from kaizen.l3.messaging.router import MessageRouter
from kaizen.l3.plan.executor import AsyncNodeCallback, AsyncPlanExecutor

__all__ = ["L3Runtime"]

logger = logging.getLogger(__name__)


class L3Runtime:
    """Wired L3 primitive runtime -- connects all 5 subsystems.

    Creates and configures all L3 primitives with cross-primitive
    integration automatically wired:

    - ``EnvelopeTracker`` + ``EnvelopeEnforcer`` for budget enforcement
    - ``MessageRouter`` for inter-agent communication
    - ``AgentFactory`` with enforcer and router integration
    - ``ContextScope`` root for hierarchical scoped context
    - ``AsyncPlanExecutor`` ready with enforcer integration

    Args:
        root_envelope: Root constraint envelope dict. Must contain
            ``financial_limit`` for budget tracking. Defaults to
            unbounded limits.
        gradient: Optional PlanGradient configuration. Uses defaults
            if not provided.
        root_owner_id: Owner ID for the root ContextScope.
            Defaults to ``"root"``.
        default_channel_capacity: Default capacity for message channels
            created during spawn. Defaults to 100.
    """

    def __init__(
        self,
        root_envelope: dict[str, Any] | None = None,
        gradient: PlanGradient | None = None,
        root_owner_id: str = "root",
        default_channel_capacity: int = 100,
    ) -> None:
        envelope = root_envelope or {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 10000,
        }
        grad = gradient or PlanGradient()

        # Envelope subsystem
        self.tracker = EnvelopeTracker(envelope=envelope, gradient=grad)
        self.enforcer = EnvelopeEnforcer(tracker=self.tracker)

        # Messaging subsystem
        self.router = MessageRouter()

        # Factory subsystem (wired to enforcer + router)
        self.registry = AgentInstanceRegistry()
        self.factory = AgentFactory(
            registry=self.registry,
            enforcer=self.enforcer,
            router=self.router,
            default_channel_capacity=default_channel_capacity,
        )

        # Context subsystem
        self.root_scope = ContextScope.root(
            owner_id=root_owner_id,
            clearance=DataClassification.TOP_SECRET,
        )

        # Register root envelope with the enforcer
        self.enforcer.register(root_owner_id, envelope)

        logger.info(
            "L3Runtime initialized: envelope=%s, root_owner=%s",
            {k: v for k, v in envelope.items() if "limit" in k.lower()},
            root_owner_id,
        )

    async def spawn_agent(
        self,
        spec: AgentSpec,
        parent_id: str | None = None,
        parent_scope: ContextScope | None = None,
    ) -> AgentInstance:
        """Spawn an agent with full L3 integration wiring.

        Delegates to ``self.factory.spawn()`` with the root scope
        as the default parent scope (when parent_scope is not provided
        and no parent_id is given).

        Args:
            spec: The AgentSpec blueprint for the new agent.
            parent_id: Optional parent instance ID.
            parent_scope: Optional parent ContextScope. If not provided
                and parent_id is None, uses self.root_scope.

        Returns:
            The newly created AgentInstance.
        """
        if parent_scope is None and parent_id is None:
            parent_scope = self.root_scope

        return await self.factory.spawn(
            child_spec=spec,
            parent_id=parent_id,
            parent_scope=parent_scope,
        )

    def create_plan_executor(
        self,
        node_callback: AsyncNodeCallback,
        agent_id: str = "plan-executor",
        max_concurrency: int | None = None,
    ) -> AsyncPlanExecutor:
        """Create an AsyncPlanExecutor wired to the enforcer.

        Args:
            node_callback: Async callback for node execution.
            agent_id: Agent instance ID for enforcer checks.
            max_concurrency: Optional concurrency limit.

        Returns:
            An AsyncPlanExecutor with enforcer integration.
        """
        return AsyncPlanExecutor(
            node_callback=node_callback,
            enforcer=self.enforcer,
            enforcer_agent_id=agent_id,
            max_concurrency=max_concurrency,
        )
