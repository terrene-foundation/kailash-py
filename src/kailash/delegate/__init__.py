# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash.delegate -- Apache 2.0 OSS Delegate composition primitive.

The audit-grade composition surface ``(Connector x Signature x ConstraintEnvelope
x Executor)`` under EATP audit per Terrene Delegate Specification v0.

DISAMBIGUATION: NOT ``kaizen_agents.delegate.Delegate`` (LLM execution facade).
The kaizen-agents Delegate is one possible ``executor=`` argument here.

Cross-implementation conformance: shares vendored conformance vectors with the
kailash-rs implementation; ``receipts_agree(rs, py)`` is the
cross-language verification gate.

Per #1035: this package MUST have zero proprietary dependencies. The
``tools/lint-delegate-fences.py`` lint enforces this fence.
"""

# Public surface -- S2 types substrate. Later shards (S3-S8) extend this list
# via parallel-shard merges per orphan-detection.md Rule 6a.
from kailash.delegate.audit import (
    AuditChainEmissionError,
    AuditChainEngine,
    AuditChainEntry,
    AuditChainSignatureError,
    CrossAnchorIntegrityError,
    DelegateEventType,
    WitnessedCrossAnchor,
)
from kailash.delegate.conformance.schema import (
    ConformanceVector,
    ConformanceVectorIntegrityError,
    ConformanceVectorLoader,
    ReceiptsAgreementError,
    ReceiptsAgreeReport,
    assert_receipts_agree,
    receipts_agree,
)
from kailash.delegate.dispatch import (
    AttestedReadReceipt,
    AuthVerifier,
    Connector,
    ConnectorInvocationResult,
    DispatchCascadeViolationError,
    DispatchEnvelopeViolationError,
    DispatchResult,
    DispatchSignatureError,
    DispatchSignerError,
    DispatchSurface,
    DispatchValidationError,
    KnowledgeLedger,
    LegacyInvokeConnector,
    Principal,
    RevocationChannel,
    SignatureContract,
    SignedActionEnvelope,
)
from kailash.delegate.envelope import DelegateConstraintEnvelope, EnvelopeWideningError
from kailash.delegate.runtime import (
    DelegateRuntime,
    Posture,
    R2Composition,
    R2CompositionError,
    RuntimeCompositionError,
    RuntimeExecutionResult,
    RuntimePhaseError,
    RuntimePostureBlockedError,
    TAODState,
    TAODTransition,
)
from kailash.delegate.trust import (
    CascadeScopeExpansionError,
    CascadeTenantViolationError,
    GrantMoment,
    TenantScope,
    TenantScopedCascade,
)
from kailash.delegate.types import (
    CapabilitySet,
    DelegateGenesisRecord,
    DelegateIdentity,
    LifecycleError,
    LifecycleState,
    PrincipalDirectory,
    PrincipalKind,
    Role,
    RoleLifecycleState,
    RoleScope,
)
from kailash.delegate.verifier import Ed25519Verifier, NullVerifier, Verifier

# ─── Issue #1035 acceptance-gate aliases ─────────────────────────────────────
# The shipped class names (DelegateRuntime, DelegateConstraintEnvelope, etc.)
# are deliberate disambiguation per the module docstring above. These aliases
# expose the unprefixed names required by the #1035 import line:
#
#     from kailash.delegate import (
#         Delegate, ConstraintEnvelope, PrincipalDirectory,
#         GenesisRecord, PostureState, AuditChain, Connector,
#     )
#
# Both forms resolve to the same class object (Delegate is DelegateRuntime
# at runtime) -- `isinstance(x, Delegate) is isinstance(x, DelegateRuntime)`.
# Use the prefixed names in NEW code to avoid the kaizen_agents.delegate.Delegate
# collision named in the module docstring; the unprefixed aliases exist for
# spec-compliance and downstream consumer ergonomics.
Delegate = DelegateRuntime
ConstraintEnvelope = DelegateConstraintEnvelope
GenesisRecord = DelegateGenesisRecord
PostureState = Posture
AuditChain = AuditChainEngine

__all__ = [
    # Group 1 -- Envelope (S2.5 F1/F7)
    "DelegateConstraintEnvelope",
    "EnvelopeWideningError",
    # Group 2 -- Identity + role substrate (S2.5 F2/F3)
    "DelegateIdentity",
    "PrincipalDirectory",
    "PrincipalKind",
    "Role",
    "RoleLifecycleState",
    "RoleScope",
    "CapabilitySet",
    # Group 3 -- Lifecycle state machine (S2 -> S2.5)
    "LifecycleState",
    "LifecycleError",
    # Group 4 -- Genesis composition (S2.5 F4)
    "DelegateGenesisRecord",
    # Group 5 -- Trust cascade (S3 -- TenantScope, GrantMoment)
    "TenantScope",
    "TenantScopedCascade",
    "GrantMoment",
    "CascadeTenantViolationError",
    "CascadeScopeExpansionError",
    # Group 6 -- Audit chain (S4 -- AuditChainEngine, WitnessedCrossAnchor)
    "AuditChainEngine",
    "AuditChainEntry",
    "WitnessedCrossAnchor",
    "DelegateEventType",
    "AuditChainEmissionError",
    "AuditChainSignatureError",
    "CrossAnchorIntegrityError",
    # Group 7 -- Dispatch + Connector (S5)
    "Connector",
    "ConnectorInvocationResult",
    "DispatchSurface",
    "DispatchResult",
    "DispatchValidationError",
    "DispatchEnvelopeViolationError",
    "DispatchCascadeViolationError",
    # Group 7b -- Connector-authoring surface (#1532 RC2). Promoted from
    # kailash.delegate.dispatch so a contrib/ connector depends on ONE stable
    # surface (kailash.delegate) instead of importing from .dispatch directly.
    "Principal",
    "SignedActionEnvelope",
    "AttestedReadReceipt",
    "RevocationChannel",
    "KnowledgeLedger",
    "AuthVerifier",
    "SignatureContract",
    "LegacyInvokeConnector",
    "DispatchSignatureError",
    "DispatchSignerError",
    # Group 8 -- Runtime spine + TAOD lifecycle (S6)
    "DelegateRuntime",
    "Posture",
    "TAODState",
    "TAODTransition",
    "R2Composition",
    "RuntimeExecutionResult",
    "RuntimeCompositionError",
    "RuntimePostureBlockedError",
    "RuntimePhaseError",
    "R2CompositionError",
    # Group 9 -- Conformance schema (S7 -- cross-SDK byte-shape contract)
    "ConformanceVector",
    "ConformanceVectorLoader",
    "ReceiptsAgreeReport",
    "receipts_agree",
    "assert_receipts_agree",
    "ConformanceVectorIntegrityError",
    "ReceiptsAgreementError",
    # Group 10 -- #1035 acceptance-gate aliases
    "Delegate",  # alias of DelegateRuntime
    "ConstraintEnvelope",  # alias of DelegateConstraintEnvelope
    "GenesisRecord",  # alias of DelegateGenesisRecord
    "PostureState",  # alias of Posture
    "AuditChain",  # alias of AuditChainEngine
    # Group 11 -- Signature verification (Shard Y C1/H2 closure)
    "Verifier",  # Protocol — fail-closed signature verification contract
    "NullVerifier",  # default fail-closed impl (rejects all)
    "Ed25519Verifier",  # cryptography-backed Ed25519 impl
]
