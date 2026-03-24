# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tests for external HELD mechanism on GovernedSupervisor (TODO-07).

Validates that GovernanceHeldError from PACT governance is caught during
node execution, transitions the node to HELD state, records a HoldRecord,
and supports resolve_hold() for human-in-the-loop approval/rejection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from kaizen_agents.supervisor import GovernedSupervisor, GovernanceHeldError, HoldRecord
from kaizen_agents.types import (
    AgentSpec,
    Plan,
    PlanEdge,
    PlanEvent,
    PlanEventType,
    PlanNode,
    PlanNodeState,
    PlanState,
)
from kailash.trust.pact.verdict import GovernanceVerdict


def _make_held_error(reason: str) -> GovernanceHeldError:
    """Construct a GovernanceHeldError with a proper GovernanceVerdict."""
    verdict = GovernanceVerdict(
        level="held",
        reason=reason,
        role_address="test-role",
        action="test-action",
    )
    return GovernanceHeldError(verdict)


# ---------------------------------------------------------------------------
# Test executors
# ---------------------------------------------------------------------------


async def governance_held_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that raises GovernanceHeldError (simulating external governance hold)."""
    raise _make_held_error("clearance_required")


async def success_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that always succeeds."""
    return {"result": f"output:{spec.name}", "cost": 0.10}


async def mixed_held_executor(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
    """Executor that holds 'held-task' nodes and succeeds on others."""
    if spec.name == "held-task":
        raise _make_held_error("needs_human_approval")
    return {"result": f"output:{spec.name}", "cost": 0.05}


# ---------------------------------------------------------------------------
# GovernanceHeldError import and fallback
# ---------------------------------------------------------------------------


class TestGovernanceHeldErrorImport:
    """Verify GovernanceHeldError is importable from supervisor module."""

    def test_governance_held_error_is_importable(self) -> None:
        """GovernanceHeldError can be imported from supervisor."""
        assert GovernanceHeldError is not None

    def test_governance_held_error_is_exception(self) -> None:
        """GovernanceHeldError is a subclass of Exception."""
        assert issubclass(GovernanceHeldError, Exception)

    def test_governance_held_error_can_be_raised_and_caught(self) -> None:
        """GovernanceHeldError can be raised and caught."""
        with pytest.raises(GovernanceHeldError):
            raise _make_held_error("test reason")


# ---------------------------------------------------------------------------
# HoldRecord dataclass
# ---------------------------------------------------------------------------


class TestHoldRecord:
    """Verify HoldRecord dataclass fields and defaults."""

    def test_hold_record_creation(self) -> None:
        """HoldRecord can be constructed with required fields."""
        record = HoldRecord(
            node_id="node-1",
            reason="clearance_required",
            details={"level": "held"},
            held_at=datetime.now(timezone.utc),
        )
        assert record.node_id == "node-1"
        assert record.reason == "clearance_required"
        assert record.details == {"level": "held"}
        assert record.approved is None
        assert record.modified_context is None

    def test_hold_record_event_not_set_by_default(self) -> None:
        """HoldRecord.event starts as not-set (for async await pattern)."""
        record = HoldRecord(
            node_id="node-1",
            reason="test",
            details={},
            held_at=datetime.now(timezone.utc),
        )
        assert not record.event.is_set()

    def test_hold_record_approved_field(self) -> None:
        """HoldRecord.approved starts as None (unresolved)."""
        record = HoldRecord(
            node_id="n",
            reason="r",
            details={},
            held_at=datetime.now(timezone.utc),
        )
        assert record.approved is None


# ---------------------------------------------------------------------------
# run() catches GovernanceHeldError
# ---------------------------------------------------------------------------


class TestRunCatchesGovernanceHeldError:
    """Test that run() catches GovernanceHeldError and sets node to HELD."""

    @pytest.mark.asyncio
    async def test_governance_held_sets_node_held(self) -> None:
        """When executor raises GovernanceHeldError, node transitions to HELD."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        result = await supervisor.run("test objective", execute_node=governance_held_executor)

        # The plan should not be fully successful since the node is HELD (not COMPLETED)
        assert result.success is False
        assert result.plan is not None

        # The single node should be in HELD state
        held_nodes = [n for n in result.plan.nodes.values() if n.state == PlanNodeState.HELD]
        assert len(held_nodes) == 1

    @pytest.mark.asyncio
    async def test_governance_held_emits_node_held_event(self) -> None:
        """When GovernanceHeldError is caught, a NODE_HELD event is emitted."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        result = await supervisor.run("test objective", execute_node=governance_held_executor)

        held_events = [e for e in result.events if e.event_type == PlanEventType.NODE_HELD]
        assert len(held_events) == 1
        assert held_events[0].node_id == "task-0"

    @pytest.mark.asyncio
    async def test_governance_held_creates_hold_record(self) -> None:
        """When GovernanceHeldError is caught, a HoldRecord is stored in _held_nodes."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        await supervisor.run("test objective", execute_node=governance_held_executor)

        assert len(supervisor.held_nodes) == 1
        record = supervisor.held_nodes["task-0"]
        assert record.node_id == "task-0"
        assert "clearance_required" in record.reason
        assert isinstance(record.held_at, datetime)
        assert record.approved is None

    @pytest.mark.asyncio
    async def test_governance_held_records_audit(self) -> None:
        """When GovernanceHeldError is caught, the hold is recorded in audit trail."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        result = await supervisor.run("test objective", execute_node=governance_held_executor)

        # Find audit records related to the hold
        held_records = [r for r in result.audit_trail if r.get("record_type") == "held"]
        assert len(held_records) >= 1

    @pytest.mark.asyncio
    async def test_governance_held_reason_from_verdict(self) -> None:
        """Hold reason is extracted from the GovernanceHeldError."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        await supervisor.run("test objective", execute_node=governance_held_executor)

        record = supervisor.held_nodes["task-0"]
        # The reason should contain the governance message
        assert "clearance_required" in record.reason


# ---------------------------------------------------------------------------
# run_plan() catches GovernanceHeldError
# ---------------------------------------------------------------------------


class TestRunPlanCatchesGovernanceHeldError:
    """Test that run_plan() also catches GovernanceHeldError."""

    @pytest.mark.asyncio
    async def test_run_plan_governance_held_sets_node_held(self) -> None:
        """run_plan() catches GovernanceHeldError and sets node to HELD."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        spec = AgentSpec(spec_id="t", name="held-task", description="test")
        plan = Plan(
            name="held-test",
            nodes={"n1": PlanNode(node_id="n1", agent_spec=spec)},
            edges=[],
        )

        result = await supervisor.run_plan(plan, execute_node=governance_held_executor)

        assert result.success is False
        held_nodes = [n for n in result.plan.nodes.values() if n.state == PlanNodeState.HELD]
        assert len(held_nodes) == 1

    @pytest.mark.asyncio
    async def test_run_plan_governance_held_creates_hold_record(self) -> None:
        """run_plan() stores HoldRecord for governance-held nodes."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        spec = AgentSpec(spec_id="t", name="task", description="test")
        plan = Plan(
            name="held-test",
            nodes={"n1": PlanNode(node_id="n1", agent_spec=spec)},
            edges=[],
        )

        await supervisor.run_plan(plan, execute_node=governance_held_executor)

        assert "n1" in supervisor.held_nodes
        record = supervisor.held_nodes["n1"]
        assert record.node_id == "n1"
        assert record.approved is None

    @pytest.mark.asyncio
    async def test_run_plan_mixed_held_and_success(self) -> None:
        """In a multi-node plan, some nodes succeed and others are HELD."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        spec_ok = AgentSpec(spec_id="ok", name="ok-task", description="succeeds")
        spec_held = AgentSpec(spec_id="held", name="held-task", description="held")

        plan = Plan(
            name="mixed-test",
            nodes={
                "ok_node": PlanNode(node_id="ok_node", agent_spec=spec_ok),
                "held_node": PlanNode(node_id="held_node", agent_spec=spec_held),
            },
            edges=[],
        )

        result = await supervisor.run_plan(plan, execute_node=mixed_held_executor)

        # ok_node should have completed
        assert "ok_node" in result.results
        # held_node should be in HELD state
        assert plan.nodes["held_node"].state == PlanNodeState.HELD
        # HoldRecord should exist
        assert "held_node" in supervisor.held_nodes

    @pytest.mark.asyncio
    async def test_run_plan_held_emits_event(self) -> None:
        """run_plan() emits NODE_HELD events for governance-held nodes."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        spec = AgentSpec(spec_id="t", name="task", description="test")
        plan = Plan(
            name="held-test",
            nodes={"n1": PlanNode(node_id="n1", agent_spec=spec)},
            edges=[],
        )

        result = await supervisor.run_plan(plan, execute_node=governance_held_executor)

        held_events = [e for e in result.events if e.event_type == PlanEventType.NODE_HELD]
        assert len(held_events) == 1
        assert held_events[0].node_id == "n1"


# ---------------------------------------------------------------------------
# resolve_hold()
# ---------------------------------------------------------------------------


class TestResolveHold:
    """Test the resolve_hold() method for resuming or rejecting held nodes."""

    def test_resolve_hold_approved_sets_fields(self) -> None:
        """resolve_hold(approved=True) sets approved and signals the event."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        record = HoldRecord(
            node_id="test_node",
            reason="governance_hold",
            details={"source": "governance"},
            held_at=datetime.now(timezone.utc),
        )
        supervisor._held_nodes["test_node"] = record

        supervisor.resolve_hold("test_node", approved=True)

        assert record.approved is True
        assert record.event.is_set()
        assert record.modified_context is None

    def test_resolve_hold_rejected_sets_fields(self) -> None:
        """resolve_hold(approved=False) sets approved=False and signals."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        record = HoldRecord(
            node_id="test_node",
            reason="governance_hold",
            details={},
            held_at=datetime.now(timezone.utc),
        )
        supervisor._held_nodes["test_node"] = record

        supervisor.resolve_hold("test_node", approved=False)

        assert record.approved is False
        assert record.event.is_set()

    def test_resolve_hold_with_modified_context(self) -> None:
        """resolve_hold can pass modified_context for the resumed node."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        record = HoldRecord(
            node_id="test_node",
            reason="test",
            details={},
            held_at=datetime.now(timezone.utc),
        )
        supervisor._held_nodes["test_node"] = record

        modified = {"override_clearance": "confidential"}
        supervisor.resolve_hold("test_node", approved=True, modified_context=modified)

        assert record.approved is True
        assert record.modified_context == {"override_clearance": "confidential"}

    def test_resolve_hold_nonexistent_raises_value_error(self) -> None:
        """resolve_hold on a node that is not held raises ValueError."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        with pytest.raises(ValueError, match="not currently held"):
            supervisor.resolve_hold("nonexistent", approved=True)


# ---------------------------------------------------------------------------
# held_nodes property
# ---------------------------------------------------------------------------


class TestHeldNodesProperty:
    """Test the held_nodes read-only property."""

    def test_held_nodes_empty_by_default(self) -> None:
        """A new supervisor has no held nodes."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        assert isinstance(supervisor.held_nodes, dict)
        assert len(supervisor.held_nodes) == 0

    def test_held_nodes_returns_copy(self) -> None:
        """held_nodes returns a copy -- mutation does not affect internals."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)

        record = HoldRecord(
            node_id="n1",
            reason="test",
            details={},
            held_at=datetime.now(timezone.utc),
        )
        supervisor._held_nodes["n1"] = record

        external = supervisor.held_nodes
        assert len(external) == 1

        # Mutating the copy should not affect the internal state
        external.pop("n1")
        assert len(supervisor.held_nodes) == 1

    @pytest.mark.asyncio
    async def test_held_nodes_populated_after_governance_hold(self) -> None:
        """held_nodes is populated after a governance hold during run()."""
        supervisor = GovernedSupervisor(model="test", budget_usd=10.0)
        await supervisor.run("test", execute_node=governance_held_executor)

        nodes = supervisor.held_nodes
        assert len(nodes) == 1
        assert "task-0" in nodes


# ---------------------------------------------------------------------------
# __all__ export
# ---------------------------------------------------------------------------


class TestExports:
    """Verify HoldRecord is exported in __all__."""

    def test_hold_record_in_module_all(self) -> None:
        """HoldRecord is in supervisor module's __all__."""
        import kaizen_agents.supervisor as mod

        assert "HoldRecord" in mod.__all__
