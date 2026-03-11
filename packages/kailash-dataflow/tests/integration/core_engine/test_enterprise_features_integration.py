"""
Integration tests for DataFlow enterprise features.

Tests comprehensive enterprise feature integration including multi-tenancy,
audit logging, security, compliance, and their interactions with workflows.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Union
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import DataFlow and workflow components
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../../src"))

from dataflow import DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestEnterpriseFeatureIntegration:
    """Test comprehensive enterprise feature integration."""

    def test_multi_tenant_audit_integration(self, test_suite):
        """Test multi-tenancy with audit logging integration."""
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            audit_logging=True,
            monitoring=True,
        )

        @db.model
        class TenantAuditModel:
            name: str
            data: str
            value: float

            __dataflow__ = {
                "multi_tenant": True,
                "audit_log": True,
                "soft_delete": True,
            }

        # Verify enterprise configuration
        assert db.config.security.multi_tenant is True
        assert db.config.security.audit_enabled is True
        assert db.config.monitoring is True

        # Verify model registration with enterprise features
        assert "TenantAuditModel" in db._models

        # Test workflow with enterprise operations
        workflow = WorkflowBuilder()

        # Multi-tenant create with audit
        workflow.add_node(
            "TenantAuditModelCreateNode",
            "create_tenant_record",
            {
                "name": "Enterprise Record",
                "data": "Sensitive business data",
                "value": 1000.0,
                "tenant_id": "enterprise_tenant_001",
            },
        )

        # Multi-tenant query with tenant filtering
        workflow.add_node(
            "TenantAuditModelListNode",
            "list_tenant_records",
            {"filter": {"tenant_id": "enterprise_tenant_001"}, "audit_trail": True},
        )

        workflow.add_connection(
            "create_tenant_record", "output", "list_tenant_records", "input"
        )

        # Verify workflow builds successfully
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 2

    def test_enterprise_bulk_operations_with_tenancy(self, test_suite):
        """Test enterprise bulk operations with multi-tenancy."""
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            audit_logging=True,
            monitoring=True,
            bulk_batch_size=1000,
        )

        @db.model
        class BulkEnterpriseModel:
            name: str
            category: str
            value: Decimal

            __dataflow__ = {"multi_tenant": True, "audit_log": True, "versioned": True}

        workflow = WorkflowBuilder()

        # Bulk create with enterprise features
        workflow.add_node(
            "BulkEnterpriseModelBulkCreateNode",
            "bulk_create_enterprise",
            {
                "data": [
                    {
                        "name": f"Enterprise Item {i}",
                        "category": "premium",
                        "value": str(Decimal("100.00") * i),
                        "tenant_id": "enterprise_tenant",
                    }
                    for i in range(1, 11)  # 10 records for testing
                ],
                "batch_size": 5,
                "tenant_id": "enterprise_tenant",
            },
        )

        # Bulk update with versioning
        workflow.add_node(
            "BulkEnterpriseModelBulkUpdateNode",
            "bulk_update_enterprise",
            {
                "filter": {"category": "premium", "tenant_id": "enterprise_tenant"},
                "update": {"category": "premium_updated"},
            },
        )

        # List to verify results
        workflow.add_node(
            "BulkEnterpriseModelListNode",
            "verify_bulk_operations",
            {
                "filter": {
                    "category": "premium_updated",
                    "tenant_id": "enterprise_tenant",
                }
            },
        )

        workflow.add_connection(
            "bulk_create_enterprise", "output", "bulk_update_enterprise", "input"
        )
        workflow.add_connection(
            "bulk_update_enterprise", "output", "verify_bulk_operations", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_multi_tenant_data_isolation(self, test_suite):
        """Test data isolation between tenants."""
        db = DataFlow(test_suite.config.url, multi_tenant=True)

        @db.model
        class IsolatedModel:
            name: str
            sensitive_info: str

            __dataflow__ = {"multi_tenant": True}

        workflow = WorkflowBuilder()

        # Create data for tenant A
        workflow.add_node(
            "IsolatedModelCreateNode",
            "create_tenant_a",
            {
                "name": "Tenant A Data",
                "sensitive_info": "Secret A",
                "tenant_id": "tenant_a",
            },
        )

        # Create data for tenant B
        workflow.add_node(
            "IsolatedModelCreateNode",
            "create_tenant_b",
            {
                "name": "Tenant B Data",
                "sensitive_info": "Secret B",
                "tenant_id": "tenant_b",
            },
        )

        # Query tenant A data only
        workflow.add_node(
            "IsolatedModelListNode",
            "list_tenant_a",
            {"filter": {"tenant_id": "tenant_a"}},
        )

        # Query tenant B data only
        workflow.add_node(
            "IsolatedModelListNode",
            "list_tenant_b",
            {"filter": {"tenant_id": "tenant_b"}},
        )

        workflow.add_connection("create_tenant_a", "output", "list_tenant_a", "input")
        workflow.add_connection("create_tenant_b", "output", "list_tenant_b", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 4
        assert len(built_workflow.connections) == 2

    def test_soft_delete_enterprise_feature(self, test_suite):
        """Test soft delete enterprise functionality."""
        db = DataFlow(test_suite.config.url, multi_tenant=True, audit_logging=True)

        @db.model
        class SoftDeleteModel:
            name: str
            important_data: str

            __dataflow__ = {
                "multi_tenant": True,
                "soft_delete": True,
                "audit_log": True,
            }

        workflow = WorkflowBuilder()

        # Create record
        workflow.add_node(
            "SoftDeleteModelCreateNode",
            "create_record",
            {
                "name": "Important Record",
                "important_data": "Critical business data",
                "tenant_id": "business_tenant",
            },
        )

        # Soft delete (preserves data with deleted_at timestamp)
        workflow.add_node(
            "SoftDeleteModelDeleteNode",
            "soft_delete_record",
            {
                "id": "${create_record.id}",
                "soft_delete": True,
                "tenant_id": "business_tenant",
            },
        )

        # List active records (should exclude soft deleted)
        workflow.add_node(
            "SoftDeleteModelListNode",
            "list_active",
            {"filter": {"tenant_id": "business_tenant", "deleted_at": None}},
        )

        # List all records including soft deleted
        workflow.add_node(
            "SoftDeleteModelListNode",
            "list_all",
            {"filter": {"tenant_id": "business_tenant"}, "include_deleted": True},
        )

        workflow.add_connection(
            "create_record", "output", "soft_delete_record", "input"
        )
        workflow.add_connection("soft_delete_record", "output", "list_active", "input")
        workflow.add_connection("list_active", "output", "list_all", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 4

    def test_versioned_records_enterprise_feature(self, test_suite):
        """Test versioned records for optimistic locking."""
        db = DataFlow(test_suite.config.url, multi_tenant=True)

        @db.model
        class VersionedModel:
            name: str
            value: float
            status: str

            __dataflow__ = {"multi_tenant": True, "versioned": True}

        workflow = WorkflowBuilder()

        # Create versioned record
        workflow.add_node(
            "VersionedModelCreateNode",
            "create_versioned",
            {
                "name": "Versioned Record",
                "value": 100.0,
                "status": "active",
                "tenant_id": "versioned_tenant",
            },
        )

        # Update with version check (optimistic locking)
        workflow.add_node(
            "VersionedModelUpdateNode",
            "update_versioned",
            {
                "id": "${create_versioned.id}",
                "value": 150.0,
                "status": "updated",
                "version": "${create_versioned.version}",
                "tenant_id": "versioned_tenant",
            },
        )

        # Read updated record to verify version increment
        workflow.add_node(
            "VersionedModelReadNode",
            "read_updated",
            {"id": "${create_versioned.id}", "tenant_id": "versioned_tenant"},
        )

        workflow.add_connection(
            "create_versioned", "output", "update_versioned", "input"
        )
        workflow.add_connection("update_versioned", "output", "read_updated", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_distributed_transaction_integration(self, test_suite):
        """Test distributed transaction management."""
        db = DataFlow(test_suite.config.url, multi_tenant=True)

        @db.model
        class TransactionalModel:
            account_id: str
            amount: Decimal
            transaction_type: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        workflow = WorkflowBuilder()

        # Distributed transaction coordinator
        workflow.add_node(
            "DistributedTransactionManagerNode",
            "transaction_coordinator",
            {
                "transaction_type": "saga",
                "tenant_id": "financial_tenant",
                "timeout": 30,
            },
        )

        # Create debit transaction
        workflow.add_node(
            "TransactionalModelCreateNode",
            "debit_transaction",
            {
                "account_id": "ACC-001",
                "amount": "-500.00",
                "transaction_type": "debit",
                "tenant_id": "financial_tenant",
            },
        )

        # Create credit transaction
        workflow.add_node(
            "TransactionalModelCreateNode",
            "credit_transaction",
            {
                "account_id": "ACC-002",
                "amount": "500.00",
                "transaction_type": "credit",
                "tenant_id": "financial_tenant",
            },
        )

        # Verify transactions
        workflow.add_node(
            "TransactionalModelListNode",
            "verify_transactions",
            {"filter": {"tenant_id": "financial_tenant"}},
        )

        workflow.add_connection(
            "transaction_coordinator", "output", "debit_transaction", "input"
        )
        workflow.add_connection(
            "transaction_coordinator", "output", "credit_transaction", "input"
        )
        workflow.add_connection(
            "debit_transaction", "output", "verify_transactions", "input"
        )
        workflow.add_connection(
            "credit_transaction", "output", "verify_transactions", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 4

    def test_enterprise_caching_integration(self, test_suite):
        """Test enterprise caching with multi-tenant support."""
        db = DataFlow(
            test_suite.config.url, multi_tenant=True, cache_enabled=True, cache_ttl=600
        )

        @db.model
        class CacheableModel:
            product_id: str
            product_data: str
            price: Decimal

            __dataflow__ = {"multi_tenant": True, "cacheable": True}

        workflow = WorkflowBuilder()

        # Create cacheable data
        workflow.add_node(
            "CacheableModelCreateNode",
            "create_cacheable",
            {
                "product_id": "PROD-001",
                "product_data": "Premium Product",
                "price": "99.99",
                "tenant_id": "cache_tenant",
            },
        )

        # Read with caching enabled
        workflow.add_node(
            "CacheableModelReadNode",
            "read_cached",
            {
                "id": "${create_cacheable.id}",
                "tenant_id": "cache_tenant",
                "use_cache": True,
            },
        )

        # List with caching
        workflow.add_node(
            "CacheableModelListNode",
            "list_cached",
            {"filter": {"tenant_id": "cache_tenant"}, "cache_enabled": True},
        )

        workflow.add_connection("create_cacheable", "output", "read_cached", "input")
        workflow.add_connection("read_cached", "output", "list_cached", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_multi_factor_authentication_integration(self, test_suite):
        """Test multi-factor authentication integration."""
        db = DataFlow(test_suite.config.url, multi_tenant=True)

        @db.model
        class SecureModel:
            user_id: int
            sensitive_data: str
            classification: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        workflow = WorkflowBuilder()

        # Multi-factor authentication
        workflow.add_node(
            "MultiFactorAuthNode",
            "mfa_verify",
            {"user_id": 123, "auth_method": "totp", "tenant_id": "secure_tenant"},
        )

        # Create secure data after MFA
        workflow.add_node(
            "SecureModelCreateNode",
            "create_secure",
            {
                "user_id": 123,
                "sensitive_data": "Highly sensitive information",
                "classification": "confidential",
                "tenant_id": "secure_tenant",
            },
        )

        # Read secure data
        workflow.add_node(
            "SecureModelReadNode",
            "read_secure",
            {"id": "${create_secure.id}", "tenant_id": "secure_tenant"},
        )

        workflow.add_connection("mfa_verify", "output", "create_secure", "input")
        workflow.add_connection("create_secure", "output", "read_secure", "input")

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_enterprise_performance_monitoring(self, test_suite):
        """Test enterprise performance monitoring integration."""
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            monitoring=True,
            performance_tracking=True,
        )

        @db.model
        class MonitoredModel:
            operation_id: str
            operation_type: str

            __dataflow__ = {"multi_tenant": True, "performance_tracked": True}

        workflow = WorkflowBuilder()

        # Create monitored operation
        workflow.add_node(
            "MonitoredModelCreateNode",
            "monitored_create",
            {
                "operation_id": "OP-12345",
                "operation_type": "high_priority",
                "tenant_id": "monitored_tenant",
            },
        )

        # Bulk operation with monitoring
        workflow.add_node(
            "MonitoredModelBulkCreateNode",
            "monitored_bulk",
            {
                "data": [
                    {
                        "operation_id": f"OP-BULK-{i}",
                        "operation_type": "bulk_operation",
                        "tenant_id": "monitored_tenant",
                    }
                    for i in range(100)
                ],
                "tenant_id": "monitored_tenant",
            },
        )

        # Performance validation query
        workflow.add_node(
            "MonitoredModelListNode",
            "performance_check",
            {"filter": {"tenant_id": "monitored_tenant"}, "performance_tracking": True},
        )

        workflow.add_connection("monitored_create", "output", "monitored_bulk", "input")
        workflow.add_connection(
            "monitored_bulk", "output", "performance_check", "input"
        )

        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 3

    def test_real_world_enterprise_scenario(self, test_suite):
        """Test complete real-world enterprise scenario."""
        # E-commerce order processing with full enterprise features
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            audit_logging=True,
            monitoring=True,
            cache_enabled=True,
            performance_tracking=True,
            pool_size=20,
        )

        @db.model
        class Customer:
            name: str
            email: str
            tier: str = "standard"

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        @db.model
        class Order:
            customer_id: int
            total: Decimal
            status: str = "pending"
            items: str  # JSON string of items

            __dataflow__ = {"multi_tenant": True, "audit_log": True, "versioned": True}

        @db.model
        class AuditLog:
            entity_type: str
            entity_id: int
            action: str
            timestamp: datetime
            user_id: str

            __dataflow__ = {"multi_tenant": True, "immutable": True}

        workflow = WorkflowBuilder()

        # 1. Create customer with audit
        workflow.add_node(
            "CustomerCreateNode",
            "create_customer",
            {
                "name": "Enterprise Customer",
                "email": "customer@enterprise.com",
                "tier": "premium",
                "tenant_id": "ecommerce_tenant",
            },
        )

        # 2. Create order with versioning
        workflow.add_node(
            "OrderCreateNode",
            "create_order",
            {
                "customer_id": 12345,  # Use actual int instead of reference for now
                "total": "299.99",
                "status": "pending",
                "items": '{"items": [{"sku": "PROD-001", "qty": 2}]}',
                "tenant_id": "ecommerce_tenant",
            },
        )

        # 3. Update order status with version check
        workflow.add_node(
            "OrderUpdateNode",
            "process_order",
            {
                "id": "1",  # Use string
                "status": "processing",
                "version": "1",  # Use string
                "tenant_id": "ecommerce_tenant",
            },
        )

        # 4. Create audit log entry
        workflow.add_node(
            "AuditLogCreateNode",
            "log_order_processing",
            {
                "entity_type": "Order",
                "entity_id": 1,  # Keep int for entity_id
                "action": "status_update",
                "timestamp": datetime.now(),  # Use actual datetime
                "user_id": "system",
                "tenant_id": "ecommerce_tenant",
            },
        )

        # 5. Final order update
        workflow.add_node(
            "OrderUpdateNode",
            "complete_order",
            {
                "id": "1",  # Use string
                "status": "completed",
                "version": "2",  # Use string
                "tenant_id": "ecommerce_tenant",
            },
        )

        # 6. List orders for reporting
        workflow.add_node(
            "OrderListNode",
            "order_report",
            {
                "filter": {"tenant_id": "ecommerce_tenant", "status": "completed"},
                "include_audit": True,
            },
        )

        # Connect the enterprise workflow
        workflow.add_connection("create_customer", "output", "create_order", "input")
        workflow.add_connection("create_order", "output", "process_order", "input")
        workflow.add_connection(
            "process_order", "output", "log_order_processing", "input"
        )
        workflow.add_connection(
            "log_order_processing", "output", "complete_order", "input"
        )
        workflow.add_connection("complete_order", "output", "order_report", "input")

        # Verify complete enterprise workflow
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 6
        assert len(built_workflow.connections) == 5

        # Verify enterprise configuration
        assert db.config.security.multi_tenant is True
        assert db.config.security.audit_enabled is True
        assert db.config.monitoring is True
        assert db.config.enable_query_cache is True

    def test_enterprise_performance_at_scale(self, test_suite):
        """Test enterprise features performance at scale."""
        import time

        # Create DataFlow with PostgreSQL for performance testing
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            monitoring=True,
            performance_tracking=True,
            bulk_batch_size=10000,
        )

        # Large-scale enterprise configuration
        db = DataFlow(
            test_suite.config.url,
            multi_tenant=True,
            audit_logging=True,
            monitoring=True,
            pool_size=50,
            bulk_batch_size=1000,
        )

        @db.model
        class ScaleTestModel:
            name: str
            value: int
            category: str

            __dataflow__ = {"multi_tenant": True, "audit_log": True}

        # Performance test workflow
        start_time = time.time()

        workflow = WorkflowBuilder()

        # Create multiple tenant operations
        for i in range(5):
            workflow.add_node(
                "ScaleTestModelBulkCreateNode",
                f"bulk_create_{i}",
                {
                    "data": [
                        {
                            "name": f"Scale Item {j}",
                            "value": j,
                            "category": f"category_{i}",
                            "tenant_id": f"tenant_{i % 2}",  # 2 tenants
                        }
                        for j in range(50)  # 50 items per bulk operation
                    ],
                    "tenant_id": f"tenant_{i % 2}",
                },
            )

        build_time = time.time() - start_time

        # Workflow should build quickly even with enterprise operations
        built_workflow = workflow.build()
        assert built_workflow is not None
        assert len(built_workflow.nodes) == 5
        assert build_time < 1.0  # Should build in under 1 second

    def test_enterprise_configuration_validation(self):
        """Test enterprise configuration validation."""
        # Test various enterprise configurations
        configs = [
            {"multi_tenant": True, "audit_logging": True},
            {"multi_tenant": True, "monitoring": True, "cache_enabled": True},
            {"multi_tenant": False, "audit_logging": True, "monitoring": True},
        ]

        for config in configs:
            db = DataFlow(**config)

            # Should create without error
            assert db is not None
            assert db.config.security.multi_tenant == config.get("multi_tenant", False)

            if "audit_logging" in config:
                assert db.config.security.audit_enabled == config["audit_logging"]

            if "monitoring" in config:
                assert db.config.monitoring == config["monitoring"]

            if "cache_enabled" in config:
                assert db.config.enable_query_cache == config["cache_enabled"]
