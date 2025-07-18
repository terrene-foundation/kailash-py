# DataFlow Node Reference

Complete reference for all auto-generated and system nodes in DataFlow.

## Auto-Generated Nodes

Every model decorated with `@db.model` automatically generates 9 nodes:

### 1. {Model}CreateNode

Creates a single record in the database.

**Parameters:**
- All model fields (except auto-generated ones like `id`, `created_at`)
- `tenant_id` (optional): For multi-tenant models
- `return_fields` (optional): List of fields to return (default: all)

**Example:**
```python
workflow.add_node("UserCreateNode", "create_user", {
    "name": "Alice Smith",
    "email": "alice@example.com",
    "active": True,
    "return_fields": ["id", "name", "created_at"]
})
```

**Output:**
```python
{
    "record": {
        "id": 1,
        "name": "Alice Smith",
        "created_at": "2025-01-13T10:00:00Z"
    }
}
```

### 2. {Model}ReadNode

Retrieves a single record by ID.

**Parameters:**
- `id` (required): Record ID to retrieve
- `fields` (optional): List of fields to return
- `include` (optional): List of related models to include
- `tenant_id` (optional): For multi-tenant models

**Example:**
```python
workflow.add_node("UserReadNode", "get_user", {
    "id": 123,
    "fields": ["id", "name", "email", "profile"],
    "include": ["posts", "comments"]
})
```

**Output:**
```python
{
    "record": {
        "id": 123,
        "name": "Alice Smith",
        "email": "alice@example.com",
        "profile": {...},
        "posts": [...],
        "comments": [...]
    }
}
```

### 3. {Model}UpdateNode

Updates a single record.

**Parameters:**
- `id` (required): Record ID to update
- All model fields to update (partial update supported)
- `version` (optional): For optimistic locking
- `tenant_id` (optional): For multi-tenant models
- `return_fields` (optional): Fields to return after update

**Example:**
```python
workflow.add_node("UserUpdateNode", "update_user", {
    "id": 123,
    "name": "Alice Johnson",
    "email": "alice.johnson@example.com",
    "version": 1  # Prevents concurrent updates
})
```

**Output:**
```python
{
    "record": {
        "id": 123,
        "name": "Alice Johnson",
        "email": "alice.johnson@example.com",
        "updated_at": "2025-01-13T11:00:00Z",
        "version": 2
    }
}
```

### 4. {Model}DeleteNode

Deletes a single record.

**Parameters:**
- `id` (required): Record ID to delete
- `soft_delete` (optional): If true, sets deleted_at instead of removing
- `tenant_id` (optional): For multi-tenant models
- `cascade` (optional): Delete related records (default: false)

**Example:**
```python
workflow.add_node("UserDeleteNode", "delete_user", {
    "id": 123,
    "soft_delete": True,
    "cascade": True
})
```

**Output:**
```python
{
    "deleted": True,
    "id": 123,
    "deleted_at": "2025-01-13T12:00:00Z"
}
```

### 5. {Model}ListNode

Queries records with filters, sorting, and pagination.

**Parameters:**
- `filter` (optional): MongoDB-style query filter
- `sort` (optional): List of sort specifications
- `limit` (optional): Maximum records to return
- `offset` (optional): Number of records to skip
- `fields` (optional): Fields to return
- `include` (optional): Related models to include
- `distinct` (optional): Field to get distinct values
- `count_only` (optional): Return only count, not records

**Filter Operators:**
- `$eq`, `$ne`: Equal, not equal
- `$gt`, `$gte`, `$lt`, `$lte`: Comparison
- `$in`, `$nin`: In list, not in list
- `$regex`: Regular expression match
- `$contains`: Array/string contains
- `$exists`: Field exists
- `$and`, `$or`, `$not`: Logical operators

**Example:**
```python
workflow.add_node("UserListNode", "search_users", {
    "filter": {
        "$and": [
            {"active": True},
            {"created_at": {"$gte": "2025-01-01"}},
            {"$or": [
                {"role": "admin"},
                {"permissions": {"$contains": "write"}}
            ]}
        ]
    },
    "sort": [
        {"field": "created_at", "direction": "desc"},
        {"field": "name", "direction": "asc"}
    ],
    "limit": 20,
    "offset": 0,
    "fields": ["id", "name", "email", "role"],
    "include": ["profile"]
})
```

**Output:**
```python
{
    "records": [
        {
            "id": 1,
            "name": "Alice Admin",
            "email": "alice@example.com",
            "role": "admin",
            "profile": {...}
        },
        ...
    ],
    "total": 150,
    "limit": 20,
    "offset": 0
}
```

### 6. {Model}BulkCreateNode

Creates multiple records efficiently.

**Parameters:**
- `data` (required): List of records to create
- `batch_size` (optional): Records per batch (default: 1000)
- `ignore_conflicts` (optional): Skip records that would cause conflicts
- `return_ids` (optional): Return created IDs (default: true)
- `use_copy` (optional): Use COPY for PostgreSQL (faster)
- `tenant_id` (optional): For multi-tenant models

**Example:**
```python
workflow.add_node("UserBulkCreateNode", "import_users", {
    "data": [
        {"name": "User 1", "email": "user1@example.com"},
        {"name": "User 2", "email": "user2@example.com"},
        # ... up to thousands of records
    ],
    "batch_size": 1000,
    "ignore_conflicts": True,
    "return_ids": False  # Faster without returning IDs
})
```

**Output:**
```python
{
    "created": 1000,
    "skipped": 5,
    "records": [...]  # If return_ids is True
}
```

### 7. {Model}BulkUpdateNode

Updates multiple records efficiently.

**Parameters:**
- `filter` (required): Records to update
- `update` (required): Fields to update
- `batch_size` (optional): Records per batch
- `limit` (optional): Maximum records to update

**Update Operators:**
- `$set`: Set field values
- `$inc`: Increment numeric fields
- `$dec`: Decrement numeric fields
- `$multiply`: Multiply numeric fields
- `$append`: Append to array fields
- `$remove`: Remove from array fields

**Example:**
```python
workflow.add_node("ProductBulkUpdateNode", "apply_discount", {
    "filter": {
        "category": "electronics",
        "price": {"$gt": 100}
    },
    "update": {
        "$multiply": {"price": 0.9},  # 10% discount
        "$set": {"on_sale": True},
        "$append": {"tags": "discounted"}
    },
    "batch_size": 500
})
```

**Output:**
```python
{
    "updated": 250,
    "batches": 1
}
```

### 8. {Model}BulkDeleteNode

Deletes multiple records efficiently.

**Parameters:**
- `filter` (required): Records to delete
- `soft_delete` (optional): Use soft delete
- `batch_size` (optional): Records per batch
- `limit` (optional): Maximum records to delete
- `confirmation_required` (optional): Require explicit confirmation

**Example:**
```python
workflow.add_node("UserBulkDeleteNode", "cleanup_inactive", {
    "filter": {
        "active": False,
        "last_login": {"$lt": "2024-01-01"}
    },
    "soft_delete": True,
    "batch_size": 100,
    "confirmation_required": True
})
```

**Output:**
```python
{
    "deleted": 500,
    "batches": 5
}
```

### 9. {Model}BulkUpsertNode

Insert or update multiple records.

**Parameters:**
- `data` (required): List of records
- `conflict_columns` (required): Columns that determine conflicts
- `update_columns` (optional): Columns to update on conflict
- `batch_size` (optional): Records per batch
- `return_ids` (optional): Return all record IDs

**Example:**
```python
workflow.add_node("ProductBulkUpsertNode", "sync_inventory", {
    "data": [
        {"sku": "PROD-001", "name": "Product 1", "stock": 100},
        {"sku": "PROD-002", "name": "Product 2", "stock": 50}
    ],
    "conflict_columns": ["sku"],
    "update_columns": ["stock"],  # Only update stock on conflict
    "batch_size": 1000
})
```

**Output:**
```python
{
    "inserted": 10,
    "updated": 90,
    "records": [...]  # If return_ids is True
}
```

## System Nodes

### AuditLogNode

Query audit logs for models with audit tracking enabled.

**Parameters:**
- `model` (required): Model name
- `record_id` (optional): Specific record ID
- `user_id` (optional): Filter by user
- `action` (optional): Filter by action (create, update, delete)
- `date_range` (optional): Date range filter
- `limit` (optional): Maximum records

**Example:**
```python
workflow.add_node("AuditLogNode", "get_audit_trail", {
    "model": "User",
    "record_id": 123,
    "action": "update",
    "date_range": {
        "start": "2025-01-01",
        "end": "2025-01-31"
    },
    "limit": 100
})
```

### TransactionNode

Execute multiple operations in a transaction.

**Parameters:**
- `operations` (required): List of node configurations
- `isolation_level` (optional): Transaction isolation level
- `timeout` (optional): Transaction timeout in seconds

**Example:**
```python
workflow.add_node("TransactionNode", "atomic_transfer", {
    "operations": [
        {
            "node": "AccountUpdateNode",
            "id": "debit",
            "params": {"id": 1, "balance": {"$dec": 100}}
        },
        {
            "node": "AccountUpdateNode",
            "id": "credit",
            "params": {"id": 2, "balance": {"$inc": 100}}
        }
    ],
    "isolation_level": "READ_COMMITTED",
    "timeout": 30
})
```

### MigrationNode

Execute database migrations.

**Parameters:**
- `action` (required): "migrate", "rollback", "status"
- `target` (optional): Target migration version
- `dry_run` (optional): Preview without applying

**Example:**
```python
workflow.add_node("MigrationNode", "upgrade_db", {
    "action": "migrate",
    "target": "latest",
    "dry_run": False
})
```

## Performance Nodes

### CacheNode

Cache query results.

**Parameters:**
- `key` (required): Cache key
- `node` (required): Node to cache results from
- `ttl` (optional): Time to live in seconds
- `invalidate_on` (optional): Events that invalidate cache

**Example:**
```python
workflow.add_node("CacheNode", "cached_users", {
    "key": "active_users",
    "node": {
        "type": "UserListNode",
        "params": {"filter": {"active": True}}
    },
    "ttl": 300,  # 5 minutes
    "invalidate_on": ["user_create", "user_update", "user_delete"]
})
```

### OptimizedQueryNode

Execute optimized cross-table queries.

**Parameters:**
- `query` (required): Query specification
- `optimize` (optional): Enable query optimization
- `explain` (optional): Return query plan

**Example:**
```python
workflow.add_node("OptimizedQueryNode", "user_posts_comments", {
    "query": {
        "from": "users",
        "join": [
            {"table": "posts", "on": "users.id = posts.user_id"},
            {"table": "comments", "on": "posts.id = comments.post_id"}
        ],
        "where": {"users.active": True},
        "select": ["users.name", "COUNT(posts.id)", "COUNT(comments.id)"],
        "group_by": ["users.id", "users.name"]
    },
    "optimize": True,
    "explain": True
})
```

## Error Handling

All nodes follow consistent error handling:

```python
{
    "error": "Error message",
    "error_type": "NodeExecutionError",
    "details": {
        "node": "UserCreateNode",
        "params": {...},
        "validation_errors": [...]
    },
    "failed": True
}
```

## Best Practices

1. **Use Bulk Operations**: For >10 records, always use bulk nodes
2. **Specify Fields**: Only request fields you need
3. **Add Indexes**: For frequently filtered fields
4. **Use Transactions**: For related operations
5. **Enable Caching**: For read-heavy queries
6. **Monitor Performance**: Use explain for complex queries

---

**Next**: See [Configuration Reference](configuration.md) for DataFlow configuration options.
