# Migrating from SQLAlchemy to DataFlow

## What Is This

This guide shows how to migrate existing SQLAlchemy models and queries to DataFlow. DataFlow is **not an ORM** - it's a workflow-based database framework that generates operation nodes automatically from model definitions.

**Key Difference**: SQLAlchemy uses session-based CRUD operations, while DataFlow uses workflow-based operations with automatic node generation.

## Core Concepts Comparison

| Concept | SQLAlchemy | DataFlow |
|---------|-----------|----------|
| **Models** | Class with Base, Column definitions | @db.model decorator with type hints |
| **Operations** | session.add(), session.query() | Workflow nodes (CreateNode, ListNode, etc.) |
| **Relationships** | relationship(), ForeignKey() | Foreign key fields only (manual joins in workflows) |
| **Execution** | session.commit() | runtime.execute(workflow.build()) |
| **Queries** | session.query(User).filter_by() | ListNode with filters parameter |
| **Auto-fields** | default=func.now() | Automatic created_at, updated_at |

## Basic Model Migration

### SQLAlchemy Model

```python
from sqlalchemy import Column, String, Integer, Boolean, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    age = Column(Integer)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Setup
engine = create_engine('postgresql://localhost/mydb')
Session = sessionmaker(bind=engine)
session = Session()
```

### DataFlow Model

```python
from dataflow import DataFlow

db = DataFlow('postgresql://localhost/mydb')

@db.model
class User:
    id: str                  # Primary key (MUST be named 'id')
    name: str
    email: str
    age: int
    is_active: bool
    # created_at: datetime  # Auto-managed - don't define
    # updated_at: datetime  # Auto-managed - don't define

# No session setup needed
```

**Key Changes**:
1. ❌ Remove `__tablename__` - derived from class name
2. ❌ Remove Column() wrappers - use type hints directly
3. ❌ Remove Base inheritance - use @db.model decorator
4. ✅ Primary key MUST be named `id` (not `user_id`)
5. ✅ Omit created_at/updated_at - auto-managed by DataFlow

## Column Type Mapping

| SQLAlchemy | DataFlow | Notes |
|------------|----------|-------|
| `Column(String)` | `str` | String type |
| `Column(Integer)` | `int` | Integer type |
| `Column(Float)` | `float` | Float type |
| `Column(Boolean)` | `bool` | Boolean type |
| `Column(DateTime)` | `datetime` | Datetime type |
| `Column(JSON)` | `dict` | JSON stored as dict |
| `Column(ARRAY)` | `list` | PostgreSQL array as list |
| `Column(Text)` | `str` | Long text as string |

**Not Supported**:
- `Column(Enum)` → Use `str` with validation in application layer
- `Column(LargeBinary)` → Store file path as `str`, not binary data
- Custom column types → Use primitive types only

## Relationship Migration

SQLAlchemy `relationship()` and `ForeignKey()` are replaced with simple foreign key fields in DataFlow.

### SQLAlchemy Relationships

```python
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(String, primary_key=True)
    name = Column(String)
    users = relationship("User", back_populates="organization")  # ❌ Not in DataFlow

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    name = Column(String)
    organization_id = Column(String, ForeignKey('organizations.id'))
    organization = relationship("Organization", back_populates="users")  # ❌ Not in DataFlow
```

### DataFlow Foreign Keys

```python
@db.model
class Organization:
    id: str
    name: str
    # No relationship() needed

@db.model
class User:
    id: str
    name: str
    organization_id: str  # ✅ Foreign key field only (no ForeignKey() wrapper)
    # No relationship() - fetch related data in workflow
```

**Key Changes**:
1. ❌ Remove `relationship()` - no ORM relationships
2. ❌ Remove `ForeignKey()` wrapper - use plain type hint
3. ✅ Use foreign key field (`organization_id: str`)
4. ✅ Fetch related data manually in workflows

## CRUD Operations Migration

### Create Operation

**SQLAlchemy**:
```python
# Create user
user = User(
    id="user-123",
    name="Alice",
    email="alice@example.com",
    age=30,
    is_active=True
)
session.add(user)
session.commit()
```

**DataFlow**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30,
    "is_active": True
    # Omit created_at, updated_at - auto-managed
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
user = results["create"]
```

### Read Operation

**SQLAlchemy**:
```python
# Get user by ID
user = session.query(User).filter_by(id="user-123").first()
```

**DataFlow**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserReadNode", "read", {
    "id": "user-123"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
user = results["read"]
```

### Update Operation

**SQLAlchemy**:
```python
# Update user
user = session.query(User).filter_by(id="user-123").first()
user.name = "Alice Updated"
session.commit()
```

**DataFlow**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
    # Omit updated_at - auto-managed
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
user = results["update"]
```

### Delete Operation

**SQLAlchemy**:
```python
# Delete user
user = session.query(User).filter_by(id="user-123").first()
session.delete(user)
session.commit()
```

**DataFlow**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserDeleteNode", "delete", {
    "id": "user-123"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

## Query Migration

### Filter Queries

**SQLAlchemy**:
```python
# Filter users
users = session.query(User).filter_by(is_active=True).all()
```

**DataFlow**:
```python
workflow = WorkflowBuilder()
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True}
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
users = results["list"]
```

### Complex Filters

**SQLAlchemy**:
```python
from sqlalchemy import and_, or_

# Complex filter
users = session.query(User).filter(
    and_(
        User.is_active == True,
        or_(
            User.age >= 18,
            User.name.like('%Admin%')
        )
    )
).all()
```

**DataFlow**:
```python
# Complex filters using dict syntax
workflow.add_node("UserListNode", "list", {
    "filters": {
        "is_active": True,
        "age__gte": 18  # Greater than or equal
        # OR conditions require separate queries
    }
})

# For complex OR logic, use PythonCodeNode
workflow.add_node("PythonCodeNode", "filter_logic", {
    "code": """
results = []
for user in users:
    if user['is_active'] and (user['age'] >= 18 or 'Admin' in user['name']):
        results.append(user)
return results
    """,
    "inputs": {"users": "$list"}
})
```

### Ordering

**SQLAlchemy**:
```python
# Order by age descending
users = session.query(User).order_by(User.age.desc()).all()
```

**DataFlow**:
```python
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "-age"  # Descending (prefix with -)
})

# Ascending
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "age"  # Ascending (no prefix)
})
```

### Pagination

**SQLAlchemy**:
```python
# Paginate results
page = 2
per_page = 20
users = session.query(User).offset((page - 1) * per_page).limit(per_page).all()
```

**DataFlow**:
```python
page = 2
per_page = 20

workflow.add_node("UserListNode", "list", {
    "filters": {},
    "limit": per_page,
    "offset": (page - 1) * per_page
})
```

## Relationship Queries

### Fetching Related Data

**SQLAlchemy**:
```python
# Get user with organization (eager loading)
user = session.query(User).options(
    joinedload(User.organization)
).filter_by(id="user-123").first()

organization = user.organization
```

**DataFlow**:
```python
# Fetch user and organization in workflow
workflow = WorkflowBuilder()

workflow.add_node("UserReadNode", "get_user", {
    "id": "user-123"
})

workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"  # Use foreign key
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["get_user"]
organization = results["get_org"]
```

### Many-to-Many Relationships

**SQLAlchemy**:
```python
# Association table
user_roles = Table('user_roles', Base.metadata,
    Column('user_id', String, ForeignKey('users.id')),
    Column('role_id', String, ForeignKey('roles.id'))
)

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    roles = relationship("Role", secondary=user_roles, back_populates="users")

class Role(Base):
    __tablename__ = 'roles'
    id = Column(String, primary_key=True)
    users = relationship("User", secondary=user_roles, back_populates="roles")

# Query
user = session.query(User).filter_by(id="user-123").first()
roles = user.roles
```

**DataFlow**:
```python
# Junction table
@db.model
class UserRole:
    id: str
    user_id: str
    role_id: str

# Query roles for user
workflow = WorkflowBuilder()

workflow.add_node("UserRoleListNode", "get_user_roles", {
    "filters": {"user_id": "user-123"}
})

# Get role details (simplified - first role)
workflow.add_node("RoleReadNode", "get_role", {
    "id": "$get_user_roles.0.role_id"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user_roles = results["get_user_roles"]
role = results["get_role"]
```

## Bulk Operations

### Bulk Create

**SQLAlchemy**:
```python
# Bulk insert
users = [
    User(id="user-1", name="Alice", email="alice@example.com"),
    User(id="user-2", name="Bob", email="bob@example.com"),
    User(id="user-3", name="Charlie", email="charlie@example.com")
]
session.bulk_save_objects(users)
session.commit()
```

**DataFlow**:
```python
workflow.add_node("UserBulkCreateNode", "bulk_create", {
    "records": [
        {"id": "user-1", "name": "Alice", "email": "alice@example.com"},
        {"id": "user-2", "name": "Bob", "email": "bob@example.com"},
        {"id": "user-3", "name": "Charlie", "email": "charlie@example.com"}
    ]
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
users = results["bulk_create"]
```

### Bulk Update

**SQLAlchemy**:
```python
# Bulk update
session.query(User).filter(User.is_active == False).update(
    {"is_active": True}
)
session.commit()
```

**DataFlow**:
```python
# Bulk update requires fetching IDs first
workflow = WorkflowBuilder()

# Step 1: Get inactive users
workflow.add_node("UserListNode", "get_inactive", {
    "filters": {"is_active": False}
})

# Step 2: Update all to active
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "records": [
        {"id": "$get_inactive.{i}.id", "is_active": True}
        # Requires loop or PythonCodeNode for dynamic list
    ]
})

# Alternative: Use PythonCodeNode for flexibility
workflow.add_node("PythonCodeNode", "prepare_updates", {
    "code": """
return [{"id": user["id"], "is_active": True} for user in inactive_users]
    """,
    "inputs": {"inactive_users": "$get_inactive"}
})

workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "records": "$prepare_updates"
})
```

## Session vs Workflow

### Transaction Handling

**SQLAlchemy**:
```python
# Transaction with rollback
try:
    user = User(id="user-123", name="Alice")
    session.add(user)

    org = Organization(id="org-456", name="Acme Corp")
    session.add(org)

    session.commit()
except Exception as e:
    session.rollback()
    raise
```

**DataFlow**:
```python
# Workflow execution (atomic by default)
workflow = WorkflowBuilder()

workflow.add_node("UserCreateNode", "create_user", {
    "id": "user-123",
    "name": "Alice"
})

workflow.add_node("OrganizationCreateNode", "create_org", {
    "id": "org-456",
    "name": "Acme Corp"
})

runtime = LocalRuntime()

try:
    results, _ = runtime.execute(workflow.build())
except Exception as e:
    # Workflow automatically rolls back on error
    raise
```

### Context Manager

**SQLAlchemy**:
```python
# Session context manager
with Session() as session:
    user = User(id="user-123", name="Alice")
    session.add(user)
    session.commit()
```

**DataFlow**:
```python
# No context manager needed - stateless workflows
workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

## Migration Strategy

### Step 1: Parallel Implementation

Keep SQLAlchemy models and add DataFlow models side-by-side:

```python
# Keep existing SQLAlchemy
class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    name = Column(String)

# Add DataFlow model (same table)
@db.model
class User:
    id: str
    name: str

# Both access same database table
```

### Step 2: Gradual Migration

Migrate operations one-by-one:

```python
# Old (SQLAlchemy)
def get_user(user_id):
    return session.query(User).filter_by(id=user_id).first()

# New (DataFlow)
def get_user_dataflow(user_id):
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": user_id})
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["read"]

# Switch callers gradually
```

### Step 3: Remove SQLAlchemy

Once all operations migrated, remove SQLAlchemy:

```python
# Remove
# from sqlalchemy import ...
# from sqlalchemy.orm import ...
# Base = declarative_base()
# Session = sessionmaker(...)

# Keep only DataFlow
from dataflow import DataFlow

db = DataFlow("postgresql://...")
```

## Common Patterns

### Pattern: Upsert (Insert or Update)

**SQLAlchemy**:
```python
from sqlalchemy.dialects.postgresql import insert

stmt = insert(User).values(
    id="user-123",
    name="Alice",
    email="alice@example.com"
).on_conflict_do_update(
    index_elements=['id'],
    set_={"name": "Alice", "email": "alice@example.com"}
)
session.execute(stmt)
session.commit()
```

**DataFlow**:
```python
workflow.add_node("UserUpsertNode", "upsert", {
    "where": {"id": "user-123"},
    "update": {"name": "Alice", "email": "alice@example.com"},
    "create": {
        "id": "user-123",
        "name": "Alice",
        "email": "alice@example.com"
    }
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
```

### Pattern: Count Records

**SQLAlchemy**:
```python
count = session.query(User).filter_by(is_active=True).count()
```

**DataFlow**:
```python
# Count via ListNode
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True}
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
count = len(results["list"])

# For large datasets, use database-specific count query
```

### Pattern: Exists Check

**SQLAlchemy**:
```python
exists = session.query(User).filter_by(email="alice@example.com").first() is not None
```

**DataFlow**:
```python
workflow.add_node("UserListNode", "list", {
    "filters": {"email": "alice@example.com"},
    "limit": 1
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
exists = len(results["list"]) > 0
```

## Troubleshooting

### Issue: Primary key not named `id`

**SQLAlchemy**:
```python
class User(Base):
    user_id = Column(String, primary_key=True)
```

**Fix**: Rename column in database

```sql
ALTER TABLE users RENAME COLUMN user_id TO id;
```

**DataFlow**:
```python
@db.model
class User:
    id: str  # Must be named 'id'
```

### Issue: Missing relationship data

**SQLAlchemy**:
```python
user.organization  # Auto-loaded via relationship()
```

**DataFlow**:
```python
# Fetch explicitly in workflow
workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"
})
```

### Issue: Complex queries

**SQLAlchemy supports complex queries via filter(), join(), subquery()**

**DataFlow**: Use PythonCodeNode for complex logic

```python
workflow.add_node("PythonCodeNode", "complex_logic", {
    "code": """
# Complex filtering logic
filtered = [u for u in users if condition(u)]
return filtered
    """,
    "inputs": {"users": "$list"}
})
```

## Complete Migration Example

**Before (SQLAlchemy)**:

```python
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()

class Organization(Base):
    __tablename__ = 'organizations'
    id = Column(String, primary_key=True)
    name = Column(String)
    users = relationship("User", back_populates="organization")

class User(Base):
    __tablename__ = 'users'
    id = Column(String, primary_key=True)
    name = Column(String)
    organization_id = Column(String, ForeignKey('organizations.id'))
    organization = relationship("Organization", back_populates="users")

engine = create_engine('postgresql://localhost/mydb')
Session = sessionmaker(bind=engine)

# Operations
session = Session()

# Create
user = User(id="user-123", name="Alice", organization_id="org-456")
session.add(user)
session.commit()

# Read with relationship
user = session.query(User).filter_by(id="user-123").first()
org_name = user.organization.name

# Update
user.name = "Alice Updated"
session.commit()

# List active users
users = session.query(User).join(Organization).filter(
    Organization.name == "Acme Corp"
).all()
```

**After (DataFlow)**:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

db = DataFlow('postgresql://localhost/mydb')

@db.model
class Organization:
    id: str
    name: str

@db.model
class User:
    id: str
    name: str
    organization_id: str

# Operations
workflow = WorkflowBuilder()

# Create
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "organization_id": "org-456"
})

# Read with relationship
workflow.add_node("UserReadNode", "get_user", {"id": "user-123"})
workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"
})

# Update
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
})

# List users in organization
workflow.add_node("UserListNode", "list_users", {
    "filters": {"organization_id": "org-456"}
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["get_user"]
org = results["get_org"]
updated_user = results["update"]
users_in_org = results["list_users"]
```

## Summary

**Key Migration Changes**:
1. ✅ Replace Column() with type hints
2. ✅ Use @db.model decorator (no Base)
3. ✅ Primary key MUST be named `id`
4. ✅ Remove relationship() - use foreign keys only
5. ✅ Replace session operations with workflow nodes
6. ✅ Omit created_at/updated_at - auto-managed
7. ✅ Fetch related data explicitly in workflows

**When to Use DataFlow vs SQLAlchemy**:
- **DataFlow**: Workflow-based operations, automatic node generation, production deployments
- **SQLAlchemy**: Complex ad-hoc queries, ORM relationships, existing large codebases

**Migration Path**: Start with parallel implementation, migrate gradually, remove SQLAlchemy when complete.
