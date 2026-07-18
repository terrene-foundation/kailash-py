# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance layer -- D/T/R grammar, addressing, clearance, access enforcement, envelopes."""

from kailash.trust.pact.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    KspDenyDetail,
    PactBridge,
    can_access,
)
from kailash.trust.pact.addressing import (
    Address,
    AddressError,
    AddressSegment,
    GrammarError,
    NodeType,
    parse_structural_address,
)
from kailash.trust.pact.agent import (
    GovernanceBlockedError,
    GovernanceHeldError,
    PactGovernedAgent,
)
from kailash.trust.pact.agent_mapping import AgentRoleMapping
from kailash.trust.pact.attestation import (
    ClearanceAttestation,
    ClearanceAttestationError,
    ReidentificationDeniedError,
    new_clearance_attestation,
    posture_can_reidentify,
)
from kailash.trust.pact.audit import (
    AuditAnchor,
    AuditChain,
    PactAuditAction,
    TieredAuditDispatcher,
    create_pact_audit_details,
)
from kailash.trust.pact.bilateral import (
    AtomicValidityError,
    BilateralDelegation,
    BilateralDelegationError,
    CrossRootFederationError,
    GuaranteeTier,
    NonRepudiationClaimError,
    PartyAnchor,
    SignerKind,
    new_bilateral_delegation,
)
from kailash.trust.pact.clearance import (
    POSTURE_CEILING,
    RoleClearance,
    VettingStatus,
    effective_clearance,
)
from kailash.trust.pact.compilation import (
    CompilationError,
    CompiledOrg,
    OrgNode,
    RoleDefinition,
    VacancyDesignation,
    VacancyStatus,
    compile_org,
)
from kailash.trust.pact.context import GovernanceContext
from kailash.trust.pact.decorators import governed_tool
from kailash.trust.pact.eatp_emitter import InMemoryPactEmitter, PactEatpEmitter
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
    check_degenerate_envelope,
    check_gradient_dereliction,
    check_passthrough_envelope,
    compute_effective_envelope,
    default_envelope_for_posture,
    intersect_envelopes,
)
from kailash.trust.pact.exceptions import (
    DeserializationError,
    PactError,
    UngovernedEgressRefused,
)
from kailash.trust.pact.explain import (
    describe_address,
    explain_access,
    explain_envelope,
)
from kailash.trust.pact.governance_posture import (
    GOVERNANCE_REQUIRED_ENV_VAR,
    is_governance_required,
    set_governance_required,
)
from kailash.trust.pact.knowledge import KnowledgeItem
from kailash.trust.pact.middleware import PactGovernanceMiddleware
from kailash.trust.pact.observation import (
    InMemoryObservationSink,
    Observation,
    ObservationSink,
)
from kailash.trust.pact.outbound import (
    DEFAULT_MAX_AUDIT_ENTRIES,
    EffectGovernor,
    EffectKind,
    EngineEffectGovernor,
    OutboundEffect,
    OutboundEffectInterceptor,
    OutboundEffectRefused,
    OutboundVerdict,
    active_interceptor,
    clear_interceptor,
    install_interceptor,
    wrap_transport,
    wrap_transport_async,
)
from kailash.trust.pact.risk_factors import (
    GLOBAL_RISK_FACTOR_REGISTRY,
    RISK_LEVEL_ORDER,
    MalformedRiskFactorError,
    RiskFactor,
    RiskFactorEvaluation,
    RiskFactorRegistry,
    combine_levels,
    evaluate_risk_factors,
    register_risk_factor,
)
from kailash.trust.pact.store import (
    MAX_STORE_SIZE,
    AccessPolicyStore,
    ClearanceStore,
    EnvelopeStore,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
    OrgStore,
)
from kailash.trust.pact.verdict import GovernanceVerdict
from kailash.trust.pact.verify_chain import (
    COMPOSITION_MODE,
    ChainLink,
    ChainResult,
    ChainVerdict,
    VerifyChainError,
    verify_chain,
)
from kailash.trust.pact.weft import (
    MissingGateError,
    UnknownWeftKindError,
    WeftDistributor,
    WeftError,
    WeftEvent,
    WeftKind,
    read_weft_events,
)
from kailash.trust.pact.yaml_loader import (
    BridgeSpec,
    ClearanceSpec,
    ConfigurationError,
    EnvelopeSpec,
    KspSpec,
    LoadedOrg,
    load_org_yaml,
)

__all__ = [
    # Error hierarchy (Ref-18, M5 convention compliance)
    "PactError",
    "DeserializationError",
    "UngovernedEgressRefused",
    # governance_required posture — direct LLM egress (#1779, EATP D6 parity)
    "GOVERNANCE_REQUIRED_ENV_VAR",
    "is_governance_required",
    "set_governance_required",
    # Addressing (Ref-1001)
    "Address",
    "AddressError",
    "AddressSegment",
    "GrammarError",
    "NodeType",
    "parse_structural_address",
    # Compilation (Ref-1003, 1004, 1005)
    "CompilationError",
    "CompiledOrg",
    "OrgNode",
    "RoleDefinition",
    "VacancyDesignation",
    "VacancyStatus",
    "compile_org",
    # Clearance (Ref-2001)
    "POSTURE_CEILING",
    "RoleClearance",
    "VettingStatus",
    "effective_clearance",
    # Knowledge (Ref-2002)
    "KnowledgeItem",
    # Access enforcement (Ref-2003 through 2006)
    "AccessDecision",
    "KnowledgeSharePolicy",
    "KspDenyDetail",
    "PactBridge",
    "can_access",
    # Agent mapping (Ref-7017)
    "AgentRoleMapping",
    # Governance context (Ref-7016)
    "GovernanceContext",
    # Envelopes (Ref-3001 through 3006)
    "MonotonicTighteningError",
    "RoleEnvelope",
    "TaskEnvelope",
    "check_degenerate_envelope",
    "check_gradient_dereliction",
    "check_passthrough_envelope",
    "compute_effective_envelope",
    "default_envelope_for_posture",
    "intersect_envelopes",
    # Audit (Ref-4003, N4 conformance)
    "AuditAnchor",
    "AuditChain",
    "PactAuditAction",
    "TieredAuditDispatcher",
    "create_pact_audit_details",
    # Observation (N5 conformance)
    "InMemoryObservationSink",
    "Observation",
    "ObservationSink",
    # Universal outbound-effect governance interceptor (#1517 leg-b)
    "DEFAULT_MAX_AUDIT_ENTRIES",
    "EffectGovernor",
    "EffectKind",
    "EngineEffectGovernor",
    "OutboundEffect",
    "OutboundEffectInterceptor",
    "OutboundEffectRefused",
    "OutboundVerdict",
    "active_interceptor",
    "clear_interceptor",
    "install_interceptor",
    "wrap_transport",
    "wrap_transport_async",
    # WEFT provenance event schema (EATP v3, #1591)
    "WeftKind",
    "WeftError",
    "UnknownWeftKindError",
    "MissingGateError",
    "WeftEvent",
    "WeftDistributor",
    "read_weft_events",
    # BilateralDelegation + guarantee-tier taxonomy (EATP v3, #1592)
    "SignerKind",
    "GuaranteeTier",
    "PartyAnchor",
    "BilateralDelegation",
    "BilateralDelegationError",
    "AtomicValidityError",
    "CrossRootFederationError",
    "NonRepudiationClaimError",
    "new_bilateral_delegation",
    # ClearanceAttestation -- posture-gated re-identification (EATP v3, #1592)
    "ClearanceAttestation",
    "ClearanceAttestationError",
    "ReidentificationDeniedError",
    "posture_can_reidentify",
    "new_clearance_attestation",
    # VERIFY_CHAIN -- deny-overrides chain composition (EATP v3, #1592)
    "COMPOSITION_MODE",
    "ChainVerdict",
    "ChainLink",
    "ChainResult",
    "VerifyChainError",
    "verify_chain",
    # Store protocols and implementations (Ref-4001, 4002)
    "MAX_STORE_SIZE",
    "AccessPolicyStore",
    "ClearanceStore",
    "EnvelopeStore",
    "MemoryAccessPolicyStore",
    "MemoryClearanceStore",
    "MemoryEnvelopeStore",
    "MemoryOrgStore",
    "OrgStore",
    # Engine (Ref-7010, 7012, 7014, 7015)
    "GovernanceEngine",
    # EATP Emitter (Section 5.7)
    "InMemoryPactEmitter",
    "PactEatpEmitter",
    # Envelope Adapter (Ref-7020)
    "EnvelopeAdapterError",
    "GovernanceEnvelopeAdapter",
    # Verdict (Ref-7010)
    "GovernanceVerdict",
    # Risk-factor calibration seam (extensible disposition)
    "GLOBAL_RISK_FACTOR_REGISTRY",
    "RISK_LEVEL_ORDER",
    "MalformedRiskFactorError",
    "RiskFactor",
    "RiskFactorEvaluation",
    "RiskFactorRegistry",
    "combine_levels",
    "evaluate_risk_factors",
    "register_risk_factor",
    # YAML loader (Ref-7011)
    "ConfigurationError",
    "ClearanceSpec",
    "EnvelopeSpec",
    "BridgeSpec",
    "KspSpec",
    "LoadedOrg",
    "load_org_yaml",
    # Explain/convenience API (Ref-7013)
    "describe_address",
    "explain_access",
    "explain_envelope",
    # Governed agent (Ref-7030)
    "GovernanceBlockedError",
    "GovernanceHeldError",
    "PactGovernedAgent",
    # Governance middleware (Ref-7031)
    "PactGovernanceMiddleware",
    # Governance decorators (Ref-7032, 7033)
    "governed_tool",
]
