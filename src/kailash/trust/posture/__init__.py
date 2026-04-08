# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Trust Posture — graduated autonomy levels for agent oversight.

Provides the five-level trust posture system defined by the EATP specification:

- :class:`TrustPosture` — Enum of posture levels (PSEUDO_AGENT through DELEGATED).
- :class:`PostureStateMachine` — State machine with transition guards.
- :class:`PostureEvidence` — Quantitative metrics supporting posture transitions.

Posture levels (lowest to highest autonomy):

1. **PSEUDO_AGENT** — Human performs all reasoning; agent is interface only.
2. **SUPERVISED** — Agent proposes; human approves each action.
3. **SHARED_PLANNING** — Human and agent co-plan; agent executes approved plans.
4. **CONTINUOUS_INSIGHT** — Agent executes; human monitors in real-time.
5. **DELEGATED** — Agent operates with full autonomy; remote monitoring.
"""

from __future__ import annotations

from kailash.trust.envelope import AgentPosture
from kailash.trust.posture.postures import (
    PostureConstraints,
    PostureEvaluationResult,
    PostureEvidence,
    PostureResult,
    PostureStateMachine,
    PostureStore,
    PostureTransition,
    PostureTransitionRequest,
    TransitionGuard,
    TransitionResult,
    TrustPosture,
    TrustPostureMapper,
    get_posture_for_action,
    map_verification_to_posture,
)

__all__ = [
    # Agent posture ceiling (SPEC-08, re-exported from envelope)
    "AgentPosture",
    # Core posture enum
    "TrustPosture",
    # Transition types
    "PostureTransition",
    # Dataclasses
    "PostureConstraints",
    "PostureResult",
    "PostureEvidence",
    "PostureEvaluationResult",
    "TransitionGuard",
    "PostureTransitionRequest",
    "TransitionResult",
    # Protocol
    "PostureStore",
    # Mapper
    "TrustPostureMapper",
    # State machine
    "PostureStateMachine",
    # Convenience functions
    "map_verification_to_posture",
    "get_posture_for_action",
]
