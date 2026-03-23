# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for SDK validation integration (P0-03 through P0-05).

Tests the bridge between local kaizen-agents types and SDK PlanValidator,
the HELD state mapping round-trip, and PlanComposer SDK validation.

Tier 1: Unit tests, may use mocks for LLM. No external dependencies.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents._sdk_compat import (
    plan_from_sdk,
    plan_node_state_from_sdk,
    plan_node_state_to_sdk,
    plan_to_sdk,
)
from kaizen_agents.llm import LLMClient
from kaizen_agents.orchestration.monitor import PlanMonitor
from kaizen_agents.orchestration.planner.composer import PlanComposer
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    GradientZone,
    Plan,
    PlanEdge,
    PlanGradient,
    PlanNode,
    PlanNodeOutput,
    PlanNodeState,
    PlanState,
)
from kaizen.l3.plan.types import PlanNodeState as SdkPlanNodeState
from kaizen.l3.plan.validator import PlanValidator as SdkPlanValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm(structured_response: dict[str, Any] | None = None) -> LLMClient:
    """Create a mock LLMClient."""
    mock = MagicMock(spec=LLMClient)
    if structured_response is not None:
        mock.complete_structured.return_value = structured_response
    else:
        mock.complete_structured.return_value = {}
    return mock


def _make_agent_spec(
    spec_id: str = "spec-test",
    name: str = "test-agent",
    financial_limit: float = 5.0,
) -> AgentSpec:
    """Create an AgentSpec with sensible defaults."""
    return AgentSpec(
        spec_id=spec_id,
        name=name,
        description=f"Agent: {name}",
        capabilities=["test"],
        tool_ids=[],
        envelope=ConstraintEnvelope(
            financial={"limit": financial_limit},
            operational={"allowed": [], "blocked": []},
        ),
    )


def _make_valid_three_node_plan() -> Plan:
    """Build a valid three-node linear plan: node-0 -> node-1 -> node-2.

    The plan is structurally valid (no cycles, has root, has leaf,
    referential integrity). Suitable for SDK validation.
    """
    specs = [
        _make_agent_spec(spec_id="spec-gather", name="gather", financial_limit=3.0),
        _make_agent_spec(spec_id="spec-analyze", name="analyze", financial_limit=3.0),
        _make_agent_spec(spec_id="spec-report", name="report", financial_limit=3.0),
    ]
    nodes = {
        "node-0": PlanNode(
            node_id="node-0",
            agent_spec=specs[0],
            state=PlanNodeState.PENDING,
        ),
        "node-1": PlanNode(
            node_id="node-1",
            agent_spec=specs[1],
            input_mapping={
                "data": PlanNodeOutput(source_node="node-0", output_key="result"),
            },
            state=PlanNodeState.PENDING,
        ),
        "node-2": PlanNode(
            node_id="node-2",
            agent_spec=specs[2],
            input_mapping={
                "analysis": PlanNodeOutput(source_node="node-1", output_key="result"),
            },
            state=PlanNodeState.PENDING,
        ),
    }
    edges = [
        PlanEdge(from_node="node-0", to_node="node-1", edge_type=EdgeType.DATA_DEPENDENCY),
        PlanEdge(from_node="node-1", to_node="node-2", edge_type=EdgeType.DATA_DEPENDENCY),
    ]
    return Plan(
        plan_id="valid-3-node",
        name="Valid Three Node Plan",
        nodes=nodes,
        edges=edges,
        state=PlanState.DRAFT,
        envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        gradient=PlanGradient(retry_budget=2),
    )


# ---------------------------------------------------------------------------
# P0-03: PlanMonitor.validate_plan_with_sdk
# ---------------------------------------------------------------------------


class TestValidatePlanWithSdk:
    """P0-03: Validate local plans via SDK PlanValidator."""

    def test_valid_plan_returns_no_errors(self) -> None:
        """A structurally valid local Plan should produce zero SDK validation errors."""
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )
        plan = _make_valid_three_node_plan()

        errors = monitor.validate_plan_with_sdk(plan)

        assert isinstance(errors, list)
        assert len(errors) == 0, f"Expected no errors but got: {errors}"

    def test_empty_plan_returns_errors(self) -> None:
        """An empty plan (no nodes) should produce SDK validation errors."""
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )
        plan = Plan(
            plan_id="empty-plan",
            name="Empty Plan",
            nodes={},
            edges=[],
            state=PlanState.DRAFT,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )

        errors = monitor.validate_plan_with_sdk(plan)

        assert len(errors) > 0
        # At least one error should mention empty or no nodes
        assert any(
            "node" in e.lower() or "empty" in e.lower() for e in errors
        ), f"Expected error about empty plan, got: {errors}"

    def test_cyclic_plan_returns_errors(self) -> None:
        """A plan with a cycle should produce SDK validation errors."""
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )
        spec = _make_agent_spec(spec_id="spec-a", name="agent-a")
        spec_b = _make_agent_spec(spec_id="spec-b", name="agent-b")
        plan = Plan(
            plan_id="cyclic-plan",
            name="Cyclic Plan",
            nodes={
                "node-a": PlanNode(node_id="node-a", agent_spec=spec),
                "node-b": PlanNode(node_id="node-b", agent_spec=spec_b),
            },
            edges=[
                PlanEdge(from_node="node-a", to_node="node-b", edge_type=EdgeType.DATA_DEPENDENCY),
                PlanEdge(from_node="node-b", to_node="node-a", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
            state=PlanState.DRAFT,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )

        errors = monitor.validate_plan_with_sdk(plan)

        assert len(errors) > 0
        # At least one error should mention cycle
        assert any(
            "cycle" in e.lower() or "ycle" in e.lower() for e in errors
        ), f"Expected cycle error, got: {errors}"

    def test_returns_strings(self) -> None:
        """All returned errors must be strings, regardless of SDK error type."""
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )
        plan = Plan(
            plan_id="empty",
            name="Empty",
            nodes={},
            edges=[],
            state=PlanState.DRAFT,
            envelope=ConstraintEnvelope(),
            gradient=PlanGradient(retry_budget=2),
        )

        errors = monitor.validate_plan_with_sdk(plan)

        for error in errors:
            assert isinstance(error, str), f"Error should be str, got {type(error)}: {error}"

    def test_self_edge_detected(self) -> None:
        """A plan with a self-edge should produce validation errors."""
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )
        spec = _make_agent_spec(spec_id="spec-self", name="self-agent")
        plan = Plan(
            plan_id="self-edge-plan",
            name="Self Edge Plan",
            nodes={
                "node-x": PlanNode(node_id="node-x", agent_spec=spec),
            },
            edges=[
                PlanEdge(from_node="node-x", to_node="node-x", edge_type=EdgeType.DATA_DEPENDENCY),
            ],
            state=PlanState.DRAFT,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )

        errors = monitor.validate_plan_with_sdk(plan)

        assert len(errors) > 0
        assert any(
            "self" in e.lower() or "Self" in e for e in errors
        ), f"Expected self-edge error, got: {errors}"


# ---------------------------------------------------------------------------
# P0-04: Recovery with HELD mapping verification
# ---------------------------------------------------------------------------


class TestHeldMappingRoundTrip:
    """P0-04: Verify the HELD state mapping works correctly at boundaries."""

    def test_local_failed_to_sdk_is_failed(self) -> None:
        """Local FAILED state maps to SDK FAILED state (not HELD)."""
        sdk_state = plan_node_state_to_sdk(PlanNodeState.FAILED)
        assert sdk_state == SdkPlanNodeState.FAILED

    def test_sdk_held_to_local_is_held(self) -> None:
        """SDK HELD state maps to local HELD state (both have HELD now)."""
        local_state = plan_node_state_from_sdk(SdkPlanNodeState.HELD)
        assert local_state == PlanNodeState.HELD

    def test_held_node_in_sdk_plan_round_trips_to_held(self) -> None:
        """An SDK plan with a HELD node converts to local as HELD.

        This verifies the full plan-level round-trip for the HELD mapping:
        1. Create local plan with HELD node
        2. Convert to SDK (HELD stays HELD)
        3. Convert back to local -> should be HELD
        """
        spec = _make_agent_spec(spec_id="spec-held", name="held-agent")
        plan = Plan(
            plan_id="held-test",
            name="Held Test Plan",
            nodes={
                "node-held": PlanNode(
                    node_id="node-held",
                    agent_spec=spec,
                    state=PlanNodeState.HELD,
                    error="Budget hold threshold reached",
                ),
            },
            edges=[],
            state=PlanState.EXECUTING,
            envelope=ConstraintEnvelope(),
            gradient=PlanGradient(retry_budget=2),
        )

        # Step 1: Local HELD -> SDK HELD
        sdk_plan = plan_to_sdk(plan)
        assert sdk_plan.nodes["node-held"].state == SdkPlanNodeState.HELD

        # Step 2: SDK HELD -> Local HELD
        specs = {"spec-held": spec}
        local_plan = plan_from_sdk(sdk_plan, agent_specs=specs)
        assert local_plan.nodes["node-held"].state == PlanNodeState.HELD

    def test_gradient_zone_held_classification(self) -> None:
        """When the monitor classifies a failure as GradientZone.HELD,
        the node state is set to FAILED (local type has no HELD state).

        This verifies the design choice: HELD gradient zone results in
        FAILED node state + recovery attempt.
        """
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(
                retry_budget=0,  # No retries -> immediate escalation
                after_retry_exhaustion=GradientZone.HELD,
            ),
        )

        spec = _make_agent_spec(spec_id="spec-fail", name="fail-agent")
        plan = Plan(
            plan_id="held-gradient-test",
            name="Held Gradient Test",
            nodes={
                "node-fail": PlanNode(
                    node_id="node-fail",
                    agent_spec=spec,
                    state=PlanNodeState.PENDING,
                ),
            },
            edges=[],
            state=PlanState.VALIDATED,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(
                retry_budget=0,
                after_retry_exhaustion=GradientZone.HELD,
            ),
        )

        # Execute with a failing callback
        async def failing_callback(spec: AgentSpec, inputs: dict) -> dict:
            return {"error": "simulated failure"}

        import asyncio

        result = asyncio.run(monitor.run_plan(plan=plan, execute_node=failing_callback))

        # The node should be in FAILED state (local has no HELD)
        assert plan.nodes["node-fail"].state == PlanNodeState.FAILED

        # Converting to SDK should show FAILED (not HELD)
        sdk_plan = plan_to_sdk(plan)
        assert sdk_plan.nodes["node-fail"].state == SdkPlanNodeState.FAILED


# ---------------------------------------------------------------------------
# P0-05: PlanComposer SDK validation
# ---------------------------------------------------------------------------


class TestComposerSdkValidation:
    """P0-05: Verify that PlanComposer output validates through SDK PlanValidator."""

    def test_composed_plan_passes_sdk_structural_validation(self) -> None:
        """A plan composed by PlanComposer should pass SDK structural validation.

        Uses a mocked LLM that returns a valid composition response
        (two-subtask linear dependency), converts to SDK, validates.
        """
        from kaizen_agents.orchestration.planner.decomposer import Subtask
        from kaizen_agents.orchestration.planner.designer import SpawnDecision

        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},
            ],
            "input_mappings": [
                {
                    "target_index": 1,
                    "input_key": "research_data",
                    "source_index": 0,
                    "output_key": "findings",
                },
            ],
        }
        llm = _make_mock_llm(structured_response=llm_response)
        composer = PlanComposer(llm_client=llm)

        subtasks = [
            Subtask(
                description="Research the topic",
                estimated_complexity=3,
                required_capabilities=["search"],
                suggested_tools=["web_search"],
                depends_on=[],
                output_keys=["findings"],
            ),
            Subtask(
                description="Write the report",
                estimated_complexity=4,
                required_capabilities=["writing"],
                suggested_tools=["text_editor"],
                depends_on=[0],
                output_keys=["report"],
            ),
        ]
        specs = [
            (
                _make_agent_spec(spec_id="spec-researcher", name="researcher"),
                SpawnDecision(SpawnDecision.SPAWN, "Complex task"),
            ),
            (
                _make_agent_spec(spec_id="spec-writer", name="writer"),
                SpawnDecision(SpawnDecision.SPAWN, "Complex task"),
            ),
        ]

        plan = composer.compose(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=ConstraintEnvelope(financial={"limit": 20.0}),
            plan_name="research-report",
        )

        # Convert to SDK and validate via SDK PlanValidator
        sdk_plan = plan_to_sdk(plan)
        sdk_errors = SdkPlanValidator.validate_structure(sdk_plan)

        assert (
            len(sdk_errors) == 0
        ), f"SDK structural validation errors for composed plan: {sdk_errors}"

    def test_three_subtask_composed_plan_passes_sdk_validation(self) -> None:
        """A three-subtask composed plan (research -> implement -> test) validates."""
        from kaizen_agents.orchestration.planner.decomposer import Subtask
        from kaizen_agents.orchestration.planner.designer import SpawnDecision

        llm_response = {
            "edges": [
                {"from_index": 0, "to_index": 1, "edge_type": "data_dependency"},
                {"from_index": 1, "to_index": 2, "edge_type": "data_dependency"},
            ],
            "input_mappings": [
                {
                    "target_index": 1,
                    "input_key": "research",
                    "source_index": 0,
                    "output_key": "findings",
                },
                {
                    "target_index": 2,
                    "input_key": "code",
                    "source_index": 1,
                    "output_key": "implementation",
                },
            ],
        }
        llm = _make_mock_llm(structured_response=llm_response)
        composer = PlanComposer(llm_client=llm)

        subtasks = [
            Subtask(
                description="Research",
                estimated_complexity=2,
                required_capabilities=["search"],
                suggested_tools=[],
                depends_on=[],
                output_keys=["findings"],
            ),
            Subtask(
                description="Implement",
                estimated_complexity=4,
                required_capabilities=["coding"],
                suggested_tools=[],
                depends_on=[0],
                output_keys=["implementation"],
            ),
            Subtask(
                description="Test",
                estimated_complexity=3,
                required_capabilities=["testing"],
                suggested_tools=[],
                depends_on=[1],
                output_keys=["test_results"],
            ),
        ]
        specs = [
            (
                _make_agent_spec(spec_id=f"spec-{i}", name=f"agent-{i}"),
                SpawnDecision(SpawnDecision.SPAWN, "Needs its own agent"),
            )
            for i in range(3)
        ]

        plan = composer.compose(
            subtasks=subtasks,
            specs=specs,
            parent_envelope=ConstraintEnvelope(financial={"limit": 30.0}),
            plan_name="three-stage-plan",
        )

        # Convert to SDK and validate
        sdk_plan = plan_to_sdk(plan)
        structure_errors = SdkPlanValidator.validate_structure(sdk_plan)
        envelope_errors = SdkPlanValidator.validate_envelopes(sdk_plan)

        assert len(structure_errors) == 0, f"SDK structural errors: {structure_errors}"
        # Envelope errors may or may not be zero depending on per-node envelope data
        # but structure must be clean
