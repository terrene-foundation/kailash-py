"""
DatabaseESA Example: Trust-Aware Database Access

Demonstrates how to use DatabaseESA for secure, auditable database operations
with automatic capability discovery and constraint enforcement.
"""

import asyncio
from datetime import datetime

from kaizen.trust.authority import OrganizationalAuthorityRegistry
from kaizen.trust.chain import CapabilityType
from kaizen.trust.esa import DatabaseESA, DatabaseType
from kaizen.trust.operations import CapabilityRequest, TrustOperations
from kaizen.trust.store import PostgresTrustStore


async def main():
    """Demonstrate DatabaseESA usage."""

    print("=" * 80)
    print("DatabaseESA Example: Trust-Aware Database Access")
    print("=" * 80)
    print()

    # =========================================================================
    # Step 1: Initialize Trust Infrastructure
    # =========================================================================
    print("Step 1: Initializing trust infrastructure...")

    # Create trust store
    trust_store = PostgresTrustStore(
        connection_string="postgresql://user:pass@localhost/trust_db"
    )
    await trust_store.initialize()

    # Create authority registry
    authority_registry = OrganizationalAuthorityRegistry()
    await authority_registry.initialize()

    # Register organizational authority
    from kaizen.trust.crypto import generate_keypair

    private_key, public_key = generate_keypair()

    authority = await authority_registry.register_authority(
        organization_id="org-acme",
        organization_name="ACME Corp",
        public_key=public_key,
        signing_key_id="key-acme-001",
    )

    # Create trust operations
    from kaizen.trust.operations import TrustKeyManager

    key_manager = TrustKeyManager()
    key_manager.register_key("key-acme-001", private_key)

    trust_ops = TrustOperations(
        authority_registry=authority_registry,
        key_manager=key_manager,
        trust_store=trust_store,
    )
    await trust_ops.initialize()

    print(f"  ✓ Authority registered: {authority.name}")
    print("  ✓ Trust infrastructure ready")
    print()

    # =========================================================================
    # Step 2: Create DatabaseESA
    # =========================================================================
    print("Step 2: Creating DatabaseESA for finance database...")

    db_esa = DatabaseESA(
        system_id="db-finance-001",
        connection_string="postgresql://finance_user:pass@localhost/finance_db",
        trust_ops=trust_ops,
        authority_id=authority.id,
        database_type=DatabaseType.POSTGRESQL,
        system_name="Finance Database",
        max_row_limit=5000,
        allowed_tables=["transactions", "accounts", "invoices"],
    )

    print(f"  ✓ DatabaseESA created: {db_esa.system_name}")
    print(f"  ✓ Database type: {db_esa.database_type.value}")
    print(f"  ✓ Max row limit: {db_esa.max_row_limit}")
    print(f"  ✓ Allowed tables: {', '.join(db_esa.allowed_tables)}")
    print()

    # =========================================================================
    # Step 3: Establish Trust
    # =========================================================================
    print("Step 3: Establishing trust for DatabaseESA...")

    await db_esa.establish_trust(
        authority_id=authority.id,
        additional_constraints=["business_hours_only", "audit_required"],
    )

    capabilities = db_esa.capabilities
    print("  ✓ Trust established")
    print(f"  ✓ Discovered {len(capabilities)} capabilities:")
    print(f"    - {', '.join(capabilities[:6])}")
    print(f"    - ... and {len(capabilities) - 6} more")
    print()

    # =========================================================================
    # Step 4: Create an AI Agent
    # =========================================================================
    print("Step 4: Creating AI agent with database access...")

    # Establish trust for AI agent
    agent_chain = await trust_ops.establish(
        agent_id="agent-financial-analyst",
        authority_id=authority.id,
        capabilities=[
            CapabilityRequest(
                capability="read_transactions",
                capability_type=CapabilityType.ACCESS,
                constraints=["read_only", "limit:1000"],
            ),
            CapabilityRequest(
                capability="read_accounts",
                capability_type=CapabilityType.ACCESS,
                constraints=["read_only"],
            ),
        ],
        constraints=["business_hours_only"],
    )

    print("  ✓ Agent established: agent-financial-analyst")
    print("  ✓ Capabilities: read_transactions, read_accounts")
    print()

    # =========================================================================
    # Step 5: Execute Database Operations via ESA
    # =========================================================================
    print("Step 5: Executing database operations...")
    print()

    # Operation 1: Read transactions
    print("  5a. Reading transactions...")
    result = await db_esa.execute(
        operation="read_transactions",
        parameters={
            "limit": 10,
            "offset": 0,
            "filters": {"amount": "> 1000"},
        },
        requesting_agent_id="agent-financial-analyst",
        context={"task_id": "task-001", "analysis": "high_value_transactions"},
    )

    if result.success:
        print("    ✓ Query executed successfully")
        print(f"    ✓ Rows returned: {len(result.result)}")
        print(f"    ✓ Duration: {result.duration_ms}ms")
        print(f"    ✓ Audit anchor: {result.audit_anchor_id}")
    else:
        print(f"    ✗ Query failed: {result.error}")
    print()

    # Operation 2: Read accounts
    print("  5b. Reading accounts...")
    result = await db_esa.execute(
        operation="read_accounts",
        parameters={"limit": 5},
        requesting_agent_id="agent-financial-analyst",
        context={"task_id": "task-001"},
    )

    if result.success:
        print("    ✓ Query executed successfully")
        print(f"    ✓ Rows returned: {len(result.result)}")
        print(f"    ✓ Duration: {result.duration_ms}ms")
    else:
        print(f"    ✗ Query failed: {result.error}")
    print()

    # =========================================================================
    # Step 6: Demonstrate Constraint Enforcement
    # =========================================================================
    print("Step 6: Demonstrating constraint enforcement...")
    print()

    # Try to access table not in allowed list
    print("  6a. Attempting to access disallowed table...")
    try:
        result = await db_esa.execute(
            operation="read_users",  # Not in allowed_tables
            parameters={"limit": 10},
            requesting_agent_id="agent-financial-analyst",
            context={"task_id": "task-002"},
        )
        print("    ✗ Unexpected success")
    except Exception as e:
        print(f"    ✓ Correctly blocked: {type(e).__name__}")
        print(f"      {str(e)[:80]}...")
    print()

    # Try to access without proper capability
    print("  6b. Attempting to insert without capability...")
    try:
        result = await db_esa.execute(
            operation="insert_transactions",
            parameters={"data": {"amount": 500}},
            requesting_agent_id="agent-financial-analyst",
            context={"task_id": "task-003"},
        )
        print("    ✗ Unexpected success")
    except Exception as e:
        print(f"    ✓ Correctly blocked: {type(e).__name__}")
        print(f"      {str(e)[:80]}...")
    print()

    # =========================================================================
    # Step 7: Capability Delegation
    # =========================================================================
    print("Step 7: Delegating capabilities to sub-agent...")

    delegation_id = await db_esa.delegate_capability(
        capability="read_transactions",
        delegatee_id="agent-sub-analyst",
        task_id="task-004",
        additional_constraints=["limit:100"],  # Tighter constraint
    )

    print("  ✓ Capability delegated: read_transactions")
    print(f"  ✓ Delegation ID: {delegation_id}")
    print("  ✓ Delegatee: agent-sub-analyst")
    print("  ✓ Additional constraints: limit:100")
    print()

    # =========================================================================
    # Step 8: Health Check and Statistics
    # =========================================================================
    print("Step 8: Checking ESA health and statistics...")

    health = await db_esa.health_check()
    stats = db_esa.get_statistics()

    print(f"  Health Status: {'✓ Healthy' if health['healthy'] else '✗ Unhealthy'}")
    print(f"  Connection: {health['checks']['connection']['status']}")
    print(f"  Trust Chain: {health['checks']['trust_chain']['status']}")
    print()

    print("  Statistics:")
    print(f"    - Total operations: {stats['operation_count']}")
    print(f"    - Successful: {stats['success_count']}")
    print(f"    - Failed: {stats['failure_count']}")
    print(f"    - Success rate: {stats['success_rate']:.2%}")
    print()

    # =========================================================================
    # Step 9: Refresh Capabilities
    # =========================================================================
    print("Step 9: Refreshing capabilities from database schema...")

    refreshed_capabilities = await db_esa.refresh_capabilities()

    print("  ✓ Capabilities refreshed")
    print(f"  ✓ Total capabilities: {len(refreshed_capabilities)}")
    print()

    # =========================================================================
    # Summary
    # =========================================================================
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print()
    print("DatabaseESA provides:")
    print("  ✓ Automatic capability discovery from database schema")
    print("  ✓ Trust-aware database access with full audit trails")
    print("  ✓ Constraint enforcement (row limits, table whitelist)")
    print("  ✓ Query parsing and validation")
    print("  ✓ Capability delegation with constraint tightening")
    print("  ✓ Health monitoring and statistics")
    print()
    print("All database operations are:")
    print("  • Verified against trust chain")
    print("  • Validated against constraints")
    print("  • Audited for compliance")
    print("  • Traceable via audit anchors")
    print()
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
