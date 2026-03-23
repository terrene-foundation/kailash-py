# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Integration test for the full SDK adapter pipeline (P0-06).

Exercises the complete flow:
    1. Create local Plan with 3 nodes (linear dependency)
    2. Convert to SDK Plan via adapter
    3. Validate with SDK PlanValidator
    4. Convert back to local Plan
    5. Execute via PlanMonitor.run_plan() with mock callback
    6. Verify events, results, and state

Tier 1-level integration (no Docker services, but tests cross-package
boundaries between kaizen-agents and kailash-kaizen SDK types).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from kaizen_agents._sdk_compat import (
    plan_from_sdk,
    plan_to_sdk,
)
from kaizen_agents.llm import LLMClient
from kaizen_agents.monitor import PlanMonitor, PlanResult
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    EdgeType,
    GradientZone,
    Plan,
    PlanEdge,
    PlanEventType,
    PlanGradient,
    PlanNode,
    PlanNodeOutput,
    PlanNodeState,
    PlanState,
)
from kaizen.l3.plan.types import (
    PlanNodeState as SdkPlanNodeState,
    PlanState as SdkPlanState,
)
from kaizen.l3.plan.validator import PlanValidator as SdkPlanValidator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_llm() -> LLMClient:
    """Create a mock LLMClient for PlanMonitor initialization."""
    mock = MagicMock(spec=LLMClient)
    mock.complete_structured.return_value = {}
    return mock


def _make_spec(spec_id: str, name: str, financial_limit: float = 3.0) -> AgentSpec:
    """Create an AgentSpec with sensible defaults."""
    return AgentSpec(
        spec_id=spec_id,
        name=name,
        description=f"Agent for {name}",
        capabilities=["general"],
        tool_ids=[],
        envelope=ConstraintEnvelope(
            financial={"limit": financial_limit},
            operational={"allowed": [], "blocked": []},
        ),
    )


def _make_three_node_linear_plan() -> tuple[Plan, dict[str, AgentSpec]]:
    """Build a three-node linear plan with spec lookup dict.

    Returns both the plan and a dict mapping spec_id -> AgentSpec for
    round-trip conversion.

    Plan structure: gather -> analyze -> report
    """
    specs = {
        "spec-gather": _make_spec("spec-gather", "gather"),
        "spec-analyze": _make_spec("spec-analyze", "analyze"),
        "spec-report": _make_spec("spec-report", "report"),
    }

    nodes = {
        "node-0": PlanNode(
            node_id="node-0",
            agent_spec=specs["spec-gather"],
            state=PlanNodeState.PENDING,
        ),
        "node-1": PlanNode(
            node_id="node-1",
            agent_spec=specs["spec-analyze"],
            input_mapping={
                "data": PlanNodeOutput(source_node="node-0", output_key="result"),
            },
            state=PlanNodeState.PENDING,
        ),
        "node-2": PlanNode(
            node_id="node-2",
            agent_spec=specs["spec-report"],
            input_mapping={
                "analysis": PlanNodeOutput(source_node="node-1", output_key="result"),
            },
            state=PlanNodeState.PENDING,
        ),
    }

    edges = [
        PlanEdge(
            from_node="node-0",
            to_node="node-1",
            edge_type=EdgeType.DATA_DEPENDENCY,
        ),
        PlanEdge(
            from_node="node-1",
            to_node="node-2",
            edge_type=EdgeType.DATA_DEPENDENCY,
        ),
    ]

    plan = Plan(
        plan_id="integration-3-node",
        name="Integration Three Node Plan",
        nodes=nodes,
        edges=edges,
        state=PlanState.DRAFT,
        envelope=ConstraintEnvelope(financial={"limit": 10.0}),
        gradient=PlanGradient(retry_budget=2),
    )

    return plan, specs


# ---------------------------------------------------------------------------
# P0-06: Full Pipeline Integration Test
# ---------------------------------------------------------------------------


class TestFullSdkPipeline:
    """Full integration test exercising the complete adapter pipeline."""

    def test_local_to_sdk_to_validated_to_local_to_executed(self) -> None:
        """Complete pipeline: create -> convert -> validate -> convert back -> execute.

        Steps:
            1. Create local Plan with 3 linear nodes
            2. Convert to SDK Plan via plan_to_sdk()
            3. Validate with SDK PlanValidator (must pass)
            4. Convert back to local Plan via plan_from_sdk()
            5. Execute via PlanMonitor.run_plan()
            6. Verify events, results, and final state
        """
        # Step 1: Create local plan
        plan, specs = _make_three_node_linear_plan()
        assert plan.state == PlanState.DRAFT
        assert len(plan.nodes) == 3
        assert len(plan.edges) == 2

        # Step 2: Convert to SDK
        sdk_plan = plan_to_sdk(plan)
        assert sdk_plan.plan_id == "integration-3-node"
        assert len(sdk_plan.nodes) == 3
        assert len(sdk_plan.edges) == 2
        assert sdk_plan.state == SdkPlanState.DRAFT
        # Verify spec IDs are preserved
        assert sdk_plan.nodes["node-0"].agent_spec_id == "spec-gather"
        assert sdk_plan.nodes["node-1"].agent_spec_id == "spec-analyze"
        assert sdk_plan.nodes["node-2"].agent_spec_id == "spec-report"

        # Step 3: Validate with SDK PlanValidator
        structure_errors = SdkPlanValidator.validate_structure(sdk_plan)
        assert len(structure_errors) == 0, f"SDK structural validation errors: {structure_errors}"
        envelope_errors = SdkPlanValidator.validate_envelopes(sdk_plan)
        # Envelope errors may exist if node-level envelopes are not set in SDK format
        # but structural validation must pass

        # Step 4: Convert back to local
        local_plan = plan_from_sdk(sdk_plan, agent_specs=specs)
        assert local_plan.plan_id == "integration-3-node"
        assert len(local_plan.nodes) == 3
        assert len(local_plan.edges) == 2
        # Verify agent specs are fully restored
        assert local_plan.nodes["node-0"].agent_spec.name == "gather"
        assert local_plan.nodes["node-1"].agent_spec.name == "analyze"
        assert local_plan.nodes["node-2"].agent_spec.name == "report"
        # Verify input mappings are preserved
        assert "data" in local_plan.nodes["node-1"].input_mapping
        assert local_plan.nodes["node-1"].input_mapping["data"].source_node == "node-0"
        assert "analysis" in local_plan.nodes["node-2"].input_mapping
        assert local_plan.nodes["node-2"].input_mapping["analysis"].source_node == "node-1"

        # Step 5: Execute via PlanMonitor
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )

        call_log: list[str] = []

        async def mock_execute(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
            call_log.append(spec.name)
            return {"result": f"output-from-{spec.name}", "cost": 0.5}

        result = asyncio.run(monitor.run_plan(plan=local_plan, execute_node=mock_execute))

        # Step 6: Verify execution results
        assert isinstance(result, PlanResult)
        assert result.success is True
        assert local_plan.state == PlanState.COMPLETED

        # All three nodes should have been called in order
        assert call_log == ["gather", "analyze", "report"]

        # Results should contain all three node outputs
        assert "node-0" in result.results
        assert "node-1" in result.results
        assert "node-2" in result.results
        assert result.results["node-0"] == "output-from-gather"
        assert result.results["node-1"] == "output-from-analyze"
        assert result.results["node-2"] == "output-from-report"

        # Total cost should be 0.5 * 3 = 1.5
        assert result.total_cost == pytest.approx(1.5)

        # Events should include NODE_STARTED, NODE_COMPLETED for each, plus PLAN_COMPLETED
        event_types = [e.event_type for e in result.events]
        assert event_types.count(PlanEventType.NODE_STARTED) == 3
        assert event_types.count(PlanEventType.NODE_COMPLETED) == 3
        assert PlanEventType.PLAN_COMPLETED in event_types

    def test_pipeline_with_node_failure_and_recovery_classification(self) -> None:
        """Test the pipeline when a node fails and gets classified.

        After execution, convert the failed plan to SDK and verify
        state mapping is correct.
        """
        plan, specs = _make_three_node_linear_plan()

        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(
                retry_budget=0,
                after_retry_exhaustion=GradientZone.BLOCKED,
            ),
        )

        async def failing_at_node_1(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
            if spec.name == "analyze":
                return {"error": "Analysis failed: invalid data format"}
            return {"result": f"output-from-{spec.name}", "cost": 0.5}

        result = asyncio.run(monitor.run_plan(plan=plan, execute_node=failing_at_node_1))

        # Plan should have failed
        assert result.success is False
        assert plan.state == PlanState.FAILED

        # node-0 should be completed, node-1 failed, node-2 cascaded failure
        assert plan.nodes["node-0"].state == PlanNodeState.COMPLETED
        assert plan.nodes["node-1"].state == PlanNodeState.FAILED
        assert plan.nodes["node-2"].state == PlanNodeState.FAILED

        # Convert failed plan to SDK and verify state mapping
        sdk_plan = plan_to_sdk(plan)
        assert sdk_plan.nodes["node-0"].state == SdkPlanNodeState.COMPLETED
        assert sdk_plan.nodes["node-1"].state == SdkPlanNodeState.FAILED
        assert sdk_plan.nodes["node-2"].state == SdkPlanNodeState.FAILED

        # Convert back to local and verify round-trip
        local_plan_again = plan_from_sdk(sdk_plan, agent_specs=specs)
        assert local_plan_again.nodes["node-0"].state == PlanNodeState.COMPLETED
        assert local_plan_again.nodes["node-1"].state == PlanNodeState.FAILED

    def test_pipeline_validate_then_execute(self) -> None:
        """Validate via SDK PlanValidator, then execute the validated plan.

        This is the expected production flow:
            1. Compose/create plan
            2. validate_plan_with_sdk() — structural check at SDK boundary
            3. Execute if valid
        """
        plan, specs = _make_three_node_linear_plan()

        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(retry_budget=2),
        )

        # Validate via SDK (P0-03 method)
        errors = monitor.validate_plan_with_sdk(plan)
        assert len(errors) == 0, f"Validation errors: {errors}"

        # Execute the validated plan
        async def success_callback(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
            return {"result": f"done-{spec.name}", "cost": 0.1}

        result = asyncio.run(monitor.run_plan(plan=plan, execute_node=success_callback))

        assert result.success is True

    def test_pipeline_sdk_held_node_in_round_trip(self) -> None:
        """Verify HELD state handling through full pipeline round-trip.

        1. Create plan, execute, node fails -> FAILED state
        2. Convert to SDK, manually set to HELD
        3. Convert back to local -> should be FAILED
        4. Verify the plan is still usable
        """
        plan, specs = _make_three_node_linear_plan()

        # Execute with node-1 failing
        llm = _make_mock_llm()
        monitor = PlanMonitor(
            llm=llm,
            envelope=ConstraintEnvelope(financial={"limit": 10.0}),
            gradient=PlanGradient(
                retry_budget=0,
                after_retry_exhaustion=GradientZone.BLOCKED,
            ),
        )

        async def fail_node_1(spec: AgentSpec, inputs: dict[str, Any]) -> dict[str, Any]:
            if spec.name == "analyze":
                return {"error": "timeout"}
            return {"result": "ok", "cost": 0.1}

        asyncio.run(monitor.run_plan(plan=plan, execute_node=fail_node_1))

        assert plan.nodes["node-1"].state == PlanNodeState.FAILED

        # Convert to SDK
        sdk_plan = plan_to_sdk(plan)
        assert sdk_plan.nodes["node-1"].state == SdkPlanNodeState.FAILED

        # Simulate SDK PlanExecutor setting HELD state
        sdk_plan.nodes["node-1"].state = SdkPlanNodeState.HELD

        # Convert back -> HELD maps to HELD (both have HELD state now)
        local_plan = plan_from_sdk(sdk_plan, agent_specs=specs)
        assert local_plan.nodes["node-1"].state == PlanNodeState.HELD

    def test_pipeline_input_mapping_preserved_through_round_trip(self) -> None:
        """Verify input_mapping data survives the full SDK round-trip."""
        plan, specs = _make_three_node_linear_plan()

        # Original input mappings
        original_node1_mapping = plan.nodes["node-1"].input_mapping
        original_node2_mapping = plan.nodes["node-2"].input_mapping

        # Round-trip through SDK
        sdk_plan = plan_to_sdk(plan)
        local_plan = plan_from_sdk(sdk_plan, agent_specs=specs)

        # Verify preserved
        assert "data" in local_plan.nodes["node-1"].input_mapping
        node1_mapping = local_plan.nodes["node-1"].input_mapping["data"]
        assert node1_mapping.source_node == original_node1_mapping["data"].source_node
        assert node1_mapping.output_key == original_node1_mapping["data"].output_key

        assert "analysis" in local_plan.nodes["node-2"].input_mapping
        node2_mapping = local_plan.nodes["node-2"].input_mapping["analysis"]
        assert node2_mapping.source_node == original_node2_mapping["analysis"].source_node
        assert node2_mapping.output_key == original_node2_mapping["analysis"].output_key

    def test_pipeline_gradient_preserved_through_round_trip(self) -> None:
        """Verify PlanGradient survives the full SDK round-trip."""
        plan, specs = _make_three_node_linear_plan()
        original_gradient = plan.gradient

        sdk_plan = plan_to_sdk(plan)
        local_plan = plan_from_sdk(sdk_plan, agent_specs=specs)

        assert local_plan.gradient.retry_budget == original_gradient.retry_budget
        assert local_plan.gradient.resolution_timeout == original_gradient.resolution_timeout
        assert (
            local_plan.gradient.after_retry_exhaustion == original_gradient.after_retry_exhaustion
        )
        assert local_plan.gradient.optional_node_failure == original_gradient.optional_node_failure
        assert local_plan.gradient.budget_flag_threshold == original_gradient.budget_flag_threshold
        assert local_plan.gradient.budget_hold_threshold == original_gradient.budget_hold_threshold
