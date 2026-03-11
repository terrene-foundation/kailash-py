"""
Comprehensive integration tests for production DataFlow with real databases.

This test suite verifies that the production DataFlow implementation actually
works with real databases, replacing the broken mock-based tests.
"""

import asyncio
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict

import pytest
from dataflow.core.config import DatabaseConfig, DataFlowConfig, Environment

# Import production implementation
from dataflow.core.engine_production import DataFlowProductionEngine as DataFlow

from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError
from kailash.workflow.builder import WorkflowBuilder
from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete integration test suite with infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


class TestProductionDataFlowRealDatabase:
    """Test DataFlow with real database operations - no mocks allowed."""

    @pytest.fixture
    def postgres_config(self, test_suite):
        """PostgreSQL test configuration."""
        return {
            "database_url": test_suite.config.url,
            "pool_size": 10,
            "monitoring": True,
            "cache_enabled": False,  # Disable cache for cleaner tests
        }

    @pytest.fixture
    def mysql_config(self, test_suite):
        """MySQL test configuration (fallback for MySQL-specific tests)."""
        return {
            "database_url": os.getenv(
                "TEST_MYSQL_URL",
                "mysql+pymysql://root:password@localhost:3306/dataflow_test",
            ),
            "pool_size": 10,
            "monitoring": True,
            "cache_enabled": False,
        }

    @pytest.fixture
    def sqlite_config(self):
        """SQLite test configuration."""
        return {
            "database_url": "sqlite:///test_dataflow.db",
            "pool_size": 5,
            "monitoring": False,
            "cache_enabled": False,
        }

    @pytest.mark.requires_postgres
    def test_postgresql_crud_operations(self, test_suite, postgres_config):
        """Test complete CRUD cycle with PostgreSQL."""
        self._test_database_crud_operations(postgres_config, "PostgreSQL")

    @pytest.mark.requires_mysql
    def test_mysql_crud_operations(self, test_suite, mysql_config):
        """Test complete CRUD cycle with MySQL."""
        self._test_database_crud_operations(mysql_config, "MySQL")

    def test_sqlite_crud_operations(self, test_suite, sqlite_config):
        """Test complete CRUD cycle with SQLite."""
        self._test_database_crud_operations(sqlite_config, "SQLite")

    def _test_database_crud_operations(self, db_config: Dict[str, Any], db_type: str):
        """Test CRUD operations with real database persistence."""

        # Initialize DataFlow with real database
        db = DataFlow(**db_config)

        try:
            # Define test model
            @db.model
            class TestProduct:
                name: str
                price: float
                category: str = "general"
                active: bool = True

            # Verify table was created
            assert db._table_exists("testproduct"), f"Table not created in {db_type}"

            runtime = LocalRuntime()

            # TEST CREATE - Real database insert
            print(f"\n=== Testing CREATE with {db_type} ===")
            create_workflow = WorkflowBuilder()
            create_workflow.add_node(
                "TestProductCreateNode",
                "create_product",
                {"name": "Test Laptop", "price": 999.99, "category": "electronics"},
            )

            create_results, _ = runtime.execute(create_workflow.build())

            # Verify creation result
            assert create_results["create_product"]["success"] is True
            assert create_results["create_product"]["data"]["name"] == "Test Laptop"
            assert create_results["create_product"]["data"]["price"] == 999.99

            product_id = create_results["create_product"]["data"]["id"]
            assert product_id is not None
            print(f"✅ Created product with ID: {product_id}")

            # Verify data actually exists in database
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute(
                    (
                        "SELECT name, price, category FROM testproduct WHERE id = %s"
                        if db_type != "SQLite"
                        else "SELECT name, price, category FROM testproduct WHERE id = ?"
                    ),
                    (product_id,),
                )
                row = cursor.fetchone()
                assert row is not None, f"Product not found in {db_type} database"
                assert row[0] == "Test Laptop"
                assert abs(row[1] - 999.99) < 0.01  # Float comparison
                assert row[2] == "electronics"

            print(f"✅ Data verified in {db_type} database")

            # TEST READ - Real database select
            print(f"\n=== Testing READ with {db_type} ===")
            read_workflow = WorkflowBuilder()
            read_workflow.add_node(
                "TestProductReadNode", "read_product", {"id": product_id}
            )

            read_results, _ = runtime.execute(read_workflow.build())

            assert read_results["read_product"]["success"] is True
            assert read_results["read_product"]["data"]["id"] == product_id
            assert read_results["read_product"]["data"]["name"] == "Test Laptop"
            print(f"✅ Read product: {read_results['read_product']['data']['name']}")

            # TEST UPDATE - Real database update
            print(f"\n=== Testing UPDATE with {db_type} ===")
            update_workflow = WorkflowBuilder()
            update_workflow.add_node(
                "TestProductUpdateNode",
                "update_product",
                {"id": product_id, "price": 899.99, "active": False},
            )

            update_results, _ = runtime.execute(update_workflow.build())

            assert update_results["update_product"]["success"] is True
            assert update_results["update_product"]["data"]["price"] == 899.99
            assert update_results["update_product"]["data"]["active"] is False
            print(
                f"✅ Updated product price to: {update_results['update_product']['data']['price']}"
            )

            # Verify update in database
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute(
                    (
                        "SELECT price, active FROM testproduct WHERE id = %s"
                        if db_type != "SQLite"
                        else "SELECT price, active FROM testproduct WHERE id = ?"
                    ),
                    (product_id,),
                )
                row = cursor.fetchone()
                assert row is not None
                assert abs(row[0] - 899.99) < 0.01
                assert (
                    row[1] is False or row[1] == 0
                )  # Different boolean representations

            # TEST LIST - Real database query
            print(f"\n=== Testing LIST with {db_type} ===")
            list_workflow = WorkflowBuilder()
            list_workflow.add_node(
                "TestProductListNode",
                "list_products",
                {"filter": {"category": "electronics"}, "limit": 10},
            )

            list_results, _ = runtime.execute(list_workflow.build())

            assert list_results["list_products"]["success"] is True
            products = list_results["list_products"]["data"]
            assert len(products) >= 1
            assert any(p["id"] == product_id for p in products)
            print(f"✅ Listed {len(products)} products")

            # TEST DELETE - Real database delete
            print(f"\n=== Testing DELETE with {db_type} ===")
            delete_workflow = WorkflowBuilder()
            delete_workflow.add_node(
                "TestProductDeleteNode", "delete_product", {"id": product_id}
            )

            delete_results, _ = runtime.execute(delete_workflow.build())

            assert delete_results["delete_product"]["success"] is True
            print(f"✅ Deleted product with ID: {product_id}")

            # Verify deletion in database
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute(
                    (
                        "SELECT id FROM testproduct WHERE id = %s"
                        if db_type != "SQLite"
                        else "SELECT id FROM testproduct WHERE id = ?"
                    ),
                    (product_id,),
                )
                row = cursor.fetchone()
                assert (
                    row is None
                ), f"Product still exists in {db_type} database after deletion"

            print(f"✅ All CRUD operations successful with {db_type}")

        finally:
            # Clean up
            db.close_sync()

    @pytest.mark.requires_postgres
    def test_bulk_operations_real_database(self, test_suite, postgres_config):
        """Test bulk operations with real database."""

        db = DataFlow(**postgres_config)

        try:

            @db.model
            class BulkTestModel:
                name: str
                value: int
                category: str = "test"

            runtime = LocalRuntime()

            # Test bulk create with large dataset
            print("\n=== Testing BULK CREATE ===")
            bulk_data = [
                {"name": f"Item_{i}", "value": i, "category": f"cat_{i % 5}"}
                for i in range(1000)  # Test with 1000 records
            ]

            bulk_workflow = WorkflowBuilder()
            bulk_workflow.add_node(
                "BulkTestModelBulkCreateNode",
                "bulk_create",
                {"data": bulk_data, "batch_size": 100},
            )

            start_time = time.time()
            bulk_results, _ = runtime.execute(bulk_workflow.build())
            elapsed_time = time.time() - start_time

            assert bulk_results["bulk_create"]["success"] is True
            assert bulk_results["bulk_create"]["records_processed"] == 1000

            # Calculate throughput
            throughput = 1000 / elapsed_time
            print(
                f"✅ Bulk created 1000 records in {elapsed_time:.2f}s ({throughput:.0f} records/sec)"
            )

            # Verify data in database
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM bulktestmodel")
                count = cursor.fetchone()[0]
                assert count == 1000, f"Expected 1000 records, found {count}"

            # Test bulk update
            print("\n=== Testing BULK UPDATE ===")
            bulk_update_workflow = WorkflowBuilder()
            bulk_update_workflow.add_node(
                "BulkTestModelBulkUpdateNode",
                "bulk_update",
                {
                    "filter": {"category": "cat_0"},
                    "update": {"value": 9999},
                    "batch_size": 50,
                },
            )

            update_results, _ = runtime.execute(bulk_update_workflow.build())
            assert update_results["bulk_update"]["success"] is True

            # Verify updates
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM bulktestmodel WHERE value = 9999"
                )
                updated_count = cursor.fetchone()[0]
                assert (
                    updated_count == 200
                ), f"Expected 200 updated records, found {updated_count}"  # Every 5th record

            print(f"✅ Bulk updated {updated_count} records")

        finally:
            db.close_sync()

    @pytest.mark.requires_postgres
    def test_security_features_real_database(self, test_suite, postgres_config):
        """Test security features with real database."""

        # Enable security features
        config = postgres_config.copy()
        config.update({"multi_tenant": True, "audit_logging": True})

        db = DataFlow(**config)

        try:

            @db.model
            class SecureModel:
                name: str
                sensitive_data: str

            runtime = LocalRuntime()

            # Test tenant isolation
            print("\n=== Testing TENANT ISOLATION ===")

            # Create data for tenant A
            db.set_tenant_context("tenant_a")
            workflow_a = WorkflowBuilder()
            workflow_a.add_node(
                "SecureModelCreateNode",
                "create_a",
                {"name": "Tenant A Data", "sensitive_data": "Secret A"},
            )

            results_a, _ = runtime.execute(workflow_a.build())
            assert results_a["create_a"]["success"] is True
            tenant_a_id = results_a["create_a"]["data"]["id"]

            # Create data for tenant B
            db.set_tenant_context("tenant_b")
            workflow_b = WorkflowBuilder()
            workflow_b.add_node(
                "SecureModelCreateNode",
                "create_b",
                {"name": "Tenant B Data", "sensitive_data": "Secret B"},
            )

            results_b, _ = runtime.execute(workflow_b.build())
            assert results_b["create_b"]["success"] is True
            tenant_b_id = results_b["create_b"]["data"]["id"]

            # Verify tenant isolation - tenant A cannot see tenant B data
            db.set_tenant_context("tenant_a")
            list_workflow = WorkflowBuilder()
            list_workflow.add_node("SecureModelListNode", "list_a", {})

            list_results, _ = runtime.execute(list_workflow.build())
            tenant_a_data = list_results["list_a"]["data"]

            # Should only see tenant A data
            assert len(tenant_a_data) == 1
            assert tenant_a_data[0]["id"] == tenant_a_id
            assert tenant_a_data[0]["name"] == "Tenant A Data"

            # Verify in database that tenant_id is properly set
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute(
                    "SELECT tenant_id FROM securemodel WHERE id = %s", (tenant_a_id,)
                )
                row = cursor.fetchone()
                assert row[0] == "tenant_a"

            print("✅ Tenant isolation working correctly")

            # Test SQL injection prevention
            print("\n=== Testing SQL INJECTION PREVENTION ===")

            with pytest.raises(NodeValidationError):
                malicious_workflow = WorkflowBuilder()
                malicious_workflow.add_node(
                    "SecureModelCreateNode",
                    "malicious",
                    {
                        "name": "'; DROP TABLE securemodel; --",
                        "sensitive_data": "malicious",
                    },
                )
                runtime.execute(malicious_workflow.build())

            # Verify table still exists
            with db.get_connection_pool().get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM securemodel")
                count = cursor.fetchone()[0]
                assert count >= 2, "Table was compromised by SQL injection"

            print("✅ SQL injection prevention working correctly")

        finally:
            db.close_sync()

    @pytest.mark.performance
    @pytest.mark.requires_postgres
    def test_performance_benchmarks(self, test_suite, postgres_config):
        """Test performance with real measurements."""

        db = DataFlow(**postgres_config)

        try:

            @db.model
            class PerformanceTest:
                name: str
                value: int
                timestamp: str

            runtime = LocalRuntime()

            # Test single operation latency
            print("\n=== PERFORMANCE TESTING ===")
            print("Testing single operation latency...")

            latencies = []
            for i in range(100):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PerformanceTestCreateNode",
                    "create",
                    {
                        "name": f"Perf Test {i}",
                        "value": i,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

                start = time.time()
                results, _ = runtime.execute(workflow.build())
                elapsed = (time.time() - start) * 1000  # Convert to milliseconds

                latencies.append(elapsed)
                assert results["create"]["success"] is True

            # Calculate statistics
            latencies.sort()
            p50 = latencies[49]  # 50th percentile
            p95 = latencies[94]  # 95th percentile
            p99 = latencies[98]  # 99th percentile
            avg = sum(latencies) / len(latencies)

            print("Single Operation Latency:")
            print(f"  Average: {avg:.2f}ms")
            print(f"  P50: {p50:.2f}ms")
            print(f"  P95: {p95:.2f}ms")
            print(f"  P99: {p99:.2f}ms")

            # Verify performance requirements
            assert p95 < 50, f"P95 latency {p95:.2f}ms exceeds 50ms threshold"
            assert avg < 20, f"Average latency {avg:.2f}ms exceeds 20ms threshold"

            print("✅ Single operation latency requirements met")

            # Test concurrent operations
            print("Testing concurrent operations...")

            def concurrent_operation(thread_id: int):
                """Execute operation in separate thread."""
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "PerformanceTestCreateNode",
                    "create",
                    {
                        "name": f"Concurrent {thread_id}",
                        "value": thread_id,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

                start = time.time()
                runtime = LocalRuntime()
                results, _ = runtime.execute(workflow.build())
                elapsed = time.time() - start

                return elapsed, results["create"]["success"]

            # Run 50 concurrent operations
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=50) as executor:
                futures = [executor.submit(concurrent_operation, i) for i in range(50)]
                results = [future.result() for future in futures]

            total_time = time.time() - start_time

            # Verify all operations succeeded
            assert all(
                success for _, success in results
            ), "Some concurrent operations failed"

            # Calculate throughput
            throughput = 50 / total_time
            print("Concurrent Operations:")
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Throughput: {throughput:.0f} ops/sec")

            # Verify performance requirements
            assert (
                throughput > 10
            ), f"Throughput {throughput:.0f} ops/sec below 10 ops/sec minimum"

            print("✅ Concurrent operation requirements met")

        finally:
            db.close_sync()

    def test_error_handling_real_database(self, test_suite, sqlite_config):
        """Test error handling with real database."""

        db = DataFlow(**sqlite_config)

        try:

            @db.model
            class ErrorTestModel:
                name: str
                value: int

            runtime = LocalRuntime()

            # Test validation errors
            print("\n=== Testing ERROR HANDLING ===")

            # Test missing required field
            with pytest.raises(NodeValidationError):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "ErrorTestModelCreateNode",
                    "create",
                    {
                        "name": "Test"
                        # Missing required 'value' field
                    },
                )
                runtime.execute(workflow.build())

            # Test invalid type
            with pytest.raises(NodeValidationError):
                workflow = WorkflowBuilder()
                workflow.add_node(
                    "ErrorTestModelCreateNode",
                    "create",
                    {"name": "Test", "value": "not_an_integer"},  # Should be int
                )
                runtime.execute(workflow.build())

            # Test reading non-existent record
            workflow = WorkflowBuilder()
            workflow.add_node(
                "ErrorTestModelReadNode", "read", {"id": 99999}
            )  # Non-existent ID

            # Should not raise exception but return empty result
            results, _ = runtime.execute(workflow.build())
            # Note: Depending on implementation, this might return None or empty result

            print("✅ Error handling working correctly")

        finally:
            db.close_sync()

    def test_health_check_real_database(self, test_suite, sqlite_config):
        """Test health check with real database."""

        db = DataFlow(**sqlite_config)

        try:
            # Test health check
            health = db.health_check()

            assert health["status"] in ["healthy", "degraded"]
            assert "components" in health
            assert "database" in health["components"]
            assert "connection_pool" in health["components"]

            # Verify database component is healthy
            db_component = health["components"]["database"]
            assert db_component["status"] == "healthy"
            assert "url" in db_component
            assert "pool_size" in db_component

            print("✅ Health check passed")
            print(f"Database status: {db_component['status']}")
            print(f"Pool size: {db_component['pool_size']}")

        finally:
            db.close_sync()


if __name__ == "__main__":
    # Run basic tests if executed directly
    test_instance = TestProductionDataFlowRealDatabase()

    # Test with SQLite (always available)
    sqlite_config = {
        "database_url": "sqlite:///test_manual.db",
        "pool_size": 5,
        "monitoring": True,
    }

    print("Running manual DataFlow production tests...")
    test_instance._test_database_crud_operations(sqlite_config, "SQLite")
    print("\n✅ All manual tests passed!")
