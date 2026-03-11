"""
Supervisor-Worker Delegation Example.

Demonstrates trust delegation in a hierarchical agent system:
1. Supervisor agent established with delegation capability
2. Worker agents receive delegated trust
3. Constraints are properly tightened
4. All actions audited for compliance

Key EATP concept: Constraints can only be TIGHTENED, never loosened.
"""

import asyncio
from datetime import datetime, timedelta

from kaizen.trust import (  # Core operations; Data structures; Storage; Authority; Crypto; Exceptions
    ActionResult,
    AuthorityPermission,
    AuthorityType,
    CapabilityRequest,
    CapabilityType,
    Constraint,
    ConstraintType,
    ConstraintViolationError,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    PostgresTrustStore,
    TrustKeyManager,
    TrustOperations,
    VerificationLevel,
    generate_keypair,
)


async def main():
    """Demonstrate supervisor-worker trust delegation."""
    print("=" * 60)
    print("EATP Supervisor-Worker Delegation Example")
    print("=" * 60)

    # =========================================================================
    # Setup Infrastructure
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    database_url = "postgresql://localhost:5432/kaizen_trust"

    trust_store = PostgresTrustStore(database_url=database_url)
    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    # Register authority
    private_key, public_key = generate_keypair()
    authority_id = "org-data-team"
    key_manager.register_key(f"key-{authority_id}", private_key)

    authority = OrganizationalAuthority(
        id=authority_id,
        name="Data Processing Team",
        authority_type=AuthorityType.ORGANIZATION,
        public_key=public_key,
        signing_key_id=f"key-{authority_id}",
        permissions=[
            AuthorityPermission.CREATE_AGENTS,
            AuthorityPermission.GRANT_CAPABILITIES,
        ],
        is_active=True,
    )

    await authority_registry.initialize()
    await trust_store.initialize()

    try:
        await authority_registry.register_authority(authority)
    except Exception:
        pass  # May already exist

    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    print("   - Infrastructure ready")

    # =========================================================================
    # Step 1: Establish Supervisor Agent
    # =========================================================================
    print("\n2. Establishing supervisor agent...")

    supervisor_id = "supervisor-etl-001"

    try:
        supervisor_chain = await trust_ops.establish(
            agent_id=supervisor_id,
            authority_id=authority_id,
            capabilities=[
                # Supervisor can process data
                CapabilityRequest(
                    capability="process_data",
                    capability_type=CapabilityType.ACTION,
                    constraints=["max_batch_size:10000"],
                ),
                # Supervisor can delegate work
                CapabilityRequest(
                    capability="delegate_work",
                    capability_type=CapabilityType.DELEGATION,
                ),
            ],
            constraints=[
                Constraint(
                    constraint_type=ConstraintType.RESOURCE_LIMIT,
                    name="max_concurrent_workers",
                    value=5,
                ),
                Constraint(
                    constraint_type=ConstraintType.TIME_WINDOW,
                    name="business_hours",
                    value={"start": "09:00", "end": "18:00"},
                ),
            ],
            metadata={"role": "ETL Supervisor"},
        )

        print(f"   - Supervisor established: {supervisor_id}")
        print("   - Has delegation capability: Yes")
        print(
            f"   - Constraints applied: {len(supervisor_chain.constraint_envelope.constraints)}"
        )

    except Exception as e:
        print(f"   Note: {e}")
        return

    # =========================================================================
    # Step 2: Delegate to Worker Agents
    # =========================================================================
    print("\n3. Delegating trust to worker agents...")

    worker_ids = ["worker-etl-001", "worker-etl-002", "worker-etl-003"]

    for i, worker_id in enumerate(worker_ids):
        # First establish the worker with basic identity
        try:
            await trust_ops.establish(
                agent_id=worker_id,
                authority_id=authority_id,
                capabilities=[],  # Will receive capabilities via delegation
                metadata={"role": f"ETL Worker {i+1}"},
            )
        except Exception:
            pass  # May already exist

        # Now delegate from supervisor to worker
        # Note: Workers get TIGHTENED constraints
        delegation = await trust_ops.delegate(
            delegator_agent_id=supervisor_id,
            delegatee_agent_id=worker_id,
            task_id=f"task-batch-{i+1}",
            capabilities=["process_data"],  # Subset of supervisor's capabilities
            constraints=[
                # Tighter batch size limit
                Constraint(
                    constraint_type=ConstraintType.RESOURCE_LIMIT,
                    name="max_batch_size",
                    value=2000,  # Reduced from 10000
                ),
                # Tighter time window
                Constraint(
                    constraint_type=ConstraintType.TIME_WINDOW,
                    name="business_hours",
                    value={"start": "10:00", "end": "16:00"},  # Stricter hours
                ),
            ],
        )

        print(f"   - Delegated to {worker_id}")
        print(f"     * Task: {delegation.task_id}")
        print(f"     * Capabilities: {delegation.capabilities_delegated}")
        print("     * Constraint: max_batch_size=2000 (tightened from 10000)")

    # =========================================================================
    # Step 3: Verify Worker Trust
    # =========================================================================
    print("\n4. Verifying worker trust chains...")

    for worker_id in worker_ids:
        result = await trust_ops.verify(
            agent_id=worker_id,
            action="process_data",
            level=VerificationLevel.STANDARD,
        )
        print(
            f"   - {worker_id}: Valid={result.valid}, Latency={result.latency_ms:.2f}ms"
        )

    # =========================================================================
    # Step 4: Demonstrate Constraint Tightening Rule
    # =========================================================================
    print("\n5. Demonstrating constraint tightening rule...")
    print("   (Attempting to LOOSEN constraints - should FAIL)")

    try:
        # Try to delegate with LOOSER constraints - this should fail!
        await trust_ops.delegate(
            delegator_agent_id=supervisor_id,
            delegatee_agent_id="worker-test",
            task_id="task-invalid",
            capabilities=["process_data"],
            constraints=[
                Constraint(
                    constraint_type=ConstraintType.RESOURCE_LIMIT,
                    name="max_batch_size",
                    value=20000,  # LOOSER than supervisor's 10000 - NOT ALLOWED!
                ),
            ],
        )
        print("   - ERROR: Should have raised ConstraintViolationError!")
    except ConstraintViolationError as e:
        print(f"   - Correctly rejected: {e}")
        print("   - EATP enforces: Constraints can only be TIGHTENED, never loosened")

    # =========================================================================
    # Step 5: Workers Perform and Audit Actions
    # =========================================================================
    print("\n6. Workers performing audited actions...")

    for i, worker_id in enumerate(worker_ids):
        # Verify before action
        result = await trust_ops.verify(
            agent_id=worker_id,
            action="process_data",
            level=VerificationLevel.STANDARD,
        )

        if result.valid:
            # Audit the action
            anchor = await trust_ops.audit(
                agent_id=worker_id,
                action_type="process_data",
                resource_uri=f"s3://data-lake/batch-{i+1}/",
                result=ActionResult.SUCCESS,
                metadata={
                    "records_processed": 1500,
                    "duration_seconds": 45,
                    "task_id": f"task-batch-{i+1}",
                },
            )
            print(f"   - {worker_id}: Processed 1500 records")
            print(f"     * Audit ID: {anchor.id[:20]}...")

    # =========================================================================
    # Step 6: Supervisor Aggregates Results
    # =========================================================================
    print("\n7. Supervisor aggregating worker results...")

    # Supervisor audits the aggregation
    anchor = await trust_ops.audit(
        agent_id=supervisor_id,
        action_type="aggregate_results",
        resource_uri="report://daily-etl-summary",
        result=ActionResult.SUCCESS,
        metadata={
            "workers_coordinated": len(worker_ids),
            "total_records": 1500 * len(worker_ids),
            "status": "complete",
        },
    )

    print("   - Supervisor completed coordination")
    print(f"   - Total records: {1500 * len(worker_ids)}")
    print(f"   - Audit ID: {anchor.id[:20]}...")

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n8. Cleaning up...")
    await trust_store.close()
    await authority_registry.close()

    print("\n" + "=" * 60)
    print("Supervisor-Worker Delegation Example Complete!")
    print("=" * 60)
    print("\nKey Takeaways:")
    print("- Supervisors can delegate to workers")
    print("- Constraints can only be TIGHTENED")
    print("- All actions are audited")
    print("- Delegation chain is cryptographically verifiable")


if __name__ == "__main__":
    asyncio.run(main())
