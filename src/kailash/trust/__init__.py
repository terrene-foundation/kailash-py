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
  operations. Requires ``pynacl`` (install via ``pip install kailash[trust]``).
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

# ---------------------------------------------------------------------------
# Core types — no pynacl dependency
# ---------------------------------------------------------------------------

# Chain data structures
from kailash.trust.chain import (
    AuthorityType,
    CapabilityType,
    ActionResult,
    ConstraintType,
    VerificationLevel,
    DelegationLimits,
    GenesisRecord,
    CapabilityAttestation,
    DelegationRecord,
    Constraint,
    ConstraintEnvelope,
    AuditAnchor,
    VerificationResult,
    TrustLineageChain,
    LinkedHashEntry,
    LinkedHashChain,
)

# Exceptions
from kailash.trust.exceptions import (
    TrustError,
    AuthorityNotFoundError,
    AuthorityInactiveError,
    TrustChainNotFoundError,
    InvalidTrustChainError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    DelegationCycleError,
    DelegationExpiredError,
    InvalidSignatureError,
    VerificationFailedError,
    AgentAlreadyEstablishedError,
    TrustStoreError,
    HookError,
    HookTimeoutError,
    PathTraversalError,
    PostureStoreError,
)

# Operations (primary user-facing API)
from kailash.trust.operations import (
    TrustOperations,
    TrustKeyManager,
    CapabilityRequest,
)

# Store types
from kailash.trust.chain_store import TrustStore
from kailash.trust.chain_store.memory import InMemoryTrustStore

# Authority types
from kailash.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    AuthorityRegistryProtocol,
)

# Posture (no pynacl dependency)
from kailash.trust.posture.postures import (
    TrustPosture,
    PostureStateMachine,
    PostureEvidence,
    PostureTransition,
    PostureConstraints,
    PostureResult,
    PostureEvaluationResult,
    TransitionGuard,
    PostureTransitionRequest,
    TransitionResult,
    PostureStore,
    TrustPostureMapper,
    map_verification_to_posture,
    get_posture_for_action,
)

# Reasoning traces (no pynacl dependency)
from kailash.trust.reasoning.traces import (
    ConfidentialityLevel,
    ReasoningTrace,
    EvidenceReference,
    reasoning_completeness_score,
)

# Hooks
from kailash.trust.hooks import (
    HookType,
    HookContext,
    HookResult,
    EATPHook,
    HookRegistry,
)

# Roles
from kailash.trust.roles import (
    TrustRole,
    ROLE_PERMISSIONS,
    check_permission,
    require_permission,
)

# Vocabulary
from kailash.trust.vocabulary import (
    POSTURE_VOCABULARY,
    CONSTRAINT_VOCABULARY,
    posture_to_eatp,
    posture_from_eatp,
    constraint_to_eatp,
    constraint_from_eatp,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded crypto names (require pynacl)
# ---------------------------------------------------------------------------

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
    "Cryptographic operations require PyNaCl. "
    "Install with: pip install kailash[trust]"
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
]
