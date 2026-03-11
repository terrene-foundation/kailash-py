"""
Integration Tests: DataFlow User Persona Workflows

Integration tests for Priority 1 and 2 user personas using real database connections.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest
from dataflow import DataFlow
from dataflow.core.config import DatabaseConfig, DataFlowConfig, MonitoringConfig

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


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


class TestStartupDeveloperIntegration:
    """Integration tests for Startup Developer (Sarah) persona - Priority 1."""

    @pytest.fixture
    async def dataflow_instance(self, test_suite):
        """Create DataFlow instance for testing."""
        database_config = DatabaseConfig(url=test_suite.config.url, pool_size=5)
        monitoring_config = MonitoringConfig(enabled=True)
        config = DataFlowConfig(database=database_config, monitoring=monitoring_config)
        db = DataFlow(config=config)

        yield db

        # No cleanup needed for in-memory testing

    def test_zero_to_first_query_flow(self, dataflow_instance):
        """Test Sarah's 'Zero to First Query' flow (5 minutes)."""
        db = dataflow_instance

        # Step 1: Define first model (should be instant)
        start_time = time.time()

        @db.model
        class User:
            name: str
            email: str
            active: bool = True
            created_at: datetime = None

        model_definition_time = time.time() - start_time
        assert model_definition_time < 1.0  # Should be sub-second

        # Step 2: Execute CRUD operations using workflow
        workflow = WorkflowBuilder()

        # Create user
        workflow.add_node(
            "UserCreateNode",
            "create_user",
            {"name": "Sarah Startup", "email": "sarah@startup.com", "active": True},
        )

        # Read user back
        workflow.add_node(
            "UserReadNode", "read_user", {"filter": {"email": "sarah@startup.com"}}
        )

        # Connect nodes
        workflow.add_connection("create_user", "id", "read_user", "id")

        # Execute workflow
        runtime = LocalRuntime()
        runtime_params = {"dataflow_instance": db}
        results, run_id = runtime.execute(workflow.build(), runtime_params)

        # Verify results
        assert results is not None
        assert "create_user" in results
        assert "read_user" in results

        created_user = results["create_user"]
        read_user = results["read_user"]

        assert created_user["name"] == "Sarah Startup"
        assert created_user["email"] == "sarah@startup.com"
        assert created_user["active"] is True
        assert read_user["id"] == created_user["id"]

        # Total time should be under 5 minutes (300 seconds)
        total_time = time.time() - start_time
        assert total_time < 300

    @pytest.mark.asyncio
    async def test_blog_application_flow(self, dataflow_instance):
        """Test Sarah's blog application building flow."""
        db = dataflow_instance

        # Step 1: Define User, Post, Comment models with relationships
        @db.model
        class BlogUser:
            username: str
            email: str
            password_hash: str
            is_active: bool = True
            created_at: datetime = None

        @db.model
        class BlogPost:
            title: str
            content: str
            author_id: int  # Foreign key to BlogUser
            published: bool = False
            created_at: datetime = None
            updated_at: datetime = None

        @db.model
        class Comment:
            content: str
            post_id: int  # Foreign key to BlogPost
            author_id: int  # Foreign key to BlogUser
            created_at: datetime = None

        # Step 2: Create blog workflow
        workflow = WorkflowBuilder()

        # Create author
        workflow.add_node(
            "BlogUserCreateNode",
            "create_author",
            {
                "username": "sarah_blogger",
                "email": "sarah@blog.com",
                "password_hash": "hashed_password_123",
                "is_active": True,
            },
        )

        # Create blog post
        workflow.add_node(
            "BlogPostCreateNode",
            "create_post",
            {
                "title": "My First DataFlow Blog Post",
                "content": "This is a test of the DataFlow blogging platform...",
                "published": True,
            },
        )

        # Create comment
        workflow.add_node(
            "CommentCreateNode",
            "create_comment",
            {"content": "Great post! DataFlow makes this so easy."},
        )

        # Connect relationships
        workflow.add_connection("create_author", "create_post", "id", "author_id")
        workflow.add_connection("create_post", "create_comment", "id", "post_id")
        workflow.add_connection("create_author", "create_comment", "id", "author_id")

        # Execute blog creation workflow
        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        # Verify blog structure
        assert results["create_author"]["username"] == "sarah_blogger"
        assert results["create_post"]["title"] == "My First DataFlow Blog Post"
        assert results["create_post"]["author_id"] == results["create_author"]["id"]
        assert results["create_comment"]["post_id"] == results["create_post"]["id"]
        assert results["create_comment"]["author_id"] == results["create_author"]["id"]

        # Step 3: Test search functionality using list nodes
        search_workflow = WorkflowBuilder()

        search_workflow.add_node(
            "BlogPostListNode",
            "search_posts",
            {
                "filter": {"published": True},
                "search_text": "DataFlow",  # Search in title/content
                "limit": 10,
            },
        )

        search_results, _ = runtime.execute(search_workflow.build())

        # Should find our post
        found_posts = search_results["search_posts"]
        assert len(found_posts) > 0
        assert any(
            post["title"] == "My First DataFlow Blog Post" for post in found_posts
        )

    @pytest.mark.asyncio
    async def test_real_time_features_flow(self, dataflow_instance):
        """Test Sarah's real-time features implementation."""
        db = dataflow_instance

        # Step 1: Define event-driven models
        @db.model
        class UserActivity:
            user_id: int
            activity_type: str  # 'login', 'post_created', 'comment_added'
            metadata: str  # JSON metadata
            timestamp: datetime = None

        @db.model
        class Notification:
            user_id: int
            message: str
            notification_type: str
            read: bool = False
            created_at: datetime = None

        # Step 2: Create activity monitoring workflow
        activity_workflow = WorkflowBuilder()

        # Log user activity
        activity_workflow.add_node(
            "UserActivityCreateNode",
            "log_activity",
            {
                "user_id": 1,
                "activity_type": "post_created",
                "metadata": '{"post_id": 123, "title": "New Post"}',
            },
        )

        # Generate notification based on activity
        activity_workflow.add_node(
            "NotificationCreateNode",
            "create_notification",
            {
                "message": "Your post has been published!",
                "notification_type": "post_published",
                "read": False,
            },
        )

        # Connect user activity to notification
        activity_workflow.add_connection(
            "log_activity", "create_notification", "user_id", "user_id"
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(activity_workflow.build())

        # Verify real-time event handling
        activity = results["log_activity"]
        notification = results["create_notification"]

        assert activity["activity_type"] == "post_created"
        assert notification["user_id"] == activity["user_id"]
        assert notification["notification_type"] == "post_published"
        assert notification["read"] is False

        # Step 3: Test performance for real-time use case
        start_time = time.time()

        # Simulate high-frequency activity logging
        bulk_activity_workflow = WorkflowBuilder()

        for i in range(10):  # Simulate 10 concurrent activities
            bulk_activity_workflow.add_node(
                "UserActivityCreateNode",
                f"activity_{i}",
                {
                    "user_id": i + 1,
                    "activity_type": "page_view",
                    "metadata": f'{{"page": "/dashboard", "session": "{i}"}}',
                },
            )

        bulk_results, _ = runtime.execute(bulk_activity_workflow.build())

        bulk_time = time.time() - start_time

        # Should handle bulk real-time events efficiently (< 2 seconds)
        assert bulk_time < 2.0
        assert len(bulk_results) == 10


class TestEnterpriseArchitectIntegration:
    """Integration tests for Enterprise Architect (Alex) persona - Priority 1."""

    @pytest.fixture
    async def enterprise_dataflow(self, test_suite):
        """Create enterprise-configured DataFlow instance."""
        config = DataFlowConfig(
            database_url=test_suite.config.url,
            pool_size=20,  # Larger pool for enterprise
            enable_multi_tenant=True,
            enable_transactions=True,
            enable_monitoring=True,
            enable_audit_logging=True,
        )
        db = DataFlow(config=config)

        await db.cleanup_test_tables()
        yield db
        await db.cleanup_test_tables()
        await db.close()

    @pytest.mark.asyncio
    async def test_multi_tenant_saas_setup(self, enterprise_dataflow):
        """Test Alex's multi-tenant SaaS setup flow."""
        db = enterprise_dataflow

        # Step 1: Define multi-tenant models
        @db.model
        class Organization:
            name: str
            plan: str  # 'basic', 'premium', 'enterprise'
            max_users: int
            created_at: datetime = None

            class Meta:
                multi_tenant = True

        @db.model
        class OrganizationUser:
            org_id: int
            email: str
            role: str  # 'admin', 'user', 'viewer'
            permissions: str  # JSON array of permissions
            created_at: datetime = None

            class Meta:
                multi_tenant = True

        # Step 2: Create multi-tenant workflow
        tenant_workflow = WorkflowBuilder()

        # Create first organization (tenant)
        tenant_workflow.add_node(
            "OrganizationCreateNode",
            "create_org_1",
            {
                "name": "ACME Corp",
                "plan": "enterprise",
                "max_users": 100,
                "tenant_id": "tenant_acme",
            },
        )

        # Create second organization (different tenant)
        tenant_workflow.add_node(
            "OrganizationCreateNode",
            "create_org_2",
            {
                "name": "Startup Inc",
                "plan": "basic",
                "max_users": 10,
                "tenant_id": "tenant_startup",
            },
        )

        # Create users for each tenant
        tenant_workflow.add_node(
            "OrganizationUserCreateNode",
            "create_user_acme",
            {
                "email": "alex@acme.com",
                "role": "admin",
                "permissions": '["manage_users", "view_analytics", "billing"]',
                "tenant_id": "tenant_acme",
            },
        )

        tenant_workflow.add_node(
            "OrganizationUserCreateNode",
            "create_user_startup",
            {
                "email": "founder@startup.com",
                "role": "admin",
                "permissions": '["manage_users"]',
                "tenant_id": "tenant_startup",
            },
        )

        # Connect organizations to users
        tenant_workflow.add_connection(
            "create_org_1", "create_user_acme", "id", "org_id"
        )
        tenant_workflow.add_connection(
            "create_org_2", "create_user_startup", "id", "org_id"
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(tenant_workflow.build())

        # Step 3: Verify tenant isolation
        acme_org = results["create_org_1"]
        startup_org = results["create_org_2"]
        acme_user = results["create_user_acme"]
        startup_user = results["create_user_startup"]

        # Organizations should be isolated
        assert acme_org["name"] == "ACME Corp"
        assert startup_org["name"] == "Startup Inc"
        assert acme_org["tenant_id"] != startup_org["tenant_id"]

        # Users should belong to correct tenants
        assert acme_user["org_id"] == acme_org["id"]
        assert startup_user["org_id"] == startup_org["id"]
        assert acme_user["tenant_id"] != startup_user["tenant_id"]

    @pytest.mark.asyncio
    async def test_distributed_transaction_implementation(self, enterprise_dataflow):
        """Test Alex's distributed transaction implementation."""
        db = enterprise_dataflow

        # Step 1: Define order processing models
        @db.model
        class Order:
            customer_id: int
            total_amount: float
            status: str  # 'pending', 'confirmed', 'shipped', 'cancelled'
            created_at: datetime = None

            class Meta:
                versioned = True  # Enable optimistic locking

        @db.model
        class OrderItem:
            order_id: int
            product_id: int
            quantity: int
            unit_price: float

        @db.model
        class Inventory:
            product_id: int
            available_quantity: int
            reserved_quantity: int = 0

            class Meta:
                versioned = True

        @db.model
        class Payment:
            order_id: int
            amount: float
            payment_method: str
            status: str  # 'pending', 'completed', 'failed'
            created_at: datetime = None

        # Step 2: Implement Saga pattern workflow
        saga_workflow = WorkflowBuilder()

        # Transaction Step 1: Create order
        saga_workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {"customer_id": 12345, "total_amount": 199.99, "status": "pending"},
        )

        # Transaction Step 2: Reserve inventory
        saga_workflow.add_node(
            "InventoryUpdateNode",
            "reserve_inventory",
            {"product_id": 1, "reserve_quantity": 2, "operation": "reserve"},
        )

        # Transaction Step 3: Process payment
        saga_workflow.add_node(
            "PaymentCreateNode",
            "process_payment",
            {"amount": 199.99, "payment_method": "credit_card", "status": "pending"},
        )

        # Transaction Step 4: Confirm order (only if payment succeeds)
        saga_workflow.add_node(
            "OrderUpdateNode",
            "confirm_order",
            {"status": "confirmed", "condition": "payment_status == 'completed'"},
        )

        # Connect saga steps with compensation logic
        saga_workflow.add_connection(
            "create_order", "reserve_inventory", "id", "order_id"
        )
        saga_workflow.add_connection(
            "create_order", "process_payment", "id", "order_id"
        )
        saga_workflow.add_connection(
            "process_payment", "confirm_order", "order_id", "id"
        )

        # Add compensation nodes (for rollback)
        saga_workflow.add_node(
            "InventoryUpdateNode",
            "release_inventory",
            {"operation": "release", "compensation_for": "reserve_inventory"},
        )

        saga_workflow.add_node(
            "OrderUpdateNode",
            "cancel_order",
            {"status": "cancelled", "compensation_for": "create_order"},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(saga_workflow.build())

        # Step 3: Verify transaction consistency
        order = results["create_order"]
        payment = results["process_payment"]

        assert order["status"] == "pending"
        assert payment["order_id"] == order["id"]
        assert payment["amount"] == order["total_amount"]

        # Step 4: Test failure scenario with compensation
        failure_workflow = WorkflowBuilder()

        failure_workflow.add_node(
            "OrderCreateNode",
            "create_failing_order",
            {"customer_id": 12346, "total_amount": 299.99, "status": "pending"},
        )

        # Simulate payment failure
        failure_workflow.add_node(
            "PaymentCreateNode",
            "failing_payment",
            {"amount": 299.99, "payment_method": "expired_card", "status": "failed"},
        )

        # Should trigger compensation
        failure_workflow.add_node(
            "OrderUpdateNode",
            "compensate_order",
            {"status": "cancelled", "reason": "payment_failed"},
        )

        failure_workflow.add_connection(
            "create_failing_order", "failing_payment", "id", "order_id"
        )
        failure_workflow.add_connection(
            "failing_payment", "compensate_order", "order_id", "id"
        )

        failure_results, _ = runtime.execute(failure_workflow.build())

        # Verify compensation executed
        failed_order = failure_results["create_failing_order"]
        failed_payment = failure_results["failing_payment"]
        compensated_order = failure_results["compensate_order"]

        assert failed_payment["status"] == "failed"
        assert compensated_order["id"] == failed_order["id"]
        assert compensated_order["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_security_and_compliance_flow(self, enterprise_dataflow):
        """Test Alex's security and compliance implementation."""
        db = enterprise_dataflow

        # Step 1: Define GDPR-compliant models
        @db.model
        class PersonalData:
            user_id: int
            data_type: str  # 'email', 'name', 'address', etc.
            encrypted_value: str  # Encrypted PII
            consent_given: bool = False
            consent_date: datetime = None
            retention_period_days: int = 365
            created_at: datetime = None

            class Meta:
                audit_enabled = True
                encryption_enabled = True

        @db.model
        class DataProcessingLog:
            user_id: int
            operation: str  # 'create', 'read', 'update', 'delete'
            data_types: str  # JSON array of data types accessed
            purpose: str  # 'service_provision', 'analytics', etc.
            legal_basis: str  # 'consent', 'legitimate_interest', etc.
            timestamp: datetime = None

            class Meta:
                audit_enabled = True
                immutable = True  # Cannot be modified once created

        # Step 2: Implement GDPR compliance workflow
        gdpr_workflow = WorkflowBuilder()

        # User gives consent for data processing
        gdpr_workflow.add_node(
            "PersonalDataCreateNode",
            "record_consent",
            {
                "user_id": 98765,
                "data_type": "email",
                "encrypted_value": "encrypted_email_data_here",
                "consent_given": True,
                "retention_period_days": 730,  # 2 years for enterprise
            },
        )

        # Log the data processing activity
        gdpr_workflow.add_node(
            "DataProcessingLogCreateNode",
            "log_processing",
            {
                "operation": "create",
                "data_types": '["email", "name"]',
                "purpose": "service_provision",
                "legal_basis": "consent",
            },
        )

        # Connect user consent to processing log
        gdpr_workflow.add_connection(
            "record_consent", "log_processing", "user_id", "user_id"
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(gdpr_workflow.build())

        # Step 3: Verify compliance features
        personal_data = results["record_consent"]
        processing_log = results["log_processing"]

        assert personal_data["consent_given"] is True
        assert personal_data["encrypted_value"] is not None
        assert processing_log["user_id"] == personal_data["user_id"]
        assert processing_log["legal_basis"] == "consent"

        # Step 4: Test data masking for non-privileged access
        data_access_workflow = WorkflowBuilder()

        data_access_workflow.add_node(
            "PersonalDataReadNode",
            "read_personal_data",
            {
                "filter": {"user_id": 98765},
                "mask_sensitive_fields": True,  # Non-admin access
                "access_purpose": "analytics",
            },
        )

        # Log the read access
        data_access_workflow.add_node(
            "DataProcessingLogCreateNode",
            "log_read_access",
            {
                "user_id": 98765,
                "operation": "read",
                "data_types": '["email"]',
                "purpose": "analytics",
                "legal_basis": "legitimate_interest",
            },
        )

        access_results, _ = runtime.execute(data_access_workflow.build())

        # Verify data masking applied
        masked_data = access_results["read_personal_data"]
        read_log = access_results["log_read_access"]

        # Sensitive data should be masked
        assert (
            "***" in masked_data["encrypted_value"]
            or masked_data["encrypted_value"] == "[MASKED]"
        )
        assert read_log["operation"] == "read"
        assert read_log["purpose"] == "analytics"


class TestDataEngineerIntegration:
    """Integration tests for Data Engineer (David) persona - Priority 2."""

    @pytest.fixture
    async def data_pipeline_dataflow(self, test_suite):
        """Create DataFlow instance optimized for data engineering."""
        config = DataFlowConfig(
            database_url=test_suite.config.url,
            pool_size=50,  # Large pool for bulk operations
            enable_bulk_operations=True,
            enable_monitoring=True,
            bulk_batch_size=1000,
        )
        db = DataFlow(config=config)

        await db.cleanup_test_tables()
        yield db
        await db.cleanup_test_tables()
        await db.close()

    @pytest.mark.asyncio
    async def test_bulk_data_import_flow(self, data_pipeline_dataflow):
        """Test David's bulk data import workflow."""
        db = data_pipeline_dataflow

        # Step 1: Define data models for bulk import
        @db.model
        class CustomerData:
            customer_id: str
            first_name: str
            last_name: str
            email: str
            phone: str
            registration_date: datetime = None

            def validate_email(self, email: str) -> str:
                """Validate email format during import."""
                if "@" not in email:
                    raise ValueError(f"Invalid email format: {email}")
                return email

        @db.model
        class ImportJob:
            job_name: str
            total_records: int
            processed_records: int = 0
            failed_records: int = 0
            status: str = "running"  # 'running', 'completed', 'failed'
            started_at: datetime = None
            completed_at: datetime = None

        # Step 2: Create bulk import workflow
        bulk_import_workflow = WorkflowBuilder()

        # Create import job tracker
        bulk_import_workflow.add_node(
            "ImportJobCreateNode",
            "create_import_job",
            {
                "job_name": "customer_data_import_2024",
                "total_records": 5000,
                "status": "running",
            },
        )

        # Generate test data for bulk import
        test_customers = []
        for i in range(100):  # Smaller test set for integration test
            test_customers.append(
                {
                    "customer_id": f"CUST_{i:04d}",
                    "first_name": f"Customer{i}",
                    "last_name": f"LastName{i}",
                    "email": f"customer{i}@example.com",
                    "phone": f"+1555000{i:04d}",
                }
            )

        # Bulk create customers
        bulk_import_workflow.add_node(
            "CustomerDataBulkCreateNode",
            "bulk_import_customers",
            {
                "data": test_customers,
                "batch_size": 25,  # Process in batches
                "on_validation_error": "skip",  # Skip invalid records
                "track_progress": True,
            },
        )

        # Update import job with results
        bulk_import_workflow.add_node(
            "ImportJobUpdateNode",
            "update_import_job",
            {"status": "completed", "processed_records": len(test_customers)},
        )

        # Connect import tracking
        bulk_import_workflow.add_connection(
            "create_import_job", "update_import_job", "id", "id"
        )

        start_time = time.time()
        runtime = LocalRuntime()
        results, _ = runtime.execute(bulk_import_workflow.build())
        bulk_time = time.time() - start_time

        # Step 3: Verify bulk import performance and results
        import_job = results["create_import_job"]
        bulk_result = results["bulk_import_customers"]
        updated_job = results["update_import_job"]

        assert import_job["total_records"] == 5000
        assert updated_job["status"] == "completed"
        assert updated_job["processed_records"] == 100

        # Bulk import should be efficient (< 5 seconds for 100 records)
        assert bulk_time < 5.0

        # Verify data integrity with sample reads
        verification_workflow = WorkflowBuilder()

        verification_workflow.add_node(
            "CustomerDataListNode",
            "verify_import",
            {"filter": {"customer_id": "CUST_0001"}, "limit": 1},
        )

        verification_results, _ = runtime.execute(verification_workflow.build())

        verified_customer = verification_results["verify_import"][0]
        assert verified_customer["customer_id"] == "CUST_0001"
        assert verified_customer["email"] == "customer1@example.com"

    @pytest.mark.asyncio
    async def test_real_time_cdc_pipeline_flow(self, data_pipeline_dataflow):
        """Test David's real-time Change Data Capture pipeline."""
        db = data_pipeline_dataflow

        # Step 1: Define source and destination models
        @db.model
        class SourceTable:
            record_id: int
            data_value: str
            last_modified: datetime = None
            version: int = 1

            class Meta:
                enable_cdc = True  # Enable change data capture

        @db.model
        class ChangeEvent:
            source_table: str
            record_id: int
            operation_type: str  # 'INSERT', 'UPDATE', 'DELETE'
            old_values: str  # JSON of old values
            new_values: str  # JSON of new values
            timestamp: datetime = None

        @db.model
        class DestinationTable:
            source_record_id: int
            processed_data: str
            sync_status: str = "pending"  # 'pending', 'synced', 'failed'
            last_synced: datetime = None

        # Step 2: Create CDC pipeline workflow
        cdc_workflow = WorkflowBuilder()

        # Create initial source record
        cdc_workflow.add_node(
            "SourceTableCreateNode",
            "create_source",
            {"record_id": 1001, "data_value": "Initial data value", "version": 1},
        )

        # CDC should automatically create change event
        cdc_workflow.add_node(
            "ChangeEventCreateNode",
            "capture_change",
            {
                "source_table": "source_table",
                "operation_type": "INSERT",
                "new_values": '{"record_id": 1001, "data_value": "Initial data value"}',
            },
        )

        # Process change to destination
        cdc_workflow.add_node(
            "DestinationTableCreateNode",
            "sync_to_destination",
            {
                "processed_data": "Processed: Initial data value",
                "sync_status": "synced",
            },
        )

        # Connect CDC pipeline
        cdc_workflow.add_connection(
            "create_source", "capture_change", "record_id", "record_id"
        )
        cdc_workflow.add_connection(
            "capture_change", "sync_to_destination", "record_id", "source_record_id"
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(cdc_workflow.build())

        # Step 3: Verify CDC pipeline
        source_record = results["create_source"]
        change_event = results["capture_change"]
        destination_record = results["sync_to_destination"]

        assert source_record["record_id"] == 1001
        assert change_event["operation_type"] == "INSERT"
        assert change_event["record_id"] == source_record["record_id"]
        assert destination_record["source_record_id"] == source_record["record_id"]
        assert destination_record["sync_status"] == "synced"

        # Step 4: Test update CDC
        update_cdc_workflow = WorkflowBuilder()

        # Update source record
        update_cdc_workflow.add_node(
            "SourceTableUpdateNode",
            "update_source",
            {
                "id": source_record["id"],
                "data_value": "Updated data value",
                "version": 2,
            },
        )

        # Capture UPDATE change event
        update_cdc_workflow.add_node(
            "ChangeEventCreateNode",
            "capture_update",
            {
                "source_table": "source_table",
                "record_id": 1001,
                "operation_type": "UPDATE",
                "old_values": '{"data_value": "Initial data value", "version": 1}',
                "new_values": '{"data_value": "Updated data value", "version": 2}',
            },
        )

        # Update destination
        update_cdc_workflow.add_node(
            "DestinationTableUpdateNode",
            "update_destination",
            {
                "source_record_id": 1001,
                "processed_data": "Processed: Updated data value",
                "sync_status": "synced",
            },
        )

        update_results, _ = runtime.execute(update_cdc_workflow.build())

        # Verify UPDATE CDC
        updated_source = update_results["update_source"]
        update_event = update_results["capture_update"]

        assert updated_source["data_value"] == "Updated data value"
        assert updated_source["version"] == 2
        assert update_event["operation_type"] == "UPDATE"


class TestDevOpsEngineerIntegration:
    """Integration tests for DevOps Engineer (Diana) persona - Priority 2."""

    @pytest.fixture
    async def production_dataflow(self, test_suite):
        """Create production-configured DataFlow instance."""
        config = DataFlowConfig(
            database_url=test_suite.config.url,
            pool_size=30,
            max_overflow=50,
            enable_monitoring=True,
            enable_health_checks=True,
            health_check_interval=30,
            connection_timeout=10,
        )
        db = DataFlow(config=config)

        await db.cleanup_test_tables()
        yield db
        await db.cleanup_test_tables()
        await db.close()

    @pytest.mark.asyncio
    async def test_production_deployment_flow(self, production_dataflow):
        """Test Diana's production deployment workflow."""
        db = production_dataflow

        # Step 1: Verify production configuration
        config = db.config

        assert config.pool_size >= 20  # Production needs larger pools
        assert config.enable_monitoring is True
        assert config.enable_health_checks is True
        assert config.connection_timeout > 0

        # Step 2: Test connection pool health
        pool_metrics = db.get_connection_pool_metrics()

        assert pool_metrics is not None
        assert "total_connections" in pool_metrics
        assert "active_connections" in pool_metrics
        assert "pool_size" in pool_metrics

        # Step 3: Verify health check endpoints
        health_check_workflow = WorkflowBuilder()

        health_check_workflow.add_node(
            "HealthCheckNode",
            "database_health",
            {"check_types": ["connection", "query", "pool_status"], "timeout": 5},
        )

        runtime = LocalRuntime()
        health_results, _ = runtime.execute(health_check_workflow.build())

        health_status = health_results["database_health"]

        assert health_status["overall_status"] == "healthy"
        assert health_status["checks"]["connection"]["status"] == "healthy"
        assert health_status["checks"]["query"]["status"] == "healthy"
        assert health_status["checks"]["pool_status"]["status"] == "healthy"

        # Step 4: Test monitoring data collection
        @db.model
        class HealthMetric:
            service_name: str
            metric_name: str
            metric_value: float
            timestamp: datetime = None

        monitoring_workflow = WorkflowBuilder()

        # Collect database metrics
        monitoring_workflow.add_node(
            "HealthMetricCreateNode",
            "log_connection_count",
            {
                "service_name": "dataflow",
                "metric_name": "active_connections",
                "metric_value": pool_metrics.get("active_connections", 0),
            },
        )

        monitoring_workflow.add_node(
            "HealthMetricCreateNode",
            "log_query_latency",
            {
                "service_name": "dataflow",
                "metric_name": "avg_query_latency_ms",
                "metric_value": 45.2,  # Sample latency
            },
        )

        monitoring_results, _ = runtime.execute(monitoring_workflow.build())

        # Verify metrics collection
        connection_metric = monitoring_results["log_connection_count"]
        latency_metric = monitoring_results["log_query_latency"]

        assert connection_metric["service_name"] == "dataflow"
        assert connection_metric["metric_name"] == "active_connections"
        assert latency_metric["metric_name"] == "avg_query_latency_ms"
        assert latency_metric["metric_value"] == 45.2

    @pytest.mark.asyncio
    async def test_performance_tuning_flow(self, production_dataflow):
        """Test Diana's performance tuning workflow."""
        db = production_dataflow

        # Step 1: Create performance test models
        @db.model
        class PerformanceTest:
            test_name: str
            operation_type: str  # 'select', 'insert', 'update', 'delete'
            execution_time_ms: float
            rows_affected: int
            timestamp: datetime = None

        @db.model
        class SlowQueryLog:
            query_text: str
            execution_time_ms: float
            rows_examined: int
            rows_returned: int
            timestamp: datetime = None

            class Meta:
                indexes = [
                    {"fields": ["execution_time_ms"], "name": "idx_slow_query_time"}
                ]

        # Step 2: Simulate performance monitoring
        perf_workflow = WorkflowBuilder()

        # Log various operation performances
        operations = [
            {"name": "user_list_query", "type": "select", "time": 125.3, "rows": 1000},
            {"name": "bulk_insert", "type": "insert", "time": 2840.7, "rows": 5000},
            {"name": "update_user_status", "type": "update", "time": 45.2, "rows": 1},
            {
                "name": "complex_join_query",
                "type": "select",
                "time": 1250.8,
                "rows": 150,
            },
        ]

        for i, op in enumerate(operations):
            perf_workflow.add_node(
                "PerformanceTestCreateNode",
                f"log_perf_{i}",
                {
                    "test_name": op["name"],
                    "operation_type": op["type"],
                    "execution_time_ms": op["time"],
                    "rows_affected": op["rows"],
                },
            )

        # Log slow queries (> 1000ms)
        slow_queries = [
            {
                "query": "SELECT * FROM users u JOIN orders o ON u.id = o.user_id WHERE o.created_at > ?",
                "time": 1250.8,
                "examined": 50000,
                "returned": 150,
            },
            {
                "query": "INSERT INTO analytics_events (user_id, event_type, data) VALUES ...",
                "time": 2840.7,
                "examined": 5000,
                "returned": 5000,
            },
        ]

        for i, query in enumerate(slow_queries):
            perf_workflow.add_node(
                "SlowQueryLogCreateNode",
                f"log_slow_{i}",
                {
                    "query_text": query["query"],
                    "execution_time_ms": query["time"],
                    "rows_examined": query["examined"],
                    "rows_returned": query["returned"],
                },
            )

        runtime = LocalRuntime()
        perf_results, _ = runtime.execute(perf_workflow.build())

        # Step 3: Analyze performance data
        performance_analysis_workflow = WorkflowBuilder()

        # Find slow operations (> 1000ms)
        performance_analysis_workflow.add_node(
            "PerformanceTestListNode",
            "find_slow_operations",
            {
                "filter": {"execution_time_ms__gt": 1000},
                "order_by": ["-execution_time_ms"],
                "limit": 10,
            },
        )

        # Get query performance statistics
        performance_analysis_workflow.add_node(
            "SlowQueryLogListNode",
            "analyze_slow_queries",
            {
                "filter": {"execution_time_ms__gt": 1000},
                "aggregate": {
                    "avg_execution_time": "AVG(execution_time_ms)",
                    "max_execution_time": "MAX(execution_time_ms)",
                    "total_slow_queries": "COUNT(*)",
                },
            },
        )

        analysis_results, _ = runtime.execute(performance_analysis_workflow.build())

        # Verify performance analysis
        slow_operations = analysis_results["find_slow_operations"]
        query_stats = analysis_results["analyze_slow_queries"]

        assert len(slow_operations) == 2  # bulk_insert and complex_join_query
        assert any(op["test_name"] == "bulk_insert" for op in slow_operations)
        assert any(op["test_name"] == "complex_join_query" for op in slow_operations)

        assert query_stats["total_slow_queries"] == 2
        assert query_stats["max_execution_time"] > 2000  # Should find the bulk insert

        # Step 4: Test connection pool optimization
        original_pool_size = db.config.pool_size

        # Simulate pool optimization
        optimized_config = db.config.copy(
            pool_size=original_pool_size + 10,  # Increase pool size
            max_overflow=original_pool_size + 20,
        )

        assert optimized_config.pool_size == original_pool_size + 10
        assert optimized_config.max_overflow == original_pool_size + 20
