"""
Constraint Enforcement Example.

Demonstrates EATP constraint system:
1. Different constraint types (resource, time, scope, action)
2. Constraint evaluation during verification
3. Constraint tightening in delegation
4. Runtime constraint checking

Constraints provide fine-grained control over agent behavior.
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
    ConstraintEnvelope,
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
    """Demonstrate constraint enforcement."""
    print("=" * 70)
    print("EATP Constraint Enforcement Example")
    print("=" * 70)

    # =========================================================================
    # Setup
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    database_url = "postgresql://localhost:5432/kaizen_trust"

    trust_store = PostgresTrustStore(database_url=database_url)
    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    # Setup authority
    private_key, public_key = generate_keypair()
    authority_id = "org-constraint-demo"
    key_manager.register_key(f"key-{authority_id}", private_key)

    await authority_registry.initialize()
    await trust_store.initialize()

    try:
        await authority_registry.register_authority(
            OrganizationalAuthority(
                id=authority_id,
                name="Constraint Demo Org",
                authority_type=AuthorityType.ORGANIZATION,
                public_key=public_key,
                signing_key_id=f"key-{authority_id}",
                permissions=[
                    AuthorityPermission.CREATE_AGENTS,
                    AuthorityPermission.GRANT_CAPABILITIES,
                ],
                is_active=True,
            )
        )
    except Exception:
        pass

    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    print("   - Infrastructure ready")

    # =========================================================================
    # Explain Constraint Types
    # =========================================================================
    print("\n2. EATP Constraint Types:")
    print("-" * 70)
    print(
        """
    RESOURCE_LIMIT:
    - Limit resource consumption (API calls, tokens, records)
    - Example: max_api_calls=1000, max_tokens=50000

    TIME_WINDOW:
    - Restrict operations to specific time periods
    - Example: business_hours_only, valid_until

    DATA_SCOPE:
    - Limit data access to specific domains
    - Example: departments=["finance"], regions=["us-east"]

    ACTION_RESTRICTION:
    - Restrict allowed actions
    - Example: read_only=true, no_delete=true

    AUDIT_REQUIREMENT:
    - Mandate specific audit behaviors
    - Example: log_all_queries=true, notify_admin_on_failure=true
    """
    )

    # =========================================================================
    # Create Agent with Multiple Constraints
    # =========================================================================
    print("\n3. Creating agent with multiple constraints...")
    print("-" * 70)

    agent_id = "agent-constrained-001"

    constraints = [
        # Resource limits
        Constraint(
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            name="max_api_calls",
            value=1000,
            metadata={"period": "hourly", "reset_policy": "rolling"},
        ),
        Constraint(
            constraint_type=ConstraintType.RESOURCE_LIMIT,
            name="max_records_per_query",
            value=10000,
        ),
        # Time window
        Constraint(
            constraint_type=ConstraintType.TIME_WINDOW,
            name="business_hours",
            value={
                "start": "09:00",
                "end": "18:00",
                "timezone": "America/New_York",
                "weekdays_only": True,
            },
        ),
        # Data scope
        Constraint(
            constraint_type=ConstraintType.DATA_SCOPE,
            name="allowed_databases",
            value=["sales_db", "analytics_db"],
            metadata={"deny_list": ["hr_db", "finance_db"]},
        ),
        # Action restriction
        Constraint(
            constraint_type=ConstraintType.ACTION_RESTRICTION,
            name="read_only",
            value=True,
            metadata={"allowed_actions": ["SELECT", "READ", "GET"]},
        ),
        # Audit requirement
        Constraint(
            constraint_type=ConstraintType.AUDIT_REQUIREMENT,
            name="log_all_queries",
            value=True,
            metadata={"include_parameters": True, "retention_days": 90},
        ),
    ]

    try:
        chain = await trust_ops.establish(
            agent_id=agent_id,
            authority_id=authority_id,
            capabilities=[
                CapabilityRequest(
                    capability="query_data",
                    capability_type=CapabilityType.ACCESS,
                ),
                CapabilityRequest(
                    capability="analyze_data",
                    capability_type=CapabilityType.ACTION,
                ),
            ],
            constraints=constraints,
        )

        print(f"   Agent established: {agent_id}")
        print("\n   Constraints applied:")
        for c in chain.constraint_envelope.constraints:
            print(f"   - [{c.constraint_type.value}] {c.name}: {c.value}")

    except Exception as e:
        print(f"   Error: {e}")
        return

    # =========================================================================
    # Constraint Evaluation During Verification
    # =========================================================================
    print("\n4. Constraint evaluation during verification...")
    print("-" * 70)

    # Normal verification (constraints satisfied)
    print("\n   Case 1: All constraints satisfied")
    result = await trust_ops.verify(
        agent_id=agent_id,
        action="query_data",
        resource_uri="database://sales_db/customers",
        level=VerificationLevel.STANDARD,
    )
    print("   - Resource: database://sales_db/customers")
    print(f"   - Valid: {result.valid}")
    print("   - Constraints checked: data_scope, action_restriction, audit_requirement")

    # Verification with constraint context (checking specific constraints)
    print("\n   Case 2: Checking against constraint values")
    eval_result = await trust_ops.evaluate_constraints(
        agent_id=agent_id,
        action="query_data",
        context={
            "records_requested": 5000,  # Under 10000 limit
            "database": "sales_db",  # In allowed list
            "operation": "SELECT",  # Allowed action
        },
    )
    print("   - Records: 5000 (limit: 10000)")
    print("   - Database: sales_db (allowed)")
    print("   - Operation: SELECT (allowed)")
    print(f"   - Permitted: {eval_result.permitted}")

    # =========================================================================
    # Constraint Violation Detection
    # =========================================================================
    print("\n5. Constraint violation detection...")
    print("-" * 70)

    # Resource limit violation
    print("\n   Case 1: Resource limit violation")
    eval_result = await trust_ops.evaluate_constraints(
        agent_id=agent_id,
        action="query_data",
        context={
            "records_requested": 50000,  # Exceeds 10000 limit!
        },
    )
    print("   - Records requested: 50000 (limit: 10000)")
    print(f"   - Permitted: {eval_result.permitted}")
    for violation in eval_result.violations:
        print(f"   - Violation: {violation['constraint']}: {violation['reason']}")

    # Data scope violation
    print("\n   Case 2: Data scope violation")
    eval_result = await trust_ops.evaluate_constraints(
        agent_id=agent_id,
        action="query_data",
        context={
            "database": "hr_db",  # Not in allowed list!
        },
    )
    print("   - Database requested: hr_db (not allowed)")
    print(f"   - Permitted: {eval_result.permitted}")
    for violation in eval_result.violations:
        print(f"   - Violation: {violation['constraint']}: {violation['reason']}")

    # Action restriction violation
    print("\n   Case 3: Action restriction violation")
    eval_result = await trust_ops.evaluate_constraints(
        agent_id=agent_id,
        action="delete_data",  # Not allowed for read_only agent
        context={
            "operation": "DELETE",
        },
    )
    print("   - Operation: DELETE (read_only constraint)")
    print(f"   - Permitted: {eval_result.permitted}")
    for violation in eval_result.violations:
        print(f"   - Violation: {violation['constraint']}: {violation['reason']}")

    # =========================================================================
    # Constraint Tightening in Delegation
    # =========================================================================
    print("\n6. Constraint tightening in delegation...")
    print("-" * 70)

    # Create a worker agent
    worker_id = "agent-worker-001"
    try:
        await trust_ops.establish(
            agent_id=worker_id,
            authority_id=authority_id,
            capabilities=[],
        )
    except Exception:
        pass

    # Delegate with TIGHTER constraints
    print("\n   Delegating with tighter constraints:")
    delegation = await trust_ops.delegate(
        delegator_agent_id=agent_id,
        delegatee_agent_id=worker_id,
        task_id="task-subset-query",
        capabilities=["query_data"],
        constraints=[
            # Tighter resource limit
            Constraint(
                constraint_type=ConstraintType.RESOURCE_LIMIT,
                name="max_records_per_query",
                value=1000,  # Tightened from 10000
            ),
            # Tighter data scope
            Constraint(
                constraint_type=ConstraintType.DATA_SCOPE,
                name="allowed_databases",
                value=["sales_db"],  # Subset of original ["sales_db", "analytics_db"]
            ),
        ],
    )

    print(f"   - Delegated to: {worker_id}")
    print("   - max_records: 10000 -> 1000 (tightened)")
    print("   - databases: [sales_db, analytics_db] -> [sales_db] (tightened)")

    # Try to LOOSEN constraints (should fail)
    print("\n   Attempting to loosen constraints (should fail):")
    try:
        await trust_ops.delegate(
            delegator_agent_id=agent_id,
            delegatee_agent_id=worker_id,
            task_id="task-invalid",
            capabilities=["query_data"],
            constraints=[
                Constraint(
                    constraint_type=ConstraintType.RESOURCE_LIMIT,
                    name="max_records_per_query",
                    value=50000,  # LOOSENING from 10000!
                ),
            ],
        )
        print("   ERROR: Should have raised ConstraintViolationError!")
    except ConstraintViolationError as e:
        print("   - Correctly rejected!")
        print("   - Reason: Constraints can only be TIGHTENED")

    # =========================================================================
    # Get Effective Constraints
    # =========================================================================
    print("\n7. Getting effective constraints for worker...")
    print("-" * 70)

    worker_chain = await trust_store.get_chain(worker_id)
    effective = worker_chain.get_effective_constraints()

    print(f"   Worker {worker_id} effective constraints:")
    for constraint in effective:
        print(f"   - {constraint.name}: {constraint.value}")
        print(f"     (type: {constraint.constraint_type.value})")

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n8. Cleaning up...")
    await trust_store.close()
    await authority_registry.close()

    print("\n" + "=" * 70)
    print("Constraint Enforcement Example Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("- 5 constraint types: RESOURCE_LIMIT, TIME_WINDOW, DATA_SCOPE,")
    print("  ACTION_RESTRICTION, AUDIT_REQUIREMENT")
    print("- Constraints are evaluated during verification")
    print("- Violations are detected and reported")
    print("- Constraints can only be TIGHTENED during delegation")
    print("- Effective constraints combine all sources")


if __name__ == "__main__":
    asyncio.run(main())
