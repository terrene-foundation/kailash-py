# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""
PACT — Governance framework for AI agent organizations.

Architecture:
    pact.governance        — D/T/R grammar, addressing, clearance, access, envelopes
    pact.governance.config — Platform configuration and agent definitions
    pact.governance.audit  — Tamper-evident audit chain
    pact.governance.gradient — Verification gradient engine
"""

__version__ = "0.2.0"

# --- Governance ---
from pact.governance import (
    # Addressing
    Address,
    AddressError,
    AddressSegment,
    GrammarError,
    NodeType,
    # Compilation
    CompilationError,
    CompiledOrg,
    OrgNode,
    RoleDefinition,
    VacancyStatus,
    compile_org,
    # Clearance
    POSTURE_CEILING,
    RoleClearance,
    VettingStatus,
    effective_clearance,
    # Knowledge
    KnowledgeItem,
    # Access enforcement
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
    # Envelopes
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
    check_degenerate_envelope,
    compute_effective_envelope,
    default_envelope_for_posture,
    intersect_envelopes,
    # Agent mapping
    AgentRoleMapping,
    # Governance context
    GovernanceContext,
    # Engine
    GovernanceEngine,
    # Envelope adapter
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
    # Verdict
    GovernanceVerdict,
    # YAML loader
    ConfigurationError,
    ClearanceSpec,
    EnvelopeSpec,
    BridgeSpec,
    KspSpec,
    LoadedOrg,
    load_org_yaml,
    # Explain/convenience API
    describe_address,
    explain_access,
    explain_envelope,
    # Governed agent
    GovernanceBlockedError,
    GovernanceHeldError,
    PactGovernedAgent,
    # Governance middleware
    PactGovernanceMiddleware,
    # Governance decorators
    governed_tool,
    # Testing utilities
    MockGovernedAgent,
    # Audit
    PactAuditAction,
    create_pact_audit_details,
    # Store protocols and implementations
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

# --- Config types ---
from pact.governance.config import (
    AgentConfig,
    CONFIDENTIALITY_ORDER,
    CommunicationConstraintConfig,
    ConstraintDimension,
    ConstraintEnvelopeConfig,
    DataAccessConstraintConfig,
    DepartmentConfig,
    FinancialConstraintConfig,
    GenesisConfig,
    GradientRuleConfig,
    OperationalConstraintConfig,
    OrgDefinition,
    PactConfig,
    PlatformConfig,
    TeamConfig,
    TemporalConstraintConfig,
    TrustPostureLevel,
    VerificationGradientConfig,
    VerificationLevel,
    WorkspaceConfig,
)

# --- Trust types (re-exported from kailash.trust) ---
from kailash.trust import (
    AuditAnchor,
    CapabilityAttestation,
    ConfidentialityLevel,
    TrustPosture,
)

# --- Audit chain ---
from pact.governance.audit import AuditChain

# --- Gradient engine ---
from pact.governance.gradient import EvaluationResult, GradientEngine

__all__ = [
    # Addressing
    "Address",
    "AddressError",
    "AddressSegment",
    "GrammarError",
    "NodeType",
    # Compilation
    "CompilationError",
    "CompiledOrg",
    "OrgNode",
    "RoleDefinition",
    "VacancyStatus",
    "compile_org",
    # Clearance
    "POSTURE_CEILING",
    "RoleClearance",
    "VettingStatus",
    "effective_clearance",
    # Knowledge
    "KnowledgeItem",
    # Access enforcement
    "AccessDecision",
    "KnowledgeSharePolicy",
    "PactBridge",
    "can_access",
    # Agent mapping
    "AgentRoleMapping",
    # Governance context
    "GovernanceContext",
    # Envelopes
    "MonotonicTighteningError",
    "RoleEnvelope",
    "TaskEnvelope",
    "check_degenerate_envelope",
    "compute_effective_envelope",
    "default_envelope_for_posture",
    "intersect_envelopes",
    # Audit
    "AuditAnchor",
    "AuditChain",
    "PactAuditAction",
    "create_pact_audit_details",
    # Store protocols and implementations
    "MAX_STORE_SIZE",
    "AccessPolicyStore",
    "ClearanceStore",
    "EnvelopeStore",
    "MemoryAccessPolicyStore",
    "MemoryClearanceStore",
    "MemoryEnvelopeStore",
    "MemoryOrgStore",
    "OrgStore",
    # Engine
    "GovernanceEngine",
    # Envelope adapter
    "EnvelopeAdapterError",
    "GovernanceEnvelopeAdapter",
    # Verdict
    "GovernanceVerdict",
    # YAML loader
    "ConfigurationError",
    "ClearanceSpec",
    "EnvelopeSpec",
    "BridgeSpec",
    "KspSpec",
    "LoadedOrg",
    "load_org_yaml",
    # Explain/convenience API
    "describe_address",
    "explain_access",
    "explain_envelope",
    # Governed agent
    "GovernanceBlockedError",
    "GovernanceHeldError",
    "PactGovernedAgent",
    # Governance middleware
    "PactGovernanceMiddleware",
    # Governance decorators
    "governed_tool",
    # Testing utilities
    "MockGovernedAgent",
    # Config types
    "AgentConfig",
    "CONFIDENTIALITY_ORDER",
    "CommunicationConstraintConfig",
    "ConstraintDimension",
    "ConstraintEnvelopeConfig",
    "DataAccessConstraintConfig",
    "DepartmentConfig",
    "FinancialConstraintConfig",
    "GenesisConfig",
    "GradientRuleConfig",
    "OperationalConstraintConfig",
    "OrgDefinition",
    "PactConfig",
    "PlatformConfig",
    "TeamConfig",
    "TemporalConstraintConfig",
    "TrustPostureLevel",
    "VerificationGradientConfig",
    "VerificationLevel",
    "WorkspaceConfig",
    # Trust types (re-exported from kailash.trust)
    "AuditAnchor",
    "CapabilityAttestation",
    "ConfidentialityLevel",
    "TrustPosture",
    # Gradient engine
    "EvaluationResult",
    "GradientEngine",
]
