# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Plan DAG, validator, and executor for L3 task graph execution."""

from __future__ import annotations

from kaizen.l3.plan.errors import (
    ExecutionError,
    ModificationError,
    PlanError,
    ValidationError,
)
from kaizen.l3.plan.executor import AsyncPlanExecutor, PlanExecutor
from kaizen.l3.plan.modification import apply_modification, apply_modifications
from kaizen.l3.plan.suspension import (
    BudgetExceededReason,
    CircuitBreakerTrippedReason,
    EnvelopeViolationReason,
    ExplicitCancellationReason,
    HumanApprovalGateReason,
    SuspensionReason,
    SuspensionRecord,
    suspension_reason_from_dict,
    suspension_reason_label,
    suspension_reason_to_dict,
)
from kaizen.l3.plan.types import (
    EdgeType,
    Plan,
    PlanEdge,
    PlanEvent,
    PlanModification,
    PlanNode,
    PlanNodeId,
    PlanNodeOutput,
    PlanNodeState,
    PlanState,
)
from kaizen.l3.plan.validator import PlanValidator

__all__ = [
    # Types
    "EdgeType",
    "Plan",
    "PlanEdge",
    "PlanEvent",
    "PlanModification",
    "PlanNode",
    "PlanNodeId",
    "PlanNodeOutput",
    "PlanNodeState",
    "PlanState",
    # Errors
    "ExecutionError",
    "ModificationError",
    "PlanError",
    "ValidationError",
    # Validator
    "PlanValidator",
    # Executor
    "AsyncPlanExecutor",
    "PlanExecutor",
    # Modification
    "apply_modification",
    "apply_modifications",
    # Suspension (PACT N3)
    "BudgetExceededReason",
    "CircuitBreakerTrippedReason",
    "EnvelopeViolationReason",
    "ExplicitCancellationReason",
    "HumanApprovalGateReason",
    "SuspensionReason",
    "SuspensionRecord",
    "suspension_reason_from_dict",
    "suspension_reason_label",
    "suspension_reason_to_dict",
]
