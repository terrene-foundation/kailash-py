---
name: dataflow-bulk-operations
description: "High-performance bulk operations for DataFlow. Use when bulk operations, batch insert, BulkCreateNode, BulkUpdateNode, mass data import, or high-throughput processing."
---

# DataFlow Bulk Operations

High-performance bulk nodes for processing thousands of records efficiently with automatic optimization.

> **Skill Metadata**
> Category: `dataflow`
> Priority: `HIGH`
> SDK Version: `0.9.25+ / DataFlow 0.6.0`
> Related Skills: [`dataflow-crud-operations`](#), [`dataflow-models`](#), [`dataflow-queries`](#)
> Related Subagents: `dataflow-specialist` (performance optimization, troubleshooting)

## Quick Reference

- **4 Bulk Nodes**: BulkCreate, BulkUpdate, BulkDelete, BulkUpsert
- **Performance**: 1,000-100,000 records/sec depending on operation
- **Auto-Optimization**: Database-specific optimizations (PostgreSQL COPY, etc.)
- **Pattern**: Use for >100 records
- **Datetime Auto-Conversion**: ISO 8601 strings → datetime objects (v0.6.4+)

```python
# Bulk create
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products_list,
    "batch_size": 1000
})

# Bulk update
workflow.add_node("ProductBulkUpdateNode", "update_prices", {
    "filter": {"category": "electronics"},
    "fields": {"price": {"$multiply": 0.9}}
})

# Bulk delete
workflow.add_node("ProductBulkDeleteNode", "cleanup", {
    "filter": {"active": False},
    "soft_delete": True
})

# Bulk upsert
workflow.add_node("ProductBulkUpsertNode", "sync", {
    "data": products_list,
    "unique_fields": ["sku"]
})
```

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

# Prepare bulk data
products = [
    {"name": f"Product {i}", "price": i * 10.0, "category": "electronics", "stock": 100}
    for i in range(1, 1001)  # 1000 products
]

workflow = WorkflowBuilder()

# Bulk create (high performance)
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "data": products,
    "batch_size": 1000,           # Process 1000 at a time
    "conflict_resolution": "skip"  # Skip duplicates
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Check results
imported = results["import_products"]["data"]
print(f"Imported {imported['records_processed']} products")
print(f"Success: {imported['success_count']}, Failed: {imported['failure_count']}")
```

## Common Use Cases

- **Data Import**: CSV/Excel imports, API data sync
- **Price Updates**: Mass price changes, discounts
- **Inventory Management**: Stock updates, reordering
- **Data Migration**: Moving data between systems
- **Cleanup Operations**: Archiving, deletion of old data

## Bulk Node Reference

| Node | Throughput | Use Case | Key Parameters |
|------|-----------|----------|----------------|
| **BulkCreateNode** | 10k+/sec | Data import | `data`, `batch_size`, `conflict_resolution` |
| **BulkUpdateNode** | 50k+/sec | Mass updates | `filter`, `updates`, `batch_size` |
| **BulkDeleteNode** | 100k+/sec | Cleanup | `filter`, `soft_delete`, `batch_size` |
| **BulkUpsertNode** | 3k+/sec | Sync operations | `data`, `unique_fields`, `batch_size` |

## Key Parameters / Options

### BulkCreateNode

```python
workflow.add_node("ProductBulkCreateNode", "import", {
    # Required
    "data": products_list,  # List of dicts

    # Performance
    "batch_size": 1000,              # Records per batch
    "parallel_batches": 4,           # Concurrent batches
    "use_copy": True,                # PostgreSQL COPY (faster)

    # Conflict resolution
    "conflict_resolution": "skip",   # skip, error, update
    "conflict_fields": ["sku"],      # Fields to check

    # Error handling
    "error_strategy": "continue",    # continue, stop
    "max_errors": 100,               # Stop if too many errors

    # Validation
    "validate_data": True,
    "skip_invalid": False
})
```

### BulkUpdateNode

```python
workflow.add_node("ProductBulkUpdateNode", "update", {
    # Filter (which records to update)
    "filter": {
        "category": "electronics",
        "active": True
    },

    # Updates to apply
    "fields": {
        "price": {"$multiply": 0.9},  # 10% discount
        "updated_at": ":current_timestamp"
    },

    # Performance
    "batch_size": 2000,
    "return_updated": True  # Return updated records
})
```

### BulkDeleteNode

```python
workflow.add_node("ProductBulkDeleteNode", "cleanup", {
    # Filter (which records to delete)
    "filter": {
        "active": False,
        "created_at": {"$lt": "2022-01-01"}
    },

    # Delete mode
    "soft_delete": True,            # Preserve data
    "hard_delete": False,           # Permanent deletion

    # Safety
    "max_delete_count": 10000,      # Safety limit
    "dry_run": False,               # Preview mode

    # Performance
    "batch_size": 1000
})
```

### BulkUpsertNode

```python
workflow.add_node("ProductBulkUpsertNode", "sync", {
    # Data to upsert
    "data": products_list,

    # Matching fields
    "unique_fields": ["sku"],       # Check these for duplicates

    # Field control
    "update_fields": ["price", "stock"],  # Update these on match
    "insert_fields": ["*"],         # All fields for new records

    # Performance
    "batch_size": 2000
})
```

## Common Mistakes

### Mistake 1: Using Single Operations for Bulk

```python
# Wrong - very slow for 1000+ records
for product in products:
    workflow.add_node("ProductCreateNode", f"create_{product['sku']}", product)
```

**Fix: Use Bulk Operations**

```python
# Correct - 10-100x faster
workflow.add_node("ProductBulkCreateNode", "import_products", {
    "data": products,
    "batch_size": 1000
})
```

### Mistake 2: Batch Size Too Small

```python
# Wrong - overhead dominates
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products,
    "batch_size": 10  # Too small!
})
```

**Fix: Use Appropriate Batch Size**

```python
# Correct - optimal performance
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products,
    "batch_size": 1000  # 1000-5000 typical
})
```

### Mistake 3: Not Handling Errors

```python
# Wrong - stops on first error
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products,
    "error_strategy": "stop"  # Fails entire batch
})
```

**Fix: Continue on Errors**

```python
# Correct - resilient import
workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products,
    "error_strategy": "continue",
    "max_errors": 1000,
    "failed_records_file": "/tmp/failed.json"
})
```

## Automatic Datetime Conversion in Bulk Operations (v0.6.4+)

DataFlow automatically converts ISO 8601 datetime strings to Python datetime objects in ALL bulk operations. This is especially powerful for data imports from external sources.

### Supported ISO 8601 Formats

- **Basic**: `2024-01-01T12:00:00`
- **With microseconds**: `2024-01-01T12:00:00.123456`
- **With timezone Z**: `2024-01-01T12:00:00Z`
- **With timezone offset**: `2024-01-01T12:00:00+05:30`

### Example: BulkCreateNode with PythonCodeNode

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# PythonCodeNode generates bulk data with ISO strings
workflow.add_node("PythonCodeNode", "generate_bulk_data", {
    "code": """
from datetime import datetime, timedelta

users = []
for i in range(1000):
    users.append({
        "name": f"User {i}",
        "email": f"user{i}@example.com",
        "registered_at": (datetime.now() - timedelta(days=i)).isoformat(),
        "last_login": datetime.now().isoformat()
    })

result = {"users": users}
    """
})

# BulkCreateNode automatically converts all ISO strings to datetime
workflow.add_node("UserBulkCreateNode", "bulk_import", {
    "data": "{{generate_bulk_data.users}}",  # All ISO strings → datetime
    "batch_size": 1000
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# All datetime fields stored as proper datetime types
imported = results["bulk_import"]["data"]
print(f"Imported {imported['success_count']} users with converted timestamps")
```

### Example: BulkUpdateNode with Datetime

```python
# Update last_login timestamps in bulk
workflow.add_node("PythonCodeNode", "generate_timestamps", {
    "code": """
from datetime import datetime

updates = []
for user_id in range(1, 101):
    updates.append({
        "id": user_id,
        "last_login": datetime.now().isoformat()
    })

result = {"updates": updates}
    """
})

# BulkUpdateNode auto-converts ISO strings
workflow.add_node("UserBulkUpdateNode", "update_logins", {
    "fields": "{{generate_timestamps.updates}}",  # ISO strings → datetime
    "batch_size": 100
})
```

### Example: BulkUpsertNode with Datetime

```python
# Sync external data with timestamps
workflow.add_node("PythonCodeNode", "fetch_external_data", {
    "code": """
import requests
from datetime import datetime

# Fetch from external API
response = requests.get("https://api.example.com/products")
products = response.json()

# Add sync timestamp
for product in products:
    product["last_synced"] = datetime.now().isoformat()

result = {"products": products}
    """
})

# BulkUpsertNode converts all datetime strings
workflow.add_node("ProductBulkUpsertNode", "sync_products", {
    "data": "{{fetch_external_data.products}}",  # ISO strings → datetime
    "unique_fields": ["external_id"],
    "batch_size": 500
})
```

### Example: CSV Import with Datetime Conversion

```python
# Import CSV with date columns
workflow.add_node("PythonCodeNode", "parse_csv_with_dates", {
    "code": """
import csv
from datetime import datetime

products = []
with open('products.csv') as f:
    for row in csv.DictReader(f):
        products.append({
            "name": row["name"],
            "price": float(row["price"]),
            "created_at": datetime.fromisoformat(row["created_date"]).isoformat(),
            "updated_at": datetime.fromisoformat(row["updated_date"]).isoformat()
        })

result = {"products": products}
    """
})

# BulkCreateNode handles datetime conversion
workflow.add_node("ProductBulkCreateNode", "import_csv", {
    "data": "{{parse_csv_with_dates.products}}",  # All timestamps auto-converted
    "batch_size": 5000
})
```

### Backward Compatibility

Existing code with datetime objects continues to work:

```python
from datetime import datetime

# Direct datetime objects still work
products = [
    {
        "name": "Product 1",
        "price": 19.99,
        "created_at": datetime.now()  # Direct datetime object
    },
    {
        "name": "Product 2",
        "price": 29.99,
        "created_at": "2024-01-15T10:30:00"  # ISO string also works
    }
]

workflow.add_node("ProductBulkCreateNode", "import", {
    "data": products,
    "batch_size": 1000
})
```

### Applies To All Bulk Nodes

Datetime auto-conversion works on:
- ✅ `ProductBulkCreateNode` - Bulk inserts
- ✅ `ProductBulkUpdateNode` - Bulk updates
- ✅ `ProductBulkUpsertNode` - Bulk upserts
- ✅ `ProductBulkDeleteNode` - Bulk deletes (for timestamp filters)

### Common Use Cases

**API Data Synchronization:**
```python
# External API returns ISO timestamps
workflow.add_node("PythonCodeNode", "sync_api", {
    "code": """
import requests
response = requests.get("https://api.partner.com/inventory")
result = {"inventory": response.json()}  # Contains ISO datetime strings
    """
})

workflow.add_node("InventoryBulkUpsertNode", "sync", {
    "data": "{{sync_api.inventory}}",  # Timestamps auto-converted
    "unique_fields": ["sku"],
    "batch_size": 1000
})
```

**Historical Data Import:**
```python
# Import historical records with date ranges
workflow.add_node("PythonCodeNode", "generate_historical", {
    "code": """
from datetime import datetime, timedelta

records = []
start_date = datetime(2020, 1, 1)
for i in range(1000):
    records.append({
        "date": (start_date + timedelta(days=i)).isoformat(),
        "value": i * 10.0
    })

result = {"records": records}
    """
})

workflow.add_node("RecordBulkCreateNode", "import_historical", {
    "data": "{{generate_historical.records}}",  # All dates converted
    "batch_size": 5000,
    "use_copy": True  # PostgreSQL optimization
})
```

**Real-Time Event Processing:**
```python
# Process events with timestamps
workflow.add_node("PythonCodeNode", "process_events", {
    "code": """
from datetime import datetime

events = []
for event in incoming_events:
    events.append({
        "user_id": event["user_id"],
        "action": event["action"],
        "timestamp": datetime.now().isoformat()
    })

result = {"events": events}
    """
})

workflow.add_node("EventBulkCreateNode", "log_events", {
    "data": "{{process_events.events}}",  # Timestamps auto-converted
    "batch_size": 100
})
```

## Related Patterns

- **For single operations**: See [`dataflow-crud-operations`](#)
- **For queries**: See [`dataflow-queries`](#)
- **For performance**: See [`dataflow-performance`](#)

## When to Escalate to Subagent

Use `dataflow-specialist` subagent when:
- Optimizing bulk operations for millions of records
- Troubleshooting performance bottlenecks
- Implementing custom batch strategies
- Working with very large datasets (>1M records)
- Setting up parallel processing pipelines

## Documentation References

### Primary Sources
- **Bulk Operations Guide**: [`sdk-users/apps/dataflow/docs/development/bulk-operations.md`](../../../../sdk-users/apps/dataflow/docs/development/bulk-operations.md)
- **README**: [`sdk-users/apps/dataflow/README.md`](../../../../sdk-users/apps/dataflow/README.md#L351-L381)
- **Performance Guide**: [`sdk-users/apps/dataflow/docs/production/performance.md`](../../../../sdk-users/apps/dataflow/docs/production/performance.md)

### Related Documentation
- **Database Optimization**: [`sdk-users/apps/dataflow/docs/advanced/database-optimization.md`](../../../../sdk-users/apps/dataflow/docs/advanced/database-optimization.md)
- **DataFlow CLAUDE**: [`sdk-users/apps/dataflow/CLAUDE.md`](../../../../sdk-users/apps/dataflow/CLAUDE.md)

## Examples

### Example 1: CSV Data Import

```python
import csv
from decimal import Decimal

# Read CSV data
products = []
with open('products.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        products.append({
            "sku": row["SKU"],
            "name": row["Name"],
            "price": Decimal(row["Price"]),
            "stock": int(row["Stock"]),
            "category": row["Category"]
        })

# Bulk import
workflow = WorkflowBuilder()
workflow.add_node("ProductBulkCreateNode", "import_csv", {
    "data": products,
    "batch_size": 5000,
    "use_copy": True,                # PostgreSQL optimization
    "conflict_resolution": "skip",   # Skip duplicates
    "error_strategy": "continue",
    "failed_records_file": "/tmp/failed_imports.json"
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Example 2: Mass Price Update

```python
# 10% discount on all electronics
workflow.add_node("ProductBulkUpdateNode", "discount_electronics", {
    "filter": {
        "category": "electronics",
        "active": True
    },
    "fields": {
        "price": {"$multiply": 0.9},  # 10% off
        "discount_applied": True,
        "updated_at": ":current_timestamp"
    },
    "batch_size": 2000,
    "return_updated": True
})

results, run_id = runtime.execute(workflow.build())
updated = results["discount_electronics"]["data"]
print(f"Updated {updated['success_count']} products")
```

### Example 3: Data Synchronization

```python
# Sync products from external API
external_products = fetch_from_api()  # Get external data

workflow = WorkflowBuilder()
workflow.add_node("ProductBulkUpsertNode", "sync_products", {
    "data": external_products,
    "unique_fields": ["external_id"],    # Match on external ID
    "update_fields": ["price", "stock"], # Update price/stock
    "insert_fields": ["*"],              # All fields for new
    "batch_size": 3000
})

results, run_id = runtime.execute(workflow.build())
sync_result = results["sync_products"]["data"]
print(f"Created: {sync_result['inserted']}, Updated: {sync_result['updated']}")
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `MemoryError` | Dataset too large | Reduce batch_size or use streaming |
| Slow performance | Small batch_size | Increase to 1000-5000 |
| Duplicate key errors | conflict_resolution="error" | Use "skip" or "update" |
| Transaction timeout | Batch too large | Reduce batch_size |

## Quick Tips

- Use 1000-5000 for batch_size (optimal)
- Enable `use_copy=True` for PostgreSQL
- Use `error_strategy="continue"` for resilient imports
- Monitor memory usage for very large datasets
- Use upsert for synchronization tasks
- Soft delete preserves audit trails
- Test with small dataset first

## Keywords for Auto-Trigger

<!-- Trigger Keywords: bulk operations, batch insert, BulkCreateNode, BulkUpdateNode, BulkDeleteNode, BulkUpsertNode, mass data import, high-throughput, bulk create, bulk update, bulk delete, batch operations, data import, mass updates -->
