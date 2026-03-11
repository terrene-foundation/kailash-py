"""
Audit Trail Query Example.

Demonstrates EATP audit capabilities:
1. Recording audit anchors for agent actions
2. Querying audit trail by various criteria
3. Generating compliance reports
4. Audit trail analysis

All EATP actions are auditable with tamper-proof signatures.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List

from kaizen.trust import (  # Core operations; Audit; Storage; Authority; Crypto
    ActionResult,
    AuditQueryService,
    AuthorityPermission,
    AuthorityType,
    CapabilityRequest,
    CapabilityType,
    OrganizationalAuthority,
    OrganizationalAuthorityRegistry,
    PostgresAuditStore,
    PostgresTrustStore,
    TrustKeyManager,
    TrustOperations,
    generate_keypair,
)


async def setup_demo_agents(trust_ops, authority_id) -> List[str]:
    """Create demo agents and perform auditable actions."""
    agent_ids = [
        "agent-analytics-001",
        "agent-processor-001",
        "agent-reporter-001",
    ]

    for agent_id in agent_ids:
        try:
            await trust_ops.establish(
                agent_id=agent_id,
                authority_id=authority_id,
                capabilities=[
                    CapabilityRequest(
                        capability="read_data",
                        capability_type=CapabilityType.ACCESS,
                    ),
                    CapabilityRequest(
                        capability="write_data",
                        capability_type=CapabilityType.ACTION,
                    ),
                    CapabilityRequest(
                        capability="generate_report",
                        capability_type=CapabilityType.ACTION,
                    ),
                ],
            )
        except Exception:
            pass  # Agent may already exist

    return agent_ids


async def generate_audit_trail(trust_ops, agent_ids: List[str]):
    """Generate sample audit trail entries."""
    actions = [
        # Agent 1 - Analytics
        (
            "agent-analytics-001",
            "read_data",
            "database://sales/customers",
            ActionResult.SUCCESS,
            {"rows_read": 1500},
        ),
        (
            "agent-analytics-001",
            "read_data",
            "database://sales/orders",
            ActionResult.SUCCESS,
            {"rows_read": 3200},
        ),
        (
            "agent-analytics-001",
            "write_data",
            "database://analytics/cache",
            ActionResult.SUCCESS,
            {"rows_written": 500},
        ),
        (
            "agent-analytics-001",
            "read_data",
            "database://restricted/hr",
            ActionResult.DENIED,
            {"reason": "no_capability"},
        ),
        # Agent 2 - Processor
        (
            "agent-processor-001",
            "read_data",
            "s3://data-lake/raw/",
            ActionResult.SUCCESS,
            {"files_read": 25},
        ),
        (
            "agent-processor-001",
            "transform_data",
            "pipeline://etl/stage1",
            ActionResult.SUCCESS,
            {"records": 10000},
        ),
        (
            "agent-processor-001",
            "write_data",
            "s3://data-lake/processed/",
            ActionResult.SUCCESS,
            {"files_written": 5},
        ),
        (
            "agent-processor-001",
            "transform_data",
            "pipeline://etl/stage2",
            ActionResult.FAILURE,
            {"error": "timeout"},
        ),
        # Agent 3 - Reporter
        (
            "agent-reporter-001",
            "read_data",
            "database://analytics/cache",
            ActionResult.SUCCESS,
            {"rows_read": 500},
        ),
        (
            "agent-reporter-001",
            "generate_report",
            "report://daily/sales",
            ActionResult.SUCCESS,
            {"pages": 15},
        ),
        (
            "agent-reporter-001",
            "send_report",
            "email://stakeholders",
            ActionResult.SUCCESS,
            {"recipients": 5},
        ),
    ]

    anchors = []
    for agent_id, action, resource, result, metadata in actions:
        anchor = await trust_ops.audit(
            agent_id=agent_id,
            action_type=action,
            resource_uri=resource,
            result=result,
            metadata=metadata,
        )
        anchors.append(anchor)
        # Small delay for timestamp differentiation
        await asyncio.sleep(0.01)

    return anchors


async def main():
    """Demonstrate audit trail capabilities."""
    print("=" * 70)
    print("EATP Audit Trail Query Example")
    print("=" * 70)

    # =========================================================================
    # Setup
    # =========================================================================
    print("\n1. Setting up infrastructure...")

    database_url = "postgresql://localhost:5432/kaizen_trust"

    trust_store = PostgresTrustStore(database_url=database_url)
    audit_store = PostgresAuditStore(database_url=database_url)
    authority_registry = OrganizationalAuthorityRegistry(database_url=database_url)
    key_manager = TrustKeyManager()

    # Setup authority
    private_key, public_key = generate_keypair()
    authority_id = "org-audit-demo"
    key_manager.register_key(f"key-{authority_id}", private_key)

    await authority_registry.initialize()
    await trust_store.initialize()
    await audit_store.initialize()

    try:
        await authority_registry.register_authority(
            OrganizationalAuthority(
                id=authority_id,
                name="Audit Demo Organization",
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
        audit_store=audit_store,
    )
    await trust_ops.initialize()

    # Create audit query service
    audit_service = AuditQueryService(audit_store=audit_store)

    print("   - Infrastructure ready")

    # =========================================================================
    # Generate Audit Trail
    # =========================================================================
    print("\n2. Setting up demo agents and generating audit trail...")

    agent_ids = await setup_demo_agents(trust_ops, authority_id)
    print(f"   - Created {len(agent_ids)} agents")

    anchors = await generate_audit_trail(trust_ops, agent_ids)
    print(f"   - Generated {len(anchors)} audit entries")

    # =========================================================================
    # Query by Agent
    # =========================================================================
    print("\n3. Querying audit trail by agent...")
    print("-" * 70)

    for agent_id in agent_ids:
        trail = await audit_service.get_audit_trail(
            agent_id=agent_id,
            limit=10,
        )
        print(f"\n   {agent_id}:")
        print(f"   Total actions: {len(trail)}")
        for entry in trail[:3]:  # Show first 3
            print(
                f"   - {entry.action_type}: {entry.result.value} ({entry.resource_uri})"
            )

    # =========================================================================
    # Query by Action Type
    # =========================================================================
    print("\n4. Querying audit trail by action type...")
    print("-" * 70)

    action_types = ["read_data", "write_data", "generate_report"]
    for action_type in action_types:
        trail = await audit_service.query_by_action_type(
            action_type=action_type,
            limit=100,
        )
        success_count = sum(1 for a in trail if a.result == ActionResult.SUCCESS)
        print(f"   {action_type}:")
        print(f"   - Total: {len(trail)}, Successful: {success_count}")

    # =========================================================================
    # Query by Time Range
    # =========================================================================
    print("\n5. Querying audit trail by time range...")
    print("-" * 70)

    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)

    trail = await audit_service.query_by_time_range(
        start_time=one_hour_ago,
        end_time=now,
        limit=100,
    )
    print(f"   Actions in last hour: {len(trail)}")

    # =========================================================================
    # Query Failed Actions
    # =========================================================================
    print("\n6. Querying failed/denied actions...")
    print("-" * 70)

    failed_trail = await audit_service.query_by_result(
        results=[ActionResult.FAILURE, ActionResult.DENIED],
        limit=100,
    )
    print(f"   Failed/Denied actions: {len(failed_trail)}")
    for entry in failed_trail:
        print(f"   - Agent: {entry.agent_id}")
        print(f"     Action: {entry.action_type}")
        print(f"     Resource: {entry.resource_uri}")
        print(f"     Result: {entry.result.value}")
        print(f"     Details: {entry.metadata}")

    # =========================================================================
    # Compliance Report
    # =========================================================================
    print("\n7. Generating compliance report...")
    print("-" * 70)

    report = await audit_service.generate_compliance_report(
        authority_id=authority_id,
        start_time=one_hour_ago,
        end_time=now,
    )

    print(f"\n   Compliance Report for {authority_id}")
    print(f"   Period: {report.start_time} to {report.end_time}")
    print("\n   Summary:")
    print(f"   - Total Actions: {report.total_actions}")
    print(f"   - Successful: {report.successful_actions}")
    print(f"   - Failed: {report.failed_actions}")
    print(f"   - Denied: {report.denied_actions}")
    print(f"   - Success Rate: {report.success_rate:.1%}")

    print("\n   Per-Agent Summary:")
    for agent_summary in report.agent_summaries:
        print(f"   - {agent_summary.agent_id}:")
        print(f"     Actions: {agent_summary.total_actions}")
        print(f"     Success Rate: {agent_summary.success_rate:.1%}")

    print("\n   Action Type Breakdown:")
    for action_summary in report.action_summaries:
        print(
            f"   - {action_summary.action_type}: {action_summary.count} ({action_summary.success_rate:.1%} success)"
        )

    # =========================================================================
    # Verify Audit Integrity
    # =========================================================================
    print("\n8. Verifying audit trail integrity...")
    print("-" * 70)

    integrity_check = await audit_service.verify_integrity(
        agent_id="agent-analytics-001",
        limit=100,
    )

    print("   Agent: agent-analytics-001")
    print(f"   Entries checked: {integrity_check.entries_checked}")
    print(f"   All signatures valid: {integrity_check.all_valid}")
    print(f"   Tampering detected: {integrity_check.tampered_entries}")

    # =========================================================================
    # Export Audit Trail
    # =========================================================================
    print("\n9. Exporting audit trail for external analysis...")
    print("-" * 70)

    export_data = await audit_service.export_audit_trail(
        agent_id="agent-processor-001",
        format="json",
        limit=100,
    )

    print(f"   Exported {len(export_data['entries'])} entries as JSON")
    print("   Export includes:")
    print("   - Agent ID")
    print("   - Action type")
    print("   - Resource URI")
    print("   - Timestamp")
    print("   - Result")
    print("   - Signature (for verification)")

    # =========================================================================
    # Cleanup
    # =========================================================================
    print("\n10. Cleaning up...")
    await trust_store.close()
    await audit_store.close()
    await authority_registry.close()

    print("\n" + "=" * 70)
    print("Audit Trail Query Example Complete!")
    print("=" * 70)
    print("\nKey Takeaways:")
    print("- All agent actions are recorded with tamper-proof signatures")
    print("- Query by agent, action type, time range, or result")
    print("- Generate compliance reports for auditors")
    print("- Verify integrity to detect tampering")
    print("- Export for external analysis tools")


if __name__ == "__main__":
    asyncio.run(main())
