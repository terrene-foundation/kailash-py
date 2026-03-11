# Primary Keys in DataFlow: The `id` Field Requirement

## What Is This

DataFlow requires **all models** to use `id` as the primary key field name. This is a mandatory naming convention that enables DataFlow's automatic node generation and workflow integration.

**Key Rule**: Primary key field MUST be named `id`, not `user_id`, `model_id`, `agent_id`, or any other variant.

## Why This Matters

Using the correct primary key name prevents this error:

```python
# ❌ WRONG - Causes VAL-001 validation error
@db.model
class User:
    user_id: str  # Error: Primary key must be named 'id'
    name: str
    email: str

# Error: ValidationError: Field 'id' is required but 'user_id' was provided
```

DataFlow's automatic node generation (11 nodes per model) expects the `id` field for all CRUD operations. Without it, generated nodes cannot function correctly.

## How to Define Models Correctly

### ✅ Correct Pattern

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str              # ✅ REQUIRED: Primary key MUST be named 'id'
    organization_id: str  # ✅ OK: Foreign keys can use descriptive names
    name: str
    email: str
```

### ✅ With Different ID Types

```python
# String IDs (recommended for UUIDs, external IDs)
@db.model
class User:
    id: str  # String preserved exactly
    name: str

# Integer IDs (for auto-increment)
@db.model
class Counter:
    id: int  # Integer type
    value: int
```

### ❌ Common Mistakes

```python
# ❌ WRONG: Using model-specific ID name
@db.model
class User:
    user_id: str  # Error: Must be 'id'
    name: str

# ❌ WRONG: Using table-specific ID name
@db.model
class Agent:
    agent_id: str  # Error: Must be 'id'
    name: str

# ❌ WRONG: Omitting ID field entirely
@db.model
class User:
    name: str  # Error: Missing 'id' field
    email: str
```

## Generated Nodes and the `id` Field

When you define a model with the `id` field, DataFlow automatically generates 11 operation nodes (7 CRUD + 4 Bulk). Each node expects the `id` field for its operations.

### CreateNode

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",  # ✅ Required: Uses 'id' field
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

### ReadNode

```python
workflow.add_node("UserReadNode", "read", {
    "id": "user-123"  # ✅ Required: Lookup by 'id'
})
```

### UpdateNode

```python
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},  # ✅ Required: Filter by 'id'
    "fields": {"name": "Alice Updated"}
})
```

### DeleteNode

```python
workflow.add_node("UserDeleteNode", "delete", {
    "id": "user-123"  # ✅ Required: Delete by 'id'
})
```

## Foreign Keys vs Primary Keys

**Primary key** (`id`): MUST be named `id`
**Foreign keys**: Can use descriptive names like `organization_id`, `user_id`, `parent_id`

```python
@db.model
class User:
    id: str              # ✅ Primary key: Must be 'id'
    organization_id: str  # ✅ Foreign key: Descriptive name OK
    name: str

@db.model
class Organization:
    id: str  # ✅ Primary key: Must be 'id'
    name: str

@db.model
class Comment:
    id: str       # ✅ Primary key: Must be 'id'
    user_id: str   # ✅ Foreign key: Descriptive name OK
    post_id: str   # ✅ Foreign key: Descriptive name OK
    content: str
```

## Migration from Other ORMs

### From SQLAlchemy

```python
# SQLAlchemy pattern
class User(Base):
    __tablename__ = 'users'
    user_id = Column(String, primary_key=True)  # ❌ Old pattern
    name = Column(String)

# DataFlow pattern
@db.model
class User:
    id: str  # ✅ Changed from 'user_id' to 'id'
    name: str
```

### From Django ORM

```python
# Django pattern
class User(models.Model):
    user_id = models.CharField(primary_key=True)  # ❌ Old pattern
    name = models.CharField(max_length=255)

# DataFlow pattern
@db.model
class User:
    id: str  # ✅ Changed from 'user_id' to 'id'
    name: str
```

### Existing Database with Different Primary Key Name

If you have an existing database where the primary key column has a different name (e.g., `user_id`), you have two options:

**Option 1: Rename database column** (recommended)

```sql
-- PostgreSQL
ALTER TABLE users RENAME COLUMN user_id TO id;

-- MySQL
ALTER TABLE users CHANGE user_id id VARCHAR(255);

-- SQLite
-- SQLite doesn't support column rename directly - requires table recreation
```

**Option 2: Use existing schema mode with custom mapping** (advanced)

```python
# Tell DataFlow to use existing schema without modification
db = DataFlow(url, existing_schema_mode=True)

# Note: Automatic node generation still expects 'id' field in model definition
# You'll need custom nodes to map between DataFlow's 'id' and database's 'user_id'
```

## String vs Integer IDs

DataFlow preserves your ID type exactly as declared:

```python
# String IDs (recommended for UUIDs, external IDs)
@db.model
class User:
    id: str  # Stored as VARCHAR/TEXT
    name: str

# Integer IDs (for auto-increment)
@db.model
class Counter:
    id: int  # Stored as INTEGER/BIGINT
    value: int

# UUID IDs (requires uuid library)
import uuid

@db.model
class Session:
    id: str  # Store UUID as string
    user_id: str
```

### Using UUIDs

```python
import uuid
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # ✅ Generate UUID and convert to string
    "name": "Alice",
    "email": "alice@example.com"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

## Validation Error Reference

**Error Code**: VAL-001
**Error Message**: "Field 'id' is required for CREATE operations"
**Cause**: Model missing `id` field or using alternative name (`user_id`, `model_id`, etc.)
**Solution**: Add `id` field to model definition

**Example Error**:

```python
@db.model
class User:
    user_id: str  # ❌ Wrong field name
    name: str

# Triggers error:
# ValidationError: Field 'id' is required but 'user_id' was provided.
# Primary key must be named 'id', not 'user_id'.
```

**Fix**:

```python
@db.model
class User:
    id: str  # ✅ Correct field name
    name: str
```

## Best Practices

1. **Always use `id` for primary keys**
   - Never use `user_id`, `model_id`, `agent_id`, etc. for primary key
   - Use descriptive names only for foreign keys

2. **Choose ID type based on use case**
   - String IDs: UUIDs, external system IDs, natural keys
   - Integer IDs: Auto-increment sequences, internal counters

3. **Use UUIDs for distributed systems**

   ```python
   @db.model
   class User:
       id: str  # UUID stored as string
       name: str

   # Generate at application layer
   user_id = str(uuid.uuid4())
   ```

4. **Explicit ID generation (recommended)**

   ```python
   # ✅ Generate ID in application code
   workflow.add_node("UserCreateNode", "create", {
       "id": str(uuid.uuid4()),
       "name": "Alice"
   })
   ```

5. **Foreign keys use descriptive names**
   ```python
   @db.model
   class Order:
       id: str              # ✅ Primary key
       user_id: str         # ✅ Foreign key - descriptive name OK
       organization_id: str # ✅ Foreign key - descriptive name OK
       total: float
   ```

## Complete Example

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

# Initialize DataFlow
db = DataFlow("postgresql://localhost/mydb")

# Define models with correct primary key naming
@db.model
class Organization:
    id: str  # ✅ Primary key
    name: str
    status: str

@db.model
class User:
    id: str              # ✅ Primary key
    organization_id: str  # ✅ Foreign key
    name: str
    email: str

@db.model
class Post:
    id: str       # ✅ Primary key
    user_id: str   # ✅ Foreign key
    title: str
    content: str

# Create records with generated IDs
workflow = WorkflowBuilder()

org_id = str(uuid.uuid4())
user_id = str(uuid.uuid4())
post_id = str(uuid.uuid4())

workflow.add_node("OrganizationCreateNode", "create_org", {
    "id": org_id,
    "name": "Acme Corp",
    "status": "active"
})

workflow.add_node("UserCreateNode", "create_user", {
    "id": user_id,
    "organization_id": org_id,
    "name": "Alice",
    "email": "alice@example.com"
})

workflow.add_node("PostCreateNode", "create_post", {
    "id": post_id,
    "user_id": user_id,
    "title": "My First Post",
    "content": "Hello, world!"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

print(f"Created organization: {results['create_org']['id']}")
print(f"Created user: {results['create_user']['id']}")
print(f"Created post: {results['create_post']['id']}")
```

## Troubleshooting

### Error: "Field 'id' is required"

**Cause**: Model definition missing `id` field

**Fix**: Add `id` field to model

```python
# ❌ Before
@db.model
class User:
    name: str

# ✅ After
@db.model
class User:
    id: str
    name: str
```

### Error: "Primary key must be named 'id'"

**Cause**: Using alternative name for primary key

**Fix**: Rename field to `id`

```python
# ❌ Before
@db.model
class User:
    user_id: str

# ✅ After
@db.model
class User:
    id: str
```

### Existing database has different column name

**Solution**: Rename database column to `id` or use existing_schema_mode

```python
# Option 1: Rename column (recommended)
# Run SQL migration: ALTER TABLE users RENAME COLUMN user_id TO id;

# Option 2: Use existing schema mode (advanced)
db = DataFlow(url, existing_schema_mode=True)
```

## Related Guides

- [Auto-Managed Fields](auto-managed-fields.md) - `created_at` and `updated_at` handling
- [Flat Fields Pattern](flat-fields.md) - No nested objects in model definitions
- [Migration from SQLAlchemy](from-sqlalchemy.md) - Converting existing ORM models
- [Migration from Django ORM](from-django-orm.md) - Converting Django models

## Summary

- **Primary key MUST be named `id`** - Non-negotiable requirement
- **Foreign keys can use descriptive names** - `user_id`, `organization_id`, etc.
- **Choose ID type intentionally** - String for UUIDs, Integer for auto-increment
- **Generate IDs in application code** - Explicit control recommended
- **Migration requires column rename** - Align database with DataFlow expectations
