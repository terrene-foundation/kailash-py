"""DataFlow Trust Module (CARE-019, CARE-020, CARE-021).

Provides trust-aware query execution for DataFlow, integrating with the
Enterprise Agent Trust Protocol (EATP) for fine-grained access control,
cryptographically signed audit records for tamper evidence, and
cross-tenant data access with explicit delegation chains.

Key Components:
    CARE-019 (Query Wrapper):
    - ConstraintEnvelopeWrapper: Translates EATP constraints to SQL filter components
    - TrustAwareQueryExecutor: Wraps DataFlow queries with trust verification
    - QueryAccessResult: Result of constraint application
    - QueryExecutionResult: Result of trust-aware query execution

    CARE-020 (Signed Audit):
    - SignedAuditRecord: Cryptographically signed audit record
    - DataFlowAuditStore: Storage and verification for audit records

    CARE-021 (Multi-Tenancy):
    - CrossTenantDelegation: Represents a delegation record between tenants
    - TenantTrustManager: Manages cross-tenant delegations and verification

Usage:
    from dataflow.trust import (
        # CARE-019: Query wrapper
        TrustAwareQueryExecutor,
        ConstraintEnvelopeWrapper,
        QueryAccessResult,
        QueryExecutionResult,
        # CARE-020: Signed audit
        SignedAuditRecord,
        DataFlowAuditStore,
        # CARE-021: Multi-tenancy
        CrossTenantDelegation,
        TenantTrustManager,
    )

    # Create executor (optional Kaizen/Core SDK dependencies)
    executor = TrustAwareQueryExecutor(
        dataflow_instance=db,
        enforcement_mode="enforcing",
    )

    # Execute trust-aware read
    result = await executor.execute_read(
        model_name="User",
        filter={"department": "finance"},
        agent_id="agent-001",
    )

    # Create audit store with signing keys (CARE-020)
    store = DataFlowAuditStore(
        signing_key=private_key_bytes,
        verify_key=public_key_bytes,
    )

    # Record and verify audit records
    record = store.record_query(
        agent_id="agent-001",
        model="User",
        operation="SELECT",
        row_count=10,
    )
    is_valid = store.verify_record(record)

    # Create cross-tenant delegation (CARE-021)
    manager = TenantTrustManager(strict_mode=True)
    delegation = await manager.create_cross_tenant_delegation(
        source_tenant_id="tenant-a",
        target_tenant_id="tenant-b",
        delegating_agent_id="agent-a",
        receiving_agent_id="agent-b",
        allowed_models=["User"],
    )

Features:
    - Standalone operation (no hard Kaizen dependency)
    - Graceful degradation when trust modules not available
    - Three enforcement modes: disabled, permissive, enforcing
    - PII column detection and filtering
    - Time window constraint translation
    - Data scope filtering
    - Row limit enforcement
    - Audit trail integration
    - Ed25519 cryptographic signatures (CARE-020)
    - SHA-256 hash chain for tamper detection (CARE-020)
    - Cross-tenant delegation management (CARE-021)
    - Trust-aware multi-tenancy with explicit EATP delegation chains (CARE-021)

Version:
    CARE-019: Added in v0.11.0
    CARE-020: Added in v0.11.0
    CARE-021: Added in v0.11.0
"""

from dataflow.trust.audit import DataFlowAuditStore, SignedAuditRecord
from dataflow.trust.multi_tenant import CrossTenantDelegation, TenantTrustManager
from dataflow.trust.query_wrapper import (
    ConstraintEnvelopeWrapper,
    QueryAccessResult,
    QueryExecutionResult,
    TrustAwareQueryExecutor,
)

__all__ = [
    # CARE-019: Query wrapper
    "ConstraintEnvelopeWrapper",
    "QueryAccessResult",
    "QueryExecutionResult",
    "TrustAwareQueryExecutor",
    # CARE-020: Signed audit
    "DataFlowAuditStore",
    "SignedAuditRecord",
    # CARE-021: Multi-tenancy
    "CrossTenantDelegation",
    "TenantTrustManager",
]
