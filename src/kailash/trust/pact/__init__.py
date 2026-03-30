# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""PACT governance layer -- D/T/R grammar, addressing, clearance, access enforcement, envelopes."""

from kailash.trust.pact.exceptions import PactError
from kailash.trust.pact.addressing import (
    Address,
    AddressError,
    AddressSegment,
    GrammarError,
    NodeType,
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
from kailash.trust.pact.access import (
    AccessDecision,
    KnowledgeSharePolicy,
    PactBridge,
    can_access,
)
from kailash.trust.pact.clearance import (
    POSTURE_CEILING,
    RoleClearance,
    VettingStatus,
    effective_clearance,
)
from kailash.trust.pact.envelopes import (
    MonotonicTighteningError,
    RoleEnvelope,
    TaskEnvelope,
    check_degenerate_envelope,
    compute_effective_envelope,
    default_envelope_for_posture,
    intersect_envelopes,
)
from kailash.trust.pact.agent import (
    GovernanceBlockedError,
    GovernanceHeldError,
    PactGovernedAgent,
)
from kailash.trust.pact.agent_mapping import AgentRoleMapping
from kailash.trust.pact.context import GovernanceContext
from kailash.trust.pact.decorators import governed_tool
from kailash.trust.pact.middleware import PactGovernanceMiddleware
from kailash.trust.pact.knowledge import KnowledgeItem
from kailash.trust.pact.audit import (
    PactAuditAction,
    create_pact_audit_details,
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
from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.envelope_adapter import (
    EnvelopeAdapterError,
    GovernanceEnvelopeAdapter,
)
from kailash.trust.pact.explain import (
    describe_address,
    explain_access,
    explain_envelope,
)
from kailash.trust.pact.verdict import GovernanceVerdict
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
    # Addressing (Ref-1001)
    "Address",
    "AddressError",
    "AddressSegment",
    "GrammarError",
    "NodeType",
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
    "compute_effective_envelope",
    "default_envelope_for_posture",
    "intersect_envelopes",
    # Audit (Ref-4003)
    "PactAuditAction",
    "create_pact_audit_details",
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
    # Envelope Adapter (Ref-7020)
    "EnvelopeAdapterError",
    "GovernanceEnvelopeAdapter",
    # Verdict (Ref-7010)
    "GovernanceVerdict",
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
