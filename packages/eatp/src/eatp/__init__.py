# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Enterprise Agent Trust Protocol (EATP) SDK.

Cryptographic trust chains, delegation, and verification for AI agent systems.
A public good by the Terrene Foundation (Apache 2.0).

EATP provides four core operations:
    - ESTABLISH: Create initial trust for an agent (genesis record + key binding)
    - DELEGATE: Transfer trust from one agent to another with constraints
    - VERIFY: Validate an agent's trust chain and produce a verification verdict
    - AUDIT: Record agent actions in an immutable, hash-linked audit trail

Quick Start::

    from eatp import TrustOperations, TrustKeyManager, CapabilityRequest
    from eatp.chain import AuthorityType, CapabilityType
    from eatp.crypto import generate_keypair
    from eatp.store.memory import InMemoryTrustStore
    from eatp.authority import OrganizationalAuthority, AuthorityPermission

    # 1. Setup
    store = InMemoryTrustStore()
    await store.initialize()
    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)

    # 2. Register authority
    authority = OrganizationalAuthority(
        id="org-acme", name="ACME",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=pub_key, signing_key_id="key-org",
        permissions=[AuthorityPermission.CREATE_AGENTS],
    )

    # 3. Create TrustOperations and use the 4 operations
    ops = TrustOperations(authority_registry=registry, key_manager=key_mgr, trust_store=store)
    chain = await ops.establish(agent_id="agent-001", authority_id="org-acme", capabilities=[...])
    result = await ops.verify(agent_id="agent-001", action="analyze_data")
"""

__version__ = "0.1.0"

# Core types
from eatp.chain import (
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)
from eatp.operations import (
    CapabilityRequest,
    TrustKeyManager,
    TrustOperations,
)

# Reasoning traces
from eatp.reasoning import (
    ConfidentialityLevel,
    EvidenceReference,
    ReasoningTrace,
    reasoning_completeness_score,
)

# Stores
from eatp.store import TrustStore
from eatp.store.memory import InMemoryTrustStore

# Crypto
from eatp.crypto import (
    DualSignature,
    dual_sign,
    dual_verify,
    generate_keypair,
    hmac_sign,
    hmac_verify,
    sign,
    verify_signature,
)

# Authority
from eatp.authority import (
    AuthorityPermission,
    AuthorityRegistryProtocol,
    OrganizationalAuthority,
)

# Postures
from eatp.postures import (
    PostureEvaluationResult,
    PostureEvidence,
    PostureStateMachine,
    TrustPosture,
)

# Budget tracking
from eatp.constraints.budget_tracker import (
    BudgetCheckResult,
    BudgetEvent,
    BudgetSnapshot,
    BudgetTracker,
)
from eatp.constraints.budget_store import SQLiteBudgetStore

# Hooks
from eatp.hooks import (
    EATPHook,
    HookContext,
    HookRegistry,
    HookResult,
    HookType,
)

# Roles
from eatp.roles import (
    ROLE_PERMISSIONS,
    TrustRole,
    check_permission,
    require_permission,
)

# Vocabulary
from eatp.vocabulary import (
    CONSTRAINT_VOCABULARY,
    POSTURE_VOCABULARY,
    constraint_from_eatp,
    constraint_to_eatp,
    posture_from_eatp,
    posture_to_eatp,
)

# Exceptions
from eatp.exceptions import (
    BehavioralScoringError,
    HookError,
    HookTimeoutError,
    KMSConnectionError,
    PathTraversalError,
    ProximityError,
    RevocationError,
    TrustChainNotFoundError,
    TrustError,
)

__all__ = [
    "__version__",
    # Operations
    "TrustOperations",
    "TrustKeyManager",
    "CapabilityRequest",
    "AuthorityRegistryProtocol",
    # Chain types
    "TrustLineageChain",
    "GenesisRecord",
    "DelegationRecord",
    "CapabilityAttestation",
    "ConstraintEnvelope",
    "AuditAnchor",
    "VerificationResult",
    "VerificationLevel",
    "AuthorityType",
    "CapabilityType",
    "ConstraintType",
    # Reasoning traces
    "ConfidentialityLevel",
    "ReasoningTrace",
    "EvidenceReference",
    "reasoning_completeness_score",
    # Stores
    "TrustStore",
    "InMemoryTrustStore",
    # Crypto
    "DualSignature",
    "dual_sign",
    "dual_verify",
    "generate_keypair",
    "hmac_sign",
    "hmac_verify",
    "sign",
    "verify_signature",
    # Authority
    "OrganizationalAuthority",
    "AuthorityPermission",
    # Postures
    "TrustPosture",
    "PostureStateMachine",
    "PostureEvidence",
    "PostureEvaluationResult",
    # Budget tracking
    "BudgetTracker",
    "BudgetSnapshot",
    "BudgetCheckResult",
    "BudgetEvent",
    "SQLiteBudgetStore",
    # Hooks
    "HookType",
    "HookContext",
    "HookResult",
    "EATPHook",
    "HookRegistry",
    # Roles
    "TrustRole",
    "ROLE_PERMISSIONS",
    "check_permission",
    "require_permission",
    # Vocabulary
    "POSTURE_VOCABULARY",
    "CONSTRAINT_VOCABULARY",
    "posture_to_eatp",
    "posture_from_eatp",
    "constraint_to_eatp",
    "constraint_from_eatp",
    # Exceptions
    "TrustError",
    "TrustChainNotFoundError",
    "HookError",
    "HookTimeoutError",
    "ProximityError",
    "BehavioralScoringError",
    "KMSConnectionError",
    "RevocationError",
    "PathTraversalError",
]
