"""
Advanced DataFlow Features

This example demonstrates:
- Multi-tenancy with automatic isolation
- Optimistic locking for concurrent updates
- Soft deletes with recovery
- Bulk operations for performance
- Transaction management
- Real-time monitoring
"""

import asyncio
from datetime import datetime, timedelta

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow, DataFlowConfig, Environment

# Configure with advanced features
config = DataFlowConfig(
    environment=Environment.DEVELOPMENT,
    monitoring=True,  # Enable monitoring
    multi_tenant=True,  # Enable multi-tenancy
)

db = DataFlow(config)


# Model with advanced features
@db.model
class Product:
    """Product model with enterprise features"""

    name: str
    price: float
    stock: int
    category: str
    active: bool = True

    # Enable advanced features
    __dataflow__ = {
        "soft_delete": True,  # Adds deleted_at field
        "versioned": True,  # Adds version field for optimistic locking
        "multi_tenant": True,  # Adds tenant_id field
    }

    __indexes__ = [
        {"name": "idx_category_active", "fields": ["category", "active"]},
        {"name": "idx_price", "fields": ["price"]},
    ]


def demo_multi_tenancy():
    """Demonstrate multi-tenant data isolation"""
    print("\n=== MULTI-TENANCY DEMO ===")

    workflow = WorkflowBuilder()

    # Create products for different tenants
    # DataFlow automatically isolates data by tenant

    # Tenant A products
    workflow.metadata["tenant_id"] = "tenant_a"
    workflow.add_node(
        "ProductCreateNode",
        "create_a1",
        {
            "name": "Laptop Pro",
            "price": 1299.99,
            "stock": 50,
            "category": "Electronics",
        },
    )
    workflow.add_node(
        "ProductCreateNode",
        "create_a2",
        {
            "name": "Wireless Mouse",
            "price": 29.99,
            "stock": 200,
            "category": "Electronics",
        },
    )

    # Tenant B products
    workflow.metadata["tenant_id"] = "tenant_b"
    workflow.add_node(
        "ProductCreateNode",
        "create_b1",
        {"name": "Office Chair", "price": 299.99, "stock": 30, "category": "Furniture"},
    )

    # List products - automatically filtered by tenant
    workflow.metadata["tenant_id"] = "tenant_a"
    workflow.add_node("ProductListNode", "list_tenant_a", {})

    workflow.metadata["tenant_id"] = "tenant_b"
    workflow.add_node("ProductListNode", "list_tenant_b", {})

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    print(f"Tenant A products: {len(results['list_tenant_a']['output'])}")
    for product in results["list_tenant_a"]["output"]:
        print(f"  - {product['name']} (${product['price']})")

    print(f"\nTenant B products: {len(results['list_tenant_b']['output'])}")
    for product in results["list_tenant_b"]["output"]:
        print(f"  - {product['name']} (${product['price']})")


def demo_optimistic_locking():
    """Demonstrate optimistic locking for concurrent updates"""
    print("\n=== OPTIMISTIC LOCKING DEMO ===")

    # Create a product
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductCreateNode",
        "create",
        {"name": "Popular Item", "price": 99.99, "stock": 100, "category": "Hot Deals"},
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    product = results["create"]["output"]

    # Simulate concurrent updates
    workflow = WorkflowBuilder()

    # User 1 tries to update stock
    workflow.add_node(
        "ProductUpdateNode",
        "update_1",
        {
            "filter": {
                "id": product["id"],
                "version": product["version"],  # Version check
            },
            "fields": {"stock": 90, "version": product["version"] + 1},
        },
    )

    # User 2 tries to update price with same version (will fail)
    workflow.add_node(
        "ProductUpdateNode",
        "update_2",
        {
            "filter": {
                "id": product["id"],
                "version": product["version"],  # Same version - conflict!
            },
            "fields": {"price": 89.99, "version": product["version"] + 1},
        },
    )

    results, run_id = runtime.execute(workflow.build())

    if results["update_1"]["status"] == "success":
        print("Update 1 succeeded (stock update)")

    if results["update_2"]["status"] == "failed":
        print("Update 2 failed due to version conflict (as expected)")
        print("This prevents lost updates in concurrent scenarios")


def demo_soft_delete():
    """Demonstrate soft delete and recovery"""
    print("\n=== SOFT DELETE DEMO ===")

    workflow = WorkflowBuilder()

    # Create a product
    workflow.add_node(
        "ProductCreateNode",
        "create",
        {
            "name": "Discontinued Item",
            "price": 49.99,
            "stock": 10,
            "category": "Clearance",
        },
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    product_id = results["create"]["output"]["id"]

    # Soft delete the product
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductDeleteNode", "soft_delete", {"filter": {"id": product_id}}
    )

    # Try to read it normally (won't find it)
    workflow.add_node("ProductReadNode", "read_deleted", {"filter": {"id": product_id}})

    # Read including soft deleted
    workflow.add_node(
        "ProductReadNode",
        "read_with_deleted",
        {"filter": {"id": product_id}, "include_deleted": True},
    )

    results, run_id = runtime.execute(workflow.build())

    print(f"Normal read found: {results['read_deleted']['output'] is not None}")
    print(
        f"Read with deleted found: {results['read_with_deleted']['output'] is not None}"
    )

    if results["read_with_deleted"]["output"]:
        print(f"Deleted at: {results['read_with_deleted']['output']['deleted_at']}")

    # Restore the product
    workflow = WorkflowBuilder()
    workflow.add_node(
        "ProductUpdateNode",
        "restore",
        {
            "filter": {"id": product_id},
            "fields": {"deleted_at": None},
            "include_deleted": True,
        },
    )

    runtime.execute(workflow.build())
    print("Product restored successfully")


def demo_bulk_operations():
    """Demonstrate high-performance bulk operations"""
    print("\n=== BULK OPERATIONS DEMO ===")

    workflow = WorkflowBuilder()

    # Bulk create 1000 products
    products = [
        {
            "name": f"Product {i}",
            "price": 10.0 + (i % 100),
            "stock": 100 + (i % 50),
            "category": f"Category {i % 10}",
        }
        for i in range(1000)
    ]

    workflow.add_node("ProductBulkCreateNode", "bulk_create", {"records": products})

    # Bulk update prices (10% discount)
    workflow.add_node(
        "ProductBulkUpdateNode",
        "bulk_update",
        {"filter": {"category": "Category 5"}, "fields": {"price": "price * 0.9"}},
    )

    # Bulk delete old stock
    workflow.add_node(
        "ProductBulkDeleteNode", "bulk_delete", {"filter": {"stock": {"$lt": 110}}}
    )

    import time

    start = time.time()

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    elapsed = time.time() - start

    print(f"Bulk operations completed in {elapsed:.2f} seconds")
    print(f"Created: {len(results['bulk_create']['output'])} products")
    print(f"Updated: {results['bulk_update']['output']['updated_count']} products")
    print(f"Deleted: {results['bulk_delete']['output']['deleted_count']} products")


def demo_transactions():
    """Demonstrate transaction management"""
    print("\n=== TRANSACTION MANAGEMENT DEMO ===")

    workflow = WorkflowBuilder()

    # Start transaction
    workflow.add_node(
        "BeginTransactionNode", "txn_start", {"isolation_level": "read_committed"}
    )

    # Create order
    workflow.add_node(
        "ProductCreateNode",
        "create_order",
        {"name": "Customer Order", "price": 299.99, "stock": 1, "category": "Orders"},
    )

    # Update inventory (will fail if not enough stock)
    workflow.add_node(
        "ProductUpdateNode",
        "update_inventory",
        {"filter": {"name": "Laptop Pro"}, "fields": {"stock": "stock - 1"}},
    )

    # Commit if all successful
    workflow.add_node("CommitTransactionNode", "txn_commit", {})

    # Rollback on any failure
    workflow.add_node("RollbackTransactionNode", "txn_rollback", {})

    # Connect nodes with conditional routing
    workflow.add_connection("txn_start", "create_order")
    workflow.add_connection(
        "create_order", "update_inventory", condition="status == 'success'"
    )
    workflow.add_connection(
        "update_inventory", "txn_commit", condition="status == 'success'"
    )

    # Rollback paths
    workflow.add_connection(
        "create_order", "txn_rollback", condition="status == 'failed'"
    )
    workflow.add_connection(
        "update_inventory", "txn_rollback", condition="status == 'failed'"
    )

    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())

    if results.get("txn_commit", {}).get("status") == "success":
        print("Transaction committed successfully")
    else:
        print("Transaction rolled back due to error")


async def demo_monitoring():
    """Demonstrate real-time monitoring capabilities"""
    print("\n=== MONITORING DEMO ===")

    # Access monitoring nodes
    monitors = db.get_monitor_nodes()

    if monitors:
        print("Active monitors:")
        for name, monitor in monitors.items():
            print(f"  - {name}: {type(monitor).__name__}")

        # Simulate some database activity
        workflow = WorkflowBuilder()

        # Create many quick operations
        for i in range(10):
            workflow.add_node(
                "ProductListNode",
                f"query_{i}",
                {"filter": {"category": f"Category {i}"}},
            )

        # One slow operation
        workflow.add_node(
            "ProductListNode",
            "slow_query",
            {
                "filter": {"price": {"$gte": 100}},
                "order_by": ["-price", "name"],
                "limit": 1000,
            },
        )

        runtime = LocalRuntime()
        runtime.execute(workflow.build())

        # Check metrics
        if "metrics" in monitors:
            print("\nPerformance metrics available:")
            print("- Query count by operation")
            print("- Average response time")
            print("- Slow query log")
            print("- Connection pool statistics")


if __name__ == "__main__":
    print("DataFlow Advanced Features Example")
    print("=" * 50)

    # Demonstrate all advanced features
    demo_multi_tenancy()
    demo_optimistic_locking()
    demo_soft_delete()
    demo_bulk_operations()
    demo_transactions()

    # Run async monitoring demo
    asyncio.run(demo_monitoring())

    print("\n" + "=" * 50)
    print("Advanced features demonstrated successfully!")
    print("\nKey takeaways:")
    print("1. Multi-tenancy provides automatic data isolation")
    print("2. Optimistic locking prevents lost updates")
    print("3. Soft delete allows data recovery")
    print("4. Bulk operations provide high performance")
    print("5. Transaction management ensures consistency")
    print("6. Built-in monitoring for production insights")
