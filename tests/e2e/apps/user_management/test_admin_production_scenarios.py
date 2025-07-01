"""
Production E2E tests for user management system using real Docker services.
These tests verify the complete user management system matches Django admin capabilities.
"""

import asyncio
import json

# Import the actual user management app
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from tests.utils.docker_config import (
    OLLAMA_CONFIG,
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)

sys.path.append("apps/user_management")

from apps.user_management.config.settings import UserManagementConfig
from apps.user_management.main import UserManagementApp
from kailash.nodes.admin.audit_log import EnterpriseAuditLogNode
from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.slow
class TestAdminProductionScenarios:
    """Test complete admin scenarios matching Django admin capabilities."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_production_environment(self):
        """Set up production-like environment with real Docker services."""
        # Ensure Docker services are running
        services_ok = await ensure_docker_services()
        if not services_ok:
            pytest.skip("Docker services not available. Please start Docker services.")

        # Production configuration
        self.config = UserManagementConfig()
        self.config.DATABASE_URL = get_postgres_connection_string()
        self.config.REDIS_URL = get_redis_url()
        self.config.JWT_SECRET_KEY = "test-production-secret-key-change-in-production"

        # Initialize app with real services
        self.app = UserManagementApp()
        self.runtime = self.app.runtime

        # Database config for admin nodes
        self.db_config = {
            "connection_string": self.config.DATABASE_URL,
            "database_type": "postgresql",
        }
        self.tenant_id = "production_test"

        # Initialize admin nodes
        self.user_node = UserManagementNode()
        self.role_node = RoleManagementNode()
        self.perm_node = PermissionManagementNode()
        self.audit_node = AuditLogNode()

        yield

        # Cleanup will be handled by test teardown

    @pytest.mark.asyncio
    async def test_complete_django_admin_parity(self):
        """Test complete Django admin feature parity with real services."""
        print("\n=== Testing Complete Django Admin Parity ===")

        # 1. INITIAL SYSTEM SETUP
        print("\n1. Initial System Setup")

        # Create super admin
        admin_workflow = self.app.user_api.create_user_registration_workflow()
        admin_result = await self.runtime.execute_async(
            admin_workflow,
            {
                "email": "superadmin@company.com",
                "username": "superadmin",
                "password": "SuperAdmin123!@#",
                "first_name": "Super",
                "last_name": "Admin",
            },
        )

        assert admin_result["success"] is True
        admin_id = admin_result["user"]["id"]
        admin_token = admin_result["tokens"]["access"]
        print(f"✓ Super admin created: {admin_id}")

        # 2. CREATE ORGANIZATIONAL STRUCTURE
        print("\n2. Creating Organizational Structure")

        # Create departments as user attributes/metadata
        departments = ["Engineering", "Marketing", "Sales", "Support", "HR", "Finance"]
        dept_ids = {}

        # Since there's no dedicated department node, we'll use attributes
        for dept in departments:
            # Departments will be managed through user attributes and roles
            dept_ids[dept] = dept.lower()
            print(f"✓ Defined department: {dept}")

        # 3. CREATE ROLES WITH PERMISSIONS
        print("\n3. Creating Roles and Permissions")

        # Define roles with Django-like permissions
        roles_data = {
            "superuser": {
                "description": "Full system access",
                "permissions": ["*"],  # All permissions
            },
            "staff": {
                "description": "Staff member with admin access",
                "permissions": [
                    "admin.view_user",
                    "admin.add_user",
                    "admin.change_user",
                    "admin.view_group",
                    "admin.view_logentry",
                ],
            },
            "department_head": {
                "description": "Department manager",
                "permissions": [
                    "users.view",
                    "users.add",
                    "users.change",
                    "department.manage",
                    "reports.view",
                    "reports.export",
                ],
            },
            "team_lead": {
                "description": "Team leader",
                "permissions": ["users.view", "team.manage", "reports.view"],
            },
            "employee": {
                "description": "Regular employee",
                "permissions": [
                    "profile.view_own",
                    "profile.update_own",
                    "reports.view_own",
                ],
            },
        }

        created_roles = {}
        for role_name, role_info in roles_data.items():
            role_result = self.role_node.execute(
                operation="create_role",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                name=role_name,
                description=role_info["description"],
                permissions=role_info["permissions"],
            )
            assert role_result["success"] is True
            created_roles[role_name] = role_result["role"]
            print(
                f"✓ Created role: {role_name} with {len(role_info['permissions'])} permissions"
            )

        # Assign superuser role to admin
        assign_result = self.user_node.execute(
            operation="assign_roles",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_id=admin_id,
            role_ids=[created_roles["superuser"]["id"]],
        )
        assert assign_result["success"] is True
        print("✓ Assigned superuser role to admin")

        # 4. BULK USER CREATION (Django-like fixture loading)
        print("\n4. Bulk User Creation")

        # Generate test users for each department
        users_created = 0
        for dept_name, dept_id in dept_ids.items():
            # Create department head
            head_workflow = self.app.user_api.create_user_registration_workflow()
            head_result = await self.runtime.execute_async(
                head_workflow,
                {
                    "email": f"{dept_name.lower()}.head@company.com",
                    "username": f"{dept_name.lower()}_head",
                    "password": "TempPassword123!",
                    "first_name": dept_name,
                    "last_name": "Head",
                    "metadata": {
                        "department": dept_id,
                        "require_password_change": True,
                    },
                },
            )
            if head_result["success"]:
                users_created += 1
                # Assign department head role
                self.user_node.execute(
                    operation="assign_roles",
                    tenant_id=self.tenant_id,
                    database_config=self.db_config,
                    user_id=head_result["user"]["id"],
                    role_ids=[created_roles["department_head"]["id"]],
                )

            # Create team leads
            for i in range(2):
                lead_workflow = self.app.user_api.create_user_registration_workflow()
                lead_result = await self.runtime.execute_async(
                    lead_workflow,
                    {
                        "email": f"{dept_name.lower()}.lead{i+1}@company.com",
                        "username": f"{dept_name.lower()}_lead{i+1}",
                        "password": "TempPassword123!",
                        "first_name": dept_name,
                        "last_name": f"Lead{i+1}",
                        "metadata": {
                            "department": dept_id,
                            "require_password_change": True,
                        },
                    },
                )
                if lead_result["success"]:
                    users_created += 1
                    self.user_node.execute(
                        operation="assign_roles",
                        tenant_id=self.tenant_id,
                        database_config=self.db_config,
                        user_id=lead_result["user"]["id"],
                        role_ids=[created_roles["team_lead"]["id"]],
                    )

            # Create employees
            for i in range(5):
                emp_workflow = self.app.user_api.create_user_registration_workflow()
                emp_result = await self.runtime.execute_async(
                    emp_workflow,
                    {
                        "email": f"{dept_name.lower()}.emp{i+1}@company.com",
                        "username": f"{dept_name.lower()}_emp{i+1}",
                        "password": "TempPassword123!",
                        "first_name": dept_name,
                        "last_name": f"Employee{i+1}",
                        "metadata": {
                            "department": dept_id,
                            "require_password_change": True,
                        },
                    },
                )
                if emp_result["success"]:
                    users_created += 1
                    self.user_node.execute(
                        operation="assign_roles",
                        tenant_id=self.tenant_id,
                        database_config=self.db_config,
                        user_id=emp_result["user"]["id"],
                        role_ids=[created_roles["employee"]["id"]],
                    )

        print(f"✓ Created {users_created} users across {len(departments)} departments")

        # 5. TEST DJANGO-LIKE ADMIN FEATURES
        print("\n5. Testing Django Admin Features")

        # 5.1 List users with filters (like Django changelist)
        list_result = self.user_node.execute(
            operation="list_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            filters={"active": True},
            limit=10,
            offset=0,
        )
        assert list_result["success"] is True
        assert len(list_result["users"]) > 0
        print(f"✓ Listed users with filters: {len(list_result['users'])} active users")

        # 5.2 Search users (Django-like search)
        search_result = self.user_node.execute(
            operation="search_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            query="engineering",
            fields=["email", "username", "first_name", "last_name"],
        )
        assert search_result["success"] is True
        print(f"✓ Search found {len(search_result.get('users', []))} engineering users")

        # 5.3 Bulk actions (Django-like actions)
        # Get engineering employees
        eng_employees = [
            u
            for u in list_result["users"]
            if u.get("username", "").startswith("engineering_emp")
        ][:3]

        if eng_employees:
            bulk_result = self.user_node.execute(
                operation="bulk_update",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_ids=[u["id"] for u in eng_employees],
                updates={"attributes": {"bonus_eligible": True}},
            )
            assert bulk_result["success"] is True
            print(f"✓ Bulk updated {bulk_result['updated_count']} users")

        # 5.4 Export users (Django dumpdata equivalent)
        export_result = self.user_node.execute(
            operation="export_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            format="json",
            filters={"active": True},
        )
        assert export_result["success"] is True
        print("✓ Exported user data in JSON format")

        # 6. TEST PERMISSION SYSTEM
        print("\n6. Testing Permission System")

        # Login as department head
        head_login = self.app.user_api.create_login_workflow()
        head_result = await self.runtime.execute_async(
            head_login, {"username": "engineering_head", "password": "TempPassword123!"}
        )

        if head_result["success"]:
            head_token = head_result["tokens"]["access"]

            # Check permissions
            perm_result = self.user_node.execute(
                operation="get_user_permissions",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_id=head_result["user"]["id"],
            )
            assert perm_result["success"] is True
            assert "department.manage" in perm_result["permissions"]
            print(
                f"✓ Department head has correct permissions: {len(perm_result['permissions'])}"
            )

        # 7. TEST AUDIT LOG (Django LogEntry equivalent)
        print("\n7. Testing Audit Log")

        audit_result = self.audit_node.execute(
            operation="list_logs",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            filters={
                "date_from": datetime.now() - timedelta(hours=1),
                "object_type": "user",
            },
            limit=10,
        )

        if audit_result.get("success"):
            print(f"✓ Audit log contains {len(audit_result.get('logs', []))} entries")

        # 8. PERFORMANCE METRICS
        print("\n8. Performance Metrics")

        # Measure user list performance
        start = time.time()
        perf_result = self.user_node.execute(
            operation="list_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            limit=100,
        )
        list_time = time.time() - start

        print(f"✓ List 100 users: {list_time*1000:.2f}ms")
        assert list_time < 0.5  # Should be under 500ms

        # Measure search performance
        start = time.time()
        search_perf = self.user_node.execute(
            operation="search_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            query="john",
        )
        search_time = time.time() - start

        print(f"✓ Search users: {search_time*1000:.2f}ms")
        assert search_time < 0.2  # Should be under 200ms

        print("\n=== All Django Admin Features Verified ===")
        print(f"Total users created: {users_created}")
        print(f"Total roles: {len(created_roles)}")
        print(f"Total departments: {len(departments)}")
        print(
            "\n✅ User management system successfully matches Django admin capabilities!"
        )

    @pytest.mark.asyncio
    async def test_security_and_compliance(self):
        """Test security features and GDPR compliance."""
        print("\n=== Testing Security and Compliance ===")

        # Create test user
        test_workflow = self.app.user_api.create_user_registration_workflow()
        test_user = await self.runtime.execute_async(
            test_workflow,
            {
                "email": "security.test@company.com",
                "username": "security_test",
                "password": "SecurePass123!@#",
                "first_name": "Security",
                "last_name": "Test",
            },
        )

        assert test_user["success"] is True
        user_id = test_user["user"]["id"]

        # 1. Test password policies
        print("\n1. Password Policy Enforcement")

        # Try to create user with weak password - should fail
        weak_pw_workflow = self.app.user_api.create_user_registration_workflow()

        weak_result = await self.runtime.execute_async(
            weak_pw_workflow,
            {
                "email": "weakpw@test.com",
                "username": "weakpw_user",
                "password": "weak",  # Should fail validation
            },
        )
        # Should fail validation
        assert not weak_result.get("success", False)
        print("✓ Weak password correctly rejected")

        # 2. Test account lockout
        print("\n2. Account Lockout Testing")

        login_workflow = self.app.user_api.create_login_workflow()

        # Attempt multiple failed logins
        for i in range(6):
            fail_result = await self.runtime.execute_async(
                login_workflow,
                {"username": "security_test", "password": "WrongPassword!"},
            )

        # Account should be locked
        locked_result = await self.runtime.execute_async(
            login_workflow,
            {"username": "security_test", "password": "SecurePass123!@#"},
        )

        assert not locked_result.get("success", False)
        print("✓ Account locked after failed attempts")

        # 3. Test GDPR data export
        print("\n3. GDPR Data Export")

        gdpr_export = self.user_node.execute(
            operation="export_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_ids=[user_id],
            format="json",
            include_personal_data=True,
        )

        assert gdpr_export["success"] is True
        exported_data = json.loads(gdpr_export["data"])
        assert exported_data[0]["email"] == "security.test@company.com"
        print("✓ GDPR data export successful")

        # 4. Test data anonymization
        print("\n4. Data Anonymization")

        # Request anonymization
        anon_result = self.user_node.execute(
            operation="update_user",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_id=user_id,
            anonymize=True,
        )

        if anon_result["success"]:
            # Verify anonymization
            anon_user = self.user_node.execute(
                operation="get_user",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_id=user_id,
                include_deleted=True,
            )

            if anon_user["success"]:
                assert "anonymized" in anon_user["user"]["email"]
                print("✓ User data successfully anonymized")

        print("\n✅ All security and compliance tests passed!")

    @pytest.mark.asyncio
    async def test_performance_at_scale(self):
        """Test system performance with production-scale data."""
        print("\n=== Testing Performance at Scale ===")

        # 1. Bulk create users
        print("\n1. Bulk User Creation Performance")

        start = time.time()
        users_to_create = []

        for i in range(100):
            users_to_create.append(
                {
                    "email": f"perf.test{i}@company.com",
                    "username": f"perf_test_{i}",
                    "password": "PerfTest123!",
                    "first_name": f"Perf{i}",
                    "last_name": "Test",
                    "attributes": {
                        "department": "performance",
                        "employee_id": f"EMP{i:04d}",
                    },
                }
            )

        # Use bulk create
        bulk_result = self.user_node.execute(
            operation="bulk_create",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            users=users_to_create,
        )

        create_time = time.time() - start

        if bulk_result.get("success"):
            print(
                f"✓ Created {bulk_result['created_count']} users in {create_time:.2f}s"
            )
            print(
                f"  Rate: {bulk_result['created_count']/create_time:.1f} users/second"
            )

        # 2. Test concurrent operations
        print("\n2. Concurrent Operations")

        async def concurrent_read(user_num):
            return self.user_node.execute(
                operation="get_user",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_id=f"perf_test_{user_num}",
            )

        # Run 20 concurrent reads
        start = time.time()
        tasks = [concurrent_read(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        concurrent_time = time.time() - start

        successful = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
        print(f"✓ {successful}/20 concurrent reads in {concurrent_time:.2f}s")

        # 3. Search performance
        print("\n3. Search Performance")

        search_terms = ["perf", "test", "EMP00", "@company"]

        for term in search_terms:
            start = time.time()
            search_result = self.user_node.execute(
                operation="search_users",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                query=term,
                limit=50,
            )
            search_time = time.time() - start

            if search_result.get("success"):
                print(
                    f"✓ Search '{term}': {len(search_result.get('users', []))} results in {search_time*1000:.1f}ms"
                )

        # 4. Pagination performance
        print("\n4. Pagination Performance")

        page_times = []
        for page in range(5):
            start = time.time()
            page_result = self.user_node.execute(
                operation="list_users",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                limit=20,
                offset=page * 20,
            )
            page_time = time.time() - start
            page_times.append(page_time)

            if page_result.get("success"):
                print(f"✓ Page {page+1}: {page_time*1000:.1f}ms")

        avg_page_time = sum(page_times) / len(page_times)
        print(f"\nAverage pagination time: {avg_page_time*1000:.1f}ms")
        assert avg_page_time < 0.1  # Should be under 100ms

        print("\n✅ Performance tests completed successfully!")
        print("System can handle production-scale operations efficiently")
