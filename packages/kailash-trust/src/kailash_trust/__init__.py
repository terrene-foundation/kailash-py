"""
kailash-trust — EATP trust plane integration for the Kailash platform.

The trust plane implementation lives in the core kailash package under
``kailash.trust``. This package re-exports the primary public surface
for consumers who prefer the standalone ``kailash-trust`` install path.

Install:
    pip install kailash-trust

Usage:
    from kailash_trust import TrustOperations, GenesisRecord, TrustStore
    # Equivalent to: from kailash.trust import TrustOperations, GenesisRecord, TrustStore
"""

__version__ = "0.1.1"

# Re-export the primary trust surface from the core kailash package.
# The trust implementation lives in kailash.trust; this package is a
# convenience install that brings kailash as a dependency and surfaces
# the trust API at the kailash_trust namespace.
try:
    from kailash.trust import (  # noqa: F401
        ALL_DIMENSIONS,
        VALID_DIMENSION_NAMES,
        ActionResult,
        AuditAnchor,
        AuthorityNotFoundError,
        AuthorityPermission,
        AuthorityType,
        CapabilityAttestation,
        CapabilityNotFoundError,
        CapabilityRequest,
        CapabilityType,
        Constraint,
        ConstraintEnvelope,
        ConstraintType,
        ConstraintViolationError,
        DelegationError,
        DelegationExpiredError,
        DelegationLimits,
        DelegationRecord,
        GenesisRecord,
        InMemoryTrustStore,
        InvalidSignatureError,
        InvalidTrustChainError,
        LinkedHashChain,
        LinkedHashEntry,
        TrustChainNotFoundError,
        TrustError,
        TrustKeyManager,
        TrustLineageChain,
        TrustOperations,
        TrustStore,
        TrustStoreError,
        VerificationFailedError,
        VerificationLevel,
        VerificationResult,
    )
except ImportError as exc:
    raise ImportError(
        "kailash-trust requires the kailash core package. "
        "Install it with: pip install kailash>=2.8.7"
    ) from exc

__all__ = [
    "__version__",
    "ALL_DIMENSIONS",
    "VALID_DIMENSION_NAMES",
    "ActionResult",
    "AuditAnchor",
    "AuthorityNotFoundError",
    "AuthorityPermission",
    "AuthorityType",
    "CapabilityAttestation",
    "CapabilityNotFoundError",
    "CapabilityRequest",
    "CapabilityType",
    "Constraint",
    "ConstraintEnvelope",
    "ConstraintType",
    "ConstraintViolationError",
    "DelegationError",
    "DelegationExpiredError",
    "DelegationLimits",
    "DelegationRecord",
    "GenesisRecord",
    "InMemoryTrustStore",
    "InvalidSignatureError",
    "InvalidTrustChainError",
    "LinkedHashChain",
    "LinkedHashEntry",
    "TrustChainNotFoundError",
    "TrustError",
    "TrustKeyManager",
    "TrustLineageChain",
    "TrustOperations",
    "TrustStore",
    "TrustStoreError",
    "VerificationFailedError",
    "VerificationLevel",
    "VerificationResult",
]
