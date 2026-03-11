"""
Kaizen Trust Module - Enterprise Agent Trust Protocol (EATP) Implementation.

This module provides cryptographically verifiable trust chains for AI agents,
enabling enterprise-grade accountability and authorization.

Key Components:
- TrustLineageChain: Complete trust chain for an agent
- PostgresTrustStore: Persistent storage for trust chains
- OrganizationalAuthorityRegistry: Authority lifecycle management
- TrustOperations: ESTABLISH, DELEGATE, VERIFY, AUDIT operations
- TrustedAgent: BaseAgent with trust capabilities (Phase 1 Week 4)
- AgentRegistry: Central registry for agent discovery (Phase 2 Week 5)
- AgentHealthMonitor: Background health monitoring for agents (Phase 2 Week 5)
- SecureChannel: End-to-end encrypted messaging between agents (Phase 2 Week 6)
- MessageVerifier: Multi-step verification of incoming messages (Phase 2 Week 6)
- InMemoryReplayProtection: Replay attack prevention (Phase 2 Week 6)
- TrustExecutionContext: Trust state propagation through workflows (Phase 2 Week 7)
- TrustPolicyEngine: Policy-based trust evaluation (Phase 2 Week 7)
- TrustAwareOrchestrationRuntime: Trust-aware workflow execution (Phase 2 Week 7)
- EnterpriseSystemAgent: Proxy agents for legacy systems (Phase 3 Week 10)

Example:
    from kaizen.trust import (
        TrustOperations,
        PostgresTrustStore,
        OrganizationalAuthorityRegistry,
        TrustKeyManager,
        CapabilityRequest,
        CapabilityType,
    )

    # Initialize components
    store = PostgresTrustStore()
    registry = OrganizationalAuthorityRegistry()
    key_manager = TrustKeyManager()
    trust_ops = TrustOperations(registry, key_manager, store)
    await trust_ops.initialize()

    # Establish trust for an agent
    chain = await trust_ops.establish(
        agent_id="agent-001",
        authority_id="org-acme",
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACCESS,
            )
        ],
    )

    # Verify trust before action
    result = await trust_ops.verify(
        agent_id="agent-001",
        action="analyze_data",
    )

    if result.valid:
        # Proceed with action
        pass
"""

# Phase 3 Week 9: A2A HTTP Service
from kaizen.trust.a2a import (
    A2AAuthenticator,
    A2AError,
    A2AMethodHandlers,
    A2AService,
    A2AServiceError,
    A2AToken,
    AgentCapability,
    AgentCard,
    AgentCardCache,
    AgentCardError,
    AgentCardGenerator,
    AuditQueryRequest,
    AuditQueryResponse,
)
from kaizen.trust.a2a import AuthenticationError as A2AAuthenticationError
from kaizen.trust.a2a import AuthorizationError as A2AAuthorizationError
from kaizen.trust.a2a import DelegationError as A2ADelegationError
from kaizen.trust.a2a import (
    DelegationRequest,
    DelegationResponse,
    InvalidTokenError,
    JsonRpcHandler,
    JsonRpcInternalError,
    JsonRpcInvalidParamsError,
    JsonRpcInvalidRequestError,
    JsonRpcMethodNotFoundError,
    JsonRpcParseError,
    JsonRpcRequest,
    JsonRpcResponse,
    TokenExpiredError,
    TrustExtensions,
)
from kaizen.trust.a2a import (
    TrustVerificationError as A2ATrustVerificationError,  # Service; Agent Card; JSON-RPC; Authentication; Request/Response Models; Exceptions
)
from kaizen.trust.a2a import (
    VerificationRequest,
    VerificationResponse,
    create_a2a_app,
    extract_token_from_header,
)
from kaizen.trust.audit_service import (
    ActionSummary,
    AgentAuditSummary,
    AuditQueryService,
    ComplianceReport,
)
from kaizen.trust.audit_store import (
    AppendOnlyAuditStore,
    AuditAnchorNotFoundError,
    AuditRecord,
    AuditStore,
    AuditStoreError,
    AuditStoreImmutabilityError,
    IntegrityVerificationResult,
    PostgresAuditStore,
)
from kaizen.trust.authority import (
    AuthorityPermission,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
)

# Phase 3 Week 11: Trust Chain Caching
from kaizen.trust.cache import CacheEntry, CacheStats, TrustChainCache
from kaizen.trust.chain import (
    ActionResult,
    AuditAnchor,
    AuthorityType,
    CapabilityAttestation,
    CapabilityType,
    Constraint,
    ConstraintEnvelope,
    ConstraintType,
    DelegationRecord,
    GenesisRecord,
    TrustLineageChain,
    VerificationLevel,
    VerificationResult,
)

# CARE-028: Posture Circuit Breaker
from kaizen.trust.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    FailureEvent,
    PostureCircuitBreaker,
)
from kaizen.trust.constraint_validator import (
    ConstraintValidator,
    ConstraintViolation,
    DelegationConstraintValidator,
    ValidationResult,
)

# CARE-013: Certificate Revocation List (CRL)
from kaizen.trust.crl import (
    CertificateRevocationList,
    CRLEntry,
    CRLMetadata,
    CRLVerificationResult,
    verify_delegation_with_crl,
)
from kaizen.trust.crypto import (
    generate_keypair,
    hash_chain,
    serialize_for_signing,
    sign,
    verify_signature,
)

# Phase 3 Week 10: Enterprise System Agent (ESA)
from kaizen.trust.esa import (  # Base ESA; ESA Exceptions
    CapabilityMetadata,
    EnterpriseSystemAgent,
    ESAAuthorizationError,
    ESACapabilityNotFoundError,
    ESAConfig,
    ESAConnectionError,
    ESADelegationError,
    ESAError,
    ESANotEstablishedError,
    ESAOperationError,
    OperationRequest,
    OperationResult,
    SystemConnectionInfo,
    SystemMetadata,
)
from kaizen.trust.exceptions import (
    AgentAlreadyEstablishedError,
    AuthorityInactiveError,
    AuthorityNotFoundError,
    CapabilityNotFoundError,
    ConstraintViolationError,
    DelegationError,
    DelegationExpiredError,
    InvalidSignatureError,
    InvalidTrustChainError,
    TrustChainInvalidError,
    TrustChainNotFoundError,
    TrustError,
    TrustStoreDatabaseError,
    TrustStoreError,
    VerificationFailedError,
)

# EATP v0.8.0 - Enterprise Agent Trust Protocol
from kaizen.trust.execution_context import (
    ExecutionContext,
    HumanOrigin,
    execution_context,
    get_current_context,
    get_delegation_chain,
    get_human_origin,
    get_trace_id,
    require_current_context,
    set_current_context,
)

# CARE-005: HSM/KMS Integration
from kaizen.trust.key_manager import (
    AWSKMSKeyManager,
    InMemoryKeyManager,
    KeyManagerError,
    KeyManagerInterface,
    KeyMetadata,
)

# CARE-038: Trust Knowledge Bridge
# CARE-037: Provenance Schema
# CARE-036: Knowledge Entry Structures
from kaizen.trust.knowledge import (
    InMemoryKnowledgeStore,
    InMemoryProvenanceStore,
    KnowledgeEntry,
    KnowledgeType,
    ProvenanceChain,
    ProvenanceRecord,
    ProvRelation,
    TrustKnowledgeBridge,
)

# CARE-012: Merkle Tree Audit Verification
from kaizen.trust.merkle import (
    MerkleNode,
    MerkleProof,
    MerkleTree,
    compute_merkle_root,
    get_proof_length,
    verify_merkle_proof,
)

# Week 6: Secure Communication
from kaizen.trust.messaging import (  # Envelope; Signer; Verifier; Replay Protection; Channel; Exceptions
    ChannelError,
    ChannelStatistics,
    InMemoryReplayProtection,
    MessageExpiredError,
    MessageMetadata,
    MessageSigner,
    MessageVerificationResult,
    MessageVerifier,
    MessagingError,
    PublicKeyNotFoundError,
    ReplayDetectedError,
    ReplayProtection,
    SecureChannel,
    SecureMessageEnvelope,
    SigningError,
    VerificationError,
)

# CARE-030: Trust Metrics Collection
from kaizen.trust.metrics import (
    POSTURE_LEVEL_MAP,
    ConstraintMetrics,
    PostureMetrics,
    TrustMetricsCollector,
)

# CARE-011: Multi-Signature Genesis Records
from kaizen.trust.multi_sig import (
    DuplicateSignatureError,
    InsufficientSignaturesError,
    MultiSigError,
    MultiSigManager,
    MultiSigPolicy,
    OperationNotFoundError,
    PendingMultiSig,
    SigningOperationExpiredError,
    UnauthorizedSignerError,
    create_genesis_payload,
    verify_multi_sig,
)
from kaizen.trust.operations import (
    CapabilityRequest,
    ConstraintEvaluationResult,
    TrustKeyManager,
    TrustOperations,
)

# Week 7: Orchestration Integration
from kaizen.trust.orchestration import (  # Execution Context; Policy; Runtime; Exceptions
    ConstraintLooseningError,
    ContextMergeStrategy,
    ContextPropagationError,
    DelegationChainError,
    DelegationEntry,
    OrchestrationTrustError,
    PolicyResult,
    PolicyType,
    PolicyViolationError,
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
    TrustExecutionContext,
    TrustPolicy,
    TrustPolicyEngine,
    TrustVerificationFailedError,
)

# CARE-029: Posture-Aware Agent
from kaizen.trust.posture_agent import (
    ApprovalHandler,
    AuditEntry,
    CircuitBreaker,
    NotificationHandler,
    PostureAwareAgent,
)
from kaizen.trust.pseudo_agent import (
    AuthProvider,
    PseudoAgent,
    PseudoAgentConfig,
    PseudoAgentFactory,
    create_pseudo_agent_for_testing,
)

# Week 5: Agent Discovery & Registration
from kaizen.trust.registry import (
    AgentAlreadyRegisteredError,
    AgentHealthMonitor,
    AgentMetadata,
)
from kaizen.trust.registry import AgentNotFoundError as RegistryAgentNotFoundError
from kaizen.trust.registry import (
    AgentRegistry,
    AgentRegistryStore,
    AgentStatus,
    DiscoveryQuery,
    HealthStatus,
    PostgresAgentRegistryStore,
    RegistrationRequest,
    RegistryError,
    TrustVerificationError,
)
from kaizen.trust.registry import ValidationError as RegistryValidationError

# CARE-007: Revocation Event Broadcasting
from kaizen.trust.revocation import (
    CascadeRevocationManager,
    DeadLetterEntry,
    DelegationRegistry,
    InMemoryDelegationRegistry,
    InMemoryRevocationBroadcaster,
    RevocationBroadcaster,
    RevocationEvent,
    RevocationType,
    TrustRevocationList,
)

# Phase 3 Week 11: Credential Rotation
from kaizen.trust.rotation import (
    CredentialRotationManager,
    RotationError,
    RotationResult,
    RotationStatus,
    RotationStatusInfo,
    ScheduledRotation,
)

# Phase 3 Week 11: Security Hardening
from kaizen.trust.security import (  # Validators; Key Storage; Rate Limiting; Audit Logging; Security Exceptions
    EncryptionError,
    RateLimitExceededError,
    SecureKeyStorage,
    SecurityAuditLogger,
    SecurityError,
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
    TrustRateLimiter,
    TrustSecurityValidator,
    ValidationError,
)
from kaizen.trust.store import (
    InMemoryTrustStore,
    PostgresTrustStore,
    TransactionContext,
)

# EATP Reasoning Trace Extension
from kaizen.trust.reasoning import ConfidentialityLevel, ReasoningTrace

# CARE-014: External Timestamp Anchoring
from kaizen.trust.timestamping import (
    LocalTimestampAuthority,
    RFC3161TimestampAuthority,
    TimestampAnchorManager,
    TimestampAuthority,
    TimestampRequest,
    TimestampResponse,
    TimestampSource,
    TimestampToken,
    verify_timestamp_token,
)
from kaizen.trust.trusted_agent import (
    TrustContext,
    TrustContextManager,
    TrustedAgent,
    TrustedAgentConfig,
    TrustedSupervisorAgent,
)

__all__ = [
    # Enums
    "AuthorityType",
    "CapabilityType",
    "ActionResult",
    "ConstraintType",
    "VerificationLevel",
    "AuthorityPermission",
    # Data structures
    "GenesisRecord",
    "CapabilityAttestation",
    "DelegationRecord",
    "Constraint",
    "ConstraintEnvelope",
    "AuditAnchor",
    "TrustLineageChain",
    "VerificationResult",
    "CapabilityRequest",
    "ConstraintEvaluationResult",
    # Authority
    "OrganizationalAuthority",
    "OrganizationalAuthorityRegistry",
    # Operations
    "TrustOperations",
    "TrustKeyManager",
    # Store
    "InMemoryTrustStore",
    "PostgresTrustStore",
    "TransactionContext",
    # Audit Store (Week 3)
    "AuditStore",
    "PostgresAuditStore",
    # CARE-010: Append-Only Audit Constraints
    "AppendOnlyAuditStore",
    "AuditRecord",
    "IntegrityVerificationResult",
    # Audit Service (Week 3)
    "AuditQueryService",
    "ComplianceReport",
    "AgentAuditSummary",
    "ActionSummary",
    # Exceptions
    "TrustError",
    "TrustStoreError",
    "AuthorityNotFoundError",
    "AuthorityInactiveError",
    "TrustChainNotFoundError",
    "TrustChainInvalidError",
    "TrustStoreDatabaseError",
    "InvalidTrustChainError",
    "CapabilityNotFoundError",
    "ConstraintViolationError",
    "DelegationError",
    "InvalidSignatureError",
    "VerificationFailedError",
    "AgentAlreadyEstablishedError",
    "DelegationExpiredError",
    "AuditStoreError",
    "AuditAnchorNotFoundError",
    "AuditStoreImmutabilityError",
    # Crypto
    "generate_keypair",
    "sign",
    "verify_signature",
    "serialize_for_signing",
    "hash_chain",
    # TrustedAgent (Week 4)
    "TrustedAgent",
    "TrustedAgentConfig",
    "TrustedSupervisorAgent",
    "TrustContext",
    "TrustContextManager",
    # Agent Registry (Week 5)
    "AgentMetadata",
    "AgentStatus",
    "RegistrationRequest",
    "AgentRegistryStore",
    "PostgresAgentRegistryStore",
    "AgentRegistry",
    "DiscoveryQuery",
    "AgentHealthMonitor",
    "HealthStatus",
    "RegistryError",
    "RegistryAgentNotFoundError",
    "AgentAlreadyRegisteredError",
    "RegistryValidationError",
    "TrustVerificationError",
    # Secure Messaging (Week 6)
    "SecureMessageEnvelope",
    "MessageMetadata",
    "MessageSigner",
    "MessageVerifier",
    "MessageVerificationResult",
    "ReplayProtection",
    "InMemoryReplayProtection",
    "SecureChannel",
    "ChannelStatistics",
    "MessagingError",
    "SigningError",
    "VerificationError",
    "ReplayDetectedError",
    "MessageExpiredError",
    "PublicKeyNotFoundError",
    "ChannelError",
    # Orchestration Integration (Week 7)
    "TrustExecutionContext",
    "DelegationEntry",
    "ContextMergeStrategy",
    "TrustPolicy",
    "PolicyType",
    "PolicyResult",
    "TrustPolicyEngine",
    "TrustAwareOrchestrationRuntime",
    "TrustAwareRuntimeConfig",
    "OrchestrationTrustError",
    "TrustVerificationFailedError",
    "PolicyViolationError",
    "ConstraintLooseningError",
    "DelegationChainError",
    "ContextPropagationError",
    # A2A HTTP Service (Phase 3 Week 9)
    "A2AService",
    "create_a2a_app",
    "AgentCardGenerator",
    "AgentCardCache",
    "AgentCard",
    "AgentCapability",
    "TrustExtensions",
    "JsonRpcHandler",
    "A2AMethodHandlers",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "A2AAuthenticator",
    "extract_token_from_header",
    "A2AToken",
    "VerificationRequest",
    "VerificationResponse",
    "DelegationRequest",
    "DelegationResponse",
    "AuditQueryRequest",
    "AuditQueryResponse",
    "A2AError",
    "A2AServiceError",
    "JsonRpcParseError",
    "JsonRpcInvalidRequestError",
    "JsonRpcMethodNotFoundError",
    "JsonRpcInvalidParamsError",
    "JsonRpcInternalError",
    "A2ATrustVerificationError",
    "A2AAuthenticationError",
    "A2AAuthorizationError",
    "A2ADelegationError",
    "AgentCardError",
    "TokenExpiredError",
    "InvalidTokenError",
    # Enterprise System Agent (ESA) - Phase 3 Week 10
    "EnterpriseSystemAgent",
    "SystemMetadata",
    "SystemConnectionInfo",
    "CapabilityMetadata",
    "OperationRequest",
    "OperationResult",
    "ESAConfig",
    "ESAError",
    "ESANotEstablishedError",
    "ESACapabilityNotFoundError",
    "ESAOperationError",
    "ESAConnectionError",
    "ESAAuthorizationError",
    "ESADelegationError",
    # Trust Chain Caching - Phase 3 Week 11
    "TrustChainCache",
    "CacheStats",
    "CacheEntry",
    # Credential Rotation - Phase 3 Week 11
    "CredentialRotationManager",
    "RotationResult",
    "RotationStatusInfo",
    "RotationStatus",
    "RotationError",
    "ScheduledRotation",
    # Security Hardening - Phase 3 Week 11
    "TrustSecurityValidator",
    "SecureKeyStorage",
    "TrustRateLimiter",
    "SecurityAuditLogger",
    "SecurityEvent",
    "SecurityEventType",
    "SecurityEventSeverity",
    "SecurityError",
    "ValidationError",
    "EncryptionError",
    "RateLimitExceededError",
    # EATP v0.8.0 - Enterprise Agent Trust Protocol
    # Execution Context
    "HumanOrigin",
    "ExecutionContext",
    "get_current_context",
    "set_current_context",
    "require_current_context",
    "execution_context",
    "get_human_origin",
    "get_delegation_chain",
    "get_trace_id",
    # PseudoAgent
    "AuthProvider",
    "PseudoAgent",
    "PseudoAgentConfig",
    "PseudoAgentFactory",
    "create_pseudo_agent_for_testing",
    # Constraint Validation
    "ConstraintValidator",
    "ConstraintViolation",
    "ValidationResult",
    "DelegationConstraintValidator",
    # Posture Circuit Breaker - CARE-028
    "CircuitState",
    "FailureEvent",
    "CircuitBreakerConfig",
    "PostureCircuitBreaker",
    # Trust Metrics Collection - CARE-030
    "TrustMetricsCollector",
    "PostureMetrics",
    "ConstraintMetrics",
    "POSTURE_LEVEL_MAP",
    # Posture-Aware Agent - CARE-029
    "PostureAwareAgent",
    "ApprovalHandler",
    "NotificationHandler",
    "CircuitBreaker",
    "AuditEntry",
    # Key Management - CARE-005
    "KeyManagerInterface",
    "InMemoryKeyManager",
    "AWSKMSKeyManager",
    "KeyMetadata",
    "KeyManagerError",
    # Revocation Broadcasting - CARE-007
    "RevocationType",
    "RevocationEvent",
    "RevocationBroadcaster",
    "InMemoryRevocationBroadcaster",
    "DelegationRegistry",
    "InMemoryDelegationRegistry",
    "CascadeRevocationManager",
    "TrustRevocationList",
    "DeadLetterEntry",
    # Multi-Signature Genesis Records - CARE-011
    "MultiSigPolicy",
    "PendingMultiSig",
    "MultiSigManager",
    "MultiSigError",
    "InsufficientSignaturesError",
    "SigningOperationExpiredError",
    "UnauthorizedSignerError",
    "DuplicateSignatureError",
    "OperationNotFoundError",
    "verify_multi_sig",
    "create_genesis_payload",
    # Merkle Tree Audit Verification - CARE-012
    "MerkleNode",
    "MerkleProof",
    "MerkleTree",
    "compute_merkle_root",
    "get_proof_length",
    "verify_merkle_proof",
    # Certificate Revocation List - CARE-013
    "CertificateRevocationList",
    "CRLEntry",
    "CRLMetadata",
    "CRLVerificationResult",
    "verify_delegation_with_crl",
    # External Timestamp Anchoring - CARE-014
    "TimestampSource",
    "TimestampToken",
    "TimestampRequest",
    "TimestampResponse",
    "TimestampAuthority",
    "LocalTimestampAuthority",
    "RFC3161TimestampAuthority",
    "TimestampAnchorManager",
    "verify_timestamp_token",
    # Knowledge Entry Structures - CARE-036
    "KnowledgeType",
    "KnowledgeEntry",
    # Provenance Schema - CARE-037
    "ProvRelation",
    "ProvenanceRecord",
    "ProvenanceChain",
    "InMemoryProvenanceStore",
    # Trust Knowledge Bridge - CARE-038
    "InMemoryKnowledgeStore",
    "TrustKnowledgeBridge",
    # Reasoning Trace Extension
    "ConfidentialityLevel",
    "ReasoningTrace",
]
