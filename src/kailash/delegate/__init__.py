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
from kailash.delegate.dispatch import (
    Connector,
    ConnectorInvocationResult,
    DispatchCascadeViolationError,
    DispatchEnvelopeViolationError,
    DispatchResult,
    DispatchSurface,
    DispatchValidationError,
)
from kailash.delegate.envelope import (
    DelegateConstraintEnvelope,
    EnvelopeWideningError,
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
    Role,
    RoleLifecycleState,
    RoleScope,
)

__all__ = [
    # Group 1 -- Envelope (S2.5 F1/F7)
    "DelegateConstraintEnvelope",
    "EnvelopeWideningError",
    # Group 2 -- Identity + role substrate (S2.5 F2/F3)
    "DelegateIdentity",
    "PrincipalDirectory",
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
]
