# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""L3 Autonomy Primitives for the Kailash Kaizen Agent Framework.

L3 enables agents that spawn child agents, allocate constrained budgets,
communicate through typed channels, and execute dynamic task graphs — all
under PACT governance with EATP audit traceability.

All L3 primitives are deterministic (no LLM calls). The orchestration layer
(kaizen-agents) decides WHAT to do; the SDK validates and enforces.

Concurrency note: L3 primitives use asyncio.Lock for shared state protection.
This overrides the PACT governance rule mandating threading.Lock, because L3
primitives are exclusively called from async code paths (PlanExecutor,
MessageRouter, AgentFactory). See AD-L3-04-AMENDED.

Subpackages:
    envelope  — EnvelopeTracker, EnvelopeSplitter, EnvelopeEnforcer (Spec 01)
    context   — ScopedContext, ScopeProjection (Spec 02)
    messaging — MessageRouter, MessageChannel, typed payloads (Spec 03)
    factory   — AgentFactory, AgentInstanceRegistry (Spec 04)
    plan      — Plan DAG, PlanValidator, PlanExecutor (Spec 05)
"""

from __future__ import annotations

# Envelope (Spec 01)
from kaizen.l3.envelope import (
    EnvelopeEnforcer,
    EnvelopeSplitter,
    EnvelopeTracker,
    GradientZone,
    Verdict,
)

# Context (Spec 02)
from kaizen.l3.context import (
    ContextScope,
    ContextValue,
    DataClassification,
    ScopeProjection,
)

# Messaging (Spec 03)
from kaizen.l3.messaging import (
    DeadLetterStore,
    MessageChannel,
    MessageEnvelope,
    MessageRouter,
    MessageType,
)

# Factory (Spec 04)
from kaizen.l3.factory import (
    AgentFactory,
    AgentInstance,
    AgentInstanceRegistry,
    AgentSpec,
)

# Plan (Spec 05)
from kaizen.l3.plan import (
    Plan,
    PlanExecutor,
    PlanValidator,
    apply_modification,
    apply_modifications,
)

__all__ = [
    # Envelope (Spec 01)
    "EnvelopeEnforcer",
    "EnvelopeSplitter",
    "EnvelopeTracker",
    "GradientZone",
    "Verdict",
    # Context (Spec 02)
    "ContextScope",
    "ContextValue",
    "DataClassification",
    "ScopeProjection",
    # Messaging (Spec 03)
    "DeadLetterStore",
    "MessageChannel",
    "MessageEnvelope",
    "MessageRouter",
    "MessageType",
    # Factory (Spec 04)
    "AgentFactory",
    "AgentInstance",
    "AgentInstanceRegistry",
    "AgentSpec",
    # Plan (Spec 05)
    "Plan",
    "PlanExecutor",
    "PlanValidator",
    "apply_modification",
    "apply_modifications",
]
