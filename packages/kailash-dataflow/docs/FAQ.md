# DataFlow FAQ

## General Questions

### Q1: What is DataFlow?

**A:** DataFlow is a zero-config database framework built on Kailash Core SDK. It automatically generates 11 workflow nodes per model (CREATE, READ, UPDATE, DELETE, LIST, UPSERT, COUNT, BULK_CREATE, BULK_UPDATE, BULK_DELETE, BULK_UPSERT). DataFlow is NOT an ORM - it's workflow-based with enterprise features like multi-tenancy and schema caching.

**Reference**: [README.md](../README.md)

---

### Q2: Is DataFlow an ORM?

**A:** No. DataFlow is a workflow-based database framework. Unlike ORMs (SQLAlchemy, Django ORM) that use model methods and QuerySets, DataFlow generates workflow nodes for database operations. Operations are executed via `runtime.execute(workflow.build())`.

**Reference**: [Migration from SQLAlchemy](guides/from-sqlalchemy.md), [Migration from Django ORM](guides/from-django-orm.md)

---

### Q3: Why do I need to use `id` as the primary key?

**A:** DataFlow requires all models to use `id` as the primary key field name (not `user_id`, `model_id`, etc.). This convention simplifies node generation and parameter passing across workflows. Using other names causes VAL-001 validation errors.

**Fix**:

```python
# ✅ CORRECT
@db.model
class User:
    id: str  # MUST be named 'id'
    name: str
```

**Reference**: [Primary Keys Guide](guides/primary-keys.md)

---

### Q4: Why can't I include `created_at` or `updated_at` fields?

**A:** DataFlow automatically manages `created_at` and `updated_at` timestamps at the database level using triggers. Manually including them causes VAL-005 validation errors. These fields are added automatically and updated on every modification.

**Fix**:

```python
# ✅ CORRECT
@db.model
class User:
    id: str
    name: str
    # Omit created_at, updated_at - auto-managed
```

**Reference**: [Auto-Managed Fields Guide](guides/auto-managed-fields.md)

---

### Q5: Can I use nested objects in models?

**A:** No. DataFlow only supports primitive types (str, int, float, bool, datetime) and simple collections (list, dict). For relationships, use foreign key fields (e.g., `organization_id: str`) instead of nested objects.

**Fix**:

```python
# ✅ CORRECT
@db.model
class User:
    id: str
    name: str
    organization_id: str  # Foreign key reference
```

**Reference**: [Flat Fields Guide](guides/flat-fields.md)

---

## Model Definition Questions

### Q6: What field types does DataFlow support?

**A:** DataFlow supports:

- `str` - String/VARCHAR
- `int` - Integer
- `float` - Float/Decimal
- `bool` - Boolean
- `datetime` - Datetime/Timestamp
- `dict` - JSON object
- `list` - JSON array

**Not supported**: Custom classes, Enums (use str), nested objects (use foreign keys).

**Reference**: [Flat Fields Guide](guides/flat-fields.md)

---

### Q7: How do I model relationships (one-to-many, many-to-many)?

**A:**

- **One-to-many**: Use foreign key field
- **Many-to-many**: Use junction table with two foreign keys

**Example**:

```python
# One-to-many
@db.model
class Organization:
    id: str
    name: str

@db.model
class User:
    id: str
    name: str
    organization_id: str  # Foreign key

# Many-to-many
@db.model
class UserRole:  # Junction table
    id: str
    user_id: str
    role_id: str
```

**Reference**: [Flat Fields Guide](guides/flat-fields.md)

---

### Q8: Can I use UUIDs as primary keys?

**A:** Yes! DataFlow preserves string IDs exactly, including UUIDs.

**Example**:

```python
import uuid

@db.model
class User:
    id: str  # Use str type for UUIDs

workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # Generate UUID
    "name": "Alice"
})
```

**Reference**: [Primary Keys Guide](guides/primary-keys.md)

---

## Workflow Questions

### Q9: Why does my workflow fail with "missing .build()"?

**A:** You must call `.build()` on WorkflowBuilder before passing to runtime.execute().

**Fix**:

```python
# ✅ CORRECT
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {...})
runtime.execute(workflow.build())  # .build() required
```

**Reference**: [Error Cheat Sheet](guides/cheat-sheet-errors.md)

---

### Q10: What's the difference between CreateNode and UpdateNode parameters?

**A:**

- **CreateNode**: Flat fields (all fields including `id`)
- **UpdateNode**: `filter` + `fields` structure

**Example**:

```python
# CREATE - Flat fields
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com"
})

# UPDATE - filter/fields structure
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})
```

**Reference**: [Common Patterns](guides/common-patterns.md)

---

### Q11: How do I use pagination with ListNode?

**A:** Use `limit` and `offset` parameters.

**Example**:

```python
# Get page 2 (records 21-40)
page = 2
per_page = 20
offset = (page - 1) * per_page

workflow.add_node("UserListNode", "list", {
    "filters": {},
    "limit": per_page,
    "offset": offset,
    "order_by": "-created_at"
})
```

**Reference**: [Common Patterns](guides/common-patterns.md)

---

### Q12: How do I filter records?

**A:** Use `filters` parameter in ListNode with Django-style filter operators.

**Example**:

```python
workflow.add_node("UserListNode", "list", {
    "filters": {
        "is_active": True,
        "age__gte": 18,              # Greater than or equal
        "name__icontains": "alice",  # Case-insensitive contains
        "organization_id__isnull": False  # NOT NULL
    }
})
```

**Reference**: [Common Patterns](guides/common-patterns.md)

---

## Performance Questions

### Q13: Why is my first workflow slow?

**A:** The first operation incurs schema migration overhead (~1500ms). Subsequent operations use the schema cache and are 99% faster (~1ms).

**Solution**: Enable schema cache (default in v0.7.3+):

```python
db = DataFlow("postgresql://...", schema_cache_enabled=True)
```

**Reference**: [CLAUDE.md - Schema Cache](../CLAUDE.md)

---

### Q14: How do I improve bulk operation performance?

**A:** Use BulkCreateNode, BulkUpdateNode, or BulkDeleteNode instead of individual operations.

**Example**:

```python
# ✅ FAST - Bulk operation (1 query)
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "records": [
        {"id": f"user-{i}", "name": f"User {i}"}
        for i in range(100)
    ]
})

# ❌ SLOW - Individual operations (100 queries)
for i in range(100):
    workflow.add_node("UserCreateNode", f"create_{i}", {
        "id": f"user-{i}",
        "name": f"User {i}"
    })
```

**Performance**: 10-100x faster for bulk operations.

**Reference**: [Common Patterns](guides/common-patterns.md)

---

### Q15: Should I use SQLite or PostgreSQL?

**A:**

- **SQLite**: Development, testing, mobile apps (<10k records)
- **PostgreSQL**: Production, concurrent users, complex queries (10k+ records)

**Recommendation**: Use SQLite for development (`:memory:` for tests), PostgreSQL for production.

**Reference**: [CLAUDE.md - Database Support](../CLAUDE.md)

---

## Error Questions

### Q16: Why do I get "ValidationError: Field 'id' is required"?

**A:** CreateNode requires `id` field. DataFlow doesn't auto-generate IDs - you must provide them.

**Fix**:

```python
import uuid

workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # Generate ID
    "name": "Alice"
})
```

**Reference**: [Error Cheat Sheet](guides/cheat-sheet-errors.md)

---

### Q17: Why do I get "Table already exists" error?

**A:** Running migration when table already exists.

**Fix**:

```python
# Use existing_schema_mode for existing tables
db = DataFlow(url, existing_schema_mode=True)
```

**Reference**: [Error Cheat Sheet](guides/cheat-sheet-errors.md)

---

### Q18: Why does my ListNode return empty results?

**A:** Common causes:

1. Filter field name typo
2. No matching records
3. Wrong filter syntax

**Fix**:

```python
# Check exact field names
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True}  # Exact match
})

# For NULL checks, use __isnull operator
workflow.add_node("UserListNode", "list", {
    "filters": {"organization_id__isnull": False}
})
```

**Reference**: [Error Cheat Sheet](guides/cheat-sheet-errors.md)

---

## Migration Questions

### Q19: How do I migrate from SQLAlchemy to DataFlow?

**A:** Follow these steps:

1. Convert Column types to type hints
2. Replace `id = Column(Integer, primary_key=True)` with `id: str`
3. Remove `relationship()` objects - use foreign key fields
4. Replace `Model.query.filter()` with ListNode + filters
5. Remove `auto_now`/`auto_now_add` - DataFlow auto-manages timestamps

**Reference**: [Migration from SQLAlchemy](guides/from-sqlalchemy.md)

---

### Q20: How do I migrate from Django ORM to DataFlow?

**A:** Follow these steps:

1. Convert Field types to type hints (CharField → str, IntegerField → int)
2. Explicitly define `id` field (Django auto-creates, DataFlow requires explicit)
3. Replace ForeignKey objects with foreign key fields (e.g., `organization_id: str`)
4. Replace QuerySets with workflow nodes (Model.objects.filter() → ListNode)
5. Omit `created_at`/`updated_at` - DataFlow auto-manages

**Reference**: [Migration from Django ORM](guides/from-django-orm.md)

---

## Advanced Questions

### Q21: Can I use DataFlow with existing databases?

**A:** Yes! Use `existing_schema_mode=True` to skip table creation.

**Example**:

```python
# Connect to existing database
db = DataFlow("postgresql://localhost/existing_db", existing_schema_mode=True)

# Define models matching existing tables
@db.model
class User:
    id: str
    name: str
    email: str
```

**Reference**: [Primary Keys Guide](guides/primary-keys.md)

---

### Q22: How do I use UpsertNode?

**A:** UpsertNode inserts if record doesn't exist, updates if it does (atomic operation).

**Example**:

```python
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"email": "alice@example.com"},
    "conflict_on": ["email"],  # Unique field for conflict detection
    "update": {"name": "Alice Updated"},
    "create": {
        "id": str(uuid.uuid4()),
        "email": "alice@example.com",
        "name": "Alice"
    }
})
```

**Reference**: [CLAUDE.md - UpsertNode](../CLAUDE.md)

---

### Q23: How do I debug workflows?

**A:** Use Inspector API to trace parameter flows and validate connections.

**Example**:

```python
from dataflow.platform.inspector import Inspector

inspector = Inspector(db)

# Validate connections
is_valid, errors = inspector.validate_connections()
if not is_valid:
    for error in errors:
        print(f"Error: {error}")

# Trace parameter source
source = inspector.find_parameter_source("read", "id")
print(f"Parameter 'id' comes from: {source}")
```

**Reference**: [Inspector API](api/inspector.md)

---

### Q24: How do I handle multi-tenancy?

**A:** Add `organization_id` foreign key to all models and filter by it in ListNode.

**Example**:

```python
@db.model
class User:
    id: str
    organization_id: str  # Tenant identifier
    name: str

# Query users for specific organization
workflow.add_node("UserListNode", "list", {
    "filters": {"organization_id": "org-123"}
})
```

**Reference**: [Common Patterns](guides/common-patterns.md)

---

### Q25: Should I use LocalRuntime or AsyncLocalRuntime?

**A:**

- **LocalRuntime**: CLI scripts, synchronous contexts
- **AsyncLocalRuntime**: Docker/FastAPI, asynchronous contexts (10-100x faster)

**Example**:

```python
# Docker/FastAPI (async)
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# CLI/scripts (sync)
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**Reference**: [CLAUDE.md - Runtime Pattern](../CLAUDE.md)

---

## Related Guides

- [Error Cheat Sheet](guides/cheat-sheet-errors.md) - Quick error reference
- [Common Patterns](guides/common-patterns.md) - Best practices
- [Primary Keys](guides/primary-keys.md) - The `id` requirement
- [Auto-Managed Fields](guides/auto-managed-fields.md) - Timestamp handling
- [Flat Fields](guides/flat-fields.md) - No nested objects
- [Migration from SQLAlchemy](guides/from-sqlalchemy.md) - SQLAlchemy conversion
- [Migration from Django ORM](guides/from-django-orm.md) - Django conversion
- [ErrorEnhancer API](api/error-enhancer.md) - Error enhancement utilities
- [Inspector API](api/inspector.md) - Workflow introspection
