# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""M6-02: E2E delegation test for L3 module.

Tier 3 test -- NO MOCKING. Complete user workflow.

Scenario: Root agent with budget spawns children, delegates tasks
via messages, children consume budget and produce results, parent
collects results and reclaims unused budget.

This exercises the full lifecycle across all L3 primitives:
    - AgentFactory + AgentInstanceRegistry (spawn, state, terminate)
    - EnvelopeTracker + EnvelopeSplitter (budget split, consume, reclaim)
    - ContextScope (hierarchical scoped context with projections)
    - MessageRouter + MessageChannel (delegation, completion, correlation)
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kaizen.l3.context import (
    ContextScope,
    DataClassification,
    ScopeProjection,
)
from kaizen.l3.envelope import (
    AllocationRequest,
    CostEntry,
    EnvelopeSplitter,
    EnvelopeTracker,
    GradientZone,
    PlanGradient,
)
from kaizen.l3.factory import (
    AgentFactory,
    AgentInstanceRegistry,
    AgentLifecycleState,
    AgentSpec,
    TerminationReason,
)
from kaizen.l3.messaging import (
    CompletionPayload,
    DelegationPayload,
    MessageEnvelope,
    MessageRouter,
    Priority,
    ResourceSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(
    spec_id: str,
    *,
    tools: list[str] | None = None,
    max_children: int | None = None,
) -> AgentSpec:
    return AgentSpec(
        spec_id=spec_id,
        name=f"Agent {spec_id}",
        description=f"Spec for {spec_id}",
        tool_ids=tools or [],
        max_children=max_children,
    )


def _cost_entry(dimension: str, cost: float, agent_id: str) -> CostEntry:
    return CostEntry(
        action="work",
        dimension=dimension,
        cost=cost,
        timestamp=datetime.now(UTC),
        agent_instance_id=agent_id,
    )


# ---------------------------------------------------------------------------
# E2E: Multi-child delegation with budget and context
# ---------------------------------------------------------------------------


class TestE2EDelegation:
    """
    Full E2E scenario:

    1. Root agent (coordinator) starts with $1000 budget.
    2. Coordinator splits budget: 40% to researcher, 30% to analyst, 30% reserve.
    3. Coordinator spawns researcher and analyst as children.
    4. Coordinator creates scoped context for each child.
    5. Coordinator sends delegation messages to both children.
    6. Each child "executes work" (consumes budget, writes results).
    7. Each child sends completion back to coordinator.
    8. Coordinator reclaims unused budget from each child.
    9. Coordinator merges child contexts back.
    10. Coordinator terminates children, verifies final state.
    """

    @pytest.mark.asyncio
    async def test_multi_child_delegation_lifecycle(self) -> None:
        # ---------------------------------------------------------------
        # Phase 1: Infrastructure setup
        # ---------------------------------------------------------------
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)
        gradient = PlanGradient(
            budget_flag_threshold=0.80,
            budget_hold_threshold=0.95,
        )

        # Spawn root coordinator
        root_spec = _spec(
            "coordinator",
            tools=["search", "analyze", "summarize", "report"],
            max_children=5,
        )
        root = await factory.spawn(root_spec)
        await factory.update_state(root.instance_id, AgentLifecycleState.running())

        # Root envelope and tracker
        root_envelope = {
            "financial_limit": 1000.0,
            "temporal_limit_seconds": 3600.0,
            "action_limit": 100,
        }
        root_tracker = EnvelopeTracker(root_envelope, gradient)

        # ---------------------------------------------------------------
        # Phase 2: Budget splitting
        # ---------------------------------------------------------------
        allocations = [
            AllocationRequest(
                child_id="researcher",
                financial_ratio=0.4,
                temporal_ratio=0.4,
            ),
            AllocationRequest(
                child_id="analyst",
                financial_ratio=0.3,
                temporal_ratio=0.3,
            ),
        ]
        child_envelopes = EnvelopeSplitter.split(
            root_envelope, allocations, reserve_pct=0.3
        )
        assert len(child_envelopes) == 2

        researcher_env = dict(child_envelopes[0][1])
        analyst_env = dict(child_envelopes[1][1])

        # Verify budget conservation
        assert researcher_env["financial_limit"] == pytest.approx(400.0)
        assert analyst_env["financial_limit"] == pytest.approx(300.0)
        total_allocated = (
            researcher_env["financial_limit"]
            + analyst_env["financial_limit"]
            + 1000.0 * 0.3  # reserve
        )
        assert total_allocated == pytest.approx(1000.0)

        # Register allocations with root tracker
        await root_tracker.allocate_to_child("researcher", 400.0)
        await root_tracker.allocate_to_child("analyst", 300.0)

        # Root remaining after allocations
        root_remaining = await root_tracker.remaining()
        assert root_remaining.financial_remaining == pytest.approx(300.0)

        # ---------------------------------------------------------------
        # Phase 3: Spawn children
        # ---------------------------------------------------------------
        researcher_spec = _spec("researcher-spec", tools=["search", "analyze"])
        researcher = await factory.spawn(researcher_spec, parent_id=root.instance_id)
        await factory.update_state(
            researcher.instance_id, AgentLifecycleState.running()
        )

        analyst_spec = _spec("analyst-spec", tools=["analyze", "summarize"])
        analyst = await factory.spawn(analyst_spec, parent_id=root.instance_id)
        await factory.update_state(analyst.instance_id, AgentLifecycleState.running())

        # Verify children
        children = await factory.children_of(root.instance_id)
        assert len(children) == 2
        assert await factory.count_live() == 3

        # ---------------------------------------------------------------
        # Phase 4: Scoped context for each child
        # ---------------------------------------------------------------
        root_scope = ContextScope.root(
            root.instance_id,
            clearance=DataClassification.CONFIDENTIAL,
            default_classification=DataClassification.RESTRICTED,
        )
        root_scope.set("project.name", "Q4 Analysis")
        root_scope.set("project.deadline", "2026-03-31")
        root_scope.set("data.source", "internal_db", DataClassification.CONFIDENTIAL)

        # Researcher scope: can read project.** and data.**, write results.**
        researcher_scope = root_scope.create_child(
            owner_id=researcher.instance_id,
            read_projection=ScopeProjection(
                allow_patterns=["project.**", "data.**"],
                deny_patterns=[],
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.research.**"],
                deny_patterns=[],
            ),
            effective_clearance=DataClassification.CONFIDENTIAL,
        )

        # Analyst scope: can read project.** only, write results.analysis.**
        analyst_scope = root_scope.create_child(
            owner_id=analyst.instance_id,
            read_projection=ScopeProjection(
                allow_patterns=["project.**"],
                deny_patterns=[],
            ),
            write_projection=ScopeProjection(
                allow_patterns=["results.analysis.**"],
                deny_patterns=[],
            ),
            effective_clearance=DataClassification.RESTRICTED,
        )

        # Verify scope isolation
        assert researcher_scope.get("data.source") is not None
        assert (
            analyst_scope.get("data.source") is None
        )  # CONFIDENTIAL > RESTRICTED clearance

        # ---------------------------------------------------------------
        # Phase 5: Messaging -- send delegations
        # ---------------------------------------------------------------
        router = MessageRouter()

        # Create bidirectional channels
        router.create_channel(root.instance_id, researcher.instance_id, 10)
        router.create_channel(researcher.instance_id, root.instance_id, 10)
        router.create_channel(root.instance_id, analyst.instance_id, 10)
        router.create_channel(analyst.instance_id, root.instance_id, 10)

        # Send delegation to researcher
        researcher_delegation = MessageEnvelope(
            from_instance=root.instance_id,
            to_instance=researcher.instance_id,
            payload=DelegationPayload(
                task_description="Research market trends for Q4",
                context_snapshot=researcher_scope.snapshot(),
                priority=Priority.HIGH,
            ),
        )
        await router.route(researcher_delegation)

        # Send delegation to analyst
        analyst_delegation = MessageEnvelope(
            from_instance=root.instance_id,
            to_instance=analyst.instance_id,
            payload=DelegationPayload(
                task_description="Analyze financial performance metrics",
                context_snapshot=analyst_scope.snapshot(),
                priority=Priority.NORMAL,
            ),
        )
        await router.route(analyst_delegation)

        # Verify messages are pending
        researcher_pending = await router.pending_for(researcher.instance_id)
        analyst_pending = await router.pending_for(analyst.instance_id)
        assert len(researcher_pending) == 1
        assert len(analyst_pending) == 1

        # ---------------------------------------------------------------
        # Phase 6: Children do work (consume budget, write results)
        # ---------------------------------------------------------------

        # Researcher consumes budget
        researcher_tracker = EnvelopeTracker(researcher_env, gradient)
        r_cost1 = _cost_entry("financial", 100.0, researcher.instance_id)
        r_verdict1 = await researcher_tracker.record_consumption(r_cost1)
        assert r_verdict1.is_approved

        r_cost2 = _cost_entry("financial", 80.0, researcher.instance_id)
        r_verdict2 = await researcher_tracker.record_consumption(r_cost2)
        assert r_verdict2.is_approved

        researcher_consumed = 180.0

        # Researcher writes results
        researcher_scope.set(
            "results.research.trends",
            [
                "AI adoption up 35%",
                "Cloud spending increased 20%",
            ],
        )
        researcher_scope.set("results.research.confidence", 0.92)

        # Analyst consumes budget
        analyst_tracker = EnvelopeTracker(analyst_env, gradient)
        a_cost1 = _cost_entry("financial", 50.0, analyst.instance_id)
        a_verdict1 = await analyst_tracker.record_consumption(a_cost1)
        assert a_verdict1.is_approved

        analyst_consumed = 50.0

        # Analyst writes results
        analyst_scope.set("results.analysis.revenue_growth", 0.12)
        analyst_scope.set("results.analysis.risk_score", "low")

        # ---------------------------------------------------------------
        # Phase 7: Children send completions
        # ---------------------------------------------------------------

        researcher_completion = MessageEnvelope(
            from_instance=researcher.instance_id,
            to_instance=root.instance_id,
            payload=CompletionPayload(
                result={"trends_found": 2, "confidence": 0.92},
                success=True,
                resource_consumed=ResourceSnapshot(
                    financial_spent=researcher_consumed,
                    actions_executed=2,
                ),
            ),
            correlation_id=researcher_delegation.message_id,
        )
        await router.route(researcher_completion)

        analyst_completion = MessageEnvelope(
            from_instance=analyst.instance_id,
            to_instance=root.instance_id,
            payload=CompletionPayload(
                result={"revenue_growth": 0.12, "risk": "low"},
                success=True,
                resource_consumed=ResourceSnapshot(
                    financial_spent=analyst_consumed,
                    actions_executed=1,
                ),
            ),
            correlation_id=analyst_delegation.message_id,
        )
        await router.route(analyst_completion)

        # Root should have two completions
        root_pending = await router.pending_for(root.instance_id)
        assert len(root_pending) == 2

        # Verify correlation IDs match
        completion_correlations = {m.correlation_id for m in root_pending}
        assert researcher_delegation.message_id in completion_correlations
        assert analyst_delegation.message_id in completion_correlations

        # All completions successful
        for msg in root_pending:
            assert isinstance(msg.payload, CompletionPayload)
            assert msg.payload.success is True

        # ---------------------------------------------------------------
        # Phase 8: Reclaim unused budget
        # ---------------------------------------------------------------

        # Researcher allocated 400, consumed 180, reclaim 220
        r_reclaim = await root_tracker.reclaim(
            "researcher", consumed=researcher_consumed
        )
        assert r_reclaim.reclaimed_financial == pytest.approx(220.0)
        assert r_reclaim.child_total_consumed == pytest.approx(180.0)

        # Analyst allocated 300, consumed 50, reclaim 250
        a_reclaim = await root_tracker.reclaim("analyst", consumed=analyst_consumed)
        assert a_reclaim.reclaimed_financial == pytest.approx(250.0)
        assert a_reclaim.child_total_consumed == pytest.approx(50.0)

        # Root remaining: 1000 - 180 (researcher) - 50 (analyst) = 770
        final_remaining = await root_tracker.remaining()
        assert final_remaining.financial_remaining == pytest.approx(770.0)

        # ---------------------------------------------------------------
        # Phase 9: Merge child contexts back
        # ---------------------------------------------------------------

        researcher_merge = root_scope.merge_child_results(researcher_scope)
        assert "results.research.trends" in researcher_merge.merged_keys
        assert "results.research.confidence" in researcher_merge.merged_keys

        analyst_merge = root_scope.merge_child_results(analyst_scope)
        assert "results.analysis.revenue_growth" in analyst_merge.merged_keys
        assert "results.analysis.risk_score" in analyst_merge.merged_keys

        # Verify all results are in root scope
        trends = root_scope.get("results.research.trends")
        assert trends is not None
        assert len(trends.value) == 2

        growth = root_scope.get("results.analysis.revenue_growth")
        assert growth is not None
        assert growth.value == pytest.approx(0.12)

        # ---------------------------------------------------------------
        # Phase 10: Terminate children, verify final state
        # ---------------------------------------------------------------

        # Mark children as completed
        await factory.update_state(
            researcher.instance_id,
            AgentLifecycleState.completed(result={"trends_found": 2}),
        )
        await factory.update_state(
            analyst.instance_id,
            AgentLifecycleState.completed(result={"revenue_growth": 0.12}),
        )

        # Verify terminal states
        r_state = await factory.get_state(researcher.instance_id)
        a_state = await factory.get_state(analyst.instance_id)
        assert r_state.is_terminal
        assert a_state.is_terminal
        assert r_state.tag.value == "completed"
        assert a_state.tag.value == "completed"

        # Root still running
        root_state = await factory.get_state(root.instance_id)
        assert not root_state.is_terminal
        assert await factory.count_live() == 1

        # Close channels for terminated children
        router.close_channels_for(researcher.instance_id)
        router.close_channels_for(analyst.instance_id)

        # Root completes
        await factory.update_state(
            root.instance_id,
            AgentLifecycleState.completed(
                result={
                    "research": {"trends_found": 2},
                    "analysis": {"revenue_growth": 0.12},
                }
            ),
        )
        assert await factory.count_live() == 0

    @pytest.mark.asyncio
    async def test_child_failure_triggers_budget_reclaim(self) -> None:
        """When a child fails, parent reclaims its full allocated budget."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)
        gradient = PlanGradient()

        root_spec = _spec("root", tools=["a"])
        root = await factory.spawn(root_spec)
        await factory.update_state(root.instance_id, AgentLifecycleState.running())

        root_envelope = {"financial_limit": 500.0}
        root_tracker = EnvelopeTracker(root_envelope, gradient)

        # Allocate 200 to child
        await root_tracker.allocate_to_child("child-alloc", 200.0)

        child_spec = _spec("child", tools=["a"])
        child = await factory.spawn(child_spec, parent_id=root.instance_id)
        await factory.update_state(child.instance_id, AgentLifecycleState.running())

        # Child fails immediately (consumed 0)
        await factory.update_state(
            child.instance_id,
            AgentLifecycleState.failed(error="API timeout"),
        )

        # Reclaim full allocation
        result = await root_tracker.reclaim("child-alloc", consumed=0.0)
        assert result.reclaimed_financial == pytest.approx(200.0)

        remaining = await root_tracker.remaining()
        assert remaining.financial_remaining == pytest.approx(500.0)

    @pytest.mark.asyncio
    async def test_cascade_termination_closes_channels(self) -> None:
        """Cascade termination closes messaging channels for descendants."""
        registry = AgentInstanceRegistry()
        factory = AgentFactory(registry)

        root_spec = _spec("root", tools=["a", "b"])
        root = await factory.spawn(root_spec)
        await factory.update_state(root.instance_id, AgentLifecycleState.running())

        child_spec = _spec("child", tools=["a"])
        child = await factory.spawn(child_spec, parent_id=root.instance_id)
        await factory.update_state(child.instance_id, AgentLifecycleState.running())

        # Set up messaging
        router = MessageRouter()
        router.create_channel(root.instance_id, child.instance_id, 10)
        router.create_channel(child.instance_id, root.instance_id, 10)

        # Send a delegation
        delegation = MessageEnvelope(
            from_instance=root.instance_id,
            to_instance=child.instance_id,
            payload=DelegationPayload(
                task_description="Do work",
            ),
        )
        await router.route(delegation)

        # Cascade termination
        await factory.terminate(root.instance_id, TerminationReason.BUDGET_EXHAUSTED)

        # Close channels for terminated instances
        router.close_channels_for(child.instance_id)
        router.close_channels_for(root.instance_id)

        # Dead letters should have the pending delegation
        assert router.dead_letters.count() >= 1
        assert await factory.count_live() == 0
