# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Multi-agent orchestration layer.

Sub-packages:
    planner: Decompose objectives into governed multi-agent plans.
    recovery: Diagnose failures and recompose plans.
    protocols: Delegation, clarification, escalation, completion.
    context: Context injection, summarization, scope bridging.

Modules:
    monitor: PlanMonitor — the autonomous orchestration execution engine.
"""

from kaizen_agents.orchestration.context import ContextInjector, ContextSummarizer, ScopeBridge
from kaizen_agents.orchestration.monitor import PlanMonitor, PlanResult
from kaizen_agents.orchestration.planner import (
    AgentDesigner,
    CapabilityMatch,
    CapabilityMatcher,
    PlanComposer,
    PlanValidator,
    SpawnDecision,
    SpawnPolicy,
    Subtask,
    TaskDecomposer,
    ValidationError,
)
from kaizen_agents.orchestration.protocols import (
    ClarificationProtocol,
    DelegationProtocol,
    EscalationAction,
    EscalationProtocol,
)
from kaizen_agents.orchestration.recovery import (
    FailureCategory,
    FailureDiagnosis,
    FailureDiagnoser,
    RecoveryPlan,
    RecoveryStrategy,
    Recomposer,
)

__all__ = [
    # planner
    "AgentDesigner",
    "CapabilityMatch",
    "CapabilityMatcher",
    "PlanComposer",
    "PlanValidator",
    "SpawnDecision",
    "SpawnPolicy",
    "Subtask",
    "TaskDecomposer",
    "ValidationError",
    # recovery
    "FailureCategory",
    "FailureDiagnosis",
    "FailureDiagnoser",
    "RecoveryPlan",
    "RecoveryStrategy",
    "Recomposer",
    # protocols
    "ClarificationProtocol",
    "DelegationProtocol",
    "EscalationAction",
    "EscalationProtocol",
    # context
    "ContextInjector",
    "ContextSummarizer",
    "ScopeBridge",
    # monitor
    "PlanMonitor",
    "PlanResult",
]
