---
name: dataflow-bulk-operations
description: "High-performance bulk operations for DataFlow with MongoDB-style operators. Use when bulk operations, batch insert, BulkCreateNode, BulkUpdateNode, mass data import, $in/$nin operators, or high-throughput processing."
---

# DataFlow Bulk Operations

High-performance bulk nodes for 1,000-100,000+ records/sec with MongoDB-style query operators.

## Quick Reference

| Node               | Throughput | Key Parameters                                                      |
| ------------------ | ---------- | ------------------------------------------------------------------- |
| **BulkCreateNode** | 10k+/sec   | `data`, `batch_size`, `conflict_resolution`, `error_strategy`       |
| **BulkUpdateNode** | 50k+/sec   | `filter`, `fields`, `batch_size`                                    |
| **BulkDeleteNode** | 100k+/sec  | `filter`, `soft_delete`, `batch_size`, `max_delete_count`           |
| **BulkUpsertNode** | 3k+/sec    | `data` (must include `id`), `conflict_resolution` ("update"/"skip") |

Use bulk for >100 records. Optimal `batch_size`: 1000-5000.

## Core Pattern

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

db = DataFlow()

@db.model
class Product:
    name: str
    price: float
    category: str
    stock: int

products = [
    {"name": f"Product {i}", "price": i * 10.0, "category": "electronics", "stock": 100}
    for i in range(1, 1001)
]

workflow = WorkflowBuilder()
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "data": products,
    "batch_size": 1000,
    "conflict_resolution": "skip"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
imported = results["import_products"]["data"]
```

## BulkCreateNode Parameters

```python
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products_list,
    "batch_size": 1000,
    "parallel_batches": 4,
    "use_copy": True,                # PostgreSQL COPY optimization
    "conflict_resolution": "skip",   # skip, error, update
    "conflict_fields": ["sku"],
    "error_strategy": "continue",    # continue, stop
    "max_errors": 100,
    "validate_data": True,
    "skip_invalid": False
})
```

## BulkUpdateNode Parameters

```python
workflow.add_node("ProductBulkUpdateNode", "discount", {
    "filter": {"category": "electronics", "active": True},
    "fields": {
        "price": {"$multiply": 0.9},
        "updated_at": ":current_timestamp"
    },
    "batch_size": 2000,
    "return_updated": True
})
```

## BulkDeleteNode Parameters

```python
workflow.add_node("ProductBulkDeleteNode", "cleanup", {
    "filter": {"active": False, "created_at": {"$lt": "2022-01-01"}},
    "soft_delete": True,
    "max_delete_count": 10000,
    "dry_run": False,
    "batch_size": 1000
})
```

## BulkUpsertNode Parameters

Conflict column is always `id`. Each record in `data` MUST include `id`.

```python
workflow.add_node("ProductBulkUpsertNode", "sync", {
    "data": products_list,          # Each item must have "id"
    "conflict_resolution": "update", # "update" (default) or "skip"/"ignore"
    "batch_size": 2000
})
```

## MongoDB-Style Operators

| Operator | SQL      | Example                                      |
| -------- | -------- | -------------------------------------------- |
| `$in`    | `IN`     | `{"status": {"$in": ["active", "pending"]}}` |
| `$nin`   | `NOT IN` | `{"type": {"$nin": ["test", "demo"]}}`       |
| `$gt`    | `>`      | `{"price": {"$gt": 100.00}}`                 |
| `$gte`   | `>=`     | `{"stock": {"$gte": 10}}`                    |
| `$lt`    | `<`      | `{"views": {"$lt": 1000}}`                   |
| `$lte`   | `<=`     | `{"age": {"$lte": 18}}`                      |
| `$ne`    | `!=`     | `{"status": {"$ne": "deleted"}}`             |

```python
# Combined operators
workflow.add_node("UserBulkUpdateNode", "flag_inactive", {
    "filter": {
        "last_login": {"$lt": "2024-01-01"},
        "account_type": {"$in": ["free", "trial"]},
        "status": {"$ne": "suspended"}
    },
    "fields": {"inactive": True}
})

# Multiple IDs
workflow.add_node("ProductBulkDeleteNode", "delete_specific", {
    "filter": {"id": {"$in": ["prod_1", "prod_2", "prod_3"]}}
})
```

Edge cases: empty lists match nothing, single values work, duplicates auto-deduped.

## Datetime Auto-Conversion

ISO 8601 strings automatically convert to datetime on all bulk nodes.

```python
workflow.add_node("PythonCodeNode", "generate_bulk_data", {
    "code": """
from datetime import datetime, timedelta
users = [{"name": f"User {i}", "email": f"user{i}@example.com",
          "registered_at": (datetime.now() - timedelta(days=i)).isoformat()}
         for i in range(1000)]
result = {"users": users}
    """
})
workflow.add_node("UserBulkCreateNode", "bulk_import", {
    "data": "{{generate_bulk_data.users}}",
    "batch_size": 1000
})
```

Both datetime objects and ISO strings accepted.

## Common Mistakes

```python
# WRONG: Single operations in loop (slow)
for product in products:
    workflow.add_node("ProductCreateNode", f"create_{product['sku']}", product)

# CORRECT: Bulk operation (10-100x faster)
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products, "batch_size": 1000
})

# WRONG: batch_size too small
"batch_size": 10  # Overhead dominates

# WRONG: No error handling
"error_strategy": "stop"  # Fails entire batch

# CORRECT: Resilient import
"error_strategy": "continue", "max_errors": 1000
```

## Troubleshooting

| Issue                | Solution                                      |
| -------------------- | --------------------------------------------- |
| `MemoryError`        | Reduce `batch_size` or use streaming          |
| Slow performance     | Increase `batch_size` to 1000-5000            |
| Duplicate key errors | Use `conflict_resolution`: "skip" or "update" |
| Transaction timeout  | Reduce `batch_size`                           |

<!-- Trigger Keywords: bulk operations, batch insert, BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode, mass data import, high-throughput, bulk create, bulk update, bulk delete -->
