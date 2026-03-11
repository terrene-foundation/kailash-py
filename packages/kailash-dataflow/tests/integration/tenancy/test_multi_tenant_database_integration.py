"""
Integration tests for multi-tenant database operations.

Tests real multi-tenant database operations with tenant isolation,
cross-tenant prevention, and performance under load.
"""

import asyncio
import time
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from kailash.runtime.local import LocalRuntime
from tests.infrastructure.test_harness import IntegrationTestSuite

# TODO: Import actual classes once implemented
# from dataflow import DataFlow
# from dataflow.tenancy.manager import MultiTenantManager
# from dataflow.tenancy.security import TenantSecurityManager


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.fixture
def runtime():
    """Create LocalRuntime for workflow execution."""
    return LocalRuntime()


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestMultiTenantDatabaseOperations:
    """Test multi-tenant database operations with real databases."""

    @pytest.fixture(autouse=True)
    async def setup_multi_tenant_database(self, test_suite):
        """Setup multi-tenant database with real PostgreSQL."""
        self.test_suite = test_suite
        # TODO: Implement once multi-tenant support exists
        # # Setup multi-tenant DataFlow instance
        # self.dataflow = DataFlow(test_suite.config.url)
        # self.tenant_manager = MultiTenantManager(self.dataflow)
        #
        # # Enable multi-tenancy
        # await self.dataflow.enable_multi_tenancy(
        #     tenant_isolation_strategy="column_based",
        #     tenant_column="tenant_id"
        # )
        #
        # # Define test models
        # @self.dataflow.model
        # class User:
        #     name: str
        #     email: str
        #     active: bool = True
        #     created_at: datetime
        #
        # @self.dataflow.model
        # class Order:
        #     user_id: int
        #     order_number: str
        #     total: float
        #     status: str = "pending"
        #     created_at: datetime
        #
        # # Initialize database
        # await self.dataflow.init_database()
        #
        # # Create test tenants
        # self.tenant_a = await self.tenant_manager.create_tenant("tenant_a_integration")
        # self.tenant_b = await self.tenant_manager.create_tenant("tenant_b_integration")
        # self.tenant_c = await self.tenant_manager.create_tenant("tenant_c_integration")
        #
        # yield
        #
        # # Cleanup
        # await self.tenant_manager.delete_tenant(self.tenant_a["id"])
        # await self.tenant_manager.delete_tenant(self.tenant_b["id"])
        # await self.tenant_manager.delete_tenant(self.tenant_c["id"])
        # await self.dataflow.close()
        pytest.skip("Multi-tenant database integration not implemented yet")

    def test_tenant_data_isolation_with_real_database(self):
        """Test tenant data isolation with real PostgreSQL database."""
        # TODO: Implement once multi-tenant support exists
        # # Create data in tenant A
        # tenant_a_context = self.tenant_manager.get_tenant_context(self.tenant_a["id"])
        #
        # user_a1 = await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Alice (Tenant A)",
        #     "email": "alice@tenant-a.com",
        #     "created_at": datetime.now()
        # }, context=tenant_a_context)
        #
        # user_a2 = await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Bob (Tenant A)",
        #     "email": "bob@tenant-a.com",
        #     "created_at": datetime.now()
        # }, context=tenant_a_context)
        #
        # # Create data in tenant B
        # tenant_b_context = self.tenant_manager.get_tenant_context(self.tenant_b["id"])
        #
        # user_b1 = await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Charlie (Tenant B)",
        #     "email": "charlie@tenant-b.com",
        #     "created_at": datetime.now()
        # }, context=tenant_b_context)
        #
        # user_b2 = await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Diana (Tenant B)",
        #     "email": "diana@tenant-b.com",
        #     "created_at": datetime.now()
        # }, context=tenant_b_context)
        #
        # # Verify tenant A can only see its data
        # tenant_a_users = await self.dataflow.execute_node("UserListNode", {
        #     "limit": 100
        # }, context=tenant_a_context)
        #
        # assert len(tenant_a_users["records"]) == 2
        # tenant_a_emails = [user["email"] for user in tenant_a_users["records"]]
        # assert "alice@tenant-a.com" in tenant_a_emails
        # assert "bob@tenant-a.com" in tenant_a_emails
        # assert "charlie@tenant-b.com" not in tenant_a_emails
        # assert "diana@tenant-b.com" not in tenant_a_emails
        #
        # # Verify tenant B can only see its data
        # tenant_b_users = await self.dataflow.execute_node("UserListNode", {
        #     "limit": 100
        # }, context=tenant_b_context)
        #
        # assert len(tenant_b_users["records"]) == 2
        # tenant_b_emails = [user["email"] for user in tenant_b_users["records"]]
        # assert "charlie@tenant-b.com" in tenant_b_emails
        # assert "diana@tenant-b.com" in tenant_b_emails
        # assert "alice@tenant-a.com" not in tenant_b_emails
        # assert "bob@tenant-a.com" not in tenant_b_emails
        pytest.skip("Multi-tenant database integration not implemented yet")

    def test_cross_tenant_query_prevention(self):
        """Test prevention of cross-tenant queries in real database."""
        # TODO: Implement once multi-tenant support exists
        # tenant_a_context = self.tenant_manager.get_tenant_context(self.tenant_a["id"])
        #
        # # Create some data in both tenants first
        # await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Test User A",
        #     "email": "test@tenant-a.com",
        #     "created_at": datetime.now()
        # }, context=tenant_a_context)
        #
        # tenant_b_context = self.tenant_manager.get_tenant_context(self.tenant_b["id"])
        # await self.dataflow.execute_node("UserCreateNode", {
        #     "name": "Test User B",
        #     "email": "test@tenant-b.com",
        #     "created_at": datetime.now()
        # }, context=tenant_b_context)
        #
        # # Attempt to access tenant B data from tenant A context
        # with pytest.raises(TenantIsolationViolationError):
        #     # This should be blocked by the multi-tenant system
        #     await self.dataflow.execute_raw_query(
        #         f"SELECT * FROM users WHERE tenant_id = '{self.tenant_b['id']}'",
        #         context=tenant_a_context
        #     )
        #
        # # Attempt to update data across tenants
        # with pytest.raises(TenantIsolationViolationError):
        #     await self.dataflow.execute_raw_query(
        #         f"UPDATE users SET email = 'hacked@evil.com' WHERE tenant_id = '{self.tenant_b['id']}'",
        #         context=tenant_a_context
        #     )
        #
        # # Attempt to delete data from another tenant
        # with pytest.raises(TenantIsolationViolationError):
        #     await self.dataflow.execute_raw_query(
        #         f"DELETE FROM users WHERE tenant_id = '{self.tenant_b['id']}'",
        #         context=tenant_a_context
        #     )
        pytest.skip("Multi-tenant database integration not implemented yet")

    def test_concurrent_multi_tenant_operations(self):
        """Test concurrent operations across multiple tenants."""
        # TODO: Implement once multi-tenant support exists
        # async def tenant_operations(tenant_id, operation_count):
        #     """Perform operations for a specific tenant."""
        #     context = self.tenant_manager.get_tenant_context(tenant_id)
        #     results = []
        #
        #     for i in range(operation_count):
        #         # Create user
        #         user = await self.dataflow.execute_node("UserCreateNode", {
        #             "name": f"User {i} (Tenant {tenant_id[:8]})",
        #             "email": f"user{i}@{tenant_id}.com",
        #             "created_at": datetime.now()
        #         }, context=context)
        #
        #         # Create order for the user
        #         order = await self.dataflow.execute_node("OrderCreateNode", {
        #             "user_id": user["id"],
        #             "order_number": f"ORD-{tenant_id[:8]}-{i}",
        #             "total": float(i * 10 + 50),
        #             "created_at": datetime.now()
        #         }, context=context)
        #
        #         results.append((user, order))
        #
        #     return results
        #
        # # Run concurrent operations for all tenants
        # start_time = time.time()
        #
        # tasks = [
        #     tenant_operations(self.tenant_a["id"], 20),
        #     tenant_operations(self.tenant_b["id"], 20),
        #     tenant_operations(self.tenant_c["id"], 20)
        # ]
        #
        # results = await asyncio.gather(*tasks)
        # execution_time = time.time() - start_time
        #
        # # Verify all operations completed
        # assert len(results) == 3
        # for tenant_results in results:
        #     assert len(tenant_results) == 20
        #
        # # Verify data isolation after concurrent operations
        # for i, tenant_id in enumerate([self.tenant_a["id"], self.tenant_b["id"], self.tenant_c["id"]]):
        #     context = self.tenant_manager.get_tenant_context(tenant_id)
        #
        #     users = await self.dataflow.execute_node("UserListNode", {"limit": 100}, context=context)
        #     orders = await self.dataflow.execute_node("OrderListNode", {"limit": 100}, context=context)
        #
        #     assert len(users["records"]) == 20
        #     assert len(orders["records"]) == 20
        #
        #     # Verify all users belong to correct tenant
        #     for user in users["records"]:
        #         assert user["email"].endswith(f"@{tenant_id}.com")
        #
        #     # Verify all orders belong to correct tenant
        #     for order in orders["records"]:
        #         assert order["order_number"].startswith(f"ORD-{tenant_id[:8]}")
        #
        # print(f"Concurrent operations completed in {execution_time:.2f}s")
        # assert execution_time < 30.0  # Should complete within reasonable time
        pytest.skip("Multi-tenant database integration not implemented yet")

    def test_tenant_specific_indexing_performance(self):
        """Test tenant-specific indexing for performance."""
        # TODO: Implement once multi-tenant support exists
        # # Create indexes for tenant-specific queries
        # await self.dataflow.execute_raw_query(
        #     "CREATE INDEX CONCURRENTLY idx_users_tenant_email ON users (tenant_id, email)"
        # )
        # await self.dataflow.execute_raw_query(
        #     "CREATE INDEX CONCURRENTLY idx_orders_tenant_status ON orders (tenant_id, status)"
        # )
        #
        # # Populate with substantial data for performance testing
        # tenant_a_context = self.tenant_manager.get_tenant_context(self.tenant_a["id"])
        #
        # # Create 1000 users and orders
        # bulk_users = []
        # for i in range(1000):
        #     bulk_users.append({
        #         "name": f"Performance User {i}",
        #         "email": f"perf{i}@tenant-a.com",
        #         "active": i % 3 != 0,  # Mix of active/inactive
        #         "created_at": datetime.now()
        #     })
        #
        # # Bulk create users
        # start_time = time.time()
        # bulk_result = await self.dataflow.execute_node("UserBulkCreateNode", {
        #     "data": bulk_users,
        #     "batch_size": 100
        # }, context=tenant_a_context)
        # bulk_insert_time = time.time() - start_time
        #
        # assert bulk_result["processed"] == 1000
        # print(f"Bulk insert time: {bulk_insert_time:.2f}s")
        #
        # # Test tenant-specific query performance
        # start_time = time.time()
        # active_users = await self.dataflow.execute_node("UserListNode", {
        #     "filter": {"active": True},
        #     "limit": 1000
        # }, context=tenant_a_context)
        # query_time = time.time() - start_time
        #
        # # Should be fast with proper indexing
        # assert query_time < 1.0  # Under 1 second
        # assert len(active_users["records"]) > 600  # About 2/3 should be active
        #
        # # Test email lookup performance
        # start_time = time.time()
        # user_by_email = await self.dataflow.execute_node("UserListNode", {
        #     "filter": {"email": "perf500@tenant-a.com"},
        #     "limit": 1
        # }, context=tenant_a_context)
        # email_query_time = time.time() - start_time
        #
        # assert email_query_time < 0.1  # Under 100ms with index
        # assert len(user_by_email["records"]) == 1
        #
        # print(f"Tenant query performance: {query_time:.3f}s, Email lookup: {email_query_time:.3f}s")
        pytest.skip("Multi-tenant database integration not implemented yet")


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTenantSecurityIntegration:
    """Test tenant security features with real database operations."""

    @pytest.fixture(autouse=True)
    async def setup_security_testing(self, test_suite):
        """Setup security testing environment."""
        self.test_suite = test_suite
        # TODO: Implement once security features exist
        # self.dataflow = DataFlow(test_suite.config.url)
        # self.security_manager = TenantSecurityManager(self.dataflow)
        #
        # # Enable multi-tenancy with security
        # await self.dataflow.enable_multi_tenancy(
        #     tenant_isolation_strategy="column_based",
        #     security_level="HIGH",
        #     audit_enabled=True
        # )
        #
        # # Define secure models
        # @self.dataflow.model
        # class SecureUser:
        #     username: str
        #     email: str
        #     password_hash: str
        #     role: str = "user"
        #     created_at: datetime
        #     last_login: datetime = None
        #
        # @self.dataflow.model
        # class AuditLog:
        #     user_id: int = None
        #     action: str
        #     resource: str
        #     resource_id: str = None
        #     timestamp: datetime
        #     ip_address: str = None
        #
        # await self.dataflow.init_database()
        #
        # # Create test tenant with security policies
        # self.secure_tenant = await self.security_manager.create_secure_tenant(
        #     tenant_name="secure_tenant_integration",
        #     security_policies={
        #         "password_policy": {"min_length": 8, "require_special": True},
        #         "access_control": {"default_role": "user", "admin_approval": True},
        #         "audit_level": "ALL_OPERATIONS"
        #     }
        # )
        #
        # yield
        #
        # # Cleanup
        # await self.security_manager.delete_tenant(self.secure_tenant["id"])
        # await self.dataflow.close()
        pytest.skip("Tenant security integration not implemented yet")

    def test_real_database_access_control(self):
        """Test access control with real database operations."""
        # TODO: Implement once security features exist
        # # Create users with different roles
        # admin_context = self.security_manager.create_user_context(
        #     tenant_id=self.secure_tenant["id"],
        #     user_role="admin",
        #     permissions=["read", "write", "delete", "admin"]
        # )
        #
        # user_context = self.security_manager.create_user_context(
        #     tenant_id=self.secure_tenant["id"],
        #     user_role="user",
        #     permissions=["read", "write"]
        # )
        #
        # readonly_context = self.security_manager.create_user_context(
        #     tenant_id=self.secure_tenant["id"],
        #     user_role="readonly",
        #     permissions=["read"]
        # )
        #
        # # Admin can create users
        # admin_created_user = await self.dataflow.execute_node("SecureUserCreateNode", {
        #     "username": "admin_created_user",
        #     "email": "admin@secure-tenant.com",
        #     "password_hash": "hashed_password_123",
        #     "role": "user",
        #     "created_at": datetime.now()
        # }, context=admin_context)
        #
        # assert admin_created_user["id"] is not None
        #
        # # Regular user can create users (if allowed)
        # user_created_user = await self.dataflow.execute_node("SecureUserCreateNode", {
        #     "username": "user_created_user",
        #     "email": "user@secure-tenant.com",
        #     "password_hash": "hashed_password_456",
        #     "role": "user",
        #     "created_at": datetime.now()
        # }, context=user_context)
        #
        # assert user_created_user["id"] is not None
        #
        # # Readonly user cannot create users
        # with pytest.raises(TenantAccessDeniedError, match="Write access denied"):
        #     await self.dataflow.execute_node("SecureUserCreateNode", {
        #         "username": "readonly_attempt",
        #         "email": "readonly@secure-tenant.com",
        #         "password_hash": "hashed_password_789",
        #         "created_at": datetime.now()
        #     }, context=readonly_context)
        #
        # # All users can read
        # for context in [admin_context, user_context, readonly_context]:
        #     users = await self.dataflow.execute_node("SecureUserListNode", {
        #         "limit": 10
        #     }, context=context)
        #     assert len(users["records"]) >= 2
        pytest.skip("Tenant security integration not implemented yet")

    def test_audit_logging_with_real_operations(self):
        """Test audit logging with real database operations."""
        # TODO: Implement once security features exist
        # user_context = self.security_manager.create_user_context(
        #     tenant_id=self.secure_tenant["id"],
        #     user_id="audit_test_user",
        #     user_role="admin",
        #     permissions=["read", "write", "delete", "admin"],
        #     ip_address="192.168.1.100"
        # )
        #
        # # Perform auditable operations
        # operations = []
        #
        # # Create operation
        # user1 = await self.dataflow.execute_node("SecureUserCreateNode", {
        #     "username": "audit_user_1",
        #     "email": "audit1@secure-tenant.com",
        #     "password_hash": "hashed_password_audit1",
        #     "created_at": datetime.now()
        # }, context=user_context)
        # operations.append(("CREATE", "SecureUser", str(user1["id"])))
        #
        # # Read operation
        # read_user = await self.dataflow.execute_node("SecureUserReadNode", {
        #     "id": user1["id"]
        # }, context=user_context)
        # operations.append(("READ", "SecureUser", str(user1["id"])))
        #
        # # Update operation
        # updated_user = await self.dataflow.execute_node("SecureUserUpdateNode", {
        #     "id": user1["id"],
        #     "last_login": datetime.now()
        # }, context=user_context)
        # operations.append(("UPDATE", "SecureUser", str(user1["id"])))
        #
        # # Delete operation
        # deleted_user = await self.dataflow.execute_node("SecureUserDeleteNode", {
        #     "id": user1["id"]
        # }, context=user_context)
        # operations.append(("DELETE", "SecureUser", str(user1["id"])))
        #
        # # Give audit system a moment to process
        # await asyncio.sleep(0.1)
        #
        # # Verify audit logs were created
        # audit_logs = await self.dataflow.execute_node("AuditLogListNode", {
        #     "filter": {"user_id": "audit_test_user"},
        #     "order_by": [{"timestamp": 1}],
        #     "limit": 10
        # }, context=user_context)
        #
        # assert len(audit_logs["records"]) >= len(operations)
        #
        # # Verify audit log details
        # logged_operations = [(log["action"], log["resource"], log["resource_id"])
        #                     for log in audit_logs["records"]]
        #
        # for expected_op in operations:
        #     assert expected_op in logged_operations
        #
        # # Verify IP address was logged
        # for log in audit_logs["records"]:
        #     if log["ip_address"]:
        #         assert log["ip_address"] == "192.168.1.100"
        pytest.skip("Tenant security integration not implemented yet")

    def test_sql_injection_prevention_real_database(self):
        """Test SQL injection prevention with real database."""
        # TODO: Implement once security features exist
        # user_context = self.security_manager.create_user_context(
        #     tenant_id=self.secure_tenant["id"],
        #     user_role="user",
        #     permissions=["read", "write"]
        # )
        #
        # # Create a legitimate user first
        # legitimate_user = await self.dataflow.execute_node("SecureUserCreateNode", {
        #     "username": "legitimate_user",
        #     "email": "legit@secure-tenant.com",
        #     "password_hash": "proper_hash",
        #     "created_at": datetime.now()
        # }, context=user_context)
        #
        # # Attempt SQL injection through search parameters
        # injection_attempts = [
        #     {"email": "test@example.com'; DROP TABLE secure_users; --"},
        #     {"username": "admin' OR '1'='1"},
        #     {"password_hash": "'; UPDATE secure_users SET role='admin' WHERE id=1; --"}
        # ]
        #
        # for malicious_params in injection_attempts:
        #     # All injection attempts should be safely handled
        #     search_result = await self.dataflow.execute_node("SecureUserListNode", {
        #         "filter": malicious_params,
        #         "limit": 10
        #     }, context=user_context)
        #
        #     # Should return empty results or properly escaped search
        #     assert len(search_result["records"]) == 0
        #
        # # Verify the legitimate user still exists and table wasn't dropped
        # legitimate_check = await self.dataflow.execute_node("SecureUserReadNode", {
        #     "id": legitimate_user["id"]
        # }, context=user_context)
        #
        # assert legitimate_check["found"] is True
        # assert legitimate_check["username"] == "legitimate_user"
        pytest.skip("Tenant security integration not implemented yet")


@pytest.mark.integration
@pytest.mark.timeout(30)
class TestTenantDataMigrationIntegration:
    """Test tenant data migration with real database operations."""

    @pytest.fixture(autouse=True)
    def setup_migration_testing(self, test_suite):
        """Setup migration testing environment."""
        self.test_suite = test_suite

    def test_tenant_data_export_import(self):
        """Test tenant data export and import with real database."""
        # TODO: Implement once migration features exist
        # source_db = DataFlow(self.test_suite.config.url)
        # target_db = DataFlow(self.test_suite.config.url)
        #
        # # Setup source tenant
        # source_tenant_manager = MultiTenantManager(source_db)
        # await source_db.enable_multi_tenancy()
        #
        # @source_db.model
        # class ExportUser:
        #     name: str
        #     email: str
        #     data: dict
        #     created_at: datetime
        #
        # await source_db.init_database()
        #
        # source_tenant = await source_tenant_manager.create_tenant("migration_source")
        # source_context = source_tenant_manager.get_tenant_context(source_tenant["id"])
        #
        # # Create test data
        # test_users = []
        # for i in range(50):
        #     user = await source_db.execute_node("ExportUserCreateNode", {
        #         "name": f"Migration User {i}",
        #         "email": f"migration{i}@source-tenant.com",
        #         "data": {"index": i, "migration_test": True},
        #         "created_at": datetime.now()
        #     }, context=source_context)
        #     test_users.append(user)
        #
        # # Export tenant data
        # export_result = await source_tenant_manager.export_tenant_data(
        #     tenant_id=source_tenant["id"],
        #     export_format="json",
        #     include_metadata=True
        # )
        #
        # assert export_result["status"] == "SUCCESS"
        # assert export_result["record_count"] == 50
        # assert "export_data" in export_result
        #
        # # Setup target database
        # target_tenant_manager = MultiTenantManager(target_db)
        # await target_db.enable_multi_tenancy()
        #
        # @target_db.model
        # class ExportUser:
        #     name: str
        #     email: str
        #     data: dict
        #     created_at: datetime
        #
        # await target_db.init_database()
        #
        # target_tenant = await target_tenant_manager.create_tenant("migration_target")
        # target_context = target_tenant_manager.get_tenant_context(target_tenant["id"])
        #
        # # Import tenant data
        # import_result = await target_tenant_manager.import_tenant_data(
        #     tenant_id=target_tenant["id"],
        #     import_data=export_result["export_data"],
        #     import_format="json",
        #     validate_integrity=True
        # )
        #
        # assert import_result["status"] == "SUCCESS"
        # assert import_result["imported_records"] == 50
        #
        # # Verify imported data
        # imported_users = await target_db.execute_node("ExportUserListNode", {
        #     "limit": 100
        # }, context=target_context)
        #
        # assert len(imported_users["records"]) == 50
        #
        # # Verify data integrity
        # source_emails = sorted([user["email"] for user in test_users])
        # imported_emails = sorted([user["email"] for user in imported_users["records"]])
        # assert source_emails == imported_emails
        #
        # # Cleanup
        # await source_tenant_manager.delete_tenant(source_tenant["id"])
        # await target_tenant_manager.delete_tenant(target_tenant["id"])
        # await source_db.close()
        # await target_db.close()
        pytest.skip("Tenant data migration not implemented yet")

    def test_tenant_archival_and_restoration(self):
        """Test tenant archival and restoration with real database."""
        # TODO: Implement once archival features exist
        # dataflow = DataFlow(self.test_suite.config.url)
        # tenant_manager = MultiTenantManager(dataflow)
        #
        # await dataflow.enable_multi_tenancy()
        #
        # @dataflow.model
        # class ArchivalUser:
        #     name: str
        #     email: str
        #     status: str = "active"
        #     created_at: datetime
        #
        # await dataflow.init_database()
        #
        # # Create tenant with data
        # tenant = await tenant_manager.create_tenant("archival_test_tenant")
        # context = tenant_manager.get_tenant_context(tenant["id"])
        #
        # # Create test data
        # users = []
        # for i in range(100):
        #     user = await dataflow.execute_node("ArchivalUserCreateNode", {
        #         "name": f"Archival User {i}",
        #         "email": f"archival{i}@test-tenant.com",
        #         "status": "active" if i % 2 == 0 else "inactive",
        #         "created_at": datetime.now()
        #     }, context=context)
        #     users.append(user)
        #
        # # Archive tenant
        # archival_result = await tenant_manager.archive_tenant(
        #     tenant_id=tenant["id"],
        #     archive_location="s3://test-bucket/archives",
        #     compression="gzip",
        #     remove_after_archive=True
        # )
        #
        # assert archival_result["status"] == "SUCCESS"
        # assert archival_result["archived_records"] == 100
        # assert archival_result["archive_size_bytes"] > 0
        #
        # # Verify data is no longer accessible in main database
        # archived_context = tenant_manager.get_tenant_context(tenant["id"])
        # remaining_users = await dataflow.execute_node("ArchivalUserListNode", {
        #     "limit": 200
        # }, context=archived_context)
        #
        # assert len(remaining_users["records"]) == 0
        #
        # # Restore from archive
        # restoration_result = await tenant_manager.restore_tenant_from_archive(
        #     tenant_id=tenant["id"],
        #     archive_location=archival_result["archive_location"],
        #     verify_integrity=True
        # )
        #
        # assert restoration_result["status"] == "SUCCESS"
        # assert restoration_result["restored_records"] == 100
        #
        # # Verify restored data
        # restored_users = await dataflow.execute_node("ArchivalUserListNode", {
        #     "limit": 200
        # }, context=context)
        #
        # assert len(restored_users["records"]) == 100
        #
        # # Verify data integrity after restoration
        # original_emails = sorted([user["email"] for user in users])
        # restored_emails = sorted([user["email"] for user in restored_users["records"]])
        # assert original_emails == restored_emails
        #
        # # Cleanup
        # await tenant_manager.delete_tenant(tenant["id"])
        # await dataflow.close()
        pytest.skip("Tenant archival not implemented yet")
