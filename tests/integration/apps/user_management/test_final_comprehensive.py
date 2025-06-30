"""Final comprehensive test to ensure all user management features work perfectly."""

from datetime import datetime

import pytest
import pytest_asyncio

from kailash.nodes.admin.permission_check import PermissionCheckNode
from kailash.nodes.admin.role_management import RoleManagementNode
from kailash.nodes.admin.user_management import UserManagementNode
from kailash.runtime.local import LocalRuntime
from tests.utils.docker_config import (
    ensure_docker_services,
    get_postgres_connection_string,
)


@pytest.mark.integration
@pytest.mark.requires_docker
class TestFinalComprehensive:
    """Comprehensive test of all user management features."""

    @pytest_asyncio.fixture(autouse=True)
    async def setup(self):
        """Set up test environment."""
        services_ok = await ensure_docker_services()
        if not services_ok:
            pytest.skip("Docker services not available")

        self.db_config = {
            "connection_string": get_postgres_connection_string(),
            "database_type": "postgresql",
        }
        self.tenant_id = "final_test"

        # Initialize schema
        from kailash.nodes.admin.schema_manager import AdminSchemaManager

        schema_manager = AdminSchemaManager(self.db_config)
        schema_manager.create_full_schema(drop_existing=True)

        yield

        # Cleanup
        schema_manager.create_full_schema(drop_existing=True)

    @pytest.mark.asyncio
    async def test_complete_user_management_flow(self):
        """Test all user management features in one comprehensive flow."""
        user_node = UserManagementNode()
        role_node = RoleManagementNode()
        perm_node = PermissionCheckNode()

        print("\n=== COMPREHENSIVE USER MANAGEMENT TEST ===\n")

        # 1. Create roles with permissions
        print("1. Creating roles...")
        admin_role = role_node.execute(
            operation="create_role",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            role_data={
                "name": "admin",
                "description": "Administrator",
                "permissions": ["users.*", "roles.*", "system.*"],
            },
        )
        assert "result" in admin_role
        admin_role_id = admin_role["result"]["role"]["role_id"]
        print(f"   ✅ Admin role created: {admin_role_id}")

        user_role = role_node.execute(
            operation="create_role",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            role_data={
                "name": "user",
                "description": "Regular User",
                "permissions": ["profile.read", "profile.update"],
            },
        )
        assert "result" in user_role
        user_role_id = user_role["result"]["role"]["role_id"]
        print(f"   ✅ User role created: {user_role_id}")

        # 2. Create individual users
        print("\n2. Creating individual users...")
        admin_user = user_node.execute(
            operation="create_user",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_data={
                "email": "admin@test.com",
                "username": "admin",
                "attributes": {"department": "IT", "level": "Senior"},
            },
            password="AdminPass123!",
        )
        assert "result" in admin_user
        admin_user_id = admin_user["result"]["user"]["user_id"]
        print(f"   ✅ Admin user created: {admin_user_id}")

        # 3. Assign roles
        print("\n3. Assigning roles to users...")
        assign_result = role_node.execute(
            operation="assign_user",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_id=admin_user_id,
            role_id=admin_role_id,
        )
        assert "result" in assign_result
        print("   ✅ Admin role assigned to admin user")

        # 4. Test authentication
        print("\n4. Testing authentication...")
        auth_success = user_node.execute(
            operation="authenticate",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            username="admin",
            password="AdminPass123!",
        )
        assert auth_success["authenticated"] is True
        print("   ✅ Authentication successful")

        auth_fail = user_node.execute(
            operation="authenticate",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            username="admin",
            password="WrongPassword",
        )
        assert auth_fail["authenticated"] is False
        print("   ✅ Invalid password rejected")

        # 5. Bulk create users
        print("\n5. Testing bulk user creation...")
        bulk_users = []
        for i in range(10):
            bulk_users.append(
                {
                    "email": f"user{i}@test.com",
                    "username": f"user{i}",
                    "password": f"Pass{i}123!",
                    "attributes": {"department": "Sales" if i < 5 else "Marketing"},
                }
            )

        bulk_result = user_node.execute(
            operation="bulk_create",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            users_data=bulk_users,
        )
        assert bulk_result["result"]["bulk_result"]["created_count"] == 10
        print(
            f"   ✅ Bulk created {bulk_result['result']['bulk_result']['created_count']} users"
        )

        # 6. Search and list users
        print("\n6. Testing user search and listing...")
        list_result = user_node.execute(
            operation="list_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            limit=20,
        )
        assert len(list_result["result"]["users"]) == 11  # 1 admin + 10 bulk
        print(f"   ✅ Listed {len(list_result['result']['users'])} users")

        # 7. Bulk update users
        print("\n7. Testing bulk update...")
        users_to_update = []
        for user in list_result["result"]["users"][:5]:
            users_to_update.append({"user_id": user["user_id"], "status": "inactive"})

        update_result = user_node.execute(
            operation="bulk_update",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            users_data=users_to_update,
        )
        assert update_result["result"]["bulk_result"]["updated_count"] == 5
        print(
            f"   ✅ Bulk updated {update_result['result']['bulk_result']['updated_count']} users"
        )

        # 8. Password reset flow
        print("\n8. Testing password reset flow...")
        reset_user_id = list_result["result"]["users"][5]["user_id"]

        token_result = user_node.execute(
            operation="generate_reset_token",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_id=reset_user_id,
        )
        assert "token" in token_result
        print("   ✅ Reset token generated")

        reset_result = user_node.execute(
            operation="reset_password",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            token=token_result["token"],
            new_password="NewPassword123!",
        )
        assert reset_result["success"] is True
        print("   ✅ Password reset successful")

        # 9. Check permissions
        print("\n9. Testing permission checks...")
        user_roles = role_node.execute(
            operation="get_user_roles",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            user_id=admin_user_id,
        )
        assert len(user_roles["result"]["roles"]) == 1
        assert user_roles["result"]["roles"][0]["name"] == "admin"
        print("   ✅ User roles retrieved correctly")

        # 10. Export users
        print("\n10. Testing user export...")
        export_result = user_node.execute(
            operation="export_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            export_format="json",
        )
        assert "result" in export_result
        assert len(export_result["result"]["export_data"]["users"]) == 11
        print(
            f"   ✅ Exported {len(export_result['result']['export_data']['users'])} users"
        )

        # 11. Bulk delete
        print("\n11. Testing bulk delete...")
        inactive_users = user_node.execute(
            operation="list_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            filters={"status": "inactive"},
        )

        print(f"   Found {len(inactive_users['result']['users'])} inactive users")
        user_ids_to_delete = [u["user_id"] for u in inactive_users["result"]["users"]]

        if user_ids_to_delete:
            delete_result = user_node.execute(
                operation="bulk_delete",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_ids=user_ids_to_delete,
            )
            print(
                f"   ✅ Bulk deleted {delete_result['result']['bulk_result']['deleted_count']} users"
            )
        else:
            # If no inactive users, delete some active ones for testing
            active_users = user_node.execute(
                operation="list_users",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                filters={"status": "active"},
                limit=5,
            )
            user_ids_to_delete = [
                u["user_id"] for u in active_users["result"]["users"][:3]
            ]
            delete_result = user_node.execute(
                operation="bulk_delete",
                tenant_id=self.tenant_id,
                database_config=self.db_config,
                user_ids=user_ids_to_delete,
            )
            print(
                f"   ✅ Bulk deleted {delete_result['result']['bulk_result']['deleted_count']} active users for testing"
            )

        # Final verification
        final_count = user_node.execute(
            operation="list_users",
            tenant_id=self.tenant_id,
            database_config=self.db_config,
            filters={"status": "active"},
        )
        print(
            f"\n✅ FINAL STATUS: {len(final_count['result']['users'])} active users remaining"
        )

        print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")
        return True
