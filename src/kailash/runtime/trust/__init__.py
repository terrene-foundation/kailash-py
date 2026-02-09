"""Trust context module for Kailash runtime (CARE-015, CARE-016, CARE-018).

This module provides RuntimeTrustContext for propagating trust information
through workflow execution, TrustVerifier for bridging to Kaizen
TrustOperations, and RuntimeAuditGenerator for EATP-compliant audit trails:
- Human origin tracking across agent delegation
- Constraint propagation and tightening
- Audit trail for compliance
- Bridge to Kaizen execution context
- Trust verification for workflows, nodes, and resources
- EATP-compliant audit generation

Usage:
    from kailash.runtime.trust import (
        RuntimeTrustContext,
        TrustVerificationMode,
        get_runtime_trust_context,
        set_runtime_trust_context,
        runtime_trust_context,
        TrustVerifier,
        TrustVerifierConfig,
        VerificationResult,
        MockTrustVerifier,
        AuditEventType,
        AuditEvent,
        RuntimeAuditGenerator,
    )

    # Create and use trust context
    ctx = RuntimeTrustContext(
        trace_id="trace-123",
        verification_mode=TrustVerificationMode.ENFORCING,
    )

    with runtime_trust_context(ctx):
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow)

    # Use trust verifier
    verifier = TrustVerifier(
        config=TrustVerifierConfig(mode="enforcing"),
    )
    result = await verifier.verify_workflow_access(
        workflow_id="my-workflow",
        agent_id="agent-123",
    )

    # Use audit generator
    generator = RuntimeAuditGenerator(enabled=True)
    await generator.workflow_started("run-1", "my-workflow", ctx)

Version:
    Added in: v0.11.0
    Part of: CARE trust implementation (Phase 2)
"""

from kailash.runtime.trust.audit import (
    AuditEvent,
    AuditEventType,
    RuntimeAuditGenerator,
)
from kailash.runtime.trust.context import (
    RuntimeTrustContext,
    TrustVerificationMode,
    get_runtime_trust_context,
    runtime_trust_context,
    set_runtime_trust_context,
)
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
    VerificationResult,
)

__all__ = [
    # Context (CARE-015)
    "RuntimeTrustContext",
    "TrustVerificationMode",
    "get_runtime_trust_context",
    "set_runtime_trust_context",
    "runtime_trust_context",
    # Verifier (CARE-016)
    "VerificationResult",
    "TrustVerifierConfig",
    "TrustVerifier",
    "MockTrustVerifier",
    # Audit (CARE-018)
    "AuditEventType",
    "AuditEvent",
    "RuntimeAuditGenerator",
]
