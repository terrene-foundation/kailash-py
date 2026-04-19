# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""
PACT -- Governance framework for AI agent organizations.

Architecture:
    kailash.trust.pact     -- D/T/R grammar, addressing, clearance, access, envelopes (core)
    kailash.trust.pact.config -- Platform configuration and agent definitions (core)
    kailash.trust.pact.audit  -- Tamper-evident audit chain (core)
    kailash.trust.pact.gradient -- Verification gradient engine (core)
    pact.governance.api    -- REST API endpoints (kailash-pact)
    pact.governance.cli    -- CLI interface (kailash-pact)
    pact.governance.testing -- Testing utilities (kailash-pact)
    pact.mcp               -- Governance enforcement on MCP tool invocations (kailash-pact)
"""

__version__ = "0.8.2"

# --- Trust types (re-exported from kailash.trust) ---
from kailash.trust import (
    AuditAnchor,
    CapabilityAttestation,
    ConfidentialityLevel,
    TrustPosture,
)

# --- Governance (re-exported from kailash.trust.pact) ---
from kailash.trust.pact import (  # Error hierarchy; Addressing; Compilation; Clearance; Knowledge; Access enforcement; Envelopes; Agent mapping; Governance context; Engine; Envelope adapter; Verdict; YAML loader; Explain/convenience API; Governed agent; Governance middleware; Governance decorators; Audit; Store protocols and implementations
    MAX_STORE_SIZE,
    POSTURE_CEILING,
    AccessDecision,
    AccessPolicyStore,
    Address,
    AddressError,
    AddressSegment,
    AgentRoleMapping,
    BridgeSpec,
    ClearanceSpec,
    ClearanceStore,
    CompilationError,
    CompiledOrg,
    ConfigurationError,
    EnvelopeAdapterError,
    EnvelopeSpec,
    EnvelopeStore,
    GovernanceBlockedError,
    GovernanceContext,
    GovernanceEngine,
    GovernanceEnvelopeAdapter,
    GovernanceHeldError,
    GovernanceVerdict,
    GrammarError,
    KnowledgeItem,
    KnowledgeSharePolicy,
    KspSpec,
    LoadedOrg,
    MemoryAccessPolicyStore,
    MemoryClearanceStore,
    MemoryEnvelopeStore,
    MemoryOrgStore,
    MonotonicTighteningError,
    NodeType,
    OrgNode,
    OrgStore,
    PactAuditAction,
    PactBridge,
    PactError,
    PactGovernanceMiddleware,
    PactGovernedAgent,
    RoleClearance,
    RoleDefinition,
    RoleEnvelope,
    TaskEnvelope,
    VacancyStatus,
    VettingStatus,
    can_access,
    check_degenerate_envelope,
    compile_org,
    compute_effective_envelope,
    create_pact_audit_details,
    default_envelope_for_posture,
    describe_address,
    effective_clearance,
    explain_access,
    explain_envelope,
    governed_tool,
    intersect_envelopes,
    load_org_yaml,
)

# --- Audit chain (re-exported from kailash.trust.pact.audit) ---
from kailash.trust.pact.audit import AuditChain

# --- Config types (re-exported from kailash.trust.pact.config) ---
from kailash.trust.pact.config import (
    CONFIDENTIALITY_ORDER,
    AgentConfig,
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

# --- Gradient engine (re-exported from kailash.trust.pact.gradient) ---
from kailash.trust.pact.gradient import EvaluationResult, GradientEngine
from pact.costs import CostTracker

# --- Enforcement modes ---
from pact.enforcement import EnforcementMode, validate_enforcement_mode

# --- PactEngine (Dual Plane bridge) ---
from pact.engine import PactEngine
from pact.events import EventBus

# --- Testing utilities (stays in kailash-pact) ---
from pact.governance.testing import MockGovernedAgent

# --- MCP governance ---
from pact.mcp import (
    DefaultPolicy,
    GovernanceDecision,
    McpActionContext,
    McpAuditEntry,
    McpAuditTrail,
    McpGovernanceConfig,
    McpGovernanceEnforcer,
    McpGovernanceMiddleware,
    McpInvocationResult,
    McpToolPolicy,
)
from pact.work import WorkResult, WorkSubmission

__all__ = [
    # Error hierarchy
    "PactError",
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
    # Enforcement modes
    "EnforcementMode",
    "validate_enforcement_mode",
    # PactEngine (Dual Plane bridge)
    "PactEngine",
    "WorkResult",
    "WorkSubmission",
    "CostTracker",
    "EventBus",
    # MCP governance
    "DefaultPolicy",
    "GovernanceDecision",
    "McpActionContext",
    "McpAuditEntry",
    "McpAuditTrail",
    "McpGovernanceConfig",
    "McpGovernanceEnforcer",
    "McpGovernanceMiddleware",
    "McpInvocationResult",
    "McpToolPolicy",
]
