---
name: dataflow-aggregation
description: "SQL aggregation queries with GROUP BY for DataFlow. Use when COUNT GROUP BY, SUM GROUP BY, AVG, MIN, MAX, aggregation queries, dashboard analytics, reporting queries, count_by, sum_by, aggregate, AggregateOp, AggregateSpec, or SQL GROUP BY."
---

# DataFlow SQL Aggregation Queries

High-level SQL aggregation functions that generate parameterized GROUP BY queries with strict identifier validation across PostgreSQL, SQLite, and MongoDB backends.

> **Skill Metadata**
> Category: `dataflow/queries`
> Priority: `P4`
> Source Module: `dataflow.query`
> Related Skills: [`dataflow-queries`](#), [`dataflow-count-node`](#), [`dataflow-performance`](#)
> Related Subagents: `dataflow-specialist` (complex analytics, cross-database optimization)

## Quick Reference

- **Module**: `from dataflow.query import count_by, sum_by, aggregate, AggregateOp, AggregateSpec`
- **Operations**: COUNT, SUM, AVG, MIN, MAX (via `AggregateOp` enum)
- **All functions are `async`** -- they execute queries directly on the connection
- **Security**: All identifiers validated with `^[a-zA-Z_][a-zA-Z0-9_]*$` regex; values always parameterized with `?` placeholders
- **NULL handling**: `{"status": None}` generates `IS NULL`; `{"status__ne": None}` generates `IS NOT NULL`
- **Soft-delete awareness**: Add `{"deleted_at": None}` to filters to exclude soft-deleted rows

## API Reference

### AggregateOp Enum

Fixed set of SQL aggregate operations. Never accept raw user input as a function name -- always use this enum.

```python
from dataflow.query import AggregateOp

AggregateOp.COUNT  # COUNT(*)  or COUNT(column)
AggregateOp.SUM    # SUM(column)
AggregateOp.AVG    # AVG(column)
AggregateOp.MIN    # MIN(column)
AggregateOp.MAX    # MAX(column)
```

### AggregateSpec Dataclass

Specification for a single aggregate expression. Validates all identifiers on construction.

```python
from dataflow.query import AggregateSpec, AggregateOp

# COUNT(*) -- wildcard only valid with COUNT
spec = AggregateSpec(op=AggregateOp.COUNT, field="*")
# -> effective_alias() returns "count_all"

# SUM with auto-generated alias
spec = AggregateSpec(op=AggregateOp.SUM, field="amount")
# -> effective_alias() returns "sum_amount"

# AVG with explicit alias
spec = AggregateSpec(op=AggregateOp.AVG, field="price", alias="avg_price")
# -> effective_alias() returns "avg_price"
```

**Validation rules:**

- `field="*"` is only valid with `AggregateOp.COUNT` (raises `ValueError` otherwise)
- `field` and `alias` must match `^[a-zA-Z_][a-zA-Z0-9_]*$` (raises `ValueError` on invalid characters)
- `op` must be an `AggregateOp` enum value (raises `TypeError` otherwise)

**Serialization:**

```python
# to_dict / from_dict for persistence and transport
d = spec.to_dict()   # {"op": "sum", "field": "amount", "alias": None}
spec2 = AggregateSpec.from_dict(d)
```

### AggregationResult Dataclass

Result container returned by all aggregation functions.

```python
from dataflow.query import AggregationResult

# Fields:
#   data: List[Dict[str, Any]]  -- row dictionaries from query result
#   query: str                  -- the SQL query that was executed
#   params: List[Any]           -- parameter values used in the query
#   row_count: int              -- number of result rows
```

### count_by()

Count rows grouped by a column. Generates `SELECT group_by, COUNT(*) AS count FROM table GROUP BY group_by`.

```python
async def count_by(
    connection: Any,
    model_or_table: Any,       # string table name or class with __tablename__
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult
```

**Example:**

```python
from dataflow.query import count_by

# Count orders by status
result = await count_by(conn, "orders", "status")
# SQL: SELECT status, COUNT(*) AS count FROM orders GROUP BY status
for row in result.data:
    print(f"{row['status']}: {row['count']}")

# Count with filter -- only paid orders by region
result = await count_by(conn, "orders", "region", {"status": "paid"})
# SQL: SELECT region, COUNT(*) AS count FROM orders WHERE status = ? GROUP BY region

# Using a model class instead of table name string
result = await count_by(conn, Order, "status")
# Resolves table name from Order.__tablename__
```

### sum_by()

Sum a numeric column grouped by another column. Generates `SELECT group_by, SUM(sum_field) AS sum_{sum_field} FROM table GROUP BY group_by`.

```python
async def sum_by(
    connection: Any,
    model_or_table: Any,       # string table name or class with __tablename__
    sum_field: str,
    group_by: str,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult
```

**Example:**

```python
from dataflow.query import sum_by

# Sum order amounts by category
result = await sum_by(conn, "orders", "amount", "category")
# SQL: SELECT category, SUM(amount) AS sum_amount FROM orders GROUP BY category
for row in result.data:
    print(f"{row['category']}: ${row['sum_amount']:.2f}")

# Sum with filter -- only completed orders
result = await sum_by(conn, "orders", "amount", "category", {"status": "completed"})
# SQL: SELECT category, SUM(amount) AS sum_amount FROM orders WHERE status = ? GROUP BY category
```

### aggregate()

Generic multi-aggregate query. Combines multiple aggregate expressions in a single SELECT with optional GROUP BY and WHERE.

```python
async def aggregate(
    connection: Any,
    model_or_table: Any,       # string table name or class with __tablename__
    specs: List[AggregateSpec],
    group_by: Optional[str] = None,
    filter: Optional[Dict[str, Any]] = None,
) -> AggregationResult
```

**Example:**

```python
from dataflow.query import aggregate, AggregateOp, AggregateSpec

# Multi-aggregate: count, sum, and average in one query
specs = [
    AggregateSpec(op=AggregateOp.COUNT, field="*"),
    AggregateSpec(op=AggregateOp.SUM, field="amount"),
    AggregateSpec(op=AggregateOp.AVG, field="amount", alias="avg_amount"),
]
result = await aggregate(conn, "orders", specs, group_by="category")
# SQL: SELECT category, COUNT(*) AS count_all, SUM(amount) AS sum_amount,
#       AVG(amount) AS avg_amount FROM orders GROUP BY category

# Without GROUP BY -- aggregate over entire table
specs = [
    AggregateSpec(op=AggregateOp.MIN, field="price", alias="min_price"),
    AggregateSpec(op=AggregateOp.MAX, field="price", alias="max_price"),
    AggregateSpec(op=AggregateOp.COUNT, field="*", alias="total"),
]
result = await aggregate(conn, "products", specs)
# SQL: SELECT MIN(price) AS min_price, MAX(price) AS max_price,
#       COUNT(*) AS total FROM products

# With filter
result = await aggregate(
    conn, "orders", specs,
    group_by="category",
    filter={"status": "paid", "amount__gt": 0}
)
# SQL: SELECT category, ... FROM orders WHERE status = ? AND amount > ? GROUP BY category
```

## Filter Operators

Filters are passed as `{column: value}` dicts. Operator suffixes on column names control comparison:

| Suffix  | SQL Generated | Example Key     | Example Value |
| ------- | ------------- | --------------- | ------------- |
| (none)  | `column = ?`  | `"status"`      | `"active"`    |
| `__gt`  | `column > ?`  | `"amount__gt"`  | `100`         |
| `__gte` | `column >= ?` | `"amount__gte"` | `100`         |
| `__lt`  | `column < ?`  | `"amount__lt"`  | `1000`        |
| `__lte` | `column <= ?` | `"amount__lte"` | `1000`        |
| `__ne`  | `column != ?` | `"status__ne"`  | `"cancelled"` |

**NULL handling:**

```python
# IS NULL -- use None value with = operator (no suffix)
filter={"deleted_at": None}
# SQL: WHERE deleted_at IS NULL

# IS NOT NULL -- use None value with __ne suffix
filter={"deleted_at__ne": None}
# SQL: WHERE deleted_at IS NOT NULL

# Cannot use >, <, >=, <= with None (raises ValueError)
```

**Combining filters (implicit AND):**

```python
filter={"status": "paid", "amount__gt": 100, "deleted_at": None}
# SQL: WHERE status = ? AND amount > ? AND deleted_at IS NULL
```

## Error Types

```python
from dataflow.query import AggregationError, AggregationFieldError

# AggregationError -- base error for all aggregation failures
# Has .details: Dict[str, Any] for structured error context
try:
    result = await aggregate(conn, "orders", [])  # empty specs
except ValueError:
    pass  # "specs must contain at least one AggregateSpec"

# AggregationFieldError -- field not found in model/table
# Has .field_name: str and .table_name: str attributes
# Inherits from AggregationError
```

## Security

**Identifier validation:** Every table name, column name, group*by column, filter column, and alias is validated against `^[a-zA-Z*][a-zA-Z0-9_]\*$` before interpolation into SQL. This prevents all injection vectors including semicolons, quotes, comments, and path traversal.

**Parameterized values:** All filter values are passed as `?` parameters -- never interpolated into the SQL string. ConnectionManager translates `?` to dialect-specific format (`$1` for PostgreSQL, `%s` for MySQL) automatically.

**Enum-restricted operations:** The `AggregateOp` enum restricts aggregate functions to five known-safe operations. Raw user strings are never accepted as SQL function names.

```python
# These all raise ValueError:
validate_identifier("users; DROP TABLE--")  # semicolon + comment
validate_identifier("../../../etc/passwd")  # path traversal
validate_identifier("col name")            # space
validate_identifier("")                     # empty

# These are valid:
validate_identifier("users")               # simple name
validate_identifier("order_items")         # underscores
validate_identifier("_private")            # leading underscore
validate_identifier("Column1")             # mixed case + digits
```

## Common Patterns

### Dashboard Analytics

```python
from dataflow.query import count_by, sum_by, aggregate, AggregateOp, AggregateSpec

# Revenue dashboard -- orders by status with totals
result = await aggregate(
    conn, "orders",
    specs=[
        AggregateSpec(op=AggregateOp.COUNT, field="*", alias="order_count"),
        AggregateSpec(op=AggregateOp.SUM, field="amount", alias="total_revenue"),
        AggregateSpec(op=AggregateOp.AVG, field="amount", alias="avg_order_value"),
    ],
    group_by="status",
    filter={"deleted_at": None}  # Soft-delete awareness
)
for row in result.data:
    print(f"{row['status']}: {row['order_count']} orders, ${row['total_revenue']:.2f} total")
```

### Soft-Delete Aware Queries

```python
# Always add deleted_at IS NULL to exclude soft-deleted rows
result = await count_by(conn, "users", "role", {"deleted_at": None})
# SQL: SELECT role, COUNT(*) AS count FROM users WHERE deleted_at IS NULL GROUP BY role
```

### Model Class Resolution

```python
# Pass a model class instead of a table name string
@db.model
class Order:
    id: str
    amount: float
    category: str
    status: str

# Uses Order.__tablename__ to resolve the table name
result = await sum_by(conn, Order, "amount", "category")
```

### Price Range Analysis

```python
specs = [
    AggregateSpec(op=AggregateOp.MIN, field="price", alias="min_price"),
    AggregateSpec(op=AggregateOp.MAX, field="price", alias="max_price"),
    AggregateSpec(op=AggregateOp.AVG, field="price", alias="avg_price"),
    AggregateSpec(op=AggregateOp.COUNT, field="*", alias="product_count"),
]
result = await aggregate(conn, "products", specs, group_by="category")
```

## CountNode vs count_by

| Feature       | CountNode                    | count_by()                              |
| ------------- | ---------------------------- | --------------------------------------- |
| Query type    | `SELECT COUNT(*) FROM table` | `SELECT col, COUNT(*) ... GROUP BY col` |
| GROUP BY      | No                           | Yes (required)                          |
| Use case      | Total count, existence check | Count distribution by category          |
| Interface     | Workflow node (add_node)     | Async function (await)                  |
| Filter syntax | MongoDB-style (`$gt`, `$in`) | Suffix-style (`__gt`, `__ne`)           |
| Result        | `{"count": N}`               | `AggregationResult` with `.data` rows   |

Use **CountNode** for simple total counts in workflows. Use **count_by** for grouped counts and analytics queries that need GROUP BY.

## Troubleshooting

| Issue                                                                                 | Cause                                    | Solution                                                     |
| ------------------------------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------ |
| `ValueError: Invalid SQL identifier`                                                  | Column/table name has special chars      | Use only `[a-zA-Z_][a-zA-Z0-9_]*` names                      |
| `ValueError: Wildcard '*' is only valid with COUNT`                                   | Used `field="*"` with SUM/AVG/MIN/MAX    | Use a column name for non-COUNT operations                   |
| `TypeError: specs must be a list`                                                     | Passed single AggregateSpec without list | Wrap in a list: `[spec]`                                     |
| `ValueError: specs must contain at least one AggregateSpec`                           | Empty specs list                         | Add at least one AggregateSpec                               |
| `TypeError: model_or_table must be a string table name or a class with __tablename__` | Passed model instance instead of class   | Pass the class itself, not an instance                       |
| `ValueError: Cannot use operator '>' with NULL value`                                 | Used `__gt` suffix with `None`           | Only `=` (IS NULL) and `__ne` (IS NOT NULL) work with `None` |

## When to Escalate to Subagent

Use `dataflow-specialist` subagent when:

- Designing complex multi-table aggregations (joins not supported in this module)
- Optimizing slow aggregation queries on large datasets
- Building HAVING clause queries (not yet supported)
- Implementing time-series rollups or sliding window aggregations

## Related Skills

- **[dataflow-queries](dataflow-queries.md)** -- MongoDB-style query filters (ListNode)
- **[dataflow-count-node](dataflow-count-node.md)** -- Simple COUNT(\*) without GROUP BY
- **[dataflow-performance](dataflow-performance.md)** -- Query performance optimization
- **[dataflow-dialects](dataflow-dialects.md)** -- Cross-database SQL dialect handling

<!-- Trigger Keywords: DataFlow aggregation, count_by, sum_by, aggregate, GROUP BY, AggregateOp, AggregateSpec, COUNT GROUP BY, SUM GROUP BY, AVG, MIN, MAX, dashboard analytics, reporting queries, SQL aggregation, aggregation queries -->
