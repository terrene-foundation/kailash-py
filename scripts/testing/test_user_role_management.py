#!/usr/bin/env python3
"""
User and Role Management Test Suite

Comprehensive tests for user management, role management, and permission systems.
Tests CRUD operations, hierarchical roles, ABAC integration, and audit trails.
"""

import asyncio
import json
import tempfile
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import pytest

# Import management nodes
from kailash.nodes.admin import (
    PermissionCheckNode,
    RoleManagementNode,
    UserManagementNode,
)
from kailash.nodes.security import AuditLogNode, SecurityEventNode
from kailash.nodes.security.abac_evaluator import ABACPermissionEvaluatorNode
from kailash.runtime.local import LocalRuntime

# Import workflow components for integration tests
from kailash.workflow import WorkflowBuilder


class TestUserManagement:
    """Test suite for UserManagementNode."""

    @pytest.mark.asyncio
    async def test_user_crud_operations(self):
        """Test complete user CRUD operations."""
        print("\n👤 Testing User CRUD Operations...")

        user_mgmt = UserManagementNode(
            operation="create",
            abac_enabled=True,
            audit_enabled=True,
            password_policy={
                "min_length": 12,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_numbers": True,
                "require_special": True,
                "history_count": 5,
            },
        )

        # Test user creation
        create_result = await user_mgmt.execute_async(
            operation="create",
            user_data={
                "username": "john.doe",
                "email": "john.doe@company.com",
                "full_name": "John Doe",
                "department": "Engineering",
                "employee_id": "EMP001",
                "password": "SecureP@ssw0rd123!",
            },
            initial_roles=["developer", "team_member"],
            metadata={
                "created_by": "admin_user",
                "onboarding_date": datetime.now(UTC).isoformat(),
            },
        )

        assert create_result["success"] is True
        assert "user_id" in create_result
        assert create_result["username"] == "john.doe"
        assert len(create_result["assigned_roles"]) == 2

        user_id = create_result["user_id"]

        # Test user read/retrieval
        read_result = await user_mgmt.execute_async(
            operation="read",
            user_id=user_id,
            include_roles=True,
            include_permissions=True,
            include_metadata=True,
        )

        assert read_result["success"] is True
        assert read_result["user"]["username"] == "john.doe"
        assert "roles" in read_result["user"]
        assert "permissions" in read_result["user"]
        assert "metadata" in read_result["user"]

        # Test user update
        update_result = await user_mgmt.execute_async(
            operation="update",
            user_id=user_id,
            updates={
                "department": "Engineering - Backend",
                "title": "Senior Developer",
                "phone": "+1-555-123-4567",
            },
            audit_reason="Promotion to senior role",
        )

        assert update_result["success"] is True
        assert update_result["fields_updated"] == ["department", "title", "phone"]

        # Test user search
        search_result = await user_mgmt.execute_async(
            operation="search",
            filters={"department": "Engineering", "status": "active"},
            sort_by="created_at",
            limit=10,
        )

        assert search_result["success"] is True
        assert search_result["total_count"] >= 1
        assert any(u["username"] == "john.doe" for u in search_result["users"])

        # Test user deactivation (soft delete)
        deactivate_result = await user_mgmt.execute_async(
            operation="deactivate",
            user_id=user_id,
            reason="Test deactivation",
            preserve_data=True,
        )

        assert deactivate_result["success"] is True
        assert deactivate_result["status"] == "deactivated"
        assert deactivate_result["data_preserved"] is True

        # Test user reactivation
        reactivate_result = await user_mgmt.execute_async(
            operation="reactivate",
            user_id=user_id,
            require_password_reset=True,
            require_mfa_setup=True,
        )

        assert reactivate_result["success"] is True
        assert reactivate_result["status"] == "active"
        assert reactivate_result["password_reset_required"] is True

        print("✅ User CRUD Operations test passed")

    @pytest.mark.asyncio
    async def test_user_bulk_operations(self):
        """Test bulk user operations."""
        print("\n👥 Testing User Bulk Operations...")

        user_mgmt = UserManagementNode(operation="bulk_create", abac_enabled=True)

        # Test bulk user creation
        users_data = [
            {
                "username": f"user{i}",
                "email": f"user{i}@company.com",
                "full_name": f"Test User {i}",
                "department": ["Engineering", "Sales", "Marketing"][i % 3],
                "password": f"TempP@ssw0rd{i}!",
            }
            for i in range(5)
        ]

        bulk_create_result = await user_mgmt.execute_async(
            operation="bulk_create",
            users=users_data,
            initial_roles=["employee"],
            send_welcome_email=False,
            require_password_change=True,
        )

        assert bulk_create_result["success"] is True
        assert bulk_create_result["created_count"] == 5
        assert len(bulk_create_result["user_ids"]) == 5

        # Test bulk update
        bulk_update_result = await user_mgmt.execute_async(
            operation="bulk_update",
            user_ids=bulk_create_result["user_ids"],
            updates={"location": "Remote", "timezone": "UTC"},
            audit_reason="Bulk location update",
        )

        assert bulk_update_result["success"] is True
        assert bulk_update_result["updated_count"] == 5

        # Test bulk role assignment
        bulk_role_result = await user_mgmt.execute_async(
            operation="bulk_assign_roles",
            filters={"department": "Engineering"},
            roles_to_add=["developer"],
            roles_to_remove=[],
        )

        assert bulk_role_result["success"] is True
        assert bulk_role_result["users_affected"] > 0

        print("✅ User Bulk Operations test passed")

    @pytest.mark.asyncio
    async def test_user_password_management(self):
        """Test password management features."""
        print("\n🔐 Testing User Password Management...")

        user_mgmt = UserManagementNode(
            operation="password_reset",
            password_policy={
                "min_length": 14,
                "max_length": 128,
                "require_uppercase": True,
                "require_lowercase": True,
                "require_numbers": True,
                "require_special": True,
                "disallow_common": True,
                "disallow_username": True,
                "history_count": 10,
                "max_age_days": 90,
            },
        )

        user_id = "test_user_pwd"

        # Test password reset initiation
        reset_result = await user_mgmt.execute_async(
            operation="initiate_password_reset",
            user_id=user_id,
            delivery_method="email",
            token_validity_hours=24,
        )

        assert reset_result["success"] is True
        assert "reset_token" in reset_result
        assert reset_result["expires_at"] is not None

        # Test password validation
        validation_result = await user_mgmt.execute_async(
            operation="validate_password",
            user_id=user_id,
            password="WeakPass123",  # Should fail
            check_history=True,
        )

        assert validation_result["valid"] is False
        assert len(validation_result["violations"]) > 0
        assert "require_special" in validation_result["violations"]

        # Test strong password
        strong_validation = await user_mgmt.execute_async(
            operation="validate_password",
            user_id=user_id,
            password="Str0ng!P@ssw0rd#2024",
            check_history=True,
        )

        assert strong_validation["valid"] is True
        assert strong_validation["strength_score"] > 0.8

        # Test password history
        history_result = await user_mgmt.execute_async(
            operation="get_password_history", user_id=user_id, include_metadata=True
        )

        assert history_result["success"] is True
        assert "history_count" in history_result
        assert isinstance(history_result["password_changes"], list)

        print("✅ User Password Management test passed")

    @pytest.mark.asyncio
    async def test_user_session_management(self):
        """Test user session management."""
        print("\n🔑 Testing User Session Management...")

        user_mgmt = UserManagementNode(operation="session_management")

        user_id = "session_test_user"

        # Test getting active sessions
        sessions_result = await user_mgmt.execute_async(
            operation="get_active_sessions", user_id=user_id
        )

        assert sessions_result["success"] is True
        assert "sessions" in sessions_result
        assert isinstance(sessions_result["sessions"], list)

        # Test terminating specific session
        if sessions_result["sessions"]:
            terminate_result = await user_mgmt.execute_async(
                operation="terminate_session",
                user_id=user_id,
                session_id=sessions_result["sessions"][0]["session_id"],
                reason="security_check",
            )

            assert terminate_result["success"] is True
            assert terminate_result["terminated"] is True

        # Test terminating all sessions
        terminate_all_result = await user_mgmt.execute_async(
            operation="terminate_all_sessions",
            user_id=user_id,
            except_current=False,
            reason="password_change",
        )

        assert terminate_all_result["success"] is True
        assert "sessions_terminated" in terminate_all_result

        print("✅ User Session Management test passed")


class TestRoleManagement:
    """Test suite for RoleManagementNode."""

    @pytest.mark.asyncio
    async def test_role_crud_operations(self):
        """Test role CRUD operations."""
        print("\n👑 Testing Role CRUD Operations...")

        role_mgmt = RoleManagementNode(
            operation="create", hierarchical=True, audit_enabled=True
        )

        # Test role creation
        create_result = await role_mgmt.execute_async(
            operation="create",
            role_data={
                "name": "senior_developer",
                "display_name": "Senior Developer",
                "description": "Senior development team member",
                "department": "Engineering",
                "level": 3,
            },
            permissions=["code:read", "code:write", "code:review", "deploy:staging"],
            parent_role="developer",
        )

        assert create_result["success"] is True
        assert "role_id" in create_result
        assert create_result["name"] == "senior_developer"
        assert len(create_result["permissions"]) == 4

        role_id = create_result["role_id"]

        # Test role read
        read_result = await role_mgmt.execute_async(
            operation="read",
            role_id=role_id,
            include_permissions=True,
            include_users=True,
            include_hierarchy=True,
        )

        assert read_result["success"] is True
        assert read_result["role"]["name"] == "senior_developer"
        assert "permissions" in read_result["role"]
        assert "parent_role" in read_result["role"]

        # Test role update
        update_result = await role_mgmt.execute_async(
            operation="update",
            role_id=role_id,
            updates={
                "description": "Senior development team member with deployment access",
                "level": 4,
            },
            add_permissions=["deploy:production"],
            remove_permissions=[],
        )

        assert update_result["success"] is True
        assert "deploy:production" in update_result["permissions"]

        # Test role hierarchy
        hierarchy_result = await role_mgmt.execute_async(
            operation="get_hierarchy",
            role_id=role_id,
            include_ancestors=True,
            include_descendants=True,
        )

        assert hierarchy_result["success"] is True
        assert "ancestors" in hierarchy_result
        assert "descendants" in hierarchy_result
        assert hierarchy_result["depth"] > 0

        # Test role deletion (with safety checks)
        delete_result = await role_mgmt.execute_async(
            operation="delete",
            role_id=role_id,
            reassign_users_to="developer",
            force=False,
        )

        assert delete_result["success"] is True
        assert delete_result["users_reassigned"] >= 0

        print("✅ Role CRUD Operations test passed")

    @pytest.mark.asyncio
    async def test_role_permission_management(self):
        """Test role permission management."""
        print("\n🔓 Testing Role Permission Management...")

        role_mgmt = RoleManagementNode(operation="manage_permissions")

        role_id = "test_role_perms"

        # Test permission assignment
        assign_result = await role_mgmt.execute_async(
            operation="assign_permissions",
            role_id=role_id,
            permissions=[
                "resource:read",
                "resource:write",
                "resource:delete",
                "admin:users:read",
            ],
            permission_metadata={
                "resource:delete": {"requires_approval": True},
                "admin:users:read": {"scope": "department"},
            },
        )

        assert assign_result["success"] is True
        assert len(assign_result["assigned_permissions"]) == 4

        # Test permission inheritance
        inheritance_result = await role_mgmt.execute_async(
            operation="get_effective_permissions",
            role_id=role_id,
            include_inherited=True,
            include_source=True,
        )

        assert inheritance_result["success"] is True
        assert "direct_permissions" in inheritance_result
        assert "inherited_permissions" in inheritance_result
        assert len(inheritance_result["all_permissions"]) >= 4

        # Test permission conflicts
        conflict_result = await role_mgmt.execute_async(
            operation="check_permission_conflicts",
            role_id=role_id,
            new_permissions=["resource:deny_all"],
        )

        assert conflict_result["success"] is True
        assert conflict_result["has_conflicts"] is True
        assert len(conflict_result["conflicts"]) > 0

        # Test permission audit
        audit_result = await role_mgmt.execute_async(
            operation="audit_permissions",
            role_id=role_id,
            check_unused=True,
            check_excessive=True,
        )

        assert audit_result["success"] is True
        assert "unused_permissions" in audit_result
        assert "excessive_permissions" in audit_result
        assert "recommendations" in audit_result

        print("✅ Role Permission Management test passed")

    @pytest.mark.asyncio
    async def test_role_assignment_workflows(self):
        """Test role assignment workflows."""
        print("\n📋 Testing Role Assignment Workflows...")

        role_mgmt = RoleManagementNode(operation="assignment_workflow")

        # Test role request
        request_result = await role_mgmt.execute_async(
            operation="request_role",
            user_id="user_123",
            role_id="senior_developer",
            justification="Promoted to senior position",
            duration_days=365,
            approvers=["manager_456", "director_789"],
        )

        assert request_result["success"] is True
        assert "request_id" in request_result
        assert request_result["status"] == "pending_approval"

        request_id = request_result["request_id"]

        # Test approval workflow
        approval_result = await role_mgmt.execute_async(
            operation="approve_request",
            request_id=request_id,
            approver_id="manager_456",
            comments="Approved based on performance review",
            conditions={"require_training": True, "probation_days": 30},
        )

        assert approval_result["success"] is True
        assert approval_result["approval_status"] == "partially_approved"
        assert approval_result["approvals_needed"] == 1

        # Test temporary role assignment
        temp_assign_result = await role_mgmt.execute_async(
            operation="assign_temporary_role",
            user_id="user_789",
            role_id="admin",
            duration_hours=24,
            reason="Emergency access for incident response",
            auto_revoke=True,
        )

        assert temp_assign_result["success"] is True
        assert "assignment_id" in temp_assign_result
        assert "expires_at" in temp_assign_result
        assert temp_assign_result["auto_revoke_scheduled"] is True

        # Test role delegation
        delegation_result = await role_mgmt.execute_async(
            operation="delegate_role",
            from_user_id="manager_123",
            to_user_id="deputy_456",
            role_id="approver",
            delegation_scope=["expense_approval", "time_approval"],
            expires_at=(datetime.now(UTC) + timedelta(days=14)).isoformat(),
        )

        assert delegation_result["success"] is True
        assert "delegation_id" in delegation_result
        assert len(delegation_result["delegated_permissions"]) > 0

        print("✅ Role Assignment Workflows test passed")

    @pytest.mark.asyncio
    async def test_role_templates(self):
        """Test role template functionality."""
        print("\n📄 Testing Role Templates...")

        role_mgmt = RoleManagementNode(operation="template_management")

        # Test creating role from template
        template_result = await role_mgmt.execute_async(
            operation="create_from_template",
            template_name="engineering_lead",
            customizations={
                "department": "Backend Engineering",
                "additional_permissions": ["deploy:production"],
                "remove_permissions": ["finance:read"],
            },
        )

        assert template_result["success"] is True
        assert "role_id" in template_result
        assert template_result["based_on_template"] == "engineering_lead"

        # Test listing available templates
        templates_result = await role_mgmt.execute_async(
            operation="list_templates", category="engineering", include_permissions=True
        )

        assert templates_result["success"] is True
        assert len(templates_result["templates"]) > 0
        assert any(
            t["name"] == "engineering_lead" for t in templates_result["templates"]
        )

        # Test template recommendations
        recommend_result = await role_mgmt.execute_async(
            operation="recommend_template",
            user_profile={
                "department": "Engineering",
                "seniority": "senior",
                "team_size": 5,
                "responsibilities": ["code_review", "mentoring", "architecture"],
            },
        )

        assert recommend_result["success"] is True
        assert len(recommend_result["recommendations"]) > 0
        assert recommend_result["recommendations"][0]["confidence"] > 0.7

        print("✅ Role Templates test passed")


class TestPermissionSystem:
    """Test suite for permission system."""

    @pytest.mark.asyncio
    async def test_permission_check_basic(self):
        """Test basic permission checking."""
        print("\n🔒 Testing Basic Permission Checking...")

        perm_check = PermissionCheckNode(
            resource="document", action="read", use_cache=True, cache_ttl=300
        )

        # Test simple permission check
        result = await perm_check.execute_async(
            user_id="user_123",
            resource="document:12345",
            action="read",
            context={
                "document_owner": "user_456",
                "document_classification": "internal",
                "user_department": "engineering",
            },
        )

        assert result["success"] is True
        assert "allowed" in result
        assert "reason" in result
        assert "evaluation_time_ms" in result

        # Test with user roles
        role_result = await perm_check.execute_async(
            user_id="user_123",
            user_roles=["developer", "team_lead"],
            resource="code_repository",
            action="merge",
            context={
                "repository": "backend-api",
                "branch": "main",
                "pr_approved": True,
            },
        )

        assert role_result["success"] is True
        assert isinstance(role_result["allowed"], bool)

        print("✅ Basic Permission Checking test passed")

    @pytest.mark.asyncio
    async def test_permission_check_abac(self):
        """Test ABAC permission checking."""
        print("\n🛡️ Testing ABAC Permission Checking...")

        abac_check = PermissionCheckNode(
            resource="sensitive_data",
            action="export",
            evaluation_mode="abac",
            policy_engine="inline",
        )

        # Complex ABAC scenario
        abac_result = await abac_check.execute_async(
            user_context={
                "user_id": "analyst_123",
                "roles": ["data_analyst"],
                "clearance_level": 3,
                "department": "analytics",
                "location": "US",
                "certifications": ["gdpr_trained", "security_cleared"],
            },
            resource_context={
                "resource_id": "dataset_456",
                "classification": "confidential",
                "data_type": "customer_analytics",
                "size_gb": 50,
                "contains_pii": True,
                "owner_department": "analytics",
            },
            action_context={
                "action": "export",
                "format": "csv",
                "destination": "secure_storage",
                "purpose": "quarterly_analysis",
                "retention_days": 30,
            },
            environment_context={
                "time": datetime.now(UTC).isoformat(),
                "day_of_week": "tuesday",
                "business_hours": True,
                "network": "corporate_vpn",
                "device_trusted": True,
                "mfa_verified": True,
            },
        )

        assert abac_result["success"] is True
        assert "allowed" in abac_result
        assert "applied_policies" in abac_result
        assert "attribute_evaluation" in abac_result

        # Test policy explanation
        if not abac_result["allowed"]:
            assert "denial_reasons" in abac_result
            assert len(abac_result["denial_reasons"]) > 0

        print("✅ ABAC Permission Checking test passed")

    @pytest.mark.asyncio
    async def test_permission_inheritance(self):
        """Test permission inheritance and precedence."""
        print("\n🌳 Testing Permission Inheritance...")

        perm_check = PermissionCheckNode(
            resource="project", action="manage", check_inheritance=True
        )

        # Test with role hierarchy
        hierarchy_result = await perm_check.execute_async(
            user_id="user_123",
            user_roles=["team_member", "project_lead", "department_manager"],
            resource="project:alpha",
            action="manage",
            check_mode="most_permissive",  # or "most_restrictive"
            context={"project_status": "active", "user_is_owner": False},
        )

        assert hierarchy_result["success"] is True
        assert "effective_permission" in hierarchy_result
        assert "permission_sources" in hierarchy_result

        # Check which role granted permission
        if hierarchy_result["allowed"]:
            assert len(hierarchy_result["permission_sources"]) > 0
            assert "role" in hierarchy_result["permission_sources"][0]

        print("✅ Permission Inheritance test passed")

    @pytest.mark.asyncio
    async def test_dynamic_permissions(self):
        """Test dynamic permission evaluation."""
        print("\n🔄 Testing Dynamic Permissions...")

        perm_check = PermissionCheckNode(
            resource="budget", action="approve", enable_dynamic_permissions=True
        )

        # Test amount-based permissions
        amounts = [100, 1000, 10000, 100000]
        user_roles = ["employee", "manager", "director", "cfo"]

        for amount, role in zip(amounts, user_roles):
            result = await perm_check.execute_async(
                user_id=f"user_{role}",
                user_roles=[role],
                resource="expense_report",
                action="approve",
                context={
                    "amount": amount,
                    "currency": "USD",
                    "category": "travel",
                    "user_level": user_roles.index(role) + 1,
                },
            )

            assert result["success"] is True
            # Higher roles should be able to approve higher amounts
            if user_roles.index(role) >= amounts.index(amount):
                assert result["allowed"] is True

        # Test time-based permissions
        time_result = await perm_check.execute_async(
            user_id="contractor_123",
            user_roles=["contractor"],
            resource="office_system",
            action="access",
            context={
                "current_time": "14:00",
                "day_of_week": "monday",
                "contract_hours": "09:00-17:00",
                "contract_days": [
                    "monday",
                    "tuesday",
                    "wednesday",
                    "thursday",
                    "friday",
                ],
            },
        )

        assert time_result["success"] is True
        assert time_result["allowed"] is True

        print("✅ Dynamic Permissions test passed")


class TestIntegratedUserRolePermissions:
    """Test integrated user, role, and permission workflows."""

    @pytest.mark.asyncio
    async def test_complete_user_lifecycle(self):
        """Test complete user lifecycle with roles and permissions."""
        print("\n🔄 Testing Complete User Lifecycle...")

        # Initialize nodes
        user_mgmt = UserManagementNode(operation="create", abac_enabled=True)
        role_mgmt = RoleManagementNode(operation="assign")
        perm_check = PermissionCheckNode(resource="system", action="access")
        audit_log = AuditLogNode(compliance_tags=["user_management"])

        # Step 1: Create new user
        user_result = await user_mgmt.execute_async(
            operation="create",
            user_data={
                "username": "lifecycle.test",
                "email": "lifecycle@company.com",
                "full_name": "Lifecycle Test User",
                "department": "IT",
            },
            initial_roles=["employee"],
            send_welcome_email=False,
        )

        assert user_result["success"] is True
        user_id = user_result["user_id"]

        # Step 2: Assign additional role
        role_result = await role_mgmt.execute_async(
            operation="assign_role",
            user_id=user_id,
            role_id="developer",
            effective_from=datetime.now(UTC).isoformat(),
        )

        assert role_result["success"] is True

        # Step 3: Check permissions
        perm_result = await perm_check.execute_async(
            user_id=user_id, resource="git_repository", action="push"
        )

        assert perm_result["success"] is True
        assert perm_result["allowed"] is True

        # Step 4: Audit the operation
        audit_result = await audit_log.execute_async(
            action="user_lifecycle",
            user_id=user_id,
            details={
                "lifecycle_stage": "onboarding",
                "roles_assigned": ["employee", "developer"],
                "permissions_verified": True,
            },
        )

        assert audit_result["audit_logged"] is True

        # Step 5: Update user status
        update_result = await user_mgmt.execute_async(
            operation="update",
            user_id=user_id,
            updates={"status": "active", "onboarding_completed": True},
        )

        assert update_result["success"] is True

        print("✅ Complete User Lifecycle test passed")

    @pytest.mark.asyncio
    async def test_security_workflow_integration(self):
        """Test integration with security monitoring."""
        print("\n🔐 Testing Security Workflow Integration...")

        # Create workflow with user management and security nodes
        builder = WorkflowBuilder("security_user_workflow")

        # Add nodes
        user_check = builder.add_node(
            "UserManagementNode",
            node_id="user_check",
            config={"operation": "validate_user"},
        )

        perm_check = builder.add_node(
            "PermissionCheckNode",
            node_id="perm_check",
            config={"resource": "sensitive_data", "action": "access"},
        )

        security_event = builder.add_node(
            "SecurityEventNode",
            node_id="security_event",
            config={"severity_threshold": "MEDIUM", "enable_alerting": True},
        )

        audit = builder.add_node(
            "AuditLogNode",
            node_id="audit",
            config={"compliance_tags": ["security", "access_control"]},
        )

        # Connect nodes
        builder.add_connection(user_check, "validated", perm_check, "user_context")
        builder.add_connection(perm_check, "result", security_event, "access_attempt")
        builder.add_connection(security_event, "event", audit, "details")

        # Build and run workflow
        workflow = builder.build()
        runtime = LocalRuntime(enable_async=True)

        result = await runtime.execute_async(
            workflow,
            initial_inputs={
                "user_id": "test_user_123",
                "requested_resource": "customer_database",
                "ip_address": "192.168.1.100",
            },
        )

        assert result is not None
        assert "audit" in result

        print("✅ Security Workflow Integration test passed")

    @pytest.mark.asyncio
    async def test_role_based_workflow_routing(self):
        """Test workflow routing based on user roles."""
        print("\n🚦 Testing Role-Based Workflow Routing...")

        # Create nodes
        user_mgmt = UserManagementNode(operation="get_user")
        perm_check = PermissionCheckNode(resource="workflow", action="execute")

        # Test different role scenarios
        test_cases = [
            {
                "user_id": "admin_user",
                "roles": ["admin", "power_user"],
                "expected_workflow": "admin_workflow",
            },
            {
                "user_id": "regular_user",
                "roles": ["employee"],
                "expected_workflow": "standard_workflow",
            },
            {
                "user_id": "guest_user",
                "roles": ["guest"],
                "expected_workflow": "limited_workflow",
            },
        ]

        for test_case in test_cases:
            # Get user with roles
            user_result = await user_mgmt.execute_async(
                operation="get_user_with_roles", user_id=test_case["user_id"]
            )

            # Check workflow permissions
            workflow_perm = await perm_check.execute_async(
                user_id=test_case["user_id"],
                user_roles=test_case["roles"],
                resource=f"workflow:{test_case['expected_workflow']}",
                action="execute",
            )

            assert workflow_perm["success"] is True
            assert workflow_perm["allowed"] is True

        print("✅ Role-Based Workflow Routing test passed")


async def run_all_tests():
    """Run all user and role management tests."""
    print("👤 Starting User and Role Management Test Suite")
    print("=" * 80)

    test_suites = [
        ("User Management", TestUserManagement()),
        ("Role Management", TestRoleManagement()),
        ("Permission System", TestPermissionSystem()),
        ("Integrated Workflows", TestIntegratedUserRolePermissions()),
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = 0

    for suite_name, test_suite in test_suites:
        print(f"\n📦 Running {suite_name} Tests...")
        print("-" * 60)

        # Get all test methods
        test_methods = [
            method
            for method in dir(test_suite)
            if method.startswith("test_") and callable(getattr(test_suite, method))
        ]

        for test_name in test_methods:
            total_tests += 1
            try:
                test_method = getattr(test_suite, test_name)
                await test_method()
                passed_tests += 1
            except Exception as e:
                print(f"❌ {test_name} failed: {str(e)}")
                import traceback

                traceback.print_exc()
                failed_tests += 1

    # Print summary
    print("\n" + "=" * 80)
    print("📊 Test Summary:")
    print(f"   • Total tests: {total_tests}")
    print(f"   • Passed: {passed_tests} ✅")
    print(f"   • Failed: {failed_tests} ❌")
    print(f"   • Success rate: {(passed_tests/total_tests*100):.1f}%")

    if failed_tests == 0:
        print("\n🎉 All user and role management tests passed successfully!")
        print("✅ User CRUD operations validated")
        print("✅ Role management and hierarchy validated")
        print("✅ Permission system (RBAC/ABAC) validated")
        print("✅ Integrated workflows validated")
        return True
    else:
        print(f"\n⚠️ {failed_tests} tests failed. Please review the errors above.")
        return False


if __name__ == "__main__":
    success = asyncio.execute(run_all_tests())
    exit(0 if success else 1)
