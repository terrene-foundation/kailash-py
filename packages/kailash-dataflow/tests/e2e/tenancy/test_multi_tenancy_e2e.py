"""
E2E tests for advanced multi-tenancy support

Tests complete multi-tenant workflows with real Docker services
and DataFlow integration. NO MOCKING - complete scenarios.
"""

import json
import time

import pytest
from dataflow import DataFlow
from dataflow.core.multi_tenancy import (
    RowLevelSecurityStrategy,
    SchemaIsolationStrategy,
    TenantConfig,
    TenantContext,
    TenantManager,
)

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


@pytest.mark.e2e
@pytest.mark.requires_docker
class TestMultiTenancyE2E:
    """End-to-end tests for complete multi-tenant workflows."""

    @pytest.fixture(scope="class")
    def multi_tenant_dataflow(self):
        """Create multi-tenant DataFlow instance."""
        # Use PostgreSQL for advanced multi-tenancy features
        db = DataFlow(
            database_url="postgresql://test:test@localhost:5432/test_multitenancy",
            multi_tenant=True,
            tenant_isolation="hybrid",  # Schema + RLS
            pool_size=20,
        )

        # Configure tenant manager
        tenant_manager = TenantManager(
            default_isolation="schema", enable_audit=True, enable_encryption=True
        )

        db._tenant_manager = tenant_manager

        return db

    @pytest.fixture(scope="class")
    def test_tenant_models(self, multi_tenant_dataflow):
        """Create multi-tenant models."""
        db = multi_tenant_dataflow

        # Customer model with multi-tenancy
        @db.model
        class Customer:
            name: str
            email: str
            phone: str
            status: str = "active"

            __dataflow__ = {
                "multi_tenant": True,
                "soft_delete": True,
                "audit_log": True,
                "encryption_fields": ["phone"],
            }

        # Order model with tenant isolation
        @db.model
        class Order:
            customer_id: int
            total: float
            status: str = "pending"
            order_date: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True, "versioned": True}

        # Invoice model with high security
        @db.model
        class Invoice:
            order_id: int
            invoice_number: str
            amount: float
            tax_amount: float
            payment_status: str = "unpaid"

            __dataflow__ = {
                "multi_tenant": True,
                "audit_log": True,
                "encryption_fields": ["invoice_number"],
                "security_level": 3,
            }

        # Analytics model (tenant-specific analytics)
        @db.model
        class TenantAnalytics:
            metric_name: str
            metric_value: float
            calculation_date: str
            metadata: str  # JSON string

            __dataflow__ = {
                "multi_tenant": True,
                "read_only": True,  # Only updated by analytics jobs
            }

        # Create schemas and tables for each tenant
        db._create_tenant_infrastructure()

        return {
            "Customer": Customer,
            "Order": Order,
            "Invoice": Invoice,
            "TenantAnalytics": TenantAnalytics,
        }

    @pytest.fixture(autouse=True)
    def setup_test_tenants(self, multi_tenant_dataflow):
        """Setup test tenants before each test."""
        db = multi_tenant_dataflow
        tenant_manager = db._tenant_manager

        # Create test tenant configurations
        test_tenants = [
            TenantConfig(
                tenant_id="saas_tenant_1",
                name="SaaS Customer 1",
                isolation_strategy="schema",
                database_config={"schema": "saas_tenant_1"},
                security_settings={"encryption": True, "audit": True},
            ),
            TenantConfig(
                tenant_id="saas_tenant_2",
                name="SaaS Customer 2",
                isolation_strategy="schema",
                database_config={"schema": "saas_tenant_2"},
                security_settings={"encryption": True, "audit": True},
            ),
            TenantConfig(
                tenant_id="enterprise_tenant",
                name="Enterprise Customer",
                isolation_strategy="hybrid",
                database_config={"schema": "enterprise_tenant"},
                security_settings={"encryption": True, "audit": True, "mfa": True},
            ),
        ]

        # Register tenants
        for tenant_config in test_tenants:
            tenant_manager.register_tenant(tenant_config)
            tenant_manager.create_tenant_infrastructure(db._engine, tenant_config)

        yield

        # Cleanup tenants after test
        for tenant_config in test_tenants:
            tenant_manager.cleanup_tenant(db._engine, tenant_config.tenant_id)

    def test_complete_saas_customer_lifecycle(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Complete SaaS customer lifecycle with tenant isolation."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Order = test_tenant_models["Order"]
        Invoice = test_tenant_models["Invoice"]

        # Phase 1: Customer onboarding (Tenant 1)
        with TenantContext.set_current("saas_tenant_1", "admin_user"):
            onboarding_workflow = WorkflowBuilder()

            # Create initial customers
            onboarding_workflow.add_node(
                "CustomerBulkCreateNode",
                "onboard_customers",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "name": "Acme Corp",
                            "email": "contact@acme.com",
                            "phone": "+1-555-0101",
                            "status": "active",
                        },
                        {
                            "name": "Beta Industries",
                            "email": "hello@beta.com",
                            "phone": "+1-555-0102",
                            "status": "active",
                        },
                    ],
                    "return_ids": True,
                },
            )

            # Create welcome orders
            onboarding_workflow.add_node(
                "OrderBulkCreateNode",
                "welcome_orders",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "customer_id": 1,
                            "total": 1000.0,
                            "status": "completed",
                            "order_date": "2025-01-15",
                        },
                        {
                            "customer_id": 2,
                            "total": 1500.0,
                            "status": "completed",
                            "order_date": "2025-01-15",
                        },
                    ],
                },
            )

            runtime = LocalRuntime()
            onboarding_results, _ = runtime.execute(onboarding_workflow.build())

            assert len(onboarding_results["onboard_customers"]["records"]) == 2
            assert len(onboarding_results["welcome_orders"]["records"]) == 2

        # Phase 2: Parallel operations for Tenant 2 (should be isolated)
        with TenantContext.set_current("saas_tenant_2", "admin_user"):
            tenant2_workflow = WorkflowBuilder()

            # Create customers for tenant 2
            tenant2_workflow.add_node(
                "CustomerBulkCreateNode",
                "tenant2_customers",
                {
                    "tenant_id": "saas_tenant_2",
                    "data": [
                        {
                            "name": "Gamma Solutions",
                            "email": "info@gamma.com",
                            "phone": "+1-555-0201",
                            "status": "active",
                        },
                        {
                            "name": "Delta Enterprises",
                            "email": "contact@delta.com",
                            "phone": "+1-555-0202",
                            "status": "trial",
                        },
                    ],
                },
            )

            tenant2_results, _ = runtime.execute(tenant2_workflow.build())

            assert len(tenant2_results["tenant2_customers"]["records"]) == 2

        # Phase 3: Verify tenant isolation - each tenant should only see their data
        with TenantContext.set_current("saas_tenant_1", "user_1"):
            tenant1_check_workflow = WorkflowBuilder()

            tenant1_check_workflow.add_node(
                "CustomerListNode",
                "check_customers",
                {"tenant_id": "saas_tenant_1", "filter": {"status": "active"}},
            )

            tenant1_check_results, _ = runtime.execute(tenant1_check_workflow.build())

            # Should only see tenant 1 customers
            tenant1_customers = tenant1_check_results["check_customers"]["records"]
            assert len(tenant1_customers) == 2

            # Verify no cross-tenant data leakage
            customer_emails = [c["email"] for c in tenant1_customers]
            assert "contact@acme.com" in customer_emails
            assert "hello@beta.com" in customer_emails
            assert (
                "info@gamma.com" not in customer_emails
            )  # Should not see tenant 2 data

        # Phase 4: Business operations - invoicing
        with TenantContext.set_current("saas_tenant_1", "billing_user"):
            billing_workflow = WorkflowBuilder()

            # Generate invoices for completed orders
            billing_workflow.add_node(
                "OrderListNode",
                "completed_orders",
                {"tenant_id": "saas_tenant_1", "filter": {"status": "completed"}},
            )

            billing_workflow.add_node(
                "InvoiceBulkCreateNode",
                "generate_invoices",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "order_id": 1,
                            "invoice_number": "INV-T1-001",
                            "amount": 1000.0,
                            "tax_amount": 100.0,
                            "payment_status": "pending",
                        },
                        {
                            "order_id": 2,
                            "invoice_number": "INV-T1-002",
                            "amount": 1500.0,
                            "tax_amount": 150.0,
                            "payment_status": "pending",
                        },
                    ],
                },
            )

            billing_results, _ = runtime.execute(billing_workflow.build())

            assert len(billing_results["generate_invoices"]["records"]) == 2

        # Phase 5: Audit trail verification
        with TenantContext.set_current("saas_tenant_1", "audit_user"):
            audit_workflow = WorkflowBuilder()

            audit_workflow.add_node(
                "AuditTrailNode",
                "check_audit",
                {
                    "tenant_id": "saas_tenant_1",
                    "table_name": "customers",
                    "operation": "INSERT",
                    "date_range": {"start": "2025-01-15", "end": "2025-01-16"},
                },
            )

            audit_results, _ = runtime.execute(audit_workflow.build())

            # Should have audit records for customer creation
            audit_records = audit_results["check_audit"]["records"]
            assert len(audit_records) >= 2  # At least 2 INSERT operations

    def test_enterprise_tenant_advanced_security(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Enterprise tenant with advanced security features."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Invoice = test_tenant_models["Invoice"]

        # Phase 1: High-security customer creation
        with TenantContext.set_current("enterprise_tenant", "security_admin"):
            secure_workflow = WorkflowBuilder()

            # Create customers with encryption
            secure_workflow.add_node(
                "CustomerBulkCreateNode",
                "secure_customers",
                {
                    "tenant_id": "enterprise_tenant",
                    "security_level": 3,
                    "encryption_enabled": True,
                    "data": [
                        {
                            "name": "Classified Corp",
                            "email": "secure@classified.com",
                            "phone": "+1-555-9999",  # Will be encrypted
                            "status": "active",
                        },
                        {
                            "name": "Top Secret Inc",
                            "email": "contact@topsecret.com",
                            "phone": "+1-555-8888",  # Will be encrypted
                            "status": "active",
                        },
                    ],
                },
            )

            runtime = LocalRuntime()
            secure_results, _ = runtime.execute(secure_workflow.build())

            assert len(secure_results["secure_customers"]["records"]) == 2

        # Phase 2: Access control testing
        with TenantContext.set_current("enterprise_tenant", "restricted_user"):
            # Lower privilege user should have limited access
            restricted_workflow = WorkflowBuilder()

            restricted_workflow.add_node(
                "CustomerListNode",
                "restricted_access",
                {
                    "tenant_id": "enterprise_tenant",
                    "security_level": 1,  # Low security level
                    "filter": {"status": "active"},
                },
            )

            # This should succeed but with limited data
            restricted_results, _ = runtime.execute(restricted_workflow.build())

            # Should see customers but encrypted fields should be masked
            customers = restricted_results["restricted_access"]["records"]
            assert len(customers) == 2

            # Phone numbers should be encrypted/masked for low-privilege user
            for customer in customers:
                assert "phone" in customer
                # Encrypted phone should not be the original number
                assert customer["phone"] != "+1-555-9999"
                assert customer["phone"] != "+1-555-8888"

        # Phase 3: High-privilege access
        with TenantContext.set_current("enterprise_tenant", "security_admin"):
            admin_workflow = WorkflowBuilder()

            admin_workflow.add_node(
                "CustomerListNode",
                "admin_access",
                {
                    "tenant_id": "enterprise_tenant",
                    "security_level": 3,  # High security level
                    "decrypt_fields": True,
                    "filter": {"status": "active"},
                },
            )

            admin_results, _ = runtime.execute(admin_workflow.build())

            # Admin should see decrypted data
            admin_customers = admin_results["admin_access"]["records"]
            assert len(admin_customers) == 2

            # At least one phone should be decrypted for admin
            phone_numbers = [c["phone"] for c in admin_customers]
            assert any(
                phone in ["+1-555-9999", "+1-555-8888"] for phone in phone_numbers
            )

        # Phase 4: Secure invoice generation
        with TenantContext.set_current("enterprise_tenant", "finance_user"):
            finance_workflow = WorkflowBuilder()

            finance_workflow.add_node(
                "InvoiceBulkCreateNode",
                "secure_invoices",
                {
                    "tenant_id": "enterprise_tenant",
                    "security_level": 3,
                    "encryption_enabled": True,
                    "data": [
                        {
                            "order_id": 1,
                            "invoice_number": "SEC-INV-001",  # Will be encrypted
                            "amount": 50000.0,
                            "tax_amount": 5000.0,
                            "payment_status": "pending",
                        },
                        {
                            "order_id": 2,
                            "invoice_number": "SEC-INV-002",  # Will be encrypted
                            "amount": 75000.0,
                            "tax_amount": 7500.0,
                            "payment_status": "pending",
                        },
                    ],
                },
            )

            finance_results, _ = runtime.execute(finance_workflow.build())

            assert len(finance_results["secure_invoices"]["records"]) == 2

        # Phase 5: Security audit
        with TenantContext.set_current("enterprise_tenant", "audit_admin"):
            security_audit_workflow = WorkflowBuilder()

            security_audit_workflow.add_node(
                "SecurityAuditNode",
                "security_check",
                {
                    "tenant_id": "enterprise_tenant",
                    "audit_type": "encryption",
                    "check_access_violations": True,
                    "check_data_leakage": True,
                },
            )

            security_audit_results, _ = runtime.execute(security_audit_workflow.build())

            # Should pass security checks
            audit_report = security_audit_results["security_check"]["report"]
            assert audit_report["encryption_status"] == "compliant"
            assert audit_report["access_violations"] == 0
            assert audit_report["data_leakage_incidents"] == 0

    def test_tenant_analytics_and_reporting(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Tenant-specific analytics and reporting."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Order = test_tenant_models["Order"]
        TenantAnalytics = test_tenant_models["TenantAnalytics"]

        # Phase 1: Setup data for analytics
        with TenantContext.set_current("saas_tenant_1", "data_user"):
            setup_workflow = WorkflowBuilder()

            # Create customers
            setup_workflow.add_node(
                "CustomerBulkCreateNode",
                "analytics_customers",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "name": f"Customer {i}",
                            "email": f"customer{i}@example.com",
                            "phone": f"+1-555-{i:04d}",
                        }
                        for i in range(1, 21)  # 20 customers
                    ],
                },
            )

            # Create orders with different patterns
            order_data = []
            for i in range(1, 21):
                customer_id = i
                order_count = (i % 3) + 1  # 1-3 orders per customer
                for j in range(order_count):
                    order_data.append(
                        {
                            "customer_id": customer_id,
                            "total": 100.0 + (i * 10) + (j * 5),
                            "status": "completed" if j % 2 == 0 else "pending",
                            "order_date": f"2025-01-{(i % 28) + 1:02d}",
                        }
                    )

            setup_workflow.add_node(
                "OrderBulkCreateNode",
                "analytics_orders",
                {"tenant_id": "saas_tenant_1", "data": order_data},
            )

            runtime = LocalRuntime()
            setup_results, _ = runtime.execute(setup_workflow.build())

            assert len(setup_results["analytics_customers"]["records"]) == 20
            assert len(setup_results["analytics_orders"]["records"]) == len(order_data)

        # Phase 2: Generate analytics
        with TenantContext.set_current("saas_tenant_1", "analytics_user"):
            analytics_workflow = WorkflowBuilder()

            # Customer analytics
            analytics_workflow.add_node(
                "CustomerAnalyticsNode",
                "customer_metrics",
                {
                    "tenant_id": "saas_tenant_1",
                    "metrics": [
                        {"name": "total_customers", "calculation": "count"},
                        {
                            "name": "active_customers",
                            "calculation": "count",
                            "filter": {"status": "active"},
                        },
                        {
                            "name": "avg_orders_per_customer",
                            "calculation": "avg_orders",
                        },
                    ],
                },
            )

            # Order analytics
            analytics_workflow.add_node(
                "OrderAnalyticsNode",
                "order_metrics",
                {
                    "tenant_id": "saas_tenant_1",
                    "metrics": [
                        {
                            "name": "total_revenue",
                            "calculation": "sum",
                            "field": "total",
                        },
                        {
                            "name": "avg_order_value",
                            "calculation": "avg",
                            "field": "total",
                        },
                        {
                            "name": "completed_orders",
                            "calculation": "count",
                            "filter": {"status": "completed"},
                        },
                        {
                            "name": "pending_orders",
                            "calculation": "count",
                            "filter": {"status": "pending"},
                        },
                    ],
                },
            )

            # Time-based analytics
            analytics_workflow.add_node(
                "TimeSeriesAnalyticsNode",
                "time_metrics",
                {
                    "tenant_id": "saas_tenant_1",
                    "group_by": "order_date",
                    "metrics": [
                        {
                            "name": "daily_revenue",
                            "calculation": "sum",
                            "field": "total",
                        },
                        {"name": "daily_orders", "calculation": "count"},
                    ],
                },
            )

            analytics_results, _ = runtime.execute(analytics_workflow.build())

            # Verify analytics results
            customer_metrics = analytics_results["customer_metrics"]["metrics"]
            assert customer_metrics["total_customers"] == 20
            assert customer_metrics["active_customers"] == 20

            order_metrics = analytics_results["order_metrics"]["metrics"]
            assert order_metrics["total_revenue"] > 0
            assert order_metrics["avg_order_value"] > 0
            assert order_metrics["completed_orders"] > 0
            assert order_metrics["pending_orders"] > 0

        # Phase 3: Store analytics for historical tracking
        with TenantContext.set_current("saas_tenant_1", "analytics_user"):
            storage_workflow = WorkflowBuilder()

            # Store calculated metrics
            metrics_data = [
                {
                    "metric_name": "daily_active_customers",
                    "metric_value": 20.0,
                    "calculation_date": "2025-01-15",
                    "metadata": json.dumps({"calculation_method": "count_distinct"}),
                },
                {
                    "metric_name": "monthly_revenue",
                    "metric_value": 15000.0,
                    "calculation_date": "2025-01-15",
                    "metadata": json.dumps({"period": "January 2025"}),
                },
            ]

            storage_workflow.add_node(
                "TenantAnalyticsBulkCreateNode",
                "store_metrics",
                {"tenant_id": "saas_tenant_1", "data": metrics_data},
            )

            storage_results, _ = runtime.execute(storage_workflow.build())

            assert len(storage_results["store_metrics"]["records"]) == 2

        # Phase 4: Cross-tenant analytics isolation
        with TenantContext.set_current("saas_tenant_2", "analytics_user"):
            # Tenant 2 should not see tenant 1's analytics
            isolation_workflow = WorkflowBuilder()

            isolation_workflow.add_node(
                "TenantAnalyticsListNode",
                "isolated_metrics",
                {
                    "tenant_id": "saas_tenant_2",
                    "filter": {},  # All metrics for this tenant
                },
            )

            isolation_results, _ = runtime.execute(isolation_workflow.build())

            # Should be empty or only contain tenant 2's metrics
            tenant2_metrics = isolation_results["isolated_metrics"]["records"]
            assert len(tenant2_metrics) == 0  # No metrics for tenant 2 yet

        # Phase 5: Historical analytics reporting
        with TenantContext.set_current("saas_tenant_1", "report_user"):
            reporting_workflow = WorkflowBuilder()

            reporting_workflow.add_node(
                "AnalyticsReportNode",
                "monthly_report",
                {
                    "tenant_id": "saas_tenant_1",
                    "report_type": "monthly_summary",
                    "date_range": {"start": "2025-01-01", "end": "2025-01-31"},
                    "include_comparisons": True,
                    "format": "json",
                },
            )

            reporting_results, _ = runtime.execute(reporting_workflow.build())

            monthly_report = reporting_results["monthly_report"]["report"]
            assert "customer_metrics" in monthly_report
            assert "order_metrics" in monthly_report
            assert "growth_metrics" in monthly_report

    def test_tenant_data_migration_and_backup(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Tenant data migration and backup scenarios."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Order = test_tenant_models["Order"]

        # Phase 1: Create initial data
        with TenantContext.set_current("saas_tenant_1", "admin_user"):
            initial_workflow = WorkflowBuilder()

            initial_workflow.add_node(
                "CustomerBulkCreateNode",
                "initial_data",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "name": "Migration Customer 1",
                            "email": "migrate1@example.com",
                            "phone": "+1-555-0001",
                        },
                        {
                            "name": "Migration Customer 2",
                            "email": "migrate2@example.com",
                            "phone": "+1-555-0002",
                        },
                        {
                            "name": "Migration Customer 3",
                            "email": "migrate3@example.com",
                            "phone": "+1-555-0003",
                        },
                    ],
                },
            )

            initial_workflow.add_node(
                "OrderBulkCreateNode",
                "initial_orders",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "customer_id": 1,
                            "total": 1000.0,
                            "status": "completed",
                            "order_date": "2025-01-10",
                        },
                        {
                            "customer_id": 2,
                            "total": 2000.0,
                            "status": "pending",
                            "order_date": "2025-01-12",
                        },
                        {
                            "customer_id": 3,
                            "total": 1500.0,
                            "status": "completed",
                            "order_date": "2025-01-14",
                        },
                    ],
                },
            )

            runtime = LocalRuntime()
            initial_results, _ = runtime.execute(initial_workflow.build())

            assert len(initial_results["initial_data"]["records"]) == 3
            assert len(initial_results["initial_orders"]["records"]) == 3

        # Phase 2: Create backup
        with TenantContext.set_current("saas_tenant_1", "backup_admin"):
            backup_workflow = WorkflowBuilder()

            backup_workflow.add_node(
                "TenantBackupNode",
                "create_backup",
                {
                    "tenant_id": "saas_tenant_1",
                    "backup_type": "full",
                    "include_audit_logs": True,
                    "compression": True,
                    "encryption": True,
                    "destination": "backup_storage",
                },
            )

            backup_results, _ = runtime.execute(backup_workflow.build())

            backup_info = backup_results["create_backup"]["backup_info"]
            assert backup_info["status"] == "completed"
            assert backup_info["records_backed_up"] >= 6  # 3 customers + 3 orders
            backup_id = backup_info["backup_id"]

        # Phase 3: Modify data (simulate changes)
        with TenantContext.set_current("saas_tenant_1", "data_user"):
            modify_workflow = WorkflowBuilder()

            # Update customer
            modify_workflow.add_node(
                "CustomerUpdateNode",
                "update_customer",
                {
                    "tenant_id": "saas_tenant_1",
                    "id": 1,
                    "name": "Updated Migration Customer 1",
                    "email": "updated1@example.com",
                },
            )

            # Delete a customer
            modify_workflow.add_node(
                "CustomerDeleteNode",
                "delete_customer",
                {"tenant_id": "saas_tenant_1", "id": 3, "soft_delete": True},
            )

            # Add new order
            modify_workflow.add_node(
                "OrderCreateNode",
                "new_order",
                {
                    "tenant_id": "saas_tenant_1",
                    "customer_id": 1,
                    "total": 3000.0,
                    "status": "pending",
                    "order_date": "2025-01-16",
                },
            )

            modify_results, _ = runtime.execute(modify_workflow.build())

            assert (
                modify_results["update_customer"]["record"]["name"]
                == "Updated Migration Customer 1"
            )
            assert modify_results["new_order"]["record"]["total"] == 3000.0

        # Phase 4: Verify changes
        with TenantContext.set_current("saas_tenant_1", "admin_user"):
            verify_workflow = WorkflowBuilder()

            verify_workflow.add_node(
                "CustomerListNode",
                "verify_customers",
                {
                    "tenant_id": "saas_tenant_1",
                    "filter": {"status": "active"},
                    "include_soft_deleted": False,
                },
            )

            verify_workflow.add_node(
                "OrderListNode",
                "verify_orders",
                {"tenant_id": "saas_tenant_1", "filter": {}},
            )

            verify_results, _ = runtime.execute(verify_workflow.build())

            # Should have 2 active customers (1 updated, 1 unchanged, 1 soft-deleted)
            active_customers = verify_results["verify_customers"]["records"]
            assert len(active_customers) == 2

            # Should have 4 orders (3 original + 1 new)
            all_orders = verify_results["verify_orders"]["records"]
            assert len(all_orders) == 4

        # Phase 5: Restore from backup
        with TenantContext.set_current("saas_tenant_1", "backup_admin"):
            restore_workflow = WorkflowBuilder()

            restore_workflow.add_node(
                "TenantRestoreNode",
                "restore_backup",
                {
                    "tenant_id": "saas_tenant_1",
                    "backup_id": backup_id,
                    "restore_type": "full",
                    "point_in_time": "backup_time",
                    "verify_integrity": True,
                },
            )

            restore_results, _ = runtime.execute(restore_workflow.build())

            restore_info = restore_results["restore_backup"]["restore_info"]
            assert restore_info["status"] == "completed"
            assert restore_info["records_restored"] >= 6

        # Phase 6: Verify restoration
        with TenantContext.set_current("saas_tenant_1", "admin_user"):
            final_verify_workflow = WorkflowBuilder()

            final_verify_workflow.add_node(
                "CustomerListNode",
                "final_customers",
                {"tenant_id": "saas_tenant_1", "filter": {}},
            )

            final_verify_workflow.add_node(
                "OrderListNode",
                "final_orders",
                {"tenant_id": "saas_tenant_1", "filter": {}},
            )

            final_results, _ = runtime.execute(final_verify_workflow.build())

            # Should be restored to original state
            restored_customers = final_results["final_customers"]["records"]
            restored_orders = final_results["final_orders"]["records"]

            assert len(restored_customers) == 3  # All original customers
            assert len(restored_orders) == 3  # Original orders only

            # Verify original data is restored
            customer_names = [c["name"] for c in restored_customers]
            assert (
                "Migration Customer 1" in customer_names
            )  # Should be original, not updated
            assert "Updated Migration Customer 1" not in customer_names

    def test_tenant_performance_and_scaling(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Test tenant performance and scaling scenarios."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Order = test_tenant_models["Order"]

        # Phase 1: Bulk data creation for performance testing
        with TenantContext.set_current("saas_tenant_1", "performance_user"):
            bulk_workflow = WorkflowBuilder()

            # Create large number of customers
            customer_data = [
                {
                    "name": f"Performance Customer {i}",
                    "email": f"perf{i}@example.com",
                    "phone": f"+1-555-{i:04d}",
                    "status": "active" if i % 10 != 0 else "trial",
                }
                for i in range(1, 1001)  # 1000 customers
            ]

            bulk_workflow.add_node(
                "CustomerBulkCreateNode",
                "bulk_customers",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": customer_data,
                    "batch_size": 100,  # Process in batches
                    "track_performance": True,
                },
            )

            runtime = LocalRuntime()
            start_time = time.time()
            bulk_results, _ = runtime.execute(bulk_workflow.build())
            creation_time = time.time() - start_time

            assert len(bulk_results["bulk_customers"]["records"]) == 1000
            assert creation_time < 30.0  # Should complete in under 30 seconds

        # Phase 2: Performance testing with large dataset
        with TenantContext.set_current("saas_tenant_1", "performance_user"):
            perf_workflow = WorkflowBuilder()

            # Test query performance
            perf_workflow.add_node(
                "CustomerListNode",
                "performance_query",
                {
                    "tenant_id": "saas_tenant_1",
                    "filter": {"status": "active"},
                    "sort": [{"name": 1}],
                    "limit": 100,
                    "track_performance": True,
                },
            )

            # Test aggregation performance
            perf_workflow.add_node(
                "CustomerAggregateNode",
                "performance_aggregate",
                {
                    "tenant_id": "saas_tenant_1",
                    "group_by": ["status"],
                    "aggregate": {"count": {"$count": "*"}, "total": {"$count": "*"}},
                    "track_performance": True,
                },
            )

            start_time = time.time()
            perf_results, _ = runtime.execute(perf_workflow.build())
            query_time = time.time() - start_time

            assert len(perf_results["performance_query"]["records"]) == 100
            assert query_time < 5.0  # Should complete in under 5 seconds

            # Verify aggregation results
            agg_results = perf_results["performance_aggregate"]["records"]
            assert len(agg_results) == 2  # active and trial statuses

        # Phase 3: Concurrent tenant operations
        import concurrent.futures
        import threading

        def tenant_operation(tenant_id, operation_id):
            """Perform operations for a specific tenant."""
            with TenantContext.set_current(tenant_id, f"user_{operation_id}"):
                workflow = WorkflowBuilder()

                # Create customers
                workflow.add_node(
                    "CustomerBulkCreateNode",
                    "concurrent_customers",
                    {
                        "tenant_id": tenant_id,
                        "data": [
                            {
                                "name": f"Concurrent Customer {operation_id}-{i}",
                                "email": f"concurrent{operation_id}_{i}@example.com",
                                "phone": f"+1-555-{operation_id}{i:02d}",
                            }
                            for i in range(1, 11)  # 10 customers per operation
                        ],
                    },
                )

                runtime = LocalRuntime()
                results, _ = runtime.execute(workflow.build())

                return len(results["concurrent_customers"]["records"])

        # Run concurrent operations for multiple tenants
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = []

            # 2 operations each for 3 tenants
            for tenant_id in ["saas_tenant_1", "saas_tenant_2", "enterprise_tenant"]:
                for op_id in range(1, 3):
                    future = executor.submit(tenant_operation, tenant_id, op_id)
                    futures.append(future)

            # Wait for all operations to complete
            results = []
            for future in concurrent.futures.as_completed(futures, timeout=60):
                result = future.result()
                results.append(result)

        # Verify all operations completed successfully
        assert len(results) == 6  # 2 operations × 3 tenants
        assert all(r == 10 for r in results)  # Each operation created 10 customers

        # Phase 4: Verify tenant isolation after concurrent operations
        with TenantContext.set_current("saas_tenant_1", "admin_user"):
            isolation_workflow = WorkflowBuilder()

            isolation_workflow.add_node(
                "CustomerListNode",
                "check_isolation",
                {
                    "tenant_id": "saas_tenant_1",
                    "filter": {"name": {"$regex": "Concurrent"}},
                    "count_only": True,
                },
            )

            isolation_results, _ = runtime.execute(isolation_workflow.build())

            # Should only see concurrent customers for this tenant
            concurrent_count = isolation_results["check_isolation"]["count"]
            assert concurrent_count == 20  # 2 operations × 10 customers each

    def test_tenant_gdpr_compliance_workflow(
        self, multi_tenant_dataflow, test_tenant_models
    ):
        """Complete GDPR compliance workflow for tenants."""
        db = multi_tenant_dataflow
        Customer = test_tenant_models["Customer"]
        Order = test_tenant_models["Order"]

        # Phase 1: Create customer data
        with TenantContext.set_current("saas_tenant_1", "gdpr_admin"):
            setup_workflow = WorkflowBuilder()

            setup_workflow.add_node(
                "CustomerBulkCreateNode",
                "gdpr_customers",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "name": "GDPR Customer 1",
                            "email": "gdpr1@example.com",
                            "phone": "+1-555-GDPR1",
                            "status": "active",
                        },
                        {
                            "name": "GDPR Customer 2",
                            "email": "gdpr2@example.com",
                            "phone": "+1-555-GDPR2",
                            "status": "active",
                        },
                    ],
                },
            )

            setup_workflow.add_node(
                "OrderBulkCreateNode",
                "gdpr_orders",
                {
                    "tenant_id": "saas_tenant_1",
                    "data": [
                        {
                            "customer_id": 1,
                            "total": 100.0,
                            "status": "completed",
                            "order_date": "2025-01-10",
                        },
                        {
                            "customer_id": 1,
                            "total": 200.0,
                            "status": "pending",
                            "order_date": "2025-01-12",
                        },
                        {
                            "customer_id": 2,
                            "total": 150.0,
                            "status": "completed",
                            "order_date": "2025-01-11",
                        },
                    ],
                },
            )

            runtime = LocalRuntime()
            setup_results, _ = runtime.execute(setup_workflow.build())

            assert len(setup_results["gdpr_customers"]["records"]) == 2
            assert len(setup_results["gdpr_orders"]["records"]) == 3

        # Phase 2: Data subject access request (right to access)
        with TenantContext.set_current("saas_tenant_1", "gdpr_officer"):
            access_workflow = WorkflowBuilder()

            access_workflow.add_node(
                "GDPRDataExportNode",
                "data_access_request",
                {
                    "tenant_id": "saas_tenant_1",
                    "subject_identifier": "gdpr1@example.com",
                    "identifier_type": "email",
                    "export_format": "json",
                    "include_relationships": True,
                    "include_audit_logs": True,
                },
            )

            access_results, _ = runtime.execute(access_workflow.build())

            export_data = access_results["data_access_request"]["export_data"]
            assert "personal_data" in export_data
            assert "order_history" in export_data
            assert "audit_trail" in export_data

            # Verify customer data is included
            personal_data = export_data["personal_data"]
            assert personal_data["email"] == "gdpr1@example.com"
            assert personal_data["name"] == "GDPR Customer 1"

            # Verify order history is included
            order_history = export_data["order_history"]
            assert len(order_history) == 2  # 2 orders for this customer

        # Phase 3: Data rectification (right to rectification)
        with TenantContext.set_current("saas_tenant_1", "gdpr_officer"):
            rectification_workflow = WorkflowBuilder()

            rectification_workflow.add_node(
                "GDPRDataRectificationNode",
                "rectify_data",
                {
                    "tenant_id": "saas_tenant_1",
                    "subject_identifier": "gdpr1@example.com",
                    "identifier_type": "email",
                    "corrections": {
                        "name": "GDPR Customer 1 - Corrected",
                        "phone": "+1-555-CORRECTED",
                    },
                    "audit_reason": "Customer requested correction",
                },
            )

            rectification_results, _ = runtime.execute(rectification_workflow.build())

            updated_data = rectification_results["rectify_data"]["updated_record"]
            assert updated_data["name"] == "GDPR Customer 1 - Corrected"
            assert updated_data["phone"] == "+1-555-CORRECTED"

        # Phase 4: Data portability (right to data portability)
        with TenantContext.set_current("saas_tenant_1", "gdpr_officer"):
            portability_workflow = WorkflowBuilder()

            portability_workflow.add_node(
                "GDPRDataPortabilityNode",
                "data_portability",
                {
                    "tenant_id": "saas_tenant_1",
                    "subject_identifier": "gdpr2@example.com",
                    "identifier_type": "email",
                    "export_format": "structured_json",
                    "include_metadata": True,
                    "portable_format": True,
                },
            )

            portability_results, _ = runtime.execute(portability_workflow.build())

            portable_data = portability_results["data_portability"]["portable_data"]
            assert "schema_version" in portable_data
            assert "export_timestamp" in portable_data
            assert "data_subject" in portable_data

            # Verify data is in portable format
            data_subject = portable_data["data_subject"]
            assert data_subject["email"] == "gdpr2@example.com"

        # Phase 5: Right to be forgotten (erasure)
        with TenantContext.set_current("saas_tenant_1", "gdpr_officer"):
            erasure_workflow = WorkflowBuilder()

            erasure_workflow.add_node(
                "GDPRDataErasureNode",
                "right_to_be_forgotten",
                {
                    "tenant_id": "saas_tenant_1",
                    "subject_identifier": "gdpr2@example.com",
                    "identifier_type": "email",
                    "erasure_type": "full",
                    "preserve_anonymous_data": True,
                    "audit_reason": "Customer requested deletion",
                },
            )

            erasure_results, _ = runtime.execute(erasure_workflow.build())

            erasure_report = erasure_results["right_to_be_forgotten"]["erasure_report"]
            assert erasure_report["status"] == "completed"
            assert erasure_report["records_erased"] > 0
            assert erasure_report["records_anonymized"] > 0

        # Phase 6: Verify erasure
        with TenantContext.set_current("saas_tenant_1", "gdpr_officer"):
            verify_workflow = WorkflowBuilder()

            verify_workflow.add_node(
                "CustomerListNode",
                "verify_erasure",
                {
                    "tenant_id": "saas_tenant_1",
                    "filter": {"email": "gdpr2@example.com"},
                },
            )

            verify_results, _ = runtime.execute(verify_workflow.build())

            # Should not find the erased customer
            found_customers = verify_results["verify_erasure"]["records"]
            assert len(found_customers) == 0

        # Phase 7: GDPR compliance report
        with TenantContext.set_current("saas_tenant_1", "gdpr_admin"):
            compliance_workflow = WorkflowBuilder()

            compliance_workflow.add_node(
                "GDPRComplianceReportNode",
                "compliance_report",
                {
                    "tenant_id": "saas_tenant_1",
                    "report_period": {"start": "2025-01-01", "end": "2025-01-31"},
                    "include_request_metrics": True,
                    "include_audit_summary": True,
                    "include_breach_reports": True,
                },
            )

            compliance_results, _ = runtime.execute(compliance_workflow.build())

            compliance_report = compliance_results["compliance_report"]["report"]
            assert "request_summary" in compliance_report
            assert "audit_summary" in compliance_report
            assert "compliance_status" in compliance_report

            # Verify compliance metrics
            request_summary = compliance_report["request_summary"]
            assert request_summary["access_requests"] >= 1
            assert request_summary["rectification_requests"] >= 1
            assert request_summary["erasure_requests"] >= 1
            assert request_summary["portability_requests"] >= 1

            # Verify overall compliance
            assert compliance_report["compliance_status"] == "compliant"
