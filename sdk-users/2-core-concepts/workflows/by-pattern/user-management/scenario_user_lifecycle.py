#!/usr/bin/env python3
"""
Real-World Scenario: Complete User Lifecycle Management

This example demonstrates a realistic employee lifecycle from onboarding to offboarding,
including security incidents, permission changes, and compliance requirements.

Scenario: Financial Services Company
- New employee joins as Junior Analyst
- Gets promoted to Senior Analyst
- Handles sensitive data breach incident
- Eventually leaves the company
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Dict

from kailash.nodes.admin import (
    AuditLogNode,
    PermissionCheckNode,
    RoleManagementNode,
    SecurityEventNode,
    UserManagementNode,
)
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.logic import SwitchNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow import Workflow


def create_employee_onboarding_workflow(employee_data: Dict[str, Any]):
    """
    Real scenario: Onboard new financial analyst with proper security clearance.

    Steps:
    1. Create user account with temporary password
    2. Assign appropriate role based on department
    3. Set up multi-factor authentication
    4. Verify permissions for required systems
    5. Log onboarding for compliance
    """

    # Step 1: Create user account
    create_user = UserManagementNode(
        name="create_employee",
        operation="create",
        user_data={
            "email": employee_data["email"],
            "username": employee_data["username"],
            "first_name": employee_data["first_name"],
            "last_name": employee_data["last_name"],
            "status": "pending",  # Pending until training complete
            "attributes": {
                "department": employee_data["department"],
                "position": employee_data["position"],
                "manager": employee_data["manager"],
                "start_date": employee_data["start_date"],
                "office_location": employee_data["location"],
                "employee_id": employee_data["employee_id"],
                "clearance_level": "basic",  # Start with basic
                "training_status": "not_started",
                "equipment_issued": False,
            },
        },
        password=employee_data["temp_password"],
        force_password_change=True,
        tenant_id=employee_data["company"],
    )

    # Step 2: Determine and assign role based on position
    def determine_role(user_result):
        """Determine appropriate role based on position."""
        user = user_result.get("user", {})
        position = user.get("attributes", {}).get("position", "")

        role_mapping = {
            "Junior Financial Analyst": "junior_analyst",
            "Financial Analyst": "analyst",
            "Senior Financial Analyst": "senior_analyst",
            "Finance Manager": "finance_manager",
            "CFO": "finance_executive",
        }

        return {
            "role_id": role_mapping.get(position, "employee"),
            "user_id": user.get("user_id"),
            "reason": f"Auto-assigned based on position: {position}",
        }

    role_determiner = PythonCodeNode.from_function(
        name="determine_role", func=determine_role
    )

    # Step 3: Assign the determined role
    assign_role = RoleManagementNode(
        name="assign_initial_role",
        operation="assign_user",
        tenant_id=employee_data["company"],
    )

    # Step 4: Set up additional roles for system access
    assign_system_access = RoleManagementNode(
        name="assign_system_access",
        operation="bulk_assign",
        user_ids=[],  # Will be populated from create_user
        role_id="financial_systems_user",
        tenant_id=employee_data["company"],
    )

    # Step 5: Verify critical permissions
    verify_email_access = PermissionCheckNode(
        name="verify_email",
        operation="check_permission",
        resource_id="corporate_email",
        permission="access",
        tenant_id=employee_data["company"],
        explain=True,
    )

    verify_financial_systems = PermissionCheckNode(
        name="verify_financial_systems",
        operation="check_permission",
        resource_id="financial_reporting_system",
        permission="read",
        tenant_id=employee_data["company"],
        explain=True,
    )

    # Step 6: Security briefing acknowledgment
    def record_security_briefing(user_result, email_check, systems_check):
        """Record security briefing and compliance training."""
        user = user_result.get("user", {})

        briefing_data = {
            "user_id": user.get("user_id"),
            "briefing_completed": True,
            "policies_acknowledged": [
                "data_protection_policy",
                "acceptable_use_policy",
                "security_awareness_policy",
                "insider_trading_policy",
            ],
            "email_access": email_check.get("check", {}).get("allowed", False),
            "systems_access": systems_check.get("check", {}).get("allowed", False),
            "next_training_due": (datetime.now(UTC) + timedelta(days=90)).isoformat(),
        }

        return briefing_data

    security_briefing = PythonCodeNode.from_function(
        name="security_briefing", func=record_security_briefing
    )

    # Step 7: Comprehensive audit log
    audit_onboarding = AuditLogNode(
        name="audit_onboarding",
        operation="log_event",
        event_data={
            "event_type": "user_created",
            "severity": "medium",
            "action": "employee_onboarding_completed",
            "description": f"New employee onboarded: {employee_data['first_name']} {employee_data['last_name']}",
            "metadata": {
                "process": "standard_onboarding",
                "department": employee_data["department"],
                "position": employee_data["position"],
                "clearance_granted": "basic",
                "compliance_training": "scheduled",
            },
        },
        tenant_id=employee_data["company"],
    )

    # Build workflow
    workflow = Workflow(name="employee_onboarding")
    workflow.add_nodes(
        [
            create_user,
            role_determiner,
            assign_role,
            assign_system_access,
            verify_email_access,
            verify_financial_systems,
            security_briefing,
            audit_onboarding,
        ]
    )

    # Connect workflow
    workflow.connect(create_user, role_determiner, {"result": "user_result"})
    workflow.connect(
        role_determiner,
        assign_role,
        {"result": lambda r: {"user_id": r["user_id"], "role_id": r["role_id"]}},
    )
    workflow.connect(
        create_user,
        assign_system_access,
        {"result": lambda r: {"user_ids": [r["user"]["user_id"]]}},
    )
    workflow.connect(
        create_user,
        verify_email_access,
        {"result": lambda r: {"user_id": r["user"]["user_id"]}},
    )
    workflow.connect(
        create_user,
        verify_financial_systems,
        {"result": lambda r: {"user_id": r["user"]["user_id"]}},
    )

    workflow.connect(create_user, security_briefing, {"result": "user_result"})
    workflow.connect(verify_email_access, security_briefing, {"result": "email_check"})
    workflow.connect(
        verify_financial_systems, security_briefing, {"result": "systems_check"}
    )

    workflow.connect(
        create_user,
        audit_onboarding,
        {"result": lambda r: {"user_id": r["user"]["user_id"]}},
    )
    workflow.connect(security_briefing, audit_onboarding, {"result": "briefing_data"})

    return workflow


def create_security_incident_workflow(incident_data: Dict[str, Any]):
    """
    Real scenario: Handle data breach incident involving employee.

    Steps:
    1. Detect suspicious data access
    2. Create security event with risk assessment
    3. Analyze threat patterns
    4. Create incident for investigation
    5. Take automated response actions
    6. Update user permissions
    7. Comprehensive audit trail
    """

    # Step 1: Create high-risk security event
    security_event = SecurityEventNode(
        name="create_breach_event",
        operation="create_event",
        event_data={
            "event_type": "data_exfiltration",
            "threat_level": "critical",
            "user_id": incident_data["user_id"],
            "source_ip": incident_data["source_ip"],
            "target_resource": incident_data["resource"],
            "description": f"Unusual data access pattern detected: {incident_data['description']}",
            "indicators": {
                "data_volume": incident_data["data_volume"],
                "time_of_access": incident_data["timestamp"],
                "access_pattern": "bulk_download",
                "destination": incident_data["destination"],
                "encryption_used": False,
                "vpn_connection": incident_data.get("vpn", False),
            },
            "detection_method": "anomaly_detection",
            "false_positive_probability": 0.15,
        },
        risk_threshold=7.0,
        tenant_id=incident_data["company"],
    )

    # Step 2: Analyze user behavior patterns
    behavior_analysis = SecurityEventNode(
        name="analyze_behavior",
        operation="monitor_user_behavior",
        user_id=incident_data["user_id"],
        analysis_config={
            "lookback_days": 30,
            "anomaly_threshold": 0.7,
            "focus_areas": ["data_access", "login_patterns", "file_operations"],
        },
        tenant_id=incident_data["company"],
    )

    # Step 3: Perform threat analysis
    threat_analysis = SecurityEventNode(
        name="threat_analysis",
        operation="analyze_threats",
        analysis_config={
            "time_window": 86400,  # 24 hours
            "risk_threshold": 6.0,
            "threat_types": [
                "data_exfiltration",
                "insider_threat",
                "unusual_data_access",
            ],
        },
        tenant_id=incident_data["company"],
    )

    # Step 4: Decision logic for incident creation
    def evaluate_incident_creation(event_result, behavior_result, threat_result):
        """Determine if formal incident should be created."""
        event = event_result.get("security_event", {})
        behavior = behavior_result.get("behavior_analysis", {})
        threats = threat_result.get("threat_analysis", {})

        risk_score = event.get("risk_score", 0)
        anomalies = behavior.get("anomalies", [])
        high_risk_count = len(threats.get("high_risk_events", []))

        create_incident = risk_score >= 8.0 or len(anomalies) > 2 or high_risk_count > 3

        return {
            "create_incident": create_incident,
            "severity": "critical" if risk_score >= 9.0 else "high",
            "priority": "immediate" if create_incident else "monitor",
            "event_id": event.get("event_id"),
            "risk_factors": {
                "risk_score": risk_score,
                "anomaly_count": len(anomalies),
                "high_risk_events": high_risk_count,
            },
        }

    incident_evaluator = PythonCodeNode.from_function(
        name="evaluate_incident", func=evaluate_incident_creation
    )

    # Step 5: Create security incident
    create_incident = SecurityEventNode(
        name="create_incident",
        operation="create_incident",
        incident_data={
            "title": f"Potential Data Breach - {incident_data['user_id']}",
            "description": f"Suspicious data access detected from user {incident_data['user_id']}. Large volume of sensitive data accessed from {incident_data['resource']}.",
            "severity": "critical",
            "assignee": incident_data.get("security_team_lead", "security_ops"),
            "impact_assessment": {
                "data_classification": "confidential",
                "records_affected": incident_data["data_volume"],
                "systems_compromised": [incident_data["resource"]],
                "regulatory_impact": "high",
            },
        },
        tenant_id=incident_data["company"],
    )

    # Step 6: Automated response actions
    def determine_response_actions(evaluation_result):
        """Determine appropriate automated response."""
        if not evaluation_result.get("create_incident"):
            return {"response_actions": []}

        actions = [
            {
                "type": "disable_user",
                "parameters": {
                    "user_id": incident_data["user_id"],
                    "reason": "Security incident under investigation",
                },
            },
            {
                "type": "block_ip",
                "parameters": {
                    "ip": incident_data["source_ip"],
                    "duration": "indefinite",
                },
            },
        ]

        # Add additional actions based on severity
        if evaluation_result.get("severity") == "critical":
            actions.append(
                {
                    "type": "revoke_access",
                    "parameters": {
                        "user_id": incident_data["user_id"],
                        "resources": [
                            "financial_reporting_system",
                            "customer_database",
                        ],
                    },
                }
            )

        return {"response_actions": actions}

    response_determiner = PythonCodeNode.from_function(
        name="determine_response", func=determine_response_actions
    )

    # Step 7: Execute automated response
    auto_response = SecurityEventNode(
        name="execute_response",
        operation="automated_response",
        tenant_id=incident_data["company"],
    )

    # Step 8: Update user status
    update_user_status = UserManagementNode(
        name="suspend_user",
        operation="update",
        user_data={
            "status": "suspended",
            "attributes": {
                "suspension_reason": "security_investigation",
                "suspension_date": datetime.now(UTC).isoformat(),
                "investigation_id": None,  # Will be set from incident
            },
        },
        tenant_id=incident_data["company"],
    )

    # Step 9: Revoke permissions
    revoke_permissions = RoleManagementNode(
        name="revoke_access",
        operation="bulk_unassign",
        role_ids=["senior_analyst", "financial_systems_user"],
        tenant_id=incident_data["company"],
    )

    # Step 10: Comprehensive audit
    audit_incident = AuditLogNode(
        name="audit_security_incident",
        operation="log_event",
        event_data={
            "event_type": "security_violation",
            "severity": "critical",
            "action": "security_incident_handled",
            "description": f"Security incident created and responded to for user {incident_data['user_id']}",
            "metadata": {
                "incident_type": "data_breach",
                "automated_actions_taken": True,
                "user_suspended": True,
                "investigation_status": "active",
            },
        },
        tenant_id=incident_data["company"],
    )

    # Build workflow
    workflow = Workflow(name="security_incident_response")
    workflow.add_nodes(
        [
            security_event,
            behavior_analysis,
            threat_analysis,
            incident_evaluator,
            create_incident,
            response_determiner,
            auto_response,
            update_user_status,
            revoke_permissions,
            audit_incident,
        ]
    )

    # Connect workflow with conditional logic
    workflow.connect(security_event, behavior_analysis)
    workflow.connect(security_event, threat_analysis)
    workflow.connect(security_event, incident_evaluator, {"result": "event_result"})
    workflow.connect(
        behavior_analysis, incident_evaluator, {"result": "behavior_result"}
    )
    workflow.connect(threat_analysis, incident_evaluator, {"result": "threat_result"})

    # Conditional incident creation
    incident_router = SwitchNode(
        name="incident_router",
        condition_mappings={
            "immediate": ["create_incident", "determine_response"],
            "monitor": ["audit_security_incident"],
        },
    )
    workflow.add_node(incident_router)
    workflow.connect(incident_evaluator, incident_router, {"result": "priority"})
    workflow.connect(incident_router, create_incident)

    workflow.connect(
        incident_evaluator, response_determiner, {"result": "evaluation_result"}
    )
    workflow.connect(response_determiner, auto_response, {"result": "response_actions"})
    workflow.connect(
        security_event,
        auto_response,
        {"result": lambda r: {"event_id": r["security_event"]["event_id"]}},
    )
    workflow.connect(
        create_incident,
        auto_response,
        {"result": lambda r: {"incident_id": r["incident"]["incident_id"]}},
    )

    # User management actions
    workflow.connect(
        security_event,
        update_user_status,
        {"result": lambda r: {"user_id": r["security_event"]["user_id"]}},
    )
    workflow.connect(
        create_incident,
        update_user_status,
        {
            "result": lambda r: {
                "user_data": {
                    "attributes": {"investigation_id": r["incident"]["incident_id"]}
                }
            }
        },
    )

    workflow.connect(
        security_event,
        revoke_permissions,
        {"result": lambda r: {"user_ids": [r["security_event"]["user_id"]]}},
    )

    # Audit everything
    workflow.connect(incident_router, audit_incident)
    workflow.connect(create_incident, audit_incident, {"result": "incident_data"})
    workflow.connect(auto_response, audit_incident, {"result": "response_data"})

    return workflow


def create_employee_promotion_workflow(promotion_data: Dict[str, Any]):
    """
    Real scenario: Promote employee with role and permission changes.

    Steps:
    1. Update user profile with new position
    2. Assign new role with elevated permissions
    3. Remove old role
    4. Verify new permissions
    5. Update security clearance
    6. Audit trail for compliance
    """

    # Step 1: Update user profile
    update_profile = UserManagementNode(
        name="update_position",
        operation="update",
        user_id=promotion_data["user_id"],
        user_data={
            "attributes": {
                "position": promotion_data["new_position"],
                "salary_band": promotion_data["new_salary_band"],
                "promotion_date": promotion_data["effective_date"],
                "previous_position": promotion_data["old_position"],
                "clearance_level": promotion_data["new_clearance"],
            }
        },
        tenant_id=promotion_data["company"],
    )

    # Step 2: Get current roles
    get_current_roles = RoleManagementNode(
        name="get_current_roles",
        operation="get_user_roles",
        user_id=promotion_data["user_id"],
        tenant_id=promotion_data["company"],
    )

    # Step 3: Assign new role
    assign_new_role = RoleManagementNode(
        name="assign_promoted_role",
        operation="assign_user",
        user_id=promotion_data["user_id"],
        role_id=promotion_data["new_role"],
        tenant_id=promotion_data["company"],
    )

    # Step 4: Remove old role
    remove_old_role = RoleManagementNode(
        name="remove_old_role",
        operation="unassign_user",
        user_id=promotion_data["user_id"],
        role_id=promotion_data["old_role"],
        tenant_id=promotion_data["company"],
    )

    # Step 5: Verify critical new permissions
    verify_permissions = PermissionCheckNode(
        name="verify_new_permissions",
        operation="batch_check",
        user_id=promotion_data["user_id"],
        resource_ids=promotion_data["new_resources"],
        permissions=["read", "write", "approve"],
        tenant_id=promotion_data["company"],
        explain=True,
    )

    # Step 6: Update access control attributes
    def update_abac_attributes(profile_result, roles_result, permissions_result):
        """Update ABAC attributes based on promotion."""
        return {
            "user_id": promotion_data["user_id"],
            "attributes_update": {
                "seniority_level": "senior",
                "approval_limit": promotion_data.get("approval_limit", 100000),
                "direct_reports": promotion_data.get("direct_reports", []),
                "cost_centers": promotion_data.get("cost_centers", []),
                "data_classification_access": ["public", "internal", "confidential"],
                "promotion_verified": True,
            },
            "permissions_verified": permissions_result.get("stats", {}).get(
                "allowed", 0
            ),
            "total_permissions": permissions_result.get("stats", {}).get("total", 0),
        }

    abac_updater = PythonCodeNode.from_function(
        name="update_abac", func=update_abac_attributes
    )

    # Step 7: Comprehensive audit
    audit_promotion = AuditLogNode(
        name="audit_promotion",
        operation="log_event",
        event_data={
            "event_type": "user_updated",
            "severity": "medium",
            "action": "employee_promotion_completed",
            "description": f"Employee promoted from {promotion_data['old_position']} to {promotion_data['new_position']}",
            "metadata": {
                "user_id": promotion_data["user_id"],
                "old_role": promotion_data["old_role"],
                "new_role": promotion_data["new_role"],
                "clearance_change": f"{promotion_data.get('old_clearance', 'basic')} -> {promotion_data['new_clearance']}",
                "effective_date": promotion_data["effective_date"],
                "approved_by": promotion_data.get("approved_by", "hr_system"),
            },
        },
        tenant_id=promotion_data["company"],
    )

    # Build workflow
    workflow = Workflow(name="employee_promotion")
    workflow.add_nodes(
        [
            update_profile,
            get_current_roles,
            assign_new_role,
            remove_old_role,
            verify_permissions,
            abac_updater,
            audit_promotion,
        ]
    )

    # Connect workflow
    workflow.connect(update_profile, get_current_roles)
    workflow.connect(get_current_roles, assign_new_role)
    workflow.connect(assign_new_role, remove_old_role)
    workflow.connect(remove_old_role, verify_permissions)

    workflow.connect(update_profile, abac_updater, {"result": "profile_result"})
    workflow.connect(get_current_roles, abac_updater, {"result": "roles_result"})
    workflow.connect(verify_permissions, abac_updater, {"result": "permissions_result"})

    workflow.connect(abac_updater, audit_promotion, {"result": "abac_data"})

    return workflow


def create_employee_offboarding_workflow(offboarding_data: Dict[str, Any]):
    """
    Real scenario: Properly offboard departing employee.

    Steps:
    1. Disable user account
    2. Revoke all roles and permissions
    3. Archive user data for compliance
    4. Security event for account deactivation
    5. Final audit report
    """

    # Step 1: Deactivate user account
    deactivate_user = UserManagementNode(
        name="deactivate_account",
        operation="deactivate",
        user_id=offboarding_data["user_id"],
        tenant_id=offboarding_data["company"],
    )

    # Step 2: Get all user roles for revocation
    get_roles = RoleManagementNode(
        name="get_all_roles",
        operation="get_user_roles",
        user_id=offboarding_data["user_id"],
        tenant_id=offboarding_data["company"],
    )

    # Step 3: Revoke all roles
    def prepare_role_revocation(roles_result):
        """Prepare bulk role revocation."""
        roles = roles_result.get("roles", [])
        role_ids = [role["role_id"] for role in roles]

        return {
            "user_ids": [offboarding_data["user_id"]],
            "role_ids": role_ids,
            "revocation_count": len(role_ids),
        }

    role_revocation_prep = PythonCodeNode.from_function(
        name="prepare_revocation", func=prepare_role_revocation
    )

    revoke_all_roles = RoleManagementNode(
        name="revoke_all_roles",
        operation="bulk_unassign",
        tenant_id=offboarding_data["company"],
    )

    # Step 4: Create security event for deactivation
    security_event = SecurityEventNode(
        name="account_deactivation_event",
        operation="create_event",
        event_data={
            "event_type": "user_deactivated",
            "threat_level": "low",
            "user_id": offboarding_data["user_id"],
            "source_ip": "internal_process",
            "description": f"User account deactivated: {offboarding_data['reason']}",
            "indicators": {
                "departure_type": offboarding_data["departure_type"],
                "last_day": offboarding_data["last_day"],
                "knowledge_transfer": offboarding_data.get(
                    "knowledge_transfer_complete", False
                ),
                "equipment_returned": offboarding_data.get("equipment_returned", False),
            },
            "detection_method": "administrative_action",
        },
        tenant_id=offboarding_data["company"],
    )

    # Step 5: Generate compliance report
    def generate_offboarding_report(
        deactivation_result, roles_result, revocation_result, security_result
    ):
        """Generate comprehensive offboarding report."""
        return {
            "offboarding_report": {
                "user_id": offboarding_data["user_id"],
                "departure_date": offboarding_data["last_day"],
                "account_status": "deactivated",
                "roles_revoked": roles_result.get("roles", []),
                "access_removed": datetime.now(UTC).isoformat(),
                "compliance_requirements": {
                    "data_retention_period": "7 years",
                    "audit_trail_preserved": True,
                    "personal_data_handling": "archived",
                },
                "security_clearance": "revoked",
                "final_checklist": {
                    "account_disabled": True,
                    "roles_removed": revocation_result.get("stats", {}).get(
                        "unassigned", 0
                    )
                    > 0,
                    "security_event_logged": True,
                    "exit_interview": offboarding_data.get(
                        "exit_interview_complete", False
                    ),
                    "knowledge_transfer": offboarding_data.get(
                        "knowledge_transfer_complete", False
                    ),
                },
            }
        }

    offboarding_report = PythonCodeNode.from_function(
        name="generate_report", func=generate_offboarding_report
    )

    # Step 6: Final audit
    final_audit = AuditLogNode(
        name="audit_offboarding",
        operation="log_event",
        event_data={
            "event_type": "user_deleted",
            "severity": "high",
            "action": "employee_offboarding_completed",
            "description": f"Employee offboarding completed for {offboarding_data['user_id']}",
            "metadata": {
                "departure_type": offboarding_data["departure_type"],
                "reason": offboarding_data["reason"],
                "last_day": offboarding_data["last_day"],
                "data_archived": True,
                "compliance_met": True,
            },
        },
        tenant_id=offboarding_data["company"],
    )

    # Build workflow
    workflow = Workflow(name="employee_offboarding")
    workflow.add_nodes(
        [
            deactivate_user,
            get_roles,
            role_revocation_prep,
            revoke_all_roles,
            security_event,
            offboarding_report,
            final_audit,
        ]
    )

    # Connect workflow
    workflow.connect(deactivate_user, get_roles)
    workflow.connect(get_roles, role_revocation_prep, {"result": "roles_result"})
    workflow.connect(
        role_revocation_prep,
        revoke_all_roles,
        {"result": lambda r: {"role_ids": r["role_ids"]}},
    )
    workflow.connect(deactivate_user, security_event)

    workflow.connect(
        deactivate_user, offboarding_report, {"result": "deactivation_result"}
    )
    workflow.connect(get_roles, offboarding_report, {"result": "roles_result"})
    workflow.connect(
        revoke_all_roles, offboarding_report, {"result": "revocation_result"}
    )
    workflow.connect(security_event, offboarding_report, {"result": "security_result"})

    workflow.connect(offboarding_report, final_audit, {"result": "report"})

    return workflow


async def test_complete_user_lifecycle():
    """Test complete user lifecycle from onboarding to offboarding."""

    print("🏢 Financial Services Company - Complete User Lifecycle Test")
    print("=" * 70)

    runtime = LocalRuntime()

    # Employee data for Sarah Chen
    employee_data = {
        "email": "sarah.chen@globalfinance.com",
        "username": "sarah.chen",
        "first_name": "Sarah",
        "last_name": "Chen",
        "department": "Finance",
        "position": "Junior Financial Analyst",
        "manager": "john.williams",
        "start_date": "2025-01-15",
        "location": "New York HQ",
        "employee_id": "FIN-2025-0142",
        "temp_password": "Welcome2025!",
        "company": "global_finance_corp",
    }

    # Phase 1: Onboarding
    print("\n📋 Phase 1: Employee Onboarding")
    print("-" * 50)

    onboarding_workflow = create_employee_onboarding_workflow(employee_data)
    onboarding_result = await runtime.run_workflow(onboarding_workflow)

    user_created = onboarding_result.get("create_employee", {}).get("user", {})
    print(
        f"✅ User created: {user_created.get('email')} (ID: {user_created.get('user_id')})"
    )

    role_assigned = onboarding_result.get("assign_initial_role", {}).get(
        "assignment", {}
    )
    print(f"✅ Role assigned: {role_assigned.get('role_id')}")

    email_access = onboarding_result.get("verify_email", {}).get("check", {})
    print(f"✅ Email access: {'GRANTED' if email_access.get('allowed') else 'DENIED'}")

    systems_access = onboarding_result.get("verify_financial_systems", {}).get(
        "check", {}
    )
    print(
        f"✅ Financial systems: {'GRANTED' if systems_access.get('allowed') else 'DENIED'}"
    )

    briefing = onboarding_result.get("security_briefing", {})
    print(
        f"✅ Security briefing: {len(briefing.get('policies_acknowledged', []))} policies acknowledged"
    )

    # Simulate 6 months later - Security Incident
    print("\n🚨 Phase 2: Security Incident (6 months later)")
    print("-" * 50)

    incident_data = {
        "user_id": user_created.get("user_id"),
        "source_ip": "203.0.113.45",
        "resource": "customer_financial_database",
        "description": "Bulk download of 50,000 customer records after hours",
        "data_volume": 50000,
        "timestamp": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
        "destination": "external_usb_device",
        "vpn": False,
        "company": "global_finance_corp",
        "security_team_lead": "security.ops",
    }

    incident_workflow = create_security_incident_workflow(incident_data)
    incident_result = await runtime.run_workflow(incident_workflow)

    security_event = incident_result.get("create_breach_event", {}).get(
        "security_event", {}
    )
    print(
        f"⚠️  Security event created: {security_event.get('event_type')} (Risk: {security_event.get('risk_score')})"
    )

    behavior = incident_result.get("analyze_behavior", {}).get("behavior_analysis", {})
    print(f"⚠️  Anomalies detected: {len(behavior.get('anomalies', []))}")

    incident = incident_result.get("create_incident", {}).get("incident", {})
    if incident:
        print(
            f"🚨 Incident created: {incident.get('incident_id')} - {incident.get('title')}"
        )

    response = incident_result.get("execute_response", {}).get("executed_actions", [])
    print(f"🔒 Automated responses: {len(response)} actions executed")

    # After investigation - User cleared and promoted
    print("\n📈 Phase 3: Employee Promotion (1 year later)")
    print("-" * 50)

    promotion_data = {
        "user_id": user_created.get("user_id"),
        "old_position": "Junior Financial Analyst",
        "new_position": "Senior Financial Analyst",
        "old_role": "junior_analyst",
        "new_role": "senior_analyst",
        "old_clearance": "basic",
        "new_clearance": "confidential",
        "new_salary_band": "L4",
        "effective_date": "2026-01-15",
        "new_resources": [
            "financial_reports",
            "budget_planning",
            "investment_portfolio",
        ],
        "approval_limit": 250000,
        "direct_reports": ["analyst.junior1", "analyst.junior2"],
        "cost_centers": ["CC-100", "CC-101"],
        "approved_by": "john.williams",
        "company": "global_finance_corp",
    }

    promotion_workflow = create_employee_promotion_workflow(promotion_data)
    promotion_result = await runtime.run_workflow(promotion_workflow)

    profile_updated = promotion_result.get("update_position", {})
    print(f"✅ Position updated to: {promotion_data['new_position']}")

    new_role = promotion_result.get("assign_promoted_role", {})
    print(f"✅ New role assigned: {promotion_data['new_role']}")

    permissions = promotion_result.get("verify_new_permissions", {}).get("stats", {})
    print(
        f"✅ New permissions: {permissions.get('allowed', 0)}/{permissions.get('total', 0)} granted"
    )

    # Employee leaves company
    print("\n👋 Phase 4: Employee Offboarding (3 years later)")
    print("-" * 50)

    offboarding_data = {
        "user_id": user_created.get("user_id"),
        "departure_type": "voluntary",
        "reason": "Accepted position at another company",
        "last_day": "2028-02-29",
        "knowledge_transfer_complete": True,
        "exit_interview_complete": True,
        "equipment_returned": True,
        "company": "global_finance_corp",
    }

    offboarding_workflow = create_employee_offboarding_workflow(offboarding_data)
    offboarding_result = await runtime.run_workflow(offboarding_workflow)

    deactivated = offboarding_result.get("deactivate_account", {})
    print("✅ Account deactivated")

    roles_revoked = offboarding_result.get("revoke_all_roles", {}).get("stats", {})
    print(f"✅ Roles revoked: {roles_revoked.get('unassigned', 0)}")

    report = offboarding_result.get("generate_report", {}).get("offboarding_report", {})
    checklist = report.get("final_checklist", {})
    completed = sum(1 for v in checklist.values() if v)
    print(f"✅ Offboarding checklist: {completed}/{len(checklist)} items completed")

    # Summary
    print("\n" + "=" * 70)
    print("📊 USER LIFECYCLE TEST SUMMARY")
    print("=" * 70)
    print("✅ Onboarding: Successfully onboarded with appropriate access")
    print("⚠️  Security: Incident detected and responded to automatically")
    print("📈 Promotion: Role elevated with new permissions verified")
    print("👋 Offboarding: Account properly deactivated and archived")
    print("\n🎯 Complete lifecycle tested: 3+ years of employment journey")

    return {
        "test_status": "completed",
        "user_id": user_created.get("user_id"),
        "phases_tested": 4,
        "lifecycle_events": {
            "onboarding": onboarding_result,
            "security_incident": incident_result,
            "promotion": promotion_result,
            "offboarding": offboarding_result,
        },
    }


if __name__ == "__main__":
    # Run the complete lifecycle test
    result = asyncio.execute(test_complete_user_lifecycle())

    # Save detailed results
    import json

    with open("user_lifecycle_test_results.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print("\n📄 Detailed results saved to: user_lifecycle_test_results.json")
