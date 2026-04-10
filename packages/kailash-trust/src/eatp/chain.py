# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Legacy shim: ``eatp.chain`` -> ``kailash.trust.chain``.

Emits a :class:`DeprecationWarning` on first import. Migrate to::

    from kailash.trust.chain import VerificationLevel
"""

from __future__ import annotations

import warnings

warnings.warn(
    "eatp.chain is deprecated. " "Use 'from kailash.trust.chain import ...' instead.",
    DeprecationWarning,
    stacklevel=2,
)

from kailash.trust.chain import (  # noqa: E402
    ALL_DIMENSIONS,
    VALID_DIMENSION_NAMES,
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ChainConstraintEnvelope,
    Constraint,
    ConstraintType,
    DelegationLimits,
    DelegationRecord,
    GenesisRecord,
    LinkedHashChain,
    LinkedHashEntry,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)

# Re-export ChainConstraintEnvelope under legacy name too
ConstraintEnvelope = ChainConstraintEnvelope

__all__ = [
    "ALL_DIMENSIONS",
    "VALID_DIMENSION_NAMES",
    "ActionResult",
    "AuditAnchor",
    "AuthorityType",
    "CapabilityAttestation",
    "CapabilityType",
    "ChainConstraintEnvelope",
    "Constraint",
    "ConstraintEnvelope",
    "ConstraintType",
    "DelegationLimits",
    "DelegationRecord",
    "GenesisRecord",
    "LinkedHashChain",
    "LinkedHashEntry",
    "TrustLineageChain",
    "VerificationLevel",
    "VerificationResult",
]
