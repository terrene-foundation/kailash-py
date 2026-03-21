# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""EATP enforcement utilities — strict, shadow mode, challenge-response, decorators.

Provides four enforcement modes for integrating EATP trust verification:

- **StrictEnforcer**: Production enforcement — blocks unauthorized actions
- **ShadowEnforcer**: Observation mode — logs verdicts without blocking
- **ChallengeProtocol**: Live trust verification via challenge-response
- **Decorators**: 3-line integration for any Python function

Example:
    >>> from kailash.trust.enforce import verified, audited, shadow
    >>>
    >>> @verified(agent_id="agent-001", action="read_data")
    ... async def read_sensitive_data(query: str) -> dict:
    ...     return await db.execute(query)
"""

from kailash.trust.enforce.challenge import (
    ChallengeError,
    ChallengeProtocol,
    ChallengeRequest,
    ChallengeResponse,
)
from kailash.trust.enforce.decorators import audited, shadow, verified
from kailash.trust.enforce.proximity import (
    CONSERVATIVE_PROXIMITY,
    ProximityAlert,
    ProximityConfig,
    ProximityScanner,
)
from kailash.trust.enforce.shadow import ShadowEnforcer, ShadowMetrics
from kailash.trust.enforce.strict import (
    EATPBlockedError,
    EATPHeldError,
    EnforcementRecord,
    HeldBehavior,
    StrictEnforcer,
    Verdict,
)

__all__ = [
    # Strict enforcement
    "StrictEnforcer",
    "Verdict",
    "HeldBehavior",
    "EATPBlockedError",
    "EATPHeldError",
    "EnforcementRecord",
    # Shadow enforcement
    "ShadowEnforcer",
    "ShadowMetrics",
    # Challenge-response
    "ChallengeProtocol",
    "ChallengeRequest",
    "ChallengeResponse",
    "ChallengeError",
    # Proximity scanning
    "ProximityScanner",
    "ProximityConfig",
    "ProximityAlert",
    "CONSERVATIVE_PROXIMITY",
    # Decorators
    "verified",
    "audited",
    "shadow",
]
