# DataFlow QueryBuilder

MongoDB-style query builder for DataFlow that generates optimized SQL for PostgreSQL, MySQL, and SQLite.

## Overview

The QueryBuilder provides an intuitive MongoDB-style interface for building complex SQL queries across different databases. It's automatically available on all DataFlow models through the `query_builder()` class method.

## Features

- **MongoDB-style operators**: `$eq`, `$gt`, `$in`, `$regex`, etc.
- **Cross-database support**: PostgreSQL, MySQL, SQLite
- **Type-safe query building**: Parameterized queries prevent SQL injection
- **Fluent interface**: Chain methods for readable query construction
- **Automatic integration**: Works seamlessly with DataFlow nodes

## Basic Usage

```python
from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow

db = DataFlow()

@db.model
class User:
    name: str
    email: str
    age: int
    status: str = "active"

# Get QueryBuilder instance
builder = User.query_builder()

# Build a query
builder.where("age", "$gte", 18)
builder.where("status", "$eq", "active")
builder.order_by("created_at", "DESC")
builder.limit(10)

# Generate SQL
sql, params = builder.build_select()
```

## MongoDB Operators

### Comparison Operators

| Operator | SQL Equivalent | Example |
|----------|----------------|---------|
| `$eq` | `=` | `where("status", "$eq", "active")` |
| `$ne` | `!=` | `where("status", "$ne", "deleted")` |
| `$gt` | `>` | `where("age", "$gt", 18)` |
| `$gte` | `>=` | `where("age", "$gte", 18)` |
| `$lt` | `<` | `where("price", "$lt", 100)` |
| `$lte` | `<=` | `where("price", "$lte", 100)` |

### List Operators

| Operator | SQL Equivalent | Example |
|----------|----------------|---------|
| `$in` | `IN` | `where("status", "$in", ["active", "premium"])` |
| `$nin` | `NOT IN` | `where("role", "$nin", ["admin", "root"])` |

### Pattern Matching

| Operator | SQL Equivalent | Example |
|----------|----------------|---------|
| `$like` | `LIKE` | `where("email", "$like", "%@example.com")` |
| `$regex` | `~` (PG), `REGEXP` (MySQL) | `where("name", "$regex", "^[A-Z]")` |

### Existence Operators

| Operator | SQL Equivalent | Example |
|----------|----------------|---------|
| `$exists` | `IS NOT NULL` | `where("email", "$exists", None)` |
| `$null` | `IS NULL` | `where("deleted_at", "$null", None)` |

## Advanced Usage

### Complex Queries

```python
builder = Order.query_builder()

# Multiple conditions
builder.where("status", "$in", ["pending", "processing"])
builder.where("total", "$gte", 100.0)
builder.where("created_at", "$gte", "2025-01-01")

# Ordering and pagination
builder.order_by("created_at", "DESC")
builder.order_by("total", "DESC")
builder.limit(50).offset(100)

sql, params = builder.build_select()
```

### Using with DataFlow Nodes

```python
workflow = WorkflowBuilder()

# ListNode automatically uses QueryBuilder for filtering
workflow.add_node("OrderListNode", "search", {
    "filter": {
        "status": {"$in": ["pending", "processing"]},
        "total": {"$gte": 100.0},
        "customer": {
            "email": {"$like": "%@enterprise.com"}
        }
    },
    "order_by": [{"created_at": -1}],
    "limit": 100
})
```

### Joins and Aggregation

```python
builder = OrderItem.query_builder()

# Select specific fields
builder.select([
    "order_items.*",
    "orders.status",
    "products.name AS product_name"
])

# Add joins
builder.join("orders", "orders.id = order_items.order_id")
builder.join("products", "products.id = order_items.product_id", "LEFT")

# Filter joined data
builder.where("orders.status", "$eq", "completed")
builder.where("order_items.quantity", "$gte", 5)

# Group and aggregate
builder.group_by(["product_id", "orders.status"])
builder.having("SUM(quantity) > 100")

sql, params = builder.build_select()
```

### CRUD Operations

```python
# INSERT
data = {"name": "Alice", "email": "alice@example.com"}
sql, params = builder.build_insert(data)

# UPDATE
builder.where("id", "$eq", 123)
updates = {"status": "premium", "updated_at": "NOW()"}
sql, params = builder.build_update(updates)

# DELETE
builder.where("status", "$eq", "deleted")
builder.where("deleted_at", "$lt", "2024-01-01")
sql, params = builder.build_delete()
```

## Database-Specific Features

### PostgreSQL

- Full regex support with `~` operator
- RETURNING clause for INSERT/UPDATE/DELETE
- Array and JSONB operators (implemented)

```python
# PostgreSQL-specific regex
builder.where("email", "$regex", "^[a-z]+@(gmail|yahoo)\.com$")
```

### MySQL

- REGEXP support for pattern matching
- ON DUPLICATE KEY UPDATE for upserts
- Full-text search operators (implemented)

```python
# MySQL will use REGEXP
builder.where("description", "$regex", "DataFlow|QueryBuilder")
```

### SQLite

- Regex converted to LIKE patterns
- INSERT OR REPLACE for upserts
- Limited pattern matching

```python
# SQLite converts regex to LIKE
builder.where("name", "$regex", ".*admin.*")  # Becomes LIKE '%admin%'
```

## Performance Considerations

1. **Parameterized Queries**: All values are parameterized, preventing SQL injection
2. **Index Usage**: Use `where()` on indexed columns for best performance
3. **Limit Results**: Always use `limit()` for large datasets
4. **Select Fields**: Use `select()` to fetch only needed columns

## Integration with DataFlow Features

### Multi-Tenant Queries

When multi-tenancy is enabled, QueryBuilder automatically adds tenant filters:

```python
db = DataFlow(multi_tenant=True)

# Queries automatically filtered by tenant_id
builder = User.query_builder()
builder.where("status", "$eq", "active")
# Generated SQL includes: AND tenant_id = $n
```

### Audit Trail

QueryBuilder integrates with DataFlow's audit system:

```python
# Audit queries
builder = UserAudit.query_builder()
builder.where("action", "$in", ["create", "update"])
builder.where("timestamp", "$gte", "2025-01-01")
```

### Caching (Coming Soon)

```python
# Future: Cached queries
result = User.cached_query()
    .where("status", "$eq", "active")
    .cache_key("active_users")
    .ttl(300)
    .execute()
```

## Common Patterns

### Search with Pagination

```python
def search_users(query, page=1, per_page=20):
    builder = User.query_builder()

    # Search conditions
    builder.where("name", "$like", f"%{query}%")
    builder.where("status", "$eq", "active")

    # Pagination
    offset = (page - 1) * per_page
    builder.limit(per_page).offset(offset)

    return builder.build_select()
```

### Dynamic Filter Building

```python
def build_dynamic_filter(filters):
    builder = Product.query_builder()

    for field, condition in filters.items():
        if isinstance(condition, dict):
            for op, value in condition.items():
                builder.where(field, op, value)
        else:
            builder.where(field, "$eq", condition)

    return builder
```

### Report Generation

```python
def monthly_sales_report(year, month):
    builder = Order.query_builder()

    builder.select([
        "DATE(created_at) as order_date",
        "COUNT(*) as order_count",
        "SUM(total) as revenue"
    ])

    builder.where("status", "$eq", "completed")
    builder.where("created_at", "$gte", f"{year}-{month:02d}-01")
    builder.where("created_at", "$lt", f"{year}-{month+1:02d}-01")

    builder.group_by("DATE(created_at)")
    builder.order_by("order_date", "ASC")

    return builder.build_select()
```

## Error Handling

```python
try:
    builder = User.query_builder()
    builder.where("age", "$invalid", 18)  # Invalid operator
except ValueError as e:
    print(f"Query error: {e}")

# Invalid parameter types
try:
    builder.where("roles", "$in", "admin")  # Should be a list
except ValueError as e:
    print(f"Parameter error: {e}")
```

## Best Practices

1. **Reset Between Queries**: Use `builder.reset()` when building multiple queries
2. **Use Appropriate Operators**: Choose the right MongoDB operator for clarity
3. **Parameterize User Input**: Never concatenate user input into queries
4. **Limit Large Results**: Always paginate when dealing with large datasets
5. **Test Cross-Database**: Verify queries work across your target databases

## Migration from Raw SQL

### Before (Raw SQL)

```python
# Vulnerable to SQL injection
query = f"SELECT * FROM users WHERE age > {min_age} AND status = '{status}'"

# Database-specific
if db_type == "postgresql":
    query = "SELECT * FROM users WHERE email ~ '^admin'"
elif db_type == "mysql":
    query = "SELECT * FROM users WHERE email REGEXP '^admin'"
```

### After (QueryBuilder)

```python
# Safe and cross-database
builder = User.query_builder()
builder.where("age", "$gt", min_age)
builder.where("status", "$eq", status)
builder.where("email", "$regex", "^admin")

sql, params = builder.build_select()
```

## Roadmap

- [ ] Aggregation pipeline support
- [ ] Geospatial operators
- [ ] Full-text search operators
- [ ] JSON/JSONB operators
- [ ] Subquery support
- [ ] Query result caching
- [ ] Query plan analysis

## See Also

- [DataFlow Models](../models.md)
- [Bulk Operations](../bulk-operations.md)
- [Multi-Tenancy](../enterprise/multi-tenant.md)
- [Performance Optimization](../enterprise/performance.md)
