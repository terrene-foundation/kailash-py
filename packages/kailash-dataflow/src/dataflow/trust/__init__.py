"""DataFlow Trust Module (CARE-019, CARE-020).

Provides trust-aware query execution for DataFlow, integrating with the
Enterprise Agent Trust Protocol (EATP) for fine-grained access control
and cryptographically signed audit records for tamper evidence.

Key Components:
    CARE-019 (Query Wrapper):
    - ConstraintEnvelopeWrapper: Translates EATP constraints to SQL filter components
    - TrustAwareQueryExecutor: Wraps DataFlow queries with trust verification
    - QueryAccessResult: Result of constraint application
    - QueryExecutionResult: Result of trust-aware query execution

    CARE-020 (Signed Audit):
    - SignedAuditRecord: Cryptographically signed audit record
    - DataFlowAuditStore: Storage and verification for audit records

    CARE-021 (Multi-Tenancy): REMOVED on 2026-04-27 (W6-006, finding F-B-05).
    `TenantTrustManager` and `CrossTenantDelegation` were exposed publicly
    but no framework hot path invoked them — orphan-detection MUST 1+3.
    Per `rules/orphan-detection.md` § 3 ("Removed = Deleted, Not Deprecated"),
    the classes have been deleted entirely. When a production cross-tenant
    delegation requirement lands, design the new surface against the
    framework's hot path (express, query engine) in the SAME PR — do not
    resurrect the orphan from git history without a real call site.

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

Version:
    CARE-019: Added in v0.11.0
    CARE-020: Added in v0.11.0
    CARE-021: Removed in v2.0.13 (orphan-detection §3 sweep, W6-006).
"""

from dataflow.trust.audit import DataFlowAuditStore, SignedAuditRecord
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
]
