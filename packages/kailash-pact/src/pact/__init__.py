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

__version__ = "0.4.1"

# --- Governance (re-exported from kailash.trust.pact) ---
from kailash.trust.pact import (
    # Error hierarchy
    PactError,
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

# --- Config types (re-exported from kailash.trust.pact.config) ---
from kailash.trust.pact.config import (
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

# --- Audit chain (re-exported from kailash.trust.pact.audit) ---
from kailash.trust.pact.audit import AuditChain

# --- Gradient engine (re-exported from kailash.trust.pact.gradient) ---
from kailash.trust.pact.gradient import EvaluationResult, GradientEngine

# --- Testing utilities (stays in kailash-pact) ---
from pact.governance.testing import MockGovernedAgent

# --- PactEngine (Dual Plane bridge) ---
from pact.engine import PactEngine
from pact.work import WorkResult, WorkSubmission
from pact.costs import CostTracker
from pact.events import EventBus

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
