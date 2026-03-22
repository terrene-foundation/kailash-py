# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Envelope tracking, splitting, and enforcement for L3 budget management.

Three primitives:
    EnvelopeTracker  -- Continuous runtime budget tracking (stateful, asyncio.Lock)
    EnvelopeSplitter -- Divide parent envelope into child envelopes (stateless)
    EnvelopeEnforcer -- Non-bypassable middleware wrapping tracker + strict checks

All types are frozen dataclasses (AD-L3-15). All numeric fields validated
with math.isfinite() (INV-7). Envelope representation uses plain dicts
for decoupling from PACT ConstraintEnvelopeConfig.
"""

from __future__ import annotations

from kaizen.l3.envelope.enforcer import EnvelopeEnforcer
from kaizen.l3.envelope.errors import EnforcerError, SplitError, TrackerError
from kaizen.l3.envelope.splitter import EnvelopeSplitter
from kaizen.l3.envelope.tracker import EnvelopeTracker
from kaizen.l3.envelope.types import (
    AllocationRequest,
    BudgetRemaining,
    CostEntry,
    DimensionGradient,
    DimensionUsage,
    EnforcementContext,
    GradientZone,
    PlanGradient,
    ReclaimResult,
    Verdict,
)

__all__ = [
    # Primitives
    "EnvelopeEnforcer",
    "EnvelopeSplitter",
    "EnvelopeTracker",
    # Types
    "AllocationRequest",
    "BudgetRemaining",
    "CostEntry",
    "DimensionGradient",
    "DimensionUsage",
    "EnforcementContext",
    "GradientZone",
    "PlanGradient",
    "ReclaimResult",
    "Verdict",
    # Errors
    "EnforcerError",
    "SplitError",
    "TrackerError",
]
