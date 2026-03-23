# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Bidirectional adapters between kaizen-agents local types and kailash-kaizen SDK types.

Local types (kaizen_agents.types) use lowercase enum values and richer Python
types (timedelta, AgentSpec objects, ConstraintEnvelope dataclass).  SDK types
(kaizen.l3.*) use UPPERCASE enum values and serialised representations (float
seconds, agent_spec_id strings, plain dicts for envelope/gradient).

All internal orchestration code continues using local types.  This module
converts at the SDK integration boundary so that SDK APIs receive/return their
own types.

Conversion strategy:
    - Enums: map by name (both sides share the same member names).
    - PlanNode: local `agent_spec: AgentSpec` -> SDK `agent_spec_id: str`.
      Reverse requires a lookup dict `agent_specs: dict[str, AgentSpec]`.
    - Plan.envelope: local `ConstraintEnvelope` -> SDK `dict[str, Any]`.
    - Plan.gradient: local `PlanGradient` -> SDK `dict[str, Any]`.
    - PlanGradient.resolution_timeout: local `timedelta` -> SDK `float` (seconds).
    - PlanNodeState.HELD: Both SDK and local now have HELD with 1:1 mapping.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

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

from kaizen_agents.types import (
    AgentSpec,
    ConstraintEnvelope,
    DimensionGradient as LocalDimensionGradient,
    EdgeType as LocalEdgeType,
    GradientZone as LocalGradientZone,
    Plan as LocalPlan,
    PlanEdge as LocalPlanEdge,
    PlanGradient as LocalPlanGradient,
    PlanNode as LocalPlanNode,
    PlanNodeOutput as LocalPlanNodeOutput,
    PlanNodeState as LocalPlanNodeState,
    PlanState as LocalPlanState,
)

__all__ = [
    "edge_type_from_sdk",
    "edge_type_to_sdk",
    "envelope_from_dict",
    "envelope_to_dict",
    "gradient_zone_from_sdk",
    "gradient_zone_to_sdk",
    "plan_edge_from_sdk",
    "plan_edge_to_sdk",
    "plan_from_sdk",
    "plan_gradient_from_dict",
    "plan_gradient_to_dict",
    "plan_node_from_sdk",
    "plan_node_state_from_sdk",
    "plan_node_state_to_sdk",
    "plan_node_to_sdk",
    "plan_state_from_sdk",
    "plan_state_to_sdk",
    "plan_to_sdk",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enum name mapping tables
# ---------------------------------------------------------------------------
# Both local and SDK enums share the same member *names* (e.g. AUTO_APPROVED,
# DATA_DEPENDENCY) but differ in *values* (lowercase vs UPPERCASE).  We map
# by name, which avoids value-based coupling entirely.

_GRADIENT_ZONE_TO_SDK: dict[LocalGradientZone, SdkGradientZone] = {
    local: SdkGradientZone[local.name] for local in LocalGradientZone
}
_GRADIENT_ZONE_FROM_SDK: dict[SdkGradientZone, LocalGradientZone] = {
    sdk: LocalGradientZone[sdk.name] for sdk in SdkGradientZone
}

_EDGE_TYPE_TO_SDK: dict[LocalEdgeType, SdkEdgeType] = {
    local: SdkEdgeType[local.name] for local in LocalEdgeType
}
_EDGE_TYPE_FROM_SDK: dict[SdkEdgeType, LocalEdgeType] = {
    sdk: LocalEdgeType[sdk.name] for sdk in SdkEdgeType
}

# PlanNodeState: both local and SDK now have 7 members including HELD.
_PLAN_NODE_STATE_TO_SDK: dict[LocalPlanNodeState, SdkPlanNodeState] = {
    local: SdkPlanNodeState[local.name] for local in LocalPlanNodeState
}
_PLAN_NODE_STATE_FROM_SDK: dict[SdkPlanNodeState, LocalPlanNodeState] = {
    sdk: LocalPlanNodeState[sdk.name] for sdk in SdkPlanNodeState
}

_PLAN_STATE_TO_SDK: dict[LocalPlanState, SdkPlanState] = {
    local: SdkPlanState[local.name] for local in LocalPlanState
}
_PLAN_STATE_FROM_SDK: dict[SdkPlanState, LocalPlanState] = {
    sdk: LocalPlanState[sdk.name] for sdk in SdkPlanState
}

# GradientZone string names used in serialized gradient dicts.
_GRADIENT_ZONE_NAME_TO_LOCAL: dict[str, LocalGradientZone] = {z.name: z for z in LocalGradientZone}


# ---------------------------------------------------------------------------
# GradientZone converters
# ---------------------------------------------------------------------------


def gradient_zone_to_sdk(local: LocalGradientZone) -> SdkGradientZone:
    """Convert a local GradientZone to its SDK equivalent."""
    return _GRADIENT_ZONE_TO_SDK[local]


def gradient_zone_from_sdk(sdk: SdkGradientZone) -> LocalGradientZone:
    """Convert an SDK GradientZone to its local equivalent."""
    return _GRADIENT_ZONE_FROM_SDK[sdk]


# ---------------------------------------------------------------------------
# EdgeType converters
# ---------------------------------------------------------------------------


def edge_type_to_sdk(local: LocalEdgeType) -> SdkEdgeType:
    """Convert a local EdgeType to its SDK equivalent."""
    return _EDGE_TYPE_TO_SDK[local]


def edge_type_from_sdk(sdk: SdkEdgeType) -> LocalEdgeType:
    """Convert an SDK EdgeType to its local equivalent."""
    return _EDGE_TYPE_FROM_SDK[sdk]


# ---------------------------------------------------------------------------
# PlanNodeState converters
# ---------------------------------------------------------------------------


def plan_node_state_to_sdk(local: LocalPlanNodeState) -> SdkPlanNodeState:
    """Convert a local PlanNodeState to its SDK equivalent."""
    return _PLAN_NODE_STATE_TO_SDK[local]


def plan_node_state_from_sdk(sdk: SdkPlanNodeState) -> LocalPlanNodeState:
    """Convert an SDK PlanNodeState to its local equivalent.

    SDK HELD (which local does not have) maps to local FAILED, since a held
    node that cannot be resolved is functionally a failure in the local model.
    """
    return _PLAN_NODE_STATE_FROM_SDK[sdk]


# ---------------------------------------------------------------------------
# PlanState converters
# ---------------------------------------------------------------------------


def plan_state_to_sdk(local: LocalPlanState) -> SdkPlanState:
    """Convert a local PlanState to its SDK equivalent."""
    return _PLAN_STATE_TO_SDK[local]


def plan_state_from_sdk(sdk: SdkPlanState) -> LocalPlanState:
    """Convert an SDK PlanState to its local equivalent."""
    return _PLAN_STATE_FROM_SDK[sdk]


# ---------------------------------------------------------------------------
# PlanEdge converters
# ---------------------------------------------------------------------------


def plan_edge_to_sdk(local: LocalPlanEdge) -> SdkPlanEdge:
    """Convert a local PlanEdge to its SDK equivalent."""
    return SdkPlanEdge(
        from_node=local.from_node,
        to_node=local.to_node,
        edge_type=edge_type_to_sdk(local.edge_type),
    )


def plan_edge_from_sdk(sdk: SdkPlanEdge) -> LocalPlanEdge:
    """Convert an SDK PlanEdge to its local equivalent."""
    return LocalPlanEdge(
        from_node=sdk.from_node,
        to_node=sdk.to_node,
        edge_type=edge_type_from_sdk(sdk.edge_type),
    )


# ---------------------------------------------------------------------------
# PlanNode converters
# ---------------------------------------------------------------------------


def plan_node_to_sdk(local: LocalPlanNode) -> SdkPlanNode:
    """Convert a local PlanNode to its SDK equivalent.

    The local ``agent_spec: AgentSpec`` is flattened to ``agent_spec_id: str``.
    """
    return SdkPlanNode(
        node_id=local.node_id,
        agent_spec_id=local.agent_spec.spec_id,
        input_mapping={
            key: SdkPlanNodeOutput(
                source_node=pno.source_node,
                output_key=pno.output_key,
            )
            for key, pno in local.input_mapping.items()
        },
        state=plan_node_state_to_sdk(local.state),
        instance_id=local.instance_id,
        optional=local.optional,
        retry_count=local.retry_count,
        output=local.output,
        error=local.error,
    )


def plan_node_from_sdk(
    sdk: SdkPlanNode,
    *,
    agent_specs: dict[str, AgentSpec],
) -> LocalPlanNode:
    """Convert an SDK PlanNode to its local equivalent.

    Requires ``agent_specs`` to resolve ``agent_spec_id`` back to a full
    ``AgentSpec`` object.  Raises ``KeyError`` if the spec_id is not found.

    Args:
        sdk: The SDK PlanNode to convert.
        agent_specs: Mapping of spec_id -> AgentSpec for resolution.

    Raises:
        KeyError: If ``sdk.agent_spec_id`` is not in ``agent_specs``.
    """
    if sdk.agent_spec_id not in agent_specs:
        raise KeyError(
            f"Agent spec '{sdk.agent_spec_id}' not found in agent_specs lookup. "
            f"Available specs: {sorted(agent_specs.keys())}"
        )
    return LocalPlanNode(
        node_id=sdk.node_id,
        agent_spec=agent_specs[sdk.agent_spec_id],
        input_mapping={
            key: LocalPlanNodeOutput(
                source_node=pno.source_node,
                output_key=pno.output_key,
            )
            for key, pno in sdk.input_mapping.items()
        },
        state=plan_node_state_from_sdk(sdk.state),
        instance_id=sdk.instance_id,
        optional=sdk.optional,
        retry_count=sdk.retry_count,
        output=sdk.output,
        error=sdk.error,
    )


# ---------------------------------------------------------------------------
# PlanGradient converters (local dataclass <-> dict)
# ---------------------------------------------------------------------------


def plan_gradient_to_dict(local: LocalPlanGradient) -> dict[str, Any]:
    """Serialize a local PlanGradient to a plain dict for the SDK Plan.gradient field.

    Key conversions:
        - resolution_timeout: timedelta -> float (seconds)
        - GradientZone enums -> UPPERCASE string names
        - DimensionGradient -> nested dict
    """
    return {
        "retry_budget": local.retry_budget,
        "after_retry_exhaustion": local.after_retry_exhaustion.name,
        "resolution_timeout": local.resolution_timeout.total_seconds(),
        "optional_node_failure": local.optional_node_failure.name,
        "budget_flag_threshold": local.budget_flag_threshold,
        "budget_hold_threshold": local.budget_hold_threshold,
        "dimension_thresholds": {
            dim: {
                "flag_threshold": dg.flag_threshold,
                "hold_threshold": dg.hold_threshold,
            }
            for dim, dg in local.dimension_thresholds.items()
        },
    }


def plan_gradient_from_dict(data: dict[str, Any]) -> LocalPlanGradient:
    """Deserialize a plain dict (from SDK Plan.gradient) to a local PlanGradient.

    Key conversions:
        - resolution_timeout: float (seconds) -> timedelta
        - UPPERCASE string names -> GradientZone enums
        - nested dict -> DimensionGradient
    """
    dim_thresholds: dict[str, LocalDimensionGradient] = {}
    for dim, thresh_dict in data.get("dimension_thresholds", {}).items():
        dim_thresholds[dim] = LocalDimensionGradient(
            flag_threshold=float(thresh_dict["flag_threshold"]),
            hold_threshold=float(thresh_dict["hold_threshold"]),
        )

    return LocalPlanGradient(
        retry_budget=int(data["retry_budget"]),
        after_retry_exhaustion=_GRADIENT_ZONE_NAME_TO_LOCAL[data["after_retry_exhaustion"]],
        resolution_timeout=timedelta(seconds=float(data["resolution_timeout"])),
        optional_node_failure=_GRADIENT_ZONE_NAME_TO_LOCAL[data["optional_node_failure"]],
        budget_flag_threshold=float(data["budget_flag_threshold"]),
        budget_hold_threshold=float(data["budget_hold_threshold"]),
        dimension_thresholds=dim_thresholds,
    )


# ---------------------------------------------------------------------------
# ConstraintEnvelope converters (local dataclass <-> dict)
# ---------------------------------------------------------------------------


def envelope_to_dict(local: ConstraintEnvelope) -> dict[str, Any]:
    """Serialize a ConstraintEnvelopeConfig to a plain dict for the SDK Plan.envelope field."""
    return {
        "financial": local.financial.model_dump() if local.financial else {},
        "operational": local.operational.model_dump(),
        "temporal": local.temporal.model_dump(),
        "data_access": local.data_access.model_dump(),
        "communication": local.communication.model_dump(),
    }


def envelope_from_dict(data: dict[str, Any]) -> ConstraintEnvelope:
    """Deserialize a plain dict (from SDK Plan.envelope) to a ConstraintEnvelopeConfig."""
    import uuid

    from kailash.trust.pact.config import (
        CommunicationConstraintConfig,
        ConstraintEnvelopeConfig,
        DataAccessConstraintConfig,
        FinancialConstraintConfig,
        OperationalConstraintConfig,
        TemporalConstraintConfig,
    )

    financial_data = data.get("financial")
    financial = None
    if financial_data and isinstance(financial_data, dict):
        financial = FinancialConstraintConfig(**financial_data)
    elif financial_data is None:
        financial = FinancialConstraintConfig(max_spend_usd=1.0)

    operational_data = data.get("operational")
    operational = OperationalConstraintConfig()
    if operational_data and isinstance(operational_data, dict):
        operational = OperationalConstraintConfig(**operational_data)

    temporal_data = data.get("temporal")
    temporal = TemporalConstraintConfig()
    if temporal_data and isinstance(temporal_data, dict):
        temporal = TemporalConstraintConfig(**temporal_data)

    data_access_data = data.get("data_access")
    data_access = DataAccessConstraintConfig()
    if data_access_data and isinstance(data_access_data, dict):
        data_access = DataAccessConstraintConfig(**data_access_data)

    communication_data = data.get("communication")
    communication = CommunicationConstraintConfig()
    if communication_data and isinstance(communication_data, dict):
        communication = CommunicationConstraintConfig(**communication_data)

    return ConstraintEnvelopeConfig(
        id=data.get("id", f"deserialized-{uuid.uuid4().hex[:8]}"),
        financial=financial,
        operational=operational,
        temporal=temporal,
        data_access=data_access,
        communication=communication,
    )


# ---------------------------------------------------------------------------
# Plan converters (full object)
# ---------------------------------------------------------------------------


def plan_to_sdk(local: LocalPlan) -> SdkPlan:
    """Convert a local Plan to its SDK equivalent.

    The local ``ConstraintEnvelope`` and ``PlanGradient`` are serialized to
    dicts, since the SDK Plan stores them as ``dict[str, Any]``.
    """
    return SdkPlan(
        plan_id=local.plan_id,
        name=local.name,
        envelope=envelope_to_dict(local.envelope),
        gradient=plan_gradient_to_dict(local.gradient),
        nodes={nid: plan_node_to_sdk(node) for nid, node in local.nodes.items()},
        edges=[plan_edge_to_sdk(e) for e in local.edges],
        state=plan_state_to_sdk(local.state),
        created_at=local.created_at,
        modified_at=local.modified_at,
    )


def plan_from_sdk(
    sdk: SdkPlan,
    *,
    agent_specs: dict[str, AgentSpec],
) -> LocalPlan:
    """Convert an SDK Plan to its local equivalent.

    Requires ``agent_specs`` to resolve ``agent_spec_id`` fields in PlanNodes.

    Args:
        sdk: The SDK Plan to convert.
        agent_specs: Mapping of spec_id -> AgentSpec for PlanNode resolution.

    Raises:
        KeyError: If any PlanNode's ``agent_spec_id`` is not in ``agent_specs``.
    """
    return LocalPlan(
        plan_id=sdk.plan_id,
        name=sdk.name,
        envelope=envelope_from_dict(sdk.envelope),
        gradient=plan_gradient_from_dict(sdk.gradient),
        nodes={
            nid: plan_node_from_sdk(node, agent_specs=agent_specs)
            for nid, node in sdk.nodes.items()
        },
        edges=[plan_edge_from_sdk(e) for e in sdk.edges],
        state=plan_state_from_sdk(sdk.state),
        created_at=sdk.created_at,
        modified_at=sdk.modified_at,
    )
