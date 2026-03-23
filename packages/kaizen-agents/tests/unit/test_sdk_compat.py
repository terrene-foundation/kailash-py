# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for kaizen_agents._sdk_compat — bidirectional SDK type converters.

Tier 1: Unit tests, no external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kaizen_agents._sdk_compat import (
    edge_type_from_sdk,
    edge_type_to_sdk,
    envelope_from_dict,
    envelope_to_dict,
    gradient_zone_from_sdk,
    gradient_zone_to_sdk,
    plan_edge_from_sdk,
    plan_edge_to_sdk,
    plan_from_sdk,
    plan_gradient_from_dict,
    plan_gradient_to_dict,
    plan_node_from_sdk,
    plan_node_state_from_sdk,
    plan_node_state_to_sdk,
    plan_node_to_sdk,
    plan_state_from_sdk,
    plan_state_to_sdk,
    plan_to_sdk,
)
from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    DimensionGradient as LocalDimensionGradient,
    EdgeType as LocalEdgeType,
    GradientZone as LocalGradientZone,
    MemoryConfig,
    Plan as LocalPlan,
    PlanEdge as LocalPlanEdge,
    PlanGradient as LocalPlanGradient,
    PlanNode as LocalPlanNode,
    PlanNodeOutput as LocalPlanNodeOutput,
    PlanNodeState as LocalPlanNodeState,
    PlanState as LocalPlanState,
)
from kaizen.l3.envelope.types import GradientZone as SdkGradientZone
from kaizen.l3.plan.types import (
    EdgeType as SdkEdgeType,
    Plan as SdkPlan,
    PlanEdge as SdkPlanEdge,
    PlanNode as SdkPlanNode,
    PlanNodeOutput as SdkPlanNodeOutput,
    PlanNodeState as SdkPlanNodeState,
    PlanState as SdkPlanState,
)


# ---------------------------------------------------------------------------
# GradientZone converters
# ---------------------------------------------------------------------------


class TestGradientZoneConverters:
    """Bidirectional GradientZone conversion tests."""

    @pytest.mark.parametrize(
        "local_zone, expected_sdk_name",
        [
            (LocalGradientZone.AUTO_APPROVED, "AUTO_APPROVED"),
            (LocalGradientZone.FLAGGED, "FLAGGED"),
            (LocalGradientZone.HELD, "HELD"),
            (LocalGradientZone.BLOCKED, "BLOCKED"),
        ],
    )
    def test_to_sdk_all_zones(self, local_zone: LocalGradientZone, expected_sdk_name: str) -> None:
        sdk = gradient_zone_to_sdk(local_zone)
        assert isinstance(sdk, SdkGradientZone)
        assert sdk.name == expected_sdk_name

    @pytest.mark.parametrize(
        "sdk_zone, expected_local_name",
        [
            (SdkGradientZone.AUTO_APPROVED, "AUTO_APPROVED"),
            (SdkGradientZone.FLAGGED, "FLAGGED"),
            (SdkGradientZone.HELD, "HELD"),
            (SdkGradientZone.BLOCKED, "BLOCKED"),
        ],
    )
    def test_from_sdk_all_zones(self, sdk_zone: SdkGradientZone, expected_local_name: str) -> None:
        local = gradient_zone_from_sdk(sdk_zone)
        assert isinstance(local, LocalGradientZone)
        assert local.name == expected_local_name

    def test_round_trip_all_zones(self) -> None:
        for zone in LocalGradientZone:
            result = gradient_zone_from_sdk(gradient_zone_to_sdk(zone))
            assert result == zone

    def test_casing_difference_verified(self) -> None:
        """Local uses lowercase values, SDK uses UPPERCASE values."""
        assert LocalGradientZone.AUTO_APPROVED.value == "auto_approved"
        assert SdkGradientZone.AUTO_APPROVED.value == "AUTO_APPROVED"
        # Conversion bridges this gap
        sdk = gradient_zone_to_sdk(LocalGradientZone.AUTO_APPROVED)
        assert sdk.value == "AUTO_APPROVED"


# ---------------------------------------------------------------------------
# EdgeType converters
# ---------------------------------------------------------------------------


class TestEdgeTypeConverters:
    """Bidirectional EdgeType conversion tests."""

    @pytest.mark.parametrize(
        "local_edge, expected_sdk_name",
        [
            (LocalEdgeType.DATA_DEPENDENCY, "DATA_DEPENDENCY"),
            (LocalEdgeType.COMPLETION_DEPENDENCY, "COMPLETION_DEPENDENCY"),
            (LocalEdgeType.CO_START, "CO_START"),
        ],
    )
    def test_to_sdk_all_types(self, local_edge: LocalEdgeType, expected_sdk_name: str) -> None:
        sdk = edge_type_to_sdk(local_edge)
        assert isinstance(sdk, SdkEdgeType)
        assert sdk.name == expected_sdk_name

    def test_round_trip_all_types(self) -> None:
        for et in LocalEdgeType:
            result = edge_type_from_sdk(edge_type_to_sdk(et))
            assert result == et

    def test_casing_difference_verified(self) -> None:
        """Local uses lowercase values, SDK uses UPPERCASE values."""
        assert LocalEdgeType.DATA_DEPENDENCY.value == "data_dependency"
        assert SdkEdgeType.DATA_DEPENDENCY.value == "DATA_DEPENDENCY"


# ---------------------------------------------------------------------------
# PlanNodeState converters
# ---------------------------------------------------------------------------


class TestPlanNodeStateConverters:
    """Bidirectional PlanNodeState conversion — including HELD edge case."""

    @pytest.mark.parametrize(
        "local_state",
        [
            LocalPlanNodeState.PENDING,
            LocalPlanNodeState.READY,
            LocalPlanNodeState.RUNNING,
            LocalPlanNodeState.COMPLETED,
            LocalPlanNodeState.FAILED,
            LocalPlanNodeState.SKIPPED,
        ],
    )
    def test_round_trip_all_shared_states(self, local_state: LocalPlanNodeState) -> None:
        sdk = plan_node_state_to_sdk(local_state)
        assert isinstance(sdk, SdkPlanNodeState)
        result = plan_node_state_from_sdk(sdk)
        assert result == local_state

    def test_sdk_held_maps_to_held(self) -> None:
        """Both SDK and local now have HELD state. Direct mapping."""
        result = plan_node_state_from_sdk(SdkPlanNodeState.HELD)
        assert result == LocalPlanNodeState.HELD

    def test_casing_difference_verified(self) -> None:
        """Local uses lowercase values, SDK uses UPPERCASE values."""
        assert LocalPlanNodeState.PENDING.value == "pending"
        assert SdkPlanNodeState.PENDING.value == "PENDING"


# ---------------------------------------------------------------------------
# PlanState converters
# ---------------------------------------------------------------------------


class TestPlanStateConverters:
    """Bidirectional PlanState conversion tests."""

    @pytest.mark.parametrize(
        "local_state",
        list(LocalPlanState),
    )
    def test_round_trip_all_states(self, local_state: LocalPlanState) -> None:
        sdk = plan_state_to_sdk(local_state)
        assert isinstance(sdk, SdkPlanState)
        result = plan_state_from_sdk(sdk)
        assert result == local_state

    def test_casing_difference_verified(self) -> None:
        """Local uses lowercase values, SDK uses UPPERCASE values."""
        assert LocalPlanState.DRAFT.value == "draft"
        assert SdkPlanState.DRAFT.value == "DRAFT"


# ---------------------------------------------------------------------------
# PlanEdge converters
# ---------------------------------------------------------------------------


class TestPlanEdgeConverters:
    """Bidirectional PlanEdge conversion tests."""

    def test_to_sdk(self) -> None:
        local = LocalPlanEdge(
            from_node="a",
            to_node="b",
            edge_type=LocalEdgeType.DATA_DEPENDENCY,
        )
        sdk = plan_edge_to_sdk(local)
        assert isinstance(sdk, SdkPlanEdge)
        assert sdk.from_node == "a"
        assert sdk.to_node == "b"
        assert sdk.edge_type == SdkEdgeType.DATA_DEPENDENCY

    def test_from_sdk(self) -> None:
        sdk = SdkPlanEdge(
            from_node="x",
            to_node="y",
            edge_type=SdkEdgeType.CO_START,
        )
        local = plan_edge_from_sdk(sdk)
        assert isinstance(local, LocalPlanEdge)
        assert local.from_node == "x"
        assert local.to_node == "y"
        assert local.edge_type == LocalEdgeType.CO_START

    def test_round_trip(self) -> None:
        local = LocalPlanEdge(
            from_node="n1",
            to_node="n2",
            edge_type=LocalEdgeType.COMPLETION_DEPENDENCY,
        )
        result = plan_edge_from_sdk(plan_edge_to_sdk(local))
        assert result.from_node == local.from_node
        assert result.to_node == local.to_node
        assert result.edge_type == local.edge_type


# ---------------------------------------------------------------------------
# PlanNode converters
# ---------------------------------------------------------------------------


class TestPlanNodeConverters:
    """Bidirectional PlanNode conversion — agent_spec vs agent_spec_id."""

    def _make_local_node(self) -> LocalPlanNode:
        return LocalPlanNode(
            node_id="node-1",
            agent_spec=AgentSpec(
                spec_id="spec-abc",
                name="Test Agent",
                description="A test agent",
                capabilities=["search"],
                tool_ids=["tool-1"],
            ),
            input_mapping={
                "data_in": LocalPlanNodeOutput(
                    source_node="node-0",
                    output_key="result",
                ),
            },
            state=LocalPlanNodeState.READY,
            instance_id="inst-001",
            optional=True,
            retry_count=1,
            output={"key": "val"},
            error=None,
        )

    def test_to_sdk_uses_spec_id(self) -> None:
        """Local PlanNode.agent_spec should be converted to SDK agent_spec_id."""
        local = self._make_local_node()
        sdk = plan_node_to_sdk(local)
        assert isinstance(sdk, SdkPlanNode)
        assert sdk.agent_spec_id == "spec-abc"
        assert sdk.node_id == "node-1"
        assert sdk.state == SdkPlanNodeState.READY
        assert sdk.instance_id == "inst-001"
        assert sdk.optional is True
        assert sdk.retry_count == 1
        assert sdk.output == {"key": "val"}
        assert sdk.error is None

    def test_to_sdk_input_mapping(self) -> None:
        """Input mapping PlanNodeOutput should convert correctly."""
        local = self._make_local_node()
        sdk = plan_node_to_sdk(local)
        assert "data_in" in sdk.input_mapping
        pno = sdk.input_mapping["data_in"]
        assert isinstance(pno, SdkPlanNodeOutput)
        assert pno.source_node == "node-0"
        assert pno.output_key == "result"

    def test_from_sdk_requires_agent_specs(self) -> None:
        """Converting SDK PlanNode back to local requires an agent_specs lookup."""
        spec = AgentSpec(
            spec_id="spec-abc",
            name="Test Agent",
            description="A test agent",
        )
        sdk = SdkPlanNode(
            node_id="node-1",
            agent_spec_id="spec-abc",
            input_mapping={
                "data_in": SdkPlanNodeOutput(
                    source_node="node-0",
                    output_key="result",
                ),
            },
            state=SdkPlanNodeState.READY,
            instance_id="inst-001",
            optional=True,
            retry_count=1,
            output={"key": "val"},
            error=None,
        )
        local = plan_node_from_sdk(sdk, agent_specs={"spec-abc": spec})
        assert isinstance(local, LocalPlanNode)
        assert local.agent_spec.spec_id == "spec-abc"
        assert local.agent_spec.name == "Test Agent"
        assert local.node_id == "node-1"
        assert local.state == LocalPlanNodeState.READY

    def test_from_sdk_missing_spec_raises(self) -> None:
        """If the agent_specs dict does not contain the spec_id, raise KeyError."""
        sdk = SdkPlanNode(
            node_id="node-1",
            agent_spec_id="nonexistent",
            input_mapping={},
            state=SdkPlanNodeState.PENDING,
            instance_id=None,
            optional=False,
            retry_count=0,
            output=None,
            error=None,
        )
        with pytest.raises(KeyError, match="nonexistent"):
            plan_node_from_sdk(sdk, agent_specs={})

    def test_round_trip(self) -> None:
        local = self._make_local_node()
        sdk = plan_node_to_sdk(local)
        specs = {"spec-abc": local.agent_spec}
        result = plan_node_from_sdk(sdk, agent_specs=specs)
        assert result.node_id == local.node_id
        assert result.agent_spec.spec_id == local.agent_spec.spec_id
        assert result.state == local.state
        assert result.optional == local.optional
        assert result.retry_count == local.retry_count
        assert result.output == local.output


# ---------------------------------------------------------------------------
# PlanGradient converters
# ---------------------------------------------------------------------------


class TestPlanGradientConverters:
    """PlanGradient to/from dict — timedelta <-> float conversion."""

    def _make_local_gradient(self) -> LocalPlanGradient:
        return LocalPlanGradient(
            retry_budget=3,
            after_retry_exhaustion=LocalGradientZone.BLOCKED,
            resolution_timeout=timedelta(seconds=600),
            optional_node_failure=LocalGradientZone.FLAGGED,
            budget_flag_threshold=0.75,
            budget_hold_threshold=0.90,
            dimension_thresholds={
                "financial": LocalDimensionGradient(
                    flag_threshold=0.70,
                    hold_threshold=0.85,
                ),
            },
        )

    def test_to_dict_timedelta_becomes_float(self) -> None:
        gradient = self._make_local_gradient()
        d = plan_gradient_to_dict(gradient)
        assert d["resolution_timeout"] == 600.0
        assert isinstance(d["resolution_timeout"], float)

    def test_to_dict_gradient_zones_become_strings(self) -> None:
        gradient = self._make_local_gradient()
        d = plan_gradient_to_dict(gradient)
        assert d["after_retry_exhaustion"] == "BLOCKED"
        assert d["optional_node_failure"] == "FLAGGED"

    def test_to_dict_dimension_thresholds(self) -> None:
        gradient = self._make_local_gradient()
        d = plan_gradient_to_dict(gradient)
        assert "financial" in d["dimension_thresholds"]
        fin = d["dimension_thresholds"]["financial"]
        assert fin["flag_threshold"] == 0.70
        assert fin["hold_threshold"] == 0.85

    def test_from_dict_float_becomes_timedelta(self) -> None:
        d = {
            "retry_budget": 3,
            "after_retry_exhaustion": "BLOCKED",
            "resolution_timeout": 600.0,
            "optional_node_failure": "FLAGGED",
            "budget_flag_threshold": 0.75,
            "budget_hold_threshold": 0.90,
            "dimension_thresholds": {},
        }
        gradient = plan_gradient_from_dict(d)
        assert isinstance(gradient, LocalPlanGradient)
        assert gradient.resolution_timeout == timedelta(seconds=600)
        assert gradient.after_retry_exhaustion == LocalGradientZone.BLOCKED

    def test_round_trip(self) -> None:
        original = self._make_local_gradient()
        result = plan_gradient_from_dict(plan_gradient_to_dict(original))
        assert result.retry_budget == original.retry_budget
        assert result.resolution_timeout == original.resolution_timeout
        assert result.after_retry_exhaustion == original.after_retry_exhaustion
        assert result.optional_node_failure == original.optional_node_failure
        assert result.budget_flag_threshold == original.budget_flag_threshold
        assert result.budget_hold_threshold == original.budget_hold_threshold
        assert "financial" in result.dimension_thresholds
        fin = result.dimension_thresholds["financial"]
        assert fin.flag_threshold == 0.70
        assert fin.hold_threshold == 0.85

    def test_from_dict_with_dimension_thresholds(self) -> None:
        d = {
            "retry_budget": 2,
            "after_retry_exhaustion": "HELD",
            "resolution_timeout": 300.0,
            "optional_node_failure": "FLAGGED",
            "budget_flag_threshold": 0.80,
            "budget_hold_threshold": 0.95,
            "dimension_thresholds": {
                "temporal": {
                    "flag_threshold": 0.60,
                    "hold_threshold": 0.80,
                },
            },
        }
        gradient = plan_gradient_from_dict(d)
        assert "temporal" in gradient.dimension_thresholds
        assert gradient.dimension_thresholds["temporal"].flag_threshold == 0.60


# ---------------------------------------------------------------------------
# ConstraintEnvelope converters
# ---------------------------------------------------------------------------


class TestEnvelopeConverters:
    """ConstraintEnvelope to/from dict conversion."""

    def _make_envelope(self) -> ConstraintEnvelope:
        return ConstraintEnvelope(
            financial={"limit": 50.0},
            operational={"allowed": ["search", "summarize"], "blocked": ["delete"]},
            temporal={"window_start": "09:00", "window_end": "17:00"},
            data_access={"ceiling": "confidential", "scopes": ["analytics"]},
            communication={"recipients": ["supervisor"], "channels": ["internal"]},
        )

    def test_to_dict_structure(self) -> None:
        env = self._make_envelope()
        d = envelope_to_dict(env)
        assert d["financial"] == {"limit": 50.0}
        assert "search" in d["operational"]["allowed"]
        assert d["data_access"]["ceiling"] == "confidential"

    def test_round_trip(self) -> None:
        original = self._make_envelope()
        result = envelope_from_dict(envelope_to_dict(original))
        assert result.financial == original.financial
        assert result.operational == original.operational
        assert result.temporal == original.temporal
        assert result.data_access == original.data_access
        assert result.communication == original.communication

    def test_from_dict_empty(self) -> None:
        """Empty dict produces default envelope."""
        result = envelope_from_dict({})
        assert isinstance(result, ConstraintEnvelope)


# ---------------------------------------------------------------------------
# Plan converters (full round-trip)
# ---------------------------------------------------------------------------


class TestPlanConverters:
    """Full Plan to/from SDK conversion."""

    def _make_local_plan(self) -> LocalPlan:
        spec_a = AgentSpec(
            spec_id="spec-a",
            name="Agent A",
            description="First agent",
        )
        spec_b = AgentSpec(
            spec_id="spec-b",
            name="Agent B",
            description="Second agent",
        )
        return LocalPlan(
            plan_id="plan-001",
            name="Test Plan",
            envelope=ConstraintEnvelope(
                financial={"limit": 100.0},
            ),
            gradient=LocalPlanGradient(
                retry_budget=2,
                resolution_timeout=timedelta(seconds=300),
            ),
            nodes={
                "node-a": LocalPlanNode(
                    node_id="node-a",
                    agent_spec=spec_a,
                    state=LocalPlanNodeState.COMPLETED,
                    output="result-a",
                ),
                "node-b": LocalPlanNode(
                    node_id="node-b",
                    agent_spec=spec_b,
                    input_mapping={
                        "prev": LocalPlanNodeOutput(
                            source_node="node-a",
                            output_key="output",
                        ),
                    },
                    state=LocalPlanNodeState.PENDING,
                ),
            },
            edges=[
                LocalPlanEdge(
                    from_node="node-a",
                    to_node="node-b",
                    edge_type=LocalEdgeType.DATA_DEPENDENCY,
                ),
            ],
            state=LocalPlanState.EXECUTING,
            created_at=datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc),
            modified_at=datetime(2026, 3, 23, 10, 5, 0, tzinfo=timezone.utc),
        )

    def test_to_sdk_plan_structure(self) -> None:
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        assert isinstance(sdk, SdkPlan)
        assert sdk.plan_id == "plan-001"
        assert sdk.name == "Test Plan"
        assert sdk.state == SdkPlanState.EXECUTING
        assert len(sdk.nodes) == 2
        assert len(sdk.edges) == 1

    def test_to_sdk_plan_envelope_is_dict(self) -> None:
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        assert isinstance(sdk.envelope, dict)
        assert sdk.envelope["financial"] == {"limit": 100.0}

    def test_to_sdk_plan_gradient_is_dict(self) -> None:
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        assert isinstance(sdk.gradient, dict)
        assert sdk.gradient["retry_budget"] == 2
        assert sdk.gradient["resolution_timeout"] == 300.0

    def test_to_sdk_plan_nodes_use_spec_id(self) -> None:
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        assert sdk.nodes["node-a"].agent_spec_id == "spec-a"
        assert sdk.nodes["node-b"].agent_spec_id == "spec-b"

    def test_to_sdk_plan_timestamps_preserved(self) -> None:
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        assert sdk.created_at == datetime(2026, 3, 23, 10, 0, 0, tzinfo=timezone.utc)
        assert sdk.modified_at == datetime(2026, 3, 23, 10, 5, 0, tzinfo=timezone.utc)

    def test_from_sdk_plan_round_trip(self) -> None:
        local = self._make_local_plan()
        specs = {
            "spec-a": local.nodes["node-a"].agent_spec,
            "spec-b": local.nodes["node-b"].agent_spec,
        }
        sdk = plan_to_sdk(local)
        result = plan_from_sdk(sdk, agent_specs=specs)

        assert isinstance(result, LocalPlan)
        assert result.plan_id == local.plan_id
        assert result.name == local.name
        assert result.state == local.state
        assert len(result.nodes) == 2
        assert len(result.edges) == 1
        assert result.nodes["node-a"].agent_spec.spec_id == "spec-a"
        assert result.nodes["node-b"].agent_spec.spec_id == "spec-b"

    def test_from_sdk_plan_gradient_round_trip(self) -> None:
        local = self._make_local_plan()
        specs = {
            "spec-a": local.nodes["node-a"].agent_spec,
            "spec-b": local.nodes["node-b"].agent_spec,
        }
        sdk = plan_to_sdk(local)
        result = plan_from_sdk(sdk, agent_specs=specs)
        assert result.gradient.retry_budget == 2
        assert result.gradient.resolution_timeout == timedelta(seconds=300)

    def test_from_sdk_plan_envelope_round_trip(self) -> None:
        local = self._make_local_plan()
        specs = {
            "spec-a": local.nodes["node-a"].agent_spec,
            "spec-b": local.nodes["node-b"].agent_spec,
        }
        sdk = plan_to_sdk(local)
        result = plan_from_sdk(sdk, agent_specs=specs)
        assert result.envelope.financial == {"limit": 100.0}

    def test_from_sdk_plan_missing_spec_raises(self) -> None:
        """Converting a plan with unknown agent_spec_id should raise."""
        local = self._make_local_plan()
        sdk = plan_to_sdk(local)
        # Only provide spec-a, not spec-b
        with pytest.raises(KeyError, match="spec-b"):
            plan_from_sdk(
                sdk,
                agent_specs={
                    "spec-a": local.nodes["node-a"].agent_spec,
                },
            )
