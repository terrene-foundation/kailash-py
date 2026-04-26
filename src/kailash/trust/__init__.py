# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Kailash Trust — EATP trust protocol and trust-plane integration.

This package provides the Enterprise Agent Trust Protocol (EATP) implementation
for the Kailash SDK, enabling cryptographic trust chains, delegation, verification,
and audit for human-AI collaborative systems.

Layers:

- **Protocol layer** (``kailash.trust.*``): Core EATP data structures, trust
  chains, posture management, reasoning traces, hooks, roles, and vocabulary.
- **Plane layer** (``kailash.trust.plane.*``): Trust-plane platform for project-
  scoped trust environments with persistent stores, constraint enforcement,
  delegation, and enterprise features (RBAC, OIDC, SIEM, dashboard).
- **Signing layer** (``kailash.trust.signing.*``): Ed25519 cryptographic
  operations. Requires ``pynacl`` (included in the base ``pip install kailash``).
- **Agents layer** (``kailash.trust.agents.*``): Trust-enhanced agent wrappers
  (TrustedAgent, PseudoAgent) for the trust sandwich pattern.

Quick start::

    from kailash.trust import (
        GenesisRecord,
        TrustPosture,
        TrustRole,
        EATPHook,
        HookRegistry,
    )

    # Crypto operations require pynacl:
    from kailash.trust import generate_keypair, sign, verify_signature

Usage notes:

- Core types (chain records, postures, roles, hooks, exceptions) are importable
  without ``pynacl`` installed.
- Cryptographic functions (``generate_keypair``, ``sign``, ``verify_signature``,
  ``dual_sign``, ``dual_verify``) use lazy loading and raise ``ImportError``
  with installation instructions if ``pynacl`` is missing.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

# Trust subsystem shares the core kailash version
from kailash import __version__  # noqa: F401

# Audit Store (SPEC-08 canonical types)
from kailash.trust.audit_store import (
    AuditEvent,
    AuditEventType,
    AuditFilter,
    AuditOutcome,
    AuditStoreProtocol,
    InMemoryAuditStore,
    SqliteAuditStore,
)

# Authority types
from kailash.trust.authority import (
    AuthorityPermission,
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)

# Chain data structures
from kailash.trust.chain import (
    ALL_DIMENSIONS,
    VALID_DIMENSION_NAMES,
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
)
from kailash.trust.chain import ChainConstraintEnvelope as ConstraintEnvelope
from kailash.trust.chain import (
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

# Store types
from kailash.trust.chain_store import TrustStore
from kailash.trust.chain_store.memory import InMemoryTrustStore

# Cost Event (SPEC-08 cost tracking with deduplication)
from kailash.trust.cost_event import (
    CostDeduplicator,
    CostEvent,
    CostEventError,
    DuplicateCostError,
)

# Canonical envelope (SPEC-07 unification)
from kailash.trust.envelope import AgentPosture, CommunicationConstraint
from kailash.trust.envelope import ConstraintEnvelope as CanonicalConstraintEnvelope
from kailash.trust.envelope import (
    DataAccessConstraint,
    EnvelopeValidationError,
    FinancialConstraint,
    GradientThresholds,
    OperationalConstraint,
    SecretRef,
    TemporalConstraint,
    UnknownEnvelopeFieldError,
    from_plane_envelope,
)
from kailash.trust.envelope import sign_envelope as sign_canonical_envelope
from kailash.trust.envelope import to_plane_envelope
from kailash.trust.envelope import verify_envelope as verify_canonical_envelope

# Exceptions
from kailash.trust.exceptions import (
    AgentAlreadyEstablishedError,
    AuthorityInactiveError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationCycleError,
    DelegationError,
    DelegationExpiredError,
    HookError,
    HookTimeoutError,
    InvalidSignatureError,
    InvalidTrustChainError,
    PathTraversalError,
    PostureStoreError,
    TrustChainNotFoundError,
    TrustError,
    TrustStoreError,
    VerificationFailedError,
)

# Hooks
from kailash.trust.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)

# Operations (primary user-facing API)
from kailash.trust.operations import CapabilityRequest, TrustKeyManager, TrustOperations

# Posture (no pynacl dependency)
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

# Reasoning traces (no pynacl dependency)
from kailash.trust.reasoning.traces import (
    ConfidentialityLevel,
    EvidenceReference,
    ReasoningTrace,
    reasoning_completeness_score,
)

# Roles
from kailash.trust.roles import (
    ROLE_PERMISSIONS,
    TrustRole,
    check_permission,
    require_permission,
)

# Vocabulary
from kailash.trust.vocabulary import (
    CONSTRAINT_VOCABULARY,
    POSTURE_VOCABULARY,
    constraint_from_eatp,
    constraint_to_eatp,
    posture_from_eatp,
    posture_to_eatp,
)

# ---------------------------------------------------------------------------
# Core types — no pynacl dependency
# ---------------------------------------------------------------------------


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded crypto names (require pynacl)
# These are resolved at runtime via __getattr__ below. The type-level
# declarations keep static analysis (pyright) happy with __all__.
# ---------------------------------------------------------------------------
if TYPE_CHECKING:
    from kailash.trust.signing.crypto import NACL_AVAILABLE as NACL_AVAILABLE
    from kailash.trust.signing.crypto import SALT_LENGTH as SALT_LENGTH
    from kailash.trust.signing.crypto import DualSignature as DualSignature
    from kailash.trust.signing.crypto import (
        derive_key_with_salt as derive_key_with_salt,
    )
    from kailash.trust.signing.crypto import dual_sign as dual_sign
    from kailash.trust.signing.crypto import dual_verify as dual_verify
    from kailash.trust.signing.crypto import generate_keypair as generate_keypair
    from kailash.trust.signing.crypto import generate_salt as generate_salt
    from kailash.trust.signing.crypto import hash_chain as hash_chain
    from kailash.trust.signing.crypto import (
        hash_reasoning_trace as hash_reasoning_trace,
    )
    from kailash.trust.signing.crypto import (
        hash_trust_chain_state as hash_trust_chain_state,
    )
    from kailash.trust.signing.crypto import (
        hash_trust_chain_state_salted as hash_trust_chain_state_salted,
    )
    from kailash.trust.signing.crypto import hmac_sign as hmac_sign
    from kailash.trust.signing.crypto import hmac_verify as hmac_verify
    from kailash.trust.signing.crypto import (
        serialize_for_signing as serialize_for_signing,
    )
    from kailash.trust.signing.crypto import sign as sign
    from kailash.trust.signing.crypto import (
        sign_reasoning_trace as sign_reasoning_trace,
    )
    from kailash.trust.signing.crypto import (
        verify_reasoning_signature as verify_reasoning_signature,
    )
    from kailash.trust.signing.crypto import verify_signature as verify_signature

# ---------------------------------------------------------------------------
# Issue #604 algorithm-agility scaffold (canonical re-export)
# ---------------------------------------------------------------------------
# `kailash.trust.signing.algorithm_id` is the canonical home; re-exporting at
# `kailash.trust` lets `from kailash.trust import AlgorithmIdentifier` work.
# These have no heavy deps (pure-Python dataclass + helper) so the import is
# eager rather than lazy via __getattr__.
from kailash.trust.signing.algorithm_id import (
    ALGORITHM_DEFAULT,
    AlgorithmIdentifier,
    coerce_algorithm_id,
)

_CRYPTO_NAMES = frozenset(
    {
        "generate_keypair",
        "sign",
        "verify_signature",
        "DualSignature",
        "dual_sign",
        "dual_verify",
        "hmac_sign",
        "hmac_verify",
        "hash_chain",
        "hash_trust_chain_state",
        "hash_trust_chain_state_salted",
        "hash_reasoning_trace",
        "sign_reasoning_trace",
        "verify_reasoning_signature",
        "serialize_for_signing",
        "generate_salt",
        "derive_key_with_salt",
        "NACL_AVAILABLE",
        "SALT_LENGTH",
    }
)

_INSTALL_HINT = (
    "Cryptographic operations require PyNaCl. " "Install with: pip install kailash"
)


def __getattr__(name: str):  # noqa: C901
    """Lazy-load cryptographic functions that depend on pynacl.

    This allows ``from kailash.trust import GenesisRecord`` to work without
    pynacl installed, while ``from kailash.trust import generate_keypair``
    raises a clear ImportError if pynacl is missing.
    """
    if name in _CRYPTO_NAMES:
        try:
            from kailash.trust.signing import crypto as _crypto
        except ImportError:
            raise ImportError(_INSTALL_HINT) from None

        # Cache the resolved attribute on the module for subsequent access
        import sys

        module = sys.modules[__name__]
        value = getattr(_crypto, name)
        setattr(module, name, value)
        return value

    raise AttributeError(f"module 'kailash.trust' has no attribute {name!r}")


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # --- Chain constants ---
    "ALL_DIMENSIONS",
    "VALID_DIMENSION_NAMES",
    # --- Chain data structures ---
    "AuthorityType",
    "CapabilityType",
    "ActionResult",
    "ConstraintType",
    "VerificationLevel",
    "DelegationLimits",
    "GenesisRecord",
    "CapabilityAttestation",
    "DelegationRecord",
    "Constraint",
    "ConstraintEnvelope",
    "AuditAnchor",
    "VerificationResult",
    "TrustLineageChain",
    "LinkedHashEntry",
    "LinkedHashChain",
    # --- Exceptions ---
    "TrustError",
    "AuthorityNotFoundError",
    "AuthorityInactiveError",
    "TrustChainNotFoundError",
    "InvalidTrustChainError",
    "CapabilityNotFoundError",
    "ConstraintViolationError",
    "DelegationError",
    "DelegationCycleError",
    "DelegationExpiredError",
    "InvalidSignatureError",
    "VerificationFailedError",
    "AgentAlreadyEstablishedError",
    "TrustStoreError",
    "HookError",
    "HookTimeoutError",
    "PathTraversalError",
    "PostureStoreError",
    # --- Operations ---
    "TrustOperations",
    "TrustKeyManager",
    "CapabilityRequest",
    # --- Stores ---
    "TrustStore",
    "InMemoryTrustStore",
    # --- Authority ---
    "AuthorityPermission",
    "OrganizationalAuthority",
    "AuthorityRegistryProtocol",
    # --- Posture ---
    "TrustPosture",
    "PostureStateMachine",
    "PostureEvidence",
    "PostureTransition",
    "PostureConstraints",
    "PostureResult",
    "PostureEvaluationResult",
    "TransitionGuard",
    "PostureTransitionRequest",
    "TransitionResult",
    "PostureStore",
    "TrustPostureMapper",
    "map_verification_to_posture",
    "get_posture_for_action",
    # --- Reasoning ---
    "ConfidentialityLevel",
    "ReasoningTrace",
    "EvidenceReference",
    "reasoning_completeness_score",
    # --- Hooks ---
    "HookType",
    "HookContext",
    "HookResult",
    "EATPHook",
    "HookRegistry",
    # --- Roles ---
    "TrustRole",
    "ROLE_PERMISSIONS",
    "check_permission",
    "require_permission",
    # --- Vocabulary ---
    "POSTURE_VOCABULARY",
    "CONSTRAINT_VOCABULARY",
    "posture_to_eatp",
    "posture_from_eatp",
    "constraint_to_eatp",
    "constraint_from_eatp",
    # --- Canonical Envelope (SPEC-07) ---
    "AgentPosture",
    "CanonicalConstraintEnvelope",
    "CommunicationConstraint",
    "DataAccessConstraint",
    "EnvelopeValidationError",
    "FinancialConstraint",
    "GradientThresholds",
    "OperationalConstraint",
    "SecretRef",
    "TemporalConstraint",
    "UnknownEnvelopeFieldError",
    "from_plane_envelope",
    "sign_canonical_envelope",
    "to_plane_envelope",
    "verify_canonical_envelope",
    # --- Audit Store (SPEC-08) ---
    "AuditEvent",
    "AuditEventType",
    "AuditOutcome",
    "AuditFilter",
    "AuditStoreProtocol",
    "InMemoryAuditStore",
    "SqliteAuditStore",
    # --- Cost Event (SPEC-08) ---
    "CostEvent",
    "CostDeduplicator",
    "CostEventError",
    "DuplicateCostError",
    # --- Crypto (lazy-loaded, requires pynacl) ---
    "generate_keypair",
    "sign",
    "verify_signature",
    "DualSignature",
    "dual_sign",
    "dual_verify",
    "hmac_sign",
    "hmac_verify",
    "hash_chain",
    "hash_trust_chain_state",
    "hash_trust_chain_state_salted",
    "hash_reasoning_trace",
    "sign_reasoning_trace",
    "verify_reasoning_signature",
    "serialize_for_signing",
    "generate_salt",
    "derive_key_with_salt",
    "NACL_AVAILABLE",
    "SALT_LENGTH",
    # --- Issue #604 algorithm-agility scaffold ---
    "ALGORITHM_DEFAULT",
    "AlgorithmIdentifier",
    "coerce_algorithm_id",
]
