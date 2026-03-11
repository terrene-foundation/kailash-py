"""
Example: External Agent Approval Workflows

Demonstrates how to use ExternalAgentApprovalManager for governance of
external agent invocations (Microsoft Copilot, custom tools, third-party AI).

This example shows:
1. Setting up approval requirements (cost-based, environment-based)
2. Creating approval requests
3. Routing to appropriate approvers (team lead, admin, owner)
4. Approving/rejecting requests
5. Handling timeouts
"""

import asyncio

from kaizen.governance import (
    ApprovalLevel,
    ApprovalRequirement,
    ApprovalStatus,
    ExternalAgentApprovalManager,
)


async def main():
    """
    Example workflow demonstrating external agent approval.
    """
    print("=" * 80)
    print("External Agent Approval Workflows - Example")
    print("=" * 80)

    # Step 1: Initialize approval manager
    manager = ExternalAgentApprovalManager()
    print("\n✅ ExternalAgentApprovalManager initialized")

    # Step 2: Configure team structure (in production, query from database)
    manager._user_teams = {
        "alice": "engineering_team",
        "bob": "data_team",
    }
    manager._team_leads = {
        "engineering_team": ["eng_lead_001"],
        "data_team": ["data_lead_001"],
    }
    manager._org_admins = ["admin_001", "admin_002"]
    manager._org_owner = "owner_001"
    print("\n✅ Team structure configured")

    # Step 3: Configure approval requirements for external agents
    # Example 1: Copilot agent - require approval for production
    copilot_requirement = ApprovalRequirement(
        require_for_environments=["production"],
        approval_level=ApprovalLevel.TEAM_LEAD,
        approval_timeout_seconds=3600,  # 1 hour
        approval_reason="Production deployment requires team lead approval",
    )
    manager.add_requirement("copilot_agent_001", copilot_requirement)
    print("\n✅ Approval requirement added for copilot_agent_001")
    print(f"   - Environments: {copilot_requirement.require_for_environments}")
    print(f"   - Approval level: {copilot_requirement.approval_level.value}")

    # Example 2: Custom API agent - require approval for high cost
    custom_api_requirement = ApprovalRequirement(
        require_for_cost_above=10.0,  # $10.00 threshold
        approval_level=ApprovalLevel.ADMIN,
        approval_timeout_seconds=1800,  # 30 minutes
        approval_reason="High-cost operations require admin approval",
    )
    manager.add_requirement("custom_api_agent_001", custom_api_requirement)
    print("\n✅ Approval requirement added for custom_api_agent_001")
    print(f"   - Cost threshold: ${custom_api_requirement.require_for_cost_above:.2f}")
    print(f"   - Approval level: {custom_api_requirement.approval_level.value}")

    # Step 4: Simulate external agent invocation - check if approval required
    print("\n" + "=" * 80)
    print("Scenario 1: Production invocation (approval required)")
    print("=" * 80)

    metadata = {
        "cost": 5.00,
        "environment": "production",
        "operation": "data_export",
    }

    required, requirement = manager.determine_if_approval_required(
        "copilot_agent_001", metadata
    )

    print(f"\n❓ Approval required: {required}")
    if required:
        print(f"   Reason: {requirement.approval_reason}")

        # Create approval request
        request_id = await manager.request_approval(
            "copilot_agent_001",
            "alice",
            metadata,
        )
        print(f"\n✅ Approval request created: {request_id}")

        # Query pending approvals for team lead
        pending = manager.get_pending_approvals("eng_lead_001")
        print(f"\n📋 Pending approvals for eng_lead_001: {len(pending)}")
        for req in pending:
            print(f"   - Request ID: {req.id}")
            print(f"   - Agent: {req.external_agent_id}")
            print(f"   - Requested by: {req.requested_by}")
            print(f"   - Cost: ${req.request_metadata['cost']:.2f}")
            print(f"   - Environment: {req.request_metadata['environment']}")

        # Simulate approval
        await manager.approve_request(request_id, "eng_lead_001")
        print("\n✅ Request approved by eng_lead_001")

        # Verify status
        request = manager.get_request(request_id)
        print(f"   - Status: {request.status.value}")
        print(f"   - Approved by: {request.approved_by}")
        print(f"   - Approved at: {request.approved_at}")

    # Step 5: Simulate rejection scenario
    print("\n" + "=" * 80)
    print("Scenario 2: High-cost invocation (rejected)")
    print("=" * 80)

    metadata2 = {
        "cost": 50.00,  # Exceeds $10.00 threshold
        "environment": "production",
        "operation": "bulk_export",
    }

    required2, requirement2 = manager.determine_if_approval_required(
        "custom_api_agent_001", metadata2
    )

    print(f"\n❓ Approval required: {required2}")
    if required2:
        print(f"   Reason: {requirement2.approval_reason}")

        # Create approval request
        request_id2 = await manager.request_approval(
            "custom_api_agent_001",
            "bob",
            metadata2,
        )
        print(f"\n✅ Approval request created: {request_id2}")

        # Simulate rejection
        rejection_reason = "Cost too high for bulk export operation"
        await manager.reject_request(request_id2, "admin_001", rejection_reason)
        print("\n❌ Request rejected by admin_001")
        print(f"   Reason: {rejection_reason}")

        # Verify status
        request2 = manager.get_request(request_id2)
        print(f"   - Status: {request2.status.value}")
        print(f"   - Rejected by: {request2.approved_by}")
        print(f"   - Rejection reason: {request2.rejection_reason}")

    # Step 6: Simulate development environment (no approval required)
    print("\n" + "=" * 80)
    print("Scenario 3: Development invocation (no approval required)")
    print("=" * 80)

    metadata3 = {
        "cost": 2.00,
        "environment": "development",
        "operation": "test_export",
    }

    required3, requirement3 = manager.determine_if_approval_required(
        "copilot_agent_001", metadata3
    )

    print(f"\n❓ Approval required: {required3}")
    if not required3:
        print("   ✅ Execution can proceed without approval (development environment)")

    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"\nTotal approval requests created: {len(manager._requests)}")
    for req_id, req in manager._requests.items():
        print(f"\n  Request {req_id[:8]}...")
        print(f"    - Agent: {req.external_agent_id}")
        print(f"    - Status: {req.status.value}")
        print(f"    - Requested by: {req.requested_by}")
        print(f"    - Approvers: {req.approvers}")

    print("\n✅ Example completed successfully")


if __name__ == "__main__":
    asyncio.run(main())
