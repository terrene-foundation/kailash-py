"""
Advanced DataFlow Features

This example demonstrates, on the current DataFlow API:
- Soft deletes with recovery (real `__dataflow__={"soft_delete": True}` feature)
- Multi-tenancy with automatic isolation (real `db.tenant_context` API)
- Search with the `$like` filter operator
- Bulk operations for performance
- Transaction management with SwitchNode commit/rollback routing
- Real-time monitoring via the connection-pool inspection API

It runs against local SQLite files (no external infrastructure required).

Notes on the current API:
- Soft delete is a first-class model feature: `__dataflow__={"soft_delete": True}`
  adds tombstone handling; `db.express.delete(...)` tombstones the row and
  `db.express.list(..., include_deleted=True)` recovers it.
- Multi-tenancy uses `DataFlow(..., multi_tenant=True)` + a model flagged
  `__dataflow__={"multi_tenant": True}` + `db.tenant_context.register_tenant(...)`
  / `switch(...)`; writes auto-stamp tenant_id and reads auto-filter by the
  bound tenant. A multi_tenant instance requires a bound tenant for EVERY
  model, so the tenant demo uses its own DataFlow instance.
- Transaction primitives are `TransactionScopeNode` / `TransactionCommitNode`
  / `TransactionRollbackNode`; conditional routing uses `SwitchNode`
  true/false-output ports (there are no `add_connection(condition=...)` edges).
- On SQLite, `express.create` does not echo the generated id, so ids are read
  back with a follow-up `express.list`.
"""

import asyncio
import os
import time

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow

# Persistent SQLite files so tables survive across the multiple short-lived
# connections DataFlow opens (an in-memory database would give each connection
# its own empty schema).
_HERE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_HERE, "02_advanced_demo.db")
_TENANT_DB_PATH = os.path.join(_HERE, "02_advanced_tenant_demo.db")
for _p in (_DB_PATH, _TENANT_DB_PATH):
    if os.path.exists(_p):
        os.remove(_p)

db = DataFlow(f"sqlite:///{_DB_PATH}", monitoring=True)


@db.model
class Product:
    """Product model with soft-delete enabled."""

    name: str
    price: float
    stock: int
    category: str

    # Real soft-delete feature: delete tombstones the row (recoverable),
    # rather than removing it.
    __dataflow__ = {"soft_delete": True}

    __indexes__ = [
        {"name": "idx_category", "fields": ["category"]},
        {"name": "idx_price", "fields": ["price"]},
    ]


async def _create_and_get_id(model: str, data: dict) -> int:
    """Create a record and return its id.

    On SQLite ``express.create`` does not echo the generated id, so it is read
    back via a list filtered on the (unique) name.
    """
    await db.express.create(model, data)
    rows = await db.express.list(model, {"name": data["name"]})
    return rows[0]["id"]


async def demo_soft_delete():
    """Demonstrate soft delete + recovery (real soft_delete feature)."""
    print("\n=== SOFT DELETE DEMO ===")

    tok = str(int(time.time() * 1_000_000))
    name = f"Discontinued Item {tok}"
    product_id = await _create_and_get_id(
        "Product",
        {"name": name, "price": 49.99, "stock": 10, "category": "Clearance"},
    )

    visible = await db.express.list("Product", {"name": name})
    print(f"Before delete, normal list finds: {len(visible)} (expected 1)")

    # Soft delete tombstones the row.
    await db.express.delete("Product", product_id)

    after = await db.express.list("Product", {"name": name})
    print(f"After delete, normal list finds: {len(after)} (expected 0)")

    recovered = await db.express.list("Product", {"name": name}, include_deleted=True)
    print(f"With include_deleted=True, list finds: {len(recovered)} (expected 1)")
    print("The tombstoned row is recoverable, not destroyed.")


async def demo_multi_tenancy():
    """Demonstrate automatic tenant isolation (real db.tenant_context API)."""
    print("\n=== MULTI-TENANCY DEMO ===")

    # A multi_tenant instance requires a bound tenant for every model, so the
    # tenant demo uses its own DataFlow instance.
    tdb = DataFlow(f"sqlite:///{_TENANT_DB_PATH}", multi_tenant=True)

    @tdb.model
    class TenantProduct:
        __tablename__ = "tenant_product"
        name: str
        price: float
        __dataflow__ = {"multi_tenant": True}

    await tdb.create_tables_async()

    tdb.tenant_context.register_tenant("tenant_a", "Tenant A")
    tdb.tenant_context.register_tenant("tenant_b", "Tenant B")

    # Writes inside a tenant context are auto-stamped with that tenant_id.
    with tdb.tenant_context.switch("tenant_a"):
        await tdb.express.create(
            "TenantProduct", {"name": "Laptop Pro", "price": 1299.99}
        )
        await tdb.express.create(
            "TenantProduct", {"name": "Wireless Mouse", "price": 29.99}
        )
    with tdb.tenant_context.switch("tenant_b"):
        await tdb.express.create(
            "TenantProduct", {"name": "Office Chair", "price": 299.99}
        )

    # Reads inside a tenant context are auto-filtered to that tenant.
    with tdb.tenant_context.switch("tenant_a"):
        products_a = await tdb.express.list("TenantProduct", {})
    with tdb.tenant_context.switch("tenant_b"):
        products_b = await tdb.express.list("TenantProduct", {})

    print(f"Tenant A products: {len(products_a)}")
    for p in sorted(products_a, key=lambda r: r["name"]):
        print(f"  - {p['name']} (${p['price']})")
    print(f"Tenant B products: {len(products_b)}")
    for p in sorted(products_b, key=lambda r: r["name"]):
        print(f"  - {p['name']} (${p['price']})")
    print("Each tenant sees only its own rows — isolation is automatic.")


async def demo_search():
    """Demonstrate search with the $like filter operator."""
    print("\n=== SEARCH DEMO ===")

    tok = str(int(time.time() * 1_000_000))
    titles = [
        f"Getting Started with DataFlow {tok}",
        f"DataFlow Performance Optimization {tok}",
        f"Building APIs with DataFlow {tok}",
        f"Unrelated Cooking Recipes {tok}",
    ]
    for i, title in enumerate(titles):
        await db.express.create(
            "Product",
            {"name": title, "price": 10.0 + i, "stock": 5, "category": "Guides"},
        )

    # Real $like operator (maps to SQL LIKE) — no python-side filtering.
    matches = await db.express.list("Product", {"name": {"$like": f"%DataFlow%{tok}"}})
    print(f"Products matching '%DataFlow%': {len(matches)} (expected 3)")
    for p in sorted(matches, key=lambda r: r["name"]):
        print(f"  - {p['name']}")


async def demo_bulk_operations():
    """Demonstrate high-performance bulk operations."""
    print("\n=== BULK OPERATIONS DEMO ===")

    tok = str(int(time.time() * 1_000_000))
    products = [
        {
            "name": f"Bulk {tok} Product {i}",
            "price": 10.0 + (i % 100),
            "stock": 100 + (i % 50),
            "category": f"Category {tok}_{i % 10}",
        }
        for i in range(1000)
    ]

    start = time.time()
    runtime = LocalRuntime()

    # Bulk create (the current bulk param is `data`).
    bc_wf = WorkflowBuilder()
    bc_wf.add_node("ProductBulkCreateNode", "bulk_create", {"data": products})
    bc_results, _ = await runtime.execute_async(bc_wf.build())

    # Bulk update: 10% discount on one category.
    bu_wf = WorkflowBuilder()
    bu_wf.add_node(
        "ProductBulkUpdateNode",
        "bulk_update",
        {"filter": {"category": f"Category {tok}_5"}, "fields": {"price": 9.0}},
    )
    bu_results, _ = await runtime.execute_async(bu_wf.build())

    # Bulk delete: drop low-stock rows from this run.
    bd_wf = WorkflowBuilder()
    bd_wf.add_node(
        "ProductBulkDeleteNode",
        "bulk_delete",
        {"filter": {"category": f"Category {tok}_0", "stock": {"$lt": 110}}},
    )
    bd_results, _ = await runtime.execute_async(bd_wf.build())
    elapsed = time.time() - start

    print(f"Bulk operations completed in {elapsed:.2f} seconds")
    print(f"Created: {bc_results['bulk_create'].get('inserted')} products")
    print(f"Updated: {bu_results['bulk_update'].get('updated')} products")
    print(f"Deleted: {bd_results['bulk_delete'].get('deleted')} products")


async def demo_transactions():
    """Demonstrate transaction management with SwitchNode commit/rollback routing."""
    print("\n=== TRANSACTION MANAGEMENT DEMO ===")

    tok = str(int(time.time() * 1_000_000))
    # skip_branches prunes the untaken commit/rollback terminal; the transaction
    # nodes read the DataFlow instance from the workflow context.
    runtime = LocalRuntime(conditional_execution="skip_branches")
    workflow = WorkflowBuilder()

    # Begin a real transaction scope.
    workflow.add_node(
        "TransactionScopeNode", "txn_start", {"isolation_level": "READ_COMMITTED"}
    )
    # Do work inside the scope.
    workflow.add_node(
        "ProductCreateNode",
        "create_order",
        {
            "name": f"Customer Order {tok}",
            "price": 299.99,
            "stock": 1,
            "category": "Orders",
        },
    )
    # Decide the outcome, then route to commit (success) or rollback.
    workflow.add_node(
        "PythonCodeNode",
        "decide",
        {"code": "result = {'status': 'success' if rows_affected else 'failed'}"},
    )
    workflow.add_node(
        "SwitchNode",
        "route",
        {"condition_field": "status", "operator": "==", "value": "success"},
    )
    workflow.add_node("TransactionCommitNode", "txn_commit", {})
    workflow.add_node("TransactionRollbackNode", "txn_rollback", {})

    workflow.add_connection(
        "txn_start", "transaction_id", "create_order", "transaction_id"
    )
    workflow.add_connection("create_order", "rows_affected", "decide", "rows_affected")
    workflow.add_connection("decide", "result", "route", "input_data")
    workflow.add_connection("route", "true_output", "txn_commit", "trigger")
    workflow.add_connection("route", "false_output", "txn_rollback", "trigger")

    results, _ = await runtime.execute_async(
        workflow.build(),
        parameters={"workflow_context": {"dataflow_instance": db}},
    )

    if results.get("txn_commit", {}).get("status") == "committed":
        print("Transaction committed successfully")
    else:
        print("Transaction rolled back due to error")


async def demo_monitoring():
    """Demonstrate monitoring via the connection-pool inspection API."""
    print("\n=== MONITORING DEMO ===")

    # Inspect the connection pool — the monitoring surface for DataFlow.
    pool = db.get_connection_pool()
    health = await pool.get_health_status()
    print(f"Pool health: {health['status']}")

    # Simulate some database activity.
    runtime = LocalRuntime()
    workflow = WorkflowBuilder()
    for i in range(10):
        workflow.add_node(
            "ProductListNode",
            f"query_{i}",
            {"filter": {"category": f"Category {i}"}, "limit": 100},
        )
    workflow.add_node(
        "ProductListNode",
        "slow_query",
        {
            "filter": {"price": {"$gte": 100}},
            "order_by": ["-price", "name"],
            "limit": 1000,
        },
    )
    await runtime.execute_async(workflow.build())

    # Read pool metrics after the activity.
    metrics = await pool.get_metrics()
    print("\nConnection pool metrics:")
    print(f"- total_connections: {metrics['total_connections']}")
    print(f"- connections_created: {metrics['connections_created']}")
    print(f"- connections_reused: {metrics['connections_reused']}")
    print(f"- active_connections: {metrics['active_connections']}")


async def main():
    print("DataFlow Advanced Features Example")
    print("=" * 50)

    await db.create_tables_async()

    await demo_soft_delete()
    await demo_multi_tenancy()
    await demo_search()
    await demo_bulk_operations()
    await demo_transactions()
    await demo_monitoring()

    print("\n" + "=" * 50)
    print("Advanced features demonstrated successfully!")
    print("\nKey takeaways:")
    print("1. Soft delete tombstones rows and keeps them recoverable")
    print("2. Multi-tenancy isolates data automatically via db.tenant_context")
    print("3. Search uses the $like filter operator")
    print("4. Bulk operations provide high performance")
    print("5. Transaction management with SwitchNode commit/rollback routing")
    print("6. Built-in monitoring via connection-pool inspection")


if __name__ == "__main__":
    asyncio.run(main())
