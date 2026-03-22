# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""M6-01: Cross-primitive integration tests for L3 module.

Tier 2 tests -- NO MOCKING. All objects are real instances.

Tests verify interactions between L3 primitives:
    - Factory + Registry lifecycle
    - Envelope Tracker + Splitter budget conservation
    - Context Scope hierarchy with projection-based access
    - Messaging pipeline with router, channels, and correlation
    - Full delegation flow combining all primitives
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from kaizen.l3.context import (
    ContextScope,
    DataClassification,
    ScopeProjection,
    WriteProjectionViolation,
)
from kaizen.l3.envelope import (
    AllocationRequest,
    CostEntry,
    EnvelopeSplitter,
    EnvelopeTracker,
    GradientZone,
    PlanGradient,
    Verdict,
)
from kaizen.l3.factory import (
    AgentFactory,
    AgentInstanceRegistry,
    AgentLifecycleState,
    AgentSpec,
    MaxChildrenExceeded,
    TerminationReason,
    ToolNotInParent,
)
from kaizen.l3.messaging import (
    CompletionPayload,
    DelegationPayload,
    MessageEnvelope,
    MessageRouter,
    Priority,
    RoutingError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_spec(
    spec_id: str,
    *,
    tool_ids: list[str] | None = None,
    max_children: int | None = None,
    max_depth: int | None = None,
) -> AgentSpec:
    """Create a minimal AgentSpec for testing."""
    return AgentSpec(
        spec_id=spec_id,
        name=f"Test Agent {spec_id}",
        description=f"Test agent spec {spec_id}",
        tool_ids=tool_ids or [],
        max_children=max_children,
        max_depth=max_depth,
    )


def _make_gradient() -> PlanGradient:
    """Create a default PlanGradient for testing."""
    return PlanGradient(
        budget_flag_threshold=0.80,
        budget_hold_threshold=0.95,
    )


def _make_cost_entry(
    dimension: str,
    cost: float,
    agent_id: str = "agent-001",
) -> CostEntry:
    """Create a CostEntry for testing."""
    return CostEntry(
        action="test_action",
        dimension=dimension,
        cost=cost,
        timestamp=datetime.now(UTC),
        agent_instance_id=agent_id,
    )


# ---------------------------------------------------------------------------
# 1. Factory + Registry Lifecycle
# ---------------------------------------------------------------------------


class TestFactoryRegistryLifecycle:
    """Test Factory + Registry interaction: spawn, lineage, terminate."""

    @pytest.fixture
    def registry(self) -> AgentInstanceRegistry:
        return AgentInstanceRegistry()

    @pytest.fixture
    def factory(self, registry: AgentInstanceRegistry) -> AgentFactory:
        return AgentFactory(registry)

    @pytest.mark.asyncio
    async def test_spawn_root_agent(
        self, factory: AgentFactory, registry: AgentInstanceRegistry
    ) -> None:
        """Spawn a root agent and verify it is registered."""
        spec = _make_spec("root-spec", tool_ids=["search", "code"])
        root = await factory.spawn(spec)

        assert root.spec_id == "root-spec"
        assert root.parent_id is None
        assert root.state.name == "pending"

        # Verify the instance is retrievable from the registry
        retrieved = await registry.get(root.instance_id)
        assert retrieved.instance_id == root.instance_id
        assert await registry.count_live() == 1

    @pytest.mark.asyncio
    async def test_spawn_child_under_running_parent(
        self, factory: AgentFactory
    ) -> None:
        """A child can be spawned under a Running parent."""
        parent_spec = _make_spec("parent-spec", tool_ids=["search", "code"])
        parent = await factory.spawn(parent_spec)

        # Transition parent to Running (Pending -> Running)
        await factory.update_state(parent.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child-spec", tool_ids=["search"])
        child = await factory.spawn(child_spec, parent_id=parent.instance_id)

        assert child.parent_id == parent.instance_id
        assert child.spec_id == "child-spec"

    @pytest.mark.asyncio
    async def test_lineage_verification(self, factory: AgentFactory) -> None:
        """Verify lineage is correctly tracked across multiple generations."""
        root_spec = _make_spec("root", tool_ids=["a", "b", "c"])
        root = await factory.spawn(root_spec)
        await factory.update_state(root.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child", tool_ids=["a", "b"])
        child = await factory.spawn(child_spec, parent_id=root.instance_id)
        await factory.update_state(child.instance_id, AgentLifecycleState.running())

        grandchild_spec = _make_spec("grandchild", tool_ids=["a"])
        grandchild = await factory.spawn(grandchild_spec, parent_id=child.instance_id)

        lineage = await factory.lineage(grandchild.instance_id)
        assert len(lineage) == 3
        assert lineage[0] == root.instance_id
        assert lineage[1] == child.instance_id
        assert lineage[2] == grandchild.instance_id

    @pytest.mark.asyncio
    async def test_cascade_termination(self, factory: AgentFactory) -> None:
        """Terminating a parent cascades to all descendants deepest-first."""
        root_spec = _make_spec("root", tool_ids=["a", "b", "c"])
        root = await factory.spawn(root_spec)
        await factory.update_state(root.instance_id, AgentLifecycleState.running())

        child_spec = _make_spec("child", tool_ids=["a", "b"])
        child = await factory.spawn(child_spec, parent_id=root.instance_id)
        await factory.update_state(child.instance_id, AgentLifecycleState.running())

        grandchild_spec = _make_spec("grandchild", tool_ids=["a"])
        grandchild = await factory.spawn(grandchild_spec, parent_id=child.instance_id)
        await factory.update_state(
            grandchild.instance_id, AgentLifecycleState.running()
        )

        # Terminate root -- should cascade to child and grandchild
        await factory.terminate(
            root.instance_id, TerminationReason.EXPLICIT_TERMINATION
        )

        root_state = await factory.get_state(root.instance_id)
        child_state = await factory.get_state(child.instance_id)
        grandchild_state = await factory.get_state(grandchild.instance_id)

        assert root_state.is_terminal
        assert child_state.is_terminal
        assert grandchild_state.is_terminal

        # Root terminated with explicit reason, descendants with PARENT_TERMINATED
        assert root_state.termination_reason == TerminationReason.EXPLICIT_TERMINATION
        assert child_state.termination_reason == TerminationReason.PARENT_TERMINATED
        assert (
            grandchild_state.termination_reason == TerminationReason.PARENT_TERMINATED
        )

        # Live count should be 0
        assert await factory.count_live() == 0

    @pytest.mark.asyncio
    async def test_tool_subsetting_enforcement(self, factory: AgentFactory) -> None:
        """Child tool_ids must be a subset of parent tool_ids."""
        parent_spec = _make_spec("parent", tool_ids=["search", "code"])
        parent = await factory.spawn(parent_spec)
        await factory.update_state(parent.instance_id, AgentLifecycleState.running())

        # A child requesting a tool the parent does not have
        bad_child_spec = _make_spec("bad-child", tool_ids=["search", "deploy"])

        with pytest.raises(ToolNotInParent):
            await factory.spawn(bad_child_spec, parent_id=parent.instance_id)

    @pytest.mark.asyncio
    async def test_max_children_enforcement(self, factory: AgentFactory) -> None:
        """max_children limit prevents spawning additional children."""
        parent_spec = _make_spec("limited-parent", tool_ids=["a"], max_children=2)
        parent = await factory.spawn(parent_spec)
        await factory.update_state(parent.instance_id, AgentLifecycleState.running())

        child1_spec = _make_spec("child-1", tool_ids=["a"])
        await factory.spawn(child1_spec, parent_id=parent.instance_id)

        child2_spec = _make_spec("child-2", tool_ids=["a"])
        await factory.spawn(child2_spec, parent_id=parent.instance_id)

        # Third child should be rejected
        child3_spec = _make_spec("child-3", tool_ids=["a"])
        with pytest.raises(MaxChildrenExceeded):
            await factory.spawn(child3_spec, parent_id=parent.instance_id)


# ---------------------------------------------------------------------------
# 2. Envelope Tracker + Splitter
# ---------------------------------------------------------------------------


class TestEnvelopeTrackerSplitter:
    """Test budget conservation: split parent envelope, track consumption."""

    @pytest.mark.asyncio
    async def test_split_and_track_budget_conservation(self) -> None:
        """Split a parent envelope, consume from children, verify conservation."""
        parent_envelope = {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 100,
        }

        # Split parent into two children: 40% and 40%, 20% reserve
        allocations = [
            AllocationRequest(
                child_id="child-a", financial_ratio=0.4, temporal_ratio=0.4
            ),
            AllocationRequest(
                child_id="child-b", financial_ratio=0.4, temporal_ratio=0.4
            ),
        ]
        child_envelopes = EnvelopeSplitter.split(
            parent_envelope, allocations, reserve_pct=0.2
        )

        assert len(child_envelopes) == 2

        # Verify child envelopes
        child_a_id, child_a_env = child_envelopes[0]
        child_b_id, child_b_env = child_envelopes[1]

        assert child_a_id == "child-a"
        assert child_b_id == "child-b"
        assert child_a_env["financial_limit"] == pytest.approx(400.0)
        assert child_b_env["financial_limit"] == pytest.approx(400.0)
        assert child_a_env["temporal_limit_seconds"] == pytest.approx(1440.0)
        assert child_b_env["temporal_limit_seconds"] == pytest.approx(1440.0)

        # Conservation: child_a + child_b + reserve = parent
        total_financial = (
            child_a_env["financial_limit"]
            + child_b_env["financial_limit"]
            + 1000.0 * 0.2  # reserve
        )
        assert total_financial == pytest.approx(1000.0)

    @pytest.mark.asyncio
    async def test_tracker_consumption_and_remaining(self) -> None:
        """Record consumption against a tracker and verify remaining budget."""
        envelope = {
            "financial_limit": 500.0,
            "temporal_limit_seconds": 1800.0,
            "action_limit": 50,
        }
        gradient = _make_gradient()
        tracker = EnvelopeTracker(envelope, gradient)

        # Record some financial consumption
        entry = _make_cost_entry("financial", 100.0)
        verdict = await tracker.record_consumption(entry)
        assert verdict.is_approved
        assert verdict.zone == GradientZone.AUTO_APPROVED

        # Check remaining
        remaining = await tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(400.0)
        assert remaining.temporal_remaining == pytest.approx(1800.0)
        assert remaining.actions_remaining == 50

    @pytest.mark.asyncio
    async def test_tracker_allocate_and_reclaim(self) -> None:
        """Allocate budget to child, then reclaim unused portion."""
        envelope = {"financial_limit": 1000.0}
        gradient = _make_gradient()
        tracker = EnvelopeTracker(envelope, gradient)

        # Allocate 300 to child
        await tracker.allocate_to_child("child-1", 300.0)
        remaining = await tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(700.0)

        # Child consumed only 150, reclaim the rest
        result = await tracker.reclaim("child-1", consumed=150.0)
        assert result.reclaimed_financial == pytest.approx(150.0)
        assert result.child_total_consumed == pytest.approx(150.0)
        assert result.child_total_allocated == pytest.approx(300.0)

        # After reclaim: parent consumed 150 (child's actual), no child alloc
        remaining = await tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(850.0)

    @pytest.mark.asyncio
    async def test_tracker_budget_exceeded_blocked(self) -> None:
        """Attempting to exceed the budget returns BLOCKED verdict."""
        envelope = {"financial_limit": 100.0}
        gradient = _make_gradient()
        tracker = EnvelopeTracker(envelope, gradient)

        # Try to consume more than the budget
        entry = _make_cost_entry("financial", 150.0)
        verdict = await tracker.record_consumption(entry)
        assert verdict.tag == "BLOCKED"
        assert verdict.dimension == "financial"

        # Budget should still be full (blocked consumption is not recorded)
        remaining = await tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_split_then_track_child_envelopes(self) -> None:
        """Split parent, create trackers for children, consume independently."""
        parent_envelope = {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 600.0,
        }

        allocations = [
            AllocationRequest(
                child_id="worker-a", financial_ratio=0.5, temporal_ratio=0.5
            ),
            AllocationRequest(
                child_id="worker-b", financial_ratio=0.3, temporal_ratio=0.3
            ),
        ]
        children = EnvelopeSplitter.split(parent_envelope, allocations, reserve_pct=0.2)

        gradient = _make_gradient()

        # Create trackers for each child
        trackers: dict[str, EnvelopeTracker] = {}
        for child_id, child_env in children:
            trackers[child_id] = EnvelopeTracker(child_env, gradient)

        # worker-a consumes 200 of its 500 financial budget
        entry_a = _make_cost_entry("financial", 200.0, agent_id="worker-a")
        verdict_a = await trackers["worker-a"].record_consumption(entry_a)
        assert verdict_a.is_approved

        remaining_a = await trackers["worker-a"].remaining()
        assert remaining_a.financial_remaining == pytest.approx(300.0)

        # worker-b consumes 100 of its 300 financial budget
        entry_b = _make_cost_entry("financial", 100.0, agent_id="worker-b")
        verdict_b = await trackers["worker-b"].record_consumption(entry_b)
        assert verdict_b.is_approved

        remaining_b = await trackers["worker-b"].remaining()
        assert remaining_b.financial_remaining == pytest.approx(200.0)

    @pytest.mark.asyncio
    async def test_gradient_zone_transitions(self) -> None:
        """Verify gradient zones transition as consumption increases."""
        envelope = {"financial_limit": 100.0}
        gradient = PlanGradient(
            budget_flag_threshold=0.70,
            budget_hold_threshold=0.90,
        )
        tracker = EnvelopeTracker(envelope, gradient)

        # 60% usage -> AUTO_APPROVED
        entry1 = _make_cost_entry("financial", 60.0)
        verdict1 = await tracker.record_consumption(entry1)
        assert verdict1.is_approved
        assert verdict1.zone == GradientZone.AUTO_APPROVED

        # +15% = 75% usage -> FLAGGED
        entry2 = _make_cost_entry("financial", 15.0)
        verdict2 = await tracker.record_consumption(entry2)
        assert verdict2.is_approved
        assert verdict2.zone == GradientZone.FLAGGED

        # +17% = 92% usage -> HELD
        entry3 = _make_cost_entry("financial", 17.0)
        verdict3 = await tracker.record_consumption(entry3)
        assert verdict3.tag == "HELD"

        # +10% = would be 102% -> BLOCKED
        entry4 = _make_cost_entry("financial", 10.0)
        verdict4 = await tracker.record_consumption(entry4)
        assert verdict4.tag == "BLOCKED"


# ---------------------------------------------------------------------------
# 3. Context Scope Hierarchy
# ---------------------------------------------------------------------------


class TestContextScopeHierarchy:
    """Test hierarchical scoped context with projections."""

    def test_root_scope_unrestricted(self) -> None:
        """Root scope has unrestricted read/write and highest clearance."""
        root = ContextScope.root("root-agent")

        root.set("project.name", "Kailash")
        root.set("project.config.db_url", "postgresql://localhost/test")
        root.set("secret.api_key", "sk-test-123", DataClassification.SECRET)

        assert root.get("project.name") is not None
        assert root.get("project.name").value == "Kailash"
        assert root.get("secret.api_key") is not None
        assert root.get("secret.api_key").value == "sk-test-123"

    def test_child_restricted_projection(self) -> None:
        """Child scope with restricted projection cannot see denied keys."""
        root = ContextScope.root("root-agent")
        root.set("project.name", "Kailash")
        root.set("project.config.db_url", "postgresql://localhost/test")
        root.set("secret.api_key", "sk-test-123", DataClassification.SECRET)

        # Child can only see project.** but not secret.**
        child = root.create_child(
            owner_id="child-agent",
            read_projection=ScopeProjection(
                allow_patterns=["project.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["project.results.**"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        # Child can see project keys from parent
        assert child.get("project.name") is not None
        assert child.get("project.name").value == "Kailash"

        # Child cannot see secret keys (not in read_projection)
        assert child.get("secret.api_key") is None

        # Child cannot see SECRET-classified data either (clearance too low)
        # Even if the key were in the projection, clearance would block it.

    def test_child_write_projection_enforcement(self) -> None:
        """Child cannot write to keys outside its write_projection."""
        root = ContextScope.root("root-agent")

        child = root.create_child(
            owner_id="child-agent",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.**"], deny_patterns=[]
            ),
        )

        # Can write within projection
        child.set("results.summary", "All good")
        assert child.get("results.summary").value == "All good"

        # Cannot write outside projection
        with pytest.raises(WriteProjectionViolation):
            child.set("config.db_url", "bad-url")

    def test_merge_child_results_back(self) -> None:
        """Merge child writes back into parent scope."""
        root = ContextScope.root("root-agent")
        root.set("project.name", "Kailash")

        child = root.create_child(
            owner_id="child-agent",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(
                allow_patterns=["results.**"], deny_patterns=[]
            ),
        )

        child.set("results.analysis", {"score": 95, "grade": "A"})
        child.set("results.timestamp", "2026-03-22T10:00:00Z")

        merge_result = root.merge_child_results(child)

        assert "results.analysis" in merge_result.merged_keys
        assert "results.timestamp" in merge_result.merged_keys
        assert len(merge_result.skipped_keys) == 0

        # Parent now has the child's results
        assert root.get("results.analysis").value == {
            "score": 95,
            "grade": "A",
        }

    def test_visible_keys_hierarchy(self) -> None:
        """visible_keys collects from local and parent, filtered by projection."""
        root = ContextScope.root("root-agent")
        root.set("project.name", "Kailash")
        root.set("project.version", "2.0")
        root.set("secret.key", "hidden", DataClassification.SECRET)

        child = root.create_child(
            owner_id="child-agent",
            read_projection=ScopeProjection(
                allow_patterns=["project.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["project.**"], deny_patterns=[]
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        child.set("project.status", "active")

        visible = child.visible_keys()

        assert "project.name" in visible
        assert "project.version" in visible
        assert "project.status" in visible
        assert "secret.key" not in visible  # filtered by projection

    def test_clearance_based_filtering(self) -> None:
        """Child with lower clearance cannot see higher-classified data."""
        root = ContextScope.root("root-agent", clearance=DataClassification.TOP_SECRET)
        root.set("public.info", "open", DataClassification.PUBLIC)
        root.set("confidential.plan", "strategy", DataClassification.CONFIDENTIAL)
        root.set("secret.key", "hidden", DataClassification.SECRET)

        child = root.create_child(
            owner_id="child-agent",
            read_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            write_projection=ScopeProjection(allow_patterns=["**"], deny_patterns=[]),
            effective_clearance=DataClassification.RESTRICTED,
        )

        # Can see PUBLIC (0 <= 1)
        assert child.get("public.info") is not None

        # Cannot see CONFIDENTIAL (2 > 1)
        assert child.get("confidential.plan") is None

        # Cannot see SECRET (3 > 1)
        assert child.get("secret.key") is None

    def test_snapshot_materializes_visible(self) -> None:
        """snapshot() returns flat dict of all visible key-value pairs.

        Only keys matching the read_projection are included. Write-only
        keys that are outside the read_projection are NOT in the snapshot.
        """
        root = ContextScope.root("root-agent")
        root.set("config.timeout", 30)
        root.set("config.retries", 3)

        child = root.create_child(
            owner_id="worker",
            read_projection=ScopeProjection(
                allow_patterns=["config.**", "output.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["output.**"], deny_patterns=[]
            ),
        )
        child.set("output.result", "done")

        snap = child.snapshot()

        # Child sees parent config keys (inherited via read_projection)
        assert snap["config.timeout"] == 30
        assert snap["config.retries"] == 3
        # Child sees its own local output key (in read_projection)
        assert snap["output.result"] == "done"


# ---------------------------------------------------------------------------
# 4. Messaging Pipeline
# ---------------------------------------------------------------------------


class TestMessagingPipeline:
    """Test router, channels, and message routing with correlation."""

    @pytest.mark.asyncio
    async def test_delegation_and_completion_flow(self) -> None:
        """Route a delegation from parent to child and completion back."""
        parent_id = "parent-001"
        child_id = "child-001"

        router = MessageRouter()

        # Create bidirectional channels
        router.create_channel(parent_id, child_id, capacity=10)
        router.create_channel(child_id, parent_id, capacity=10)

        # Parent sends delegation to child
        delegation_msg = MessageEnvelope(
            from_instance=parent_id,
            to_instance=child_id,
            payload=DelegationPayload(
                task_description="Analyze the dataset",
                context_snapshot={"dataset": "sales_2026.csv"},
                priority=Priority.HIGH,
            ),
        )
        await router.route(delegation_msg)

        # Verify child has a pending message
        pending = await router.pending_for(child_id)
        assert len(pending) == 1
        assert isinstance(pending[0].payload, DelegationPayload)
        assert pending[0].payload.task_description == "Analyze the dataset"

        # Child sends completion back to parent with correlation_id
        completion_msg = MessageEnvelope(
            from_instance=child_id,
            to_instance=parent_id,
            payload=CompletionPayload(
                result={"rows_analyzed": 50000, "anomalies": 3},
                success=True,
            ),
            correlation_id=delegation_msg.message_id,
        )
        await router.route(completion_msg)

        # Parent has the completion
        parent_pending = await router.pending_for(parent_id)
        assert len(parent_pending) == 1
        assert isinstance(parent_pending[0].payload, CompletionPayload)
        assert parent_pending[0].correlation_id == delegation_msg.message_id
        assert parent_pending[0].payload.result["anomalies"] == 3

    @pytest.mark.asyncio
    async def test_self_message_rejected(self) -> None:
        """Router rejects messages where from == to."""
        router = MessageRouter()

        msg = MessageEnvelope(
            from_instance="agent-001",
            to_instance="agent-001",
            payload=DelegationPayload(task_description="self-task"),
        )

        with pytest.raises(RoutingError) as exc_info:
            await router.route(msg)
        assert exc_info.value.variant == "SelfMessage"

    @pytest.mark.asyncio
    async def test_no_channel_rejected(self) -> None:
        """Router rejects messages when no channel exists."""
        router = MessageRouter()

        msg = MessageEnvelope(
            from_instance="agent-a",
            to_instance="agent-b",
            payload=DelegationPayload(task_description="task"),
        )

        with pytest.raises(RoutingError) as exc_info:
            await router.route(msg)
        assert exc_info.value.variant == "NoChannel"

    @pytest.mark.asyncio
    async def test_completion_requires_correlation_id(self) -> None:
        """CompletionPayload requires correlation_id."""
        router = MessageRouter()
        router.create_channel("child", "parent", capacity=10)

        # Completion without correlation_id
        msg = MessageEnvelope(
            from_instance="child",
            to_instance="parent",
            payload=CompletionPayload(result="done"),
            correlation_id=None,
        )

        with pytest.raises(RoutingError) as exc_info:
            await router.route(msg)
        assert exc_info.value.variant == "CorrelationRequired"

    @pytest.mark.asyncio
    async def test_close_channels_drains_to_dead_letters(self) -> None:
        """Closing channels for an instance moves pending messages to dead letters."""
        router = MessageRouter()
        router.create_channel("sender", "target", capacity=10)

        # Send a message
        msg = MessageEnvelope(
            from_instance="sender",
            to_instance="target",
            payload=DelegationPayload(task_description="work"),
        )
        await router.route(msg)

        # Close channels for target
        router.close_channels_for("target")

        # Dead letter store should have the pending message
        assert router.dead_letters.count() == 1


# ---------------------------------------------------------------------------
# 5. Full Delegation Flow (all primitives combined)
# ---------------------------------------------------------------------------


class TestFullDelegationFlow:
    """Combine Factory + Context + Messaging + Envelope in a single flow."""

    @pytest.mark.asyncio
    async def test_full_delegation_lifecycle(self) -> None:
        """
        End-to-end: root agent spawns child, creates scoped context,
        routes delegation, child consumes budget, sends completion,
        parent reclaims budget and merges context.
        """
        # --- Setup: Factory + Registry ---
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _make_spec("coordinator", tool_ids=["search", "analyze", "report"])
        root_instance = await factory.spawn(root_spec)
        await factory.update_state(
            root_instance.instance_id, AgentLifecycleState.running()
        )

        child_spec = _make_spec("analyst", tool_ids=["search", "analyze"])
        child_instance = await factory.spawn(
            child_spec, parent_id=root_instance.instance_id
        )
        await factory.update_state(
            child_instance.instance_id, AgentLifecycleState.running()
        )

        # --- Setup: Envelope (budget split) ---
        parent_envelope = {
            "financial_limit": 500.0,
            "temporal_limit_seconds": 1800.0,
        }
        gradient = _make_gradient()
        parent_tracker = EnvelopeTracker(parent_envelope, gradient)

        # Allocate 200 to child
        await parent_tracker.allocate_to_child(child_instance.instance_id, 200.0)

        child_envelope = {"financial_limit": 200.0}
        child_tracker = EnvelopeTracker(child_envelope, gradient)

        # --- Setup: Context (scoped) ---
        root_scope = ContextScope.root(root_instance.instance_id)
        root_scope.set("task.objective", "Analyze Q4 sales data")
        root_scope.set("task.dataset", "sales_q4_2025.csv")

        child_scope = root_scope.create_child(
            owner_id=child_instance.instance_id,
            read_projection=ScopeProjection(
                allow_patterns=["task.**"], deny_patterns=[]
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.**"], deny_patterns=[]
            ),
        )

        # --- Setup: Messaging ---
        router = MessageRouter()
        router.create_channel(
            root_instance.instance_id,
            child_instance.instance_id,
            capacity=10,
        )
        router.create_channel(
            child_instance.instance_id,
            root_instance.instance_id,
            capacity=10,
        )

        # --- Step 1: Parent sends delegation ---
        context_snapshot = child_scope.snapshot()
        delegation = MessageEnvelope(
            from_instance=root_instance.instance_id,
            to_instance=child_instance.instance_id,
            payload=DelegationPayload(
                task_description="Analyze Q4 sales data",
                context_snapshot=context_snapshot,
                priority=Priority.NORMAL,
            ),
        )
        await router.route(delegation)

        # Child receives the delegation
        child_pending = await router.pending_for(child_instance.instance_id)
        assert len(child_pending) == 1
        received_delegation = child_pending[0]
        assert isinstance(received_delegation.payload, DelegationPayload)

        # --- Step 2: Child does work, consumes budget ---
        cost_entry = _make_cost_entry(
            "financial", 75.0, agent_id=child_instance.instance_id
        )
        verdict = await child_tracker.record_consumption(cost_entry)
        assert verdict.is_approved

        # Child writes results to its scoped context
        child_scope.set("results.revenue_total", 2_500_000)
        child_scope.set("results.anomaly_count", 3)
        child_scope.set("results.recommendation", "Investigate region_west")

        # --- Step 3: Child sends completion back ---
        completion = MessageEnvelope(
            from_instance=child_instance.instance_id,
            to_instance=root_instance.instance_id,
            payload=CompletionPayload(
                result={
                    "revenue_total": 2_500_000,
                    "anomaly_count": 3,
                },
                success=True,
            ),
            correlation_id=delegation.message_id,
        )
        await router.route(completion)

        # --- Step 4: Parent processes completion ---
        parent_pending = await router.pending_for(root_instance.instance_id)
        assert len(parent_pending) == 1
        received_completion = parent_pending[0]
        assert isinstance(received_completion.payload, CompletionPayload)
        assert received_completion.correlation_id == delegation.message_id
        assert received_completion.payload.success is True

        # --- Step 5: Reclaim unused budget ---
        reclaim_result = await parent_tracker.reclaim(
            child_instance.instance_id, consumed=75.0
        )
        assert reclaim_result.reclaimed_financial == pytest.approx(125.0)

        parent_remaining = await parent_tracker.remaining()
        # Parent consumed 75 (child's actual), reclaimed 125, so remaining = 500 - 75 = 425
        assert parent_remaining.financial_remaining == pytest.approx(425.0)

        # --- Step 6: Merge child context back ---
        merge_result = root_scope.merge_child_results(child_scope)
        assert "results.revenue_total" in merge_result.merged_keys
        assert "results.anomaly_count" in merge_result.merged_keys
        assert "results.recommendation" in merge_result.merged_keys

        # Verify parent now has child's results
        assert root_scope.get("results.revenue_total").value == 2_500_000

        # --- Step 7: Terminate child ---
        await factory.update_state(
            child_instance.instance_id,
            AgentLifecycleState.completed(result={"revenue_total": 2_500_000}),
        )

        child_state = await factory.get_state(child_instance.instance_id)
        assert child_state.is_terminal
        assert child_state.tag.value == "completed"

        # Root still running
        root_state = await factory.get_state(root_instance.instance_id)
        assert not root_state.is_terminal

        # Final live count = 1 (root only)
        assert await factory.count_live() == 1
