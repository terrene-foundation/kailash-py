"""End-to-end tests for admin scenarios using real Docker services."""

import asyncio
import json
from datetime import datetime, timedelta

import pytest
import pytest_asyncio

# Import the user management app
from apps.user_management.main import create_user_management_app
from kailash.middleware.communication.api_gateway import create_gateway
from kailash.runtime.local import LocalRuntime
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
    get_redis_url,
)


@pytest.mark.e2e
@pytest.mark.requires_docker
@pytest.mark.slow
class TestAdminE2EScenarios:
    """Test complete admin scenarios with real infrastructure."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup_infrastructure(self):
        """Set up complete infrastructure for E2E tests."""
        # Ensure Docker services are running
        services_ok = await ensure_docker_services()
        if not services_ok:
            pytest.skip("Docker services not available")

        # Database configuration
        self.db_url = get_postgres_connection_string("e2e_user_mgmt")
        self.redis_url = get_redis_url()

        # Create the user management app instance
        from apps.user_management.main import UserManagementApp

        self.app_manager = UserManagementApp()

        # Configure the app with test settings
        self.app_manager.config.DATABASE_URL = self.db_url
        self.app_manager.config.REDIS_URL = self.redis_url
        self.app_manager.config.JWT_SECRET_KEY = "test-secret-key"

        # Create the FastAPI app
        self.app = self.app_manager.create_app()

        # Get runtime
        self.runtime = self.app_manager.runtime

        yield

        # Cleanup
        await self.app.shutdown()

    @pytest.mark.asyncio
    async def test_complete_admin_system_setup(self):
        """Test complete system setup by admin - matching Django admin capabilities."""

        # Step 1: Admin creates initial system configuration
        admin_setup_result = await self.runtime.execute_async(
            self.app.workflows["system_setup"],
            admin_email="superadmin@company.com",
            admin_password="SuperSecure123!@#",
            company_name="Test Corporation",
            settings={
                "password_policy": {
                    "min_length": 12,
                    "require_uppercase": True,
                    "require_lowercase": True,
                    "require_numbers": True,
                    "require_special": True,
                    "expiry_days": 90,
                },
                "session_timeout": 3600,
                "max_login_attempts": 5,
                "enable_2fa": True,
            },
        )

        assert admin_setup_result["success"] is True
        admin_token = admin_setup_result["admin_token"]

        # Step 2: Create organizational structure
        departments = ["Engineering", "Marketing", "Sales", "Support", "HR"]
        created_departments = {}

        for dept in departments:
            dept_result = await self.runtime.execute_async(
                self.app.workflows["create_department"],
                token=admin_token,
                name=dept,
                description=f"{dept} department",
            )
            created_departments[dept] = dept_result["department"]

        # Step 3: Create roles with permissions
        roles_config = {
            "department_head": {
                "name": "Department Head",
                "permissions": [
                    "users.create",
                    "users.read",
                    "users.update",
                    "department.manage",
                    "reports.view",
                    "reports.export",
                ],
            },
            "team_lead": {
                "name": "Team Lead",
                "permissions": ["users.read", "team.manage", "reports.view"],
            },
            "employee": {
                "name": "Employee",
                "permissions": ["profile.update", "reports.view_own"],
            },
        }

        created_roles = {}
        for role_key, role_data in roles_config.items():
            role_result = await self.runtime.execute_async(
                self.app.workflows["create_role"],
                token=admin_token,
                name=role_data["name"],
                permissions=role_data["permissions"],
            )
            created_roles[role_key] = role_result["role"]

        # Step 4: Bulk create users with roles
        users_data = []
        for dept_name, dept in created_departments.items():
            # Department head
            users_data.append(
                {
                    "email": f"{dept_name.lower()}.head@company.com",
                    "username": f"{dept_name.lower()}_head",
                    "password": "TempPass123!@#",
                    "first_name": dept_name,
                    "last_name": "Head",
                    "department_id": dept["id"],
                    "role_id": created_roles["department_head"]["id"],
                    "require_password_change": True,
                }
            )

            # Team leads
            for i in range(2):
                users_data.append(
                    {
                        "email": f"{dept_name.lower()}.lead{i+1}@company.com",
                        "username": f"{dept_name.lower()}_lead{i+1}",
                        "password": "TempPass123!@#",
                        "first_name": f"{dept_name}",
                        "last_name": f"Lead{i+1}",
                        "department_id": dept["id"],
                        "role_id": created_roles["team_lead"]["id"],
                        "require_password_change": True,
                    }
                )

            # Regular employees
            for i in range(5):
                users_data.append(
                    {
                        "email": f"{dept_name.lower()}.emp{i+1}@company.com",
                        "username": f"{dept_name.lower()}_emp{i+1}",
                        "password": "TempPass123!@#",
                        "first_name": f"{dept_name}",
                        "last_name": f"Employee{i+1}",
                        "department_id": dept["id"],
                        "role_id": created_roles["employee"]["id"],
                        "require_password_change": True,
                    }
                )

        # Bulk create users
        bulk_result = await self.runtime.execute_async(
            self.app.workflows["bulk_create_users"],
            token=admin_token,
            users=users_data,
            send_welcome_email=True,
        )

        assert bulk_result["success"] is True
        assert bulk_result["created_count"] == len(users_data)

        # Step 5: Test audit logging
        audit_logs = await self.runtime.execute_async(
            self.app.workflows["get_audit_logs"],
            token=admin_token,
            filters={
                "action_type": "user.created",
                "date_from": datetime.now() - timedelta(hours=1),
            },
        )

        assert len(audit_logs["logs"]) == len(users_data) + 1  # +1 for admin

        # Step 6: Generate and verify reports
        report_result = await self.runtime.execute_async(
            self.app.workflows["generate_user_report"],
            token=admin_token,
            report_type="department_summary",
            format="json",
        )

        assert report_result["success"] is True
        report_data = report_result["data"]

        # Verify department counts
        for dept in departments:
            dept_data = next(d for d in report_data["departments"] if d["name"] == dept)
            assert dept_data["user_count"] == 8  # 1 head + 2 leads + 5 employees
            assert dept_data["roles"]["Department Head"] == 1
            assert dept_data["roles"]["Team Lead"] == 2
            assert dept_data["roles"]["Employee"] == 5

        # Step 7: Test access control
        # Login as department head
        dept_head_login = await self.runtime.execute_async(
            self.app.workflows["login"],
            username="engineering_head",
            password="TempPass123!@#",
        )

        dept_head_token = dept_head_login["token"]

        # Department head should be able to view their department
        dept_users = await self.runtime.execute_async(
            self.app.workflows["list_department_users"],
            token=dept_head_token,
            department_id=created_departments["Engineering"]["id"],
        )

        assert len(dept_users["users"]) == 8

        # But not other departments
        other_dept_result = await self.runtime.execute_async(
            self.app.workflows["list_department_users"],
            token=dept_head_token,
            department_id=created_departments["Marketing"]["id"],
        )

        assert other_dept_result.get("error") == "Access denied"

        # Step 8: Test session management
        active_sessions = await self.runtime.execute_async(
            self.app.workflows["get_active_sessions"], token=admin_token
        )

        assert active_sessions["total_sessions"] >= 2  # Admin + dept head

        # Step 9: Test system health monitoring
        health_result = await self.runtime.execute_async(
            self.app.workflows["system_health_check"], token=admin_token
        )

        assert health_result["status"] == "healthy"
        assert health_result["database"]["status"] == "connected"
        assert health_result["redis"]["status"] == "connected"
        assert health_result["users"]["total"] == len(users_data) + 1

        # Step 10: Export data (like Django's dumpdata)
        export_result = await self.runtime.execute_async(
            self.app.workflows["export_data"],
            token=admin_token,
            models=["users", "roles", "permissions", "departments"],
            format="json",
        )

        assert export_result["success"] is True
        exported_data = json.loads(export_result["data"])
        assert len(exported_data["users"]) == len(users_data) + 1
        assert len(exported_data["roles"]) == len(created_roles)
        assert len(exported_data["departments"]) == len(departments)

    @pytest.mark.asyncio
    async def test_security_incident_response(self):
        """Test security incident response scenario."""

        # Create users for testing
        setup_result = await self._setup_test_users()
        admin_token = setup_result["admin_token"]
        user_tokens = setup_result["user_tokens"]

        # Simulate security incident - multiple failed login attempts
        target_user = "testuser1"

        for i in range(6):  # Exceed max attempts
            try:
                await self.runtime.execute_async(
                    self.app.workflows["login"],
                    username=target_user,
                    password="WrongPassword!",
                )
            except:
                pass  # Expected to fail

        # Check security alerts
        alerts = await self.runtime.execute_async(
            self.app.workflows["get_security_alerts"],
            token=admin_token,
            severity="high",
        )

        assert len(alerts["alerts"]) > 0
        assert any(a["type"] == "excessive_login_attempts" for a in alerts["alerts"])

        # Admin investigates the incident
        investigation = await self.runtime.execute_async(
            self.app.workflows["investigate_user"],
            token=admin_token,
            username=target_user,
            include_logs=True,
            include_sessions=True,
            include_permissions=True,
        )

        assert investigation["user"]["is_locked"] is True
        assert len(investigation["recent_login_attempts"]) >= 6
        assert all(
            not attempt["successful"]
            for attempt in investigation["recent_login_attempts"]
        )

        # Admin takes action - force password reset
        reset_result = await self.runtime.execute_async(
            self.app.workflows["admin_password_reset"],
            token=admin_token,
            username=target_user,
            temporary_password="TempSecure123!@#",
            require_change=True,
            unlock_account=True,
        )

        assert reset_result["success"] is True

        # Verify user can now login with temp password
        temp_login = await self.runtime.execute_async(
            self.app.workflows["login"],
            username=target_user,
            password="TempSecure123!@#",
        )

        assert temp_login["success"] is True
        assert temp_login["require_password_change"] is True

        # User must change password
        change_result = await self.runtime.execute_async(
            self.app.workflows["change_password"],
            token=temp_login["token"],
            current_password="TempSecure123!@#",
            new_password="NewSecurePass123!@#",
        )

        assert change_result["success"] is True

        # Generate security report
        report = await self.runtime.execute_async(
            self.app.workflows["generate_security_report"],
            token=admin_token,
            date_from=datetime.now() - timedelta(hours=1),
            include_incidents=True,
            include_resolutions=True,
        )

        assert report["incidents"]["total"] >= 1
        assert report["incidents"]["resolved"] >= 1

    @pytest.mark.asyncio
    async def test_data_privacy_compliance(self):
        """Test GDPR compliance features."""

        # Setup users
        setup_result = await self._setup_test_users()
        admin_token = setup_result["admin_token"]

        # User requests data export (GDPR right to access)
        user_export = await self.runtime.execute_async(
            self.app.workflows["export_user_data"],
            user_id=setup_result["users"][0]["id"],
            include_activity_logs=True,
            include_permissions=True,
            format="json",
        )

        assert user_export["success"] is True
        exported = json.loads(user_export["data"])
        assert exported["user"]["email"] == setup_result["users"][0]["email"]
        assert "activity_logs" in exported
        assert "permissions" in exported

        # User requests data deletion (GDPR right to erasure)
        deletion_request = await self.runtime.execute_async(
            self.app.workflows["request_data_deletion"],
            user_id=setup_result["users"][0]["id"],
            reason="User requested under GDPR",
            anonymize=True,  # Don't fully delete, anonymize for audit trail
        )

        assert deletion_request["success"] is True
        request_id = deletion_request["request_id"]

        # Admin approves deletion
        approval_result = await self.runtime.execute_async(
            self.app.workflows["approve_deletion_request"],
            token=admin_token,
            request_id=request_id,
            approved=True,
            admin_notes="Approved under GDPR Article 17",
        )

        assert approval_result["success"] is True

        # Verify anonymization
        anonymized_user = await self.runtime.execute_async(
            self.app.workflows["get_user"],
            token=admin_token,
            user_id=setup_result["users"][0]["id"],
        )

        assert anonymized_user["user"]["email"] != setup_result["users"][0]["email"]
        assert anonymized_user["user"]["email"].startswith("anonymized_")
        assert anonymized_user["user"]["is_active"] is False

        # Generate compliance report
        compliance_report = await self.runtime.execute_async(
            self.app.workflows["generate_compliance_report"],
            token=admin_token,
            report_type="gdpr_requests",
            date_from=datetime.now() - timedelta(days=30),
        )

        assert compliance_report["total_requests"] >= 1
        assert compliance_report["completed_requests"] >= 1

    async def _setup_test_users(self):
        """Helper to set up test users."""
        # Quick admin setup
        admin_result = await self.runtime.execute_async(
            self.app.workflows["system_setup"],
            admin_email="admin@test.com",
            admin_password="AdminPass123!@#",
            company_name="Test Corp",
        )

        admin_token = admin_result["admin_token"]

        # Create test users
        users = []
        user_tokens = {}

        for i in range(3):
            user = await self.runtime.execute_async(
                self.app.workflows["create_user"],
                token=admin_token,
                email=f"testuser{i+1}@test.com",
                username=f"testuser{i+1}",
                password="UserPass123!@#",
                first_name=f"Test{i+1}",
                last_name="User",
            )
            users.append(user["user"])

            # Get token for user
            login = await self.runtime.execute_async(
                self.app.workflows["login"],
                username=f"testuser{i+1}",
                password="UserPass123!@#",
            )
            user_tokens[f"testuser{i+1}"] = login["token"]

        return {"admin_token": admin_token, "users": users, "user_tokens": user_tokens}
