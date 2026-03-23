# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for L3 cross-primitive integration layer.

Covers:
- Factory -> Enforcer wiring (spawn registers agent envelope)
- Factory -> Router wiring (spawn creates bidirectional channels)
- Factory -> Context wiring (spawn creates child ContextScope)
- Enforcer -> Plan wiring (AsyncPlanExecutor checks envelope before node execution)
- L3Runtime convenience class (all primitives wired together)
- Backward compatibility (existing APIs work without integration params)
"""

from __future__ import annotations

import pytest

from kaizen.l3.context.projection import ScopeProjection
from kaizen.l3.context.scope import ContextScope
from kaizen.l3.context.types import DataClassification
from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
from kaizen.l3.envelope.tracker import EnvelopeTracker
from kaizen.l3.envelope.types import (
    EnforcementContext,
    GradientZone,
    PlanGradient,
    Verdict,
)
from kaizen.l3.factory.factory import AgentFactory
from kaizen.l3.factory.instance import (
    AgentInstance,
    AgentLifecycleState,
    TerminationReason,
)
from kaizen.l3.factory.registry import AgentInstanceRegistry
from kaizen.l3.factory.spec import AgentSpec
from kaizen.l3.integration import L3Runtime
from kaizen.l3.messaging.router import MessageRouter
from kaizen.l3.plan.executor import AsyncPlanExecutor, PlanExecutor
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEdge,
    PlanEvent,
    PlanNode,
    PlanNodeState,
    PlanState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_SENTINEL = object()


def _make_spec(
    spec_id: str = "spec-a",
    tool_ids: list[str] | None = None,
    envelope: dict | object = _SENTINEL,
    max_children: int | None = None,
    max_depth: int | None = None,
) -> AgentSpec:
    """Helper to create a test AgentSpec."""
    if envelope is _SENTINEL:
        envelope = {"financial_limit": 50.0}
    return AgentSpec(
        spec_id=spec_id,
        name=f"Agent {spec_id}",
        description=f"Test agent for {spec_id}",
        tool_ids=tool_ids or [],
        envelope=envelope,  # type: ignore[arg-type]
        max_children=max_children,
        max_depth=max_depth,
    )


def _make_tracker_and_enforcer(
    financial_limit: float = 100.0,
) -> tuple[EnvelopeTracker, EnvelopeEnforcer]:
    """Create a tracker + enforcer pair for testing."""
    envelope = {
        "financial_limit": financial_limit,
        "temporal_limit_seconds": 3600.0,
        "action_limit": 1000,
    }
    gradient = PlanGradient()
    tracker = EnvelopeTracker(envelope=envelope, gradient=gradient)
    enforcer = EnvelopeEnforcer(tracker=tracker)
    return tracker, enforcer


def _make_plan_with_nodes(
    node_ids: list[str],
    edges: list[tuple[str, str]] | None = None,
    node_envelopes: dict[str, dict] | None = None,
) -> Plan:
    """Create a simple validated plan for testing."""
    nodes = {}
    for nid in node_ids:
        env = (node_envelopes or {}).get(nid, {})
        nodes[nid] = PlanNode(
            node_id=nid,
            agent_spec_id=f"spec-{nid}",
            input_mapping={},
            state=PlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
            envelope=env,
        )

    plan_edges = []
    if edges:
        for from_id, to_id in edges:
            plan_edges.append(
                PlanEdge(
                    from_node=from_id,
                    to_node=to_id,
                    edge_type=EdgeType.DATA_DEPENDENCY,
                )
            )

    plan = Plan(
        plan_id="test-plan",
        name="test-plan",
        envelope={},
        nodes=nodes,
        edges=plan_edges,
        gradient={},
        state=PlanState.VALIDATED,
    )
    return plan


# ===================================================================
# Test Factory -> Enforcer integration
# ===================================================================


class TestFactoryEnforcerIntegration:
    """Factory -> Enforcer: spawn registers agent envelope."""

    @pytest.mark.asyncio
    async def test_spawn_registers_envelope_with_enforcer(self):
        """When enforcer is set, spawn() registers the agent's envelope."""
        _, enforcer = _make_tracker_and_enforcer()
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry, enforcer=enforcer)

        spec = _make_spec("agent-a", envelope={"financial_limit": 50.0})
        instance = await factory.spawn(spec)

        assert enforcer.is_registered(instance.instance_id)
        assert enforcer.get_agent_envelope(instance.instance_id) == {
            "financial_limit": 50.0
        }

    @pytest.mark.asyncio
    async def test_spawn_without_enforcer_works(self):
        """Backward compat: spawn works without enforcer."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        spec = _make_spec("agent-a")
        instance = await factory.spawn(spec)

        assert instance.spec_id == "agent-a"
        assert instance.parent_id is None

    @pytest.mark.asyncio
    async def test_spawn_with_empty_envelope_skips_registration(self):
        """If agent spec has empty envelope, enforcer.register is not called."""
        _, enforcer = _make_tracker_and_enforcer()
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry, enforcer=enforcer)

        spec = _make_spec("agent-a", envelope={})
        instance = await factory.spawn(spec)

        assert not enforcer.is_registered(instance.instance_id)

    @pytest.mark.asyncio
    async def test_enforcer_register_rejects_duplicate(self):
        """EnvelopeEnforcer.register rejects duplicate agent_id."""
        _, enforcer = _make_tracker_and_enforcer()
        enforcer.register("agent-1", {"financial_limit": 10.0})

        with pytest.raises(ValueError, match="already registered"):
            enforcer.register("agent-1", {"financial_limit": 20.0})

    @pytest.mark.asyncio
    async def test_enforcer_deregister(self):
        """EnvelopeEnforcer.deregister removes agent registration."""
        _, enforcer = _make_tracker_and_enforcer()
        enforcer.register("agent-1", {"financial_limit": 10.0})
        assert enforcer.is_registered("agent-1")

        enforcer.deregister("agent-1")
        assert not enforcer.is_registered("agent-1")

    @pytest.mark.asyncio
    async def test_enforcer_deregister_nonexistent_is_noop(self):
        """Deregistering a non-existent agent is a no-op."""
        _, enforcer = _make_tracker_and_enforcer()
        enforcer.deregister("never-registered")  # Should not raise


# ===================================================================
# Test Factory -> Router integration
# ===================================================================


class TestFactoryRouterIntegration:
    """Factory -> Router: spawn creates bidirectional channels."""

    @pytest.mark.asyncio
    async def test_spawn_creates_channels_with_router(self):
        """When router is set, spawn with parent creates bidirectional channels."""
        registry = AgentInstanceRegistry()
        router = MessageRouter()
        factory = AgentFactory(registry=registry, router=router)

        # Spawn root agent
        root_spec = _make_spec("root-spec")
        root = await factory.spawn(root_spec)
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        # Spawn child agent
        child_spec = _make_spec("child-spec")
        child = await factory.spawn(child_spec, parent_id=root.instance_id)

        # Verify bidirectional channels exist by checking internal state
        parent_to_child = (root.instance_id, child.instance_id)
        child_to_parent = (child.instance_id, root.instance_id)
        assert parent_to_child in router._channels
        assert child_to_parent in router._channels

    @pytest.mark.asyncio
    async def test_spawn_root_no_channels_created(self):
        """Root agent spawn (no parent) does not create channels."""
        registry = AgentInstanceRegistry()
        router = MessageRouter()
        factory = AgentFactory(registry=registry, router=router)

        root_spec = _make_spec("root-spec")
        await factory.spawn(root_spec)

        # No channels should exist
        assert len(router._channels) == 0

    @pytest.mark.asyncio
    async def test_spawn_without_router_works(self):
        """Backward compat: spawn works without router."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        root_spec = _make_spec("root-spec")
        root = await factory.spawn(root_spec)
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child-spec")
        child = await factory.spawn(child_spec, parent_id=root.instance_id)

        assert child.parent_id == root.instance_id

    @pytest.mark.asyncio
    async def test_custom_channel_capacity(self):
        """Custom channel capacity is used for created channels."""
        registry = AgentInstanceRegistry()
        router = MessageRouter()
        factory = AgentFactory(
            registry=registry, router=router, default_channel_capacity=50
        )

        root_spec = _make_spec("root-spec")
        root = await factory.spawn(root_spec)
        await registry.update_state(root.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child-spec")
        child = await factory.spawn(child_spec, parent_id=root.instance_id)

        # Check channel capacity
        channel = router._channels[(root.instance_id, child.instance_id)]
        assert channel.capacity == 50


# ===================================================================
# Test Factory -> Context integration
# ===================================================================


class TestFactoryContextIntegration:
    """Factory -> Context: spawn creates child ContextScope."""

    @pytest.mark.asyncio
    async def test_spawn_creates_child_scope(self):
        """When parent_scope is provided, spawn creates a child scope."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        parent_scope = ContextScope.root(owner_id="root-agent")

        spec = _make_spec("child-agent")
        instance = await factory.spawn(spec, parent_scope=parent_scope)

        # Verify child scope was created
        assert len(parent_scope.children) == 1
        child_scope = parent_scope.children[0]
        assert child_scope.owner_id == instance.instance_id

        # Verify scope_id reference is stored in instance envelope
        assert instance.envelope is not None
        assert "_context_scope_id" in instance.envelope
        assert instance.envelope["_context_scope_id"] == child_scope.scope_id

    @pytest.mark.asyncio
    async def test_spawn_without_parent_scope_no_context(self):
        """Spawn without parent_scope does not create child scope."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        spec = _make_spec("agent-a")
        instance = await factory.spawn(spec)

        # No context wiring -- envelope should not have scope reference
        # (envelope is None by default on AgentInstance)
        if instance.envelope is not None:
            assert "_context_scope_id" not in instance.envelope

    @pytest.mark.asyncio
    async def test_child_scope_inherits_projections(self):
        """Child scope inherits read/write projections from parent."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        parent_scope = ContextScope.root(owner_id="root-agent")
        parent_scope.set("config.key1", "value1")
        parent_scope.set("config.key2", "value2")

        spec = _make_spec("child-agent")
        await factory.spawn(spec, parent_scope=parent_scope)

        child_scope = parent_scope.children[0]

        # Child inherits parent projections (allow all)
        assert child_scope.read_projection.allow_patterns == ["**"]
        assert child_scope.write_projection.allow_patterns == ["**"]

        # Child can see parent's keys through traversal
        val = child_scope.get("config.key1")
        assert val is not None
        assert val.value == "value1"

    @pytest.mark.asyncio
    async def test_multiple_children_each_get_own_scope(self):
        """Each spawned child gets its own ContextScope."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        parent_scope = ContextScope.root(owner_id="root-agent")

        spec_a = _make_spec("child-a")
        instance_a = await factory.spawn(spec_a, parent_scope=parent_scope)

        spec_b = _make_spec("child-b")
        instance_b = await factory.spawn(spec_b, parent_scope=parent_scope)

        assert len(parent_scope.children) == 2
        scope_a = parent_scope.children[0]
        scope_b = parent_scope.children[1]

        assert scope_a.owner_id == instance_a.instance_id
        assert scope_b.owner_id == instance_b.instance_id
        assert scope_a.scope_id != scope_b.scope_id


# ===================================================================
# Test Enforcer -> Plan integration (AsyncPlanExecutor)
# ===================================================================


class TestEnforcerPlanIntegration:
    """Enforcer -> Plan: executor checks envelope before node execution."""

    @pytest.mark.asyncio
    async def test_executor_blocks_node_on_budget_exceeded(self):
        """When enforcer returns BLOCKED, node is blocked and downstream cascaded."""
        # Set a very small budget that will block
        envelope = {
            "financial_limit": 0.01,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 1000,
        }
        gradient = PlanGradient()
        tracker = EnvelopeTracker(envelope=envelope, gradient=gradient)
        enforcer = EnvelopeEnforcer(tracker=tracker)

        call_count = 0

        async def callback(node_id: str, spec_id: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"output": "done", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(
            node_callback=callback,
            enforcer=enforcer,
            enforcer_agent_id="test-agent",
        )

        # Create plan with one node that has a high estimated_cost
        plan = _make_plan_with_nodes(
            ["node-expensive"],
            node_envelopes={
                "node-expensive": {
                    "estimated_cost": 100.0,
                    "dimension_costs": {"financial": 100.0},
                }
            },
        )

        events = await executor.execute(plan)

        # The node should have been blocked, callback never called
        assert call_count == 0
        blocked_events = [e for e in events if e.tag == "NodeBlocked"]
        assert len(blocked_events) == 1
        assert "node-expensive" in blocked_events[0].node_id

    @pytest.mark.asyncio
    async def test_executor_allows_node_within_budget(self):
        """When enforcer returns APPROVED, node executes normally."""
        envelope = {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 1000,
        }
        gradient = PlanGradient()
        tracker = EnvelopeTracker(envelope=envelope, gradient=gradient)
        enforcer = EnvelopeEnforcer(tracker=tracker)

        async def callback(node_id: str, spec_id: str) -> dict:
            return {"output": "result", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(
            node_callback=callback,
            enforcer=enforcer,
            enforcer_agent_id="test-agent",
        )

        plan = _make_plan_with_nodes(
            ["node-cheap"],
            node_envelopes={
                "node-cheap": {
                    "estimated_cost": 1.0,
                    "dimension_costs": {"financial": 1.0},
                }
            },
        )

        events = await executor.execute(plan)

        completed_events = [e for e in events if e.tag == "NodeCompleted"]
        assert len(completed_events) == 1
        assert plan.nodes["node-cheap"].output == "result"

    @pytest.mark.asyncio
    async def test_executor_without_enforcer_works(self):
        """Backward compat: executor works without enforcer."""
        async def callback(node_id: str, spec_id: str) -> dict:
            return {"output": "ok", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(node_callback=callback)
        plan = _make_plan_with_nodes(["node-a"])
        events = await executor.execute(plan)

        completed_events = [e for e in events if e.tag == "NodeCompleted"]
        assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_executor_no_estimated_cost_skips_check(self):
        """Nodes without estimated_cost (0.0) pass enforcer check trivially."""
        envelope = {
            "financial_limit": 100.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 1000,
        }
        gradient = PlanGradient()
        tracker = EnvelopeTracker(envelope=envelope, gradient=gradient)
        enforcer = EnvelopeEnforcer(tracker=tracker)

        async def callback(node_id: str, spec_id: str) -> dict:
            return {"output": "done", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(
            node_callback=callback,
            enforcer=enforcer,
            enforcer_agent_id="test-agent",
        )

        # No envelope on node -> estimated_cost defaults to 0.0
        plan = _make_plan_with_nodes(["node-free"])
        events = await executor.execute(plan)

        completed_events = [e for e in events if e.tag == "NodeCompleted"]
        assert len(completed_events) == 1

    @pytest.mark.asyncio
    async def test_sync_executor_accepts_enforcer_param(self):
        """PlanExecutor accepts enforcer param (API parity, no runtime check)."""
        _, enforcer = _make_tracker_and_enforcer()

        def callback(node_id: str, spec_id: str) -> dict:
            return {"output": "ok", "error": None, "retryable": False}

        # Should not raise -- parameter accepted
        executor = PlanExecutor(
            node_callback=callback,
            enforcer=enforcer,
        )
        assert executor._enforcer is enforcer

    @pytest.mark.asyncio
    async def test_blocked_node_cascades_to_downstream(self):
        """Blocked node cascades skip to data-dependent downstream nodes."""
        envelope = {
            "financial_limit": 0.01,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 1000,
        }
        gradient = PlanGradient()
        tracker = EnvelopeTracker(envelope=envelope, gradient=gradient)
        enforcer = EnvelopeEnforcer(tracker=tracker)

        async def callback(node_id: str, spec_id: str) -> dict:
            return {"output": "done", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(
            node_callback=callback,
            enforcer=enforcer,
            enforcer_agent_id="test-agent",
        )

        plan = _make_plan_with_nodes(
            ["node-a", "node-b"],
            edges=[("node-a", "node-b")],
            node_envelopes={
                "node-a": {
                    "estimated_cost": 999.0,
                    "dimension_costs": {"financial": 999.0},
                },
            },
        )

        events = await executor.execute(plan)

        blocked_events = [e for e in events if e.tag == "NodeBlocked"]
        skipped_events = [e for e in events if e.tag == "NodeSkipped"]
        assert len(blocked_events) == 1
        assert len(skipped_events) == 1
        assert skipped_events[0].node_id == "node-b"


# ===================================================================
# Test L3Runtime convenience class
# ===================================================================


class TestL3Runtime:
    """L3Runtime wires all primitives together."""

    def test_initialization(self):
        """L3Runtime creates all subsystems."""
        runtime = L3Runtime(root_envelope={"financial_limit": 500.0})

        assert runtime.tracker is not None
        assert runtime.enforcer is not None
        assert runtime.router is not None
        assert runtime.factory is not None
        assert runtime.registry is not None
        assert runtime.root_scope is not None

        # Root is registered with enforcer
        assert runtime.enforcer.is_registered("root")

    def test_default_initialization(self):
        """L3Runtime works with default parameters."""
        runtime = L3Runtime()

        assert runtime.tracker is not None
        assert runtime.root_scope.owner_id == "root"

    @pytest.mark.asyncio
    async def test_spawn_agent_root(self):
        """spawn_agent creates a root agent with full integration."""
        runtime = L3Runtime(root_envelope={"financial_limit": 200.0})
        spec = _make_spec("root-spec", envelope={"financial_limit": 50.0})

        instance = await runtime.spawn_agent(spec)

        assert instance.spec_id == "root-spec"
        # Envelope registered with enforcer
        assert runtime.enforcer.is_registered(instance.instance_id)
        # Context scope created as child of root_scope
        assert len(runtime.root_scope.children) == 1

    @pytest.mark.asyncio
    async def test_spawn_agent_child_creates_channels(self):
        """Spawning a child agent creates message channels."""
        runtime = L3Runtime(root_envelope={"financial_limit": 200.0})

        # Spawn root
        root_spec = _make_spec("root-spec", envelope={"financial_limit": 100.0})
        root = await runtime.spawn_agent(root_spec)
        await runtime.registry.update_state(
            root.instance_id, AgentLifecycleState.running()
        )

        # Spawn child
        child_spec = _make_spec("child-spec", envelope={"financial_limit": 50.0})
        child = await runtime.spawn_agent(child_spec, parent_id=root.instance_id)

        # Channels exist
        assert (root.instance_id, child.instance_id) in runtime.router._channels
        assert (child.instance_id, root.instance_id) in runtime.router._channels

    @pytest.mark.asyncio
    async def test_create_plan_executor_with_enforcer(self):
        """create_plan_executor returns wired AsyncPlanExecutor."""
        runtime = L3Runtime(root_envelope={"financial_limit": 200.0})

        async def cb(nid: str, sid: str) -> dict:
            return {"output": "ok", "error": None, "retryable": False}

        executor = runtime.create_plan_executor(node_callback=cb)

        assert executor._enforcer is runtime.enforcer

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """End-to-end: spawn agent, create plan, execute with enforcement."""
        runtime = L3Runtime(
            root_envelope={
                "financial_limit": 100.0,
                "temporal_limit_seconds": 3600.0,
                "action_limit": 1000,
            }
        )

        # Spawn agent
        spec = _make_spec("worker", envelope={"financial_limit": 50.0})
        agent = await runtime.spawn_agent(spec)

        # Verify all integration points
        assert runtime.enforcer.is_registered(agent.instance_id)
        assert len(runtime.root_scope.children) == 1

        # Create and execute plan
        async def cb(nid: str, sid: str) -> dict:
            return {"output": f"result-{nid}", "error": None, "retryable": False}

        executor = runtime.create_plan_executor(
            node_callback=cb, agent_id=agent.instance_id
        )
        plan = _make_plan_with_nodes(
            ["task-1", "task-2"],
            edges=[("task-1", "task-2")],
            node_envelopes={
                "task-1": {"estimated_cost": 1.0, "dimension_costs": {"financial": 1.0}},
                "task-2": {"estimated_cost": 1.0, "dimension_costs": {"financial": 1.0}},
            },
        )

        events = await executor.execute(plan)

        completed = [e for e in events if e.tag == "NodeCompleted"]
        assert len(completed) == 2
        assert plan.state == PlanState.COMPLETED


# ===================================================================
# Test backward compatibility
# ===================================================================


class TestBackwardCompatibility:
    """All existing APIs work without integration parameters."""

    @pytest.mark.asyncio
    async def test_factory_init_only_registry(self):
        """AgentFactory(registry=...) works as before."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)
        spec = _make_spec("compat-spec")
        instance = await factory.spawn(spec)
        assert instance.spec_id == "compat-spec"

    @pytest.mark.asyncio
    async def test_async_executor_init_only_callback(self):
        """AsyncPlanExecutor(node_callback=...) works as before."""
        async def cb(nid: str, sid: str) -> dict:
            return {"output": "ok", "error": None, "retryable": False}

        executor = AsyncPlanExecutor(node_callback=cb)
        plan = _make_plan_with_nodes(["n1"])
        events = await executor.execute(plan)
        assert plan.state == PlanState.COMPLETED

    def test_sync_executor_init_only_callback(self):
        """PlanExecutor(node_callback=...) works as before."""
        def cb(nid: str, sid: str) -> dict:
            return {"output": "ok", "error": None, "retryable": False}

        executor = PlanExecutor(node_callback=cb)
        plan = _make_plan_with_nodes(["n1"])
        events = executor.execute(plan)
        assert plan.state == PlanState.COMPLETED

    @pytest.mark.asyncio
    async def test_enforcer_init_unchanged(self):
        """EnvelopeEnforcer(tracker=...) works as before."""
        tracker, enforcer = _make_tracker_and_enforcer()

        # Existing check_action still works
        ctx = EnforcementContext(
            action="test-action",
            estimated_cost=1.0,
            agent_instance_id="agent-1",
            dimension_costs={"financial": 1.0},
        )
        verdict = await enforcer.check_action(ctx)
        assert verdict.is_approved

    @pytest.mark.asyncio
    async def test_factory_spawn_signature_backward_compat(self):
        """spawn(child_spec) and spawn(child_spec, parent_id) still work."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry=registry)

        # No parent
        root = await factory.spawn(_make_spec("root"))
        assert root.parent_id is None

        # With parent
        await registry.update_state(root.instance_id, AgentLifecycleState.running())
        child = await factory.spawn(_make_spec("child"), parent_id=root.instance_id)
        assert child.parent_id == root.instance_id

    @pytest.mark.asyncio
    async def test_enforcer_register_rejects_empty_id(self):
        """EnvelopeEnforcer.register rejects empty agent_id."""
        _, enforcer = _make_tracker_and_enforcer()
        with pytest.raises(ValueError, match="non-empty"):
            enforcer.register("", {"financial_limit": 10.0})
