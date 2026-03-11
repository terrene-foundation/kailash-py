# Migrating from Django ORM to DataFlow

## What Is This

This guide shows how to migrate Django ORM models and queries to DataFlow. DataFlow is **not an ORM** - it's a workflow-based database framework optimized for standalone Python applications, not Django web apps.

**Key Difference**: Django ORM uses model methods and QuerySets, while DataFlow uses workflow nodes with automatic generation from model definitions.

## When to Use DataFlow vs Django ORM

**Use Django ORM when**:
- Building Django web applications
- Need Django admin integration
- Using Django forms and views
- Require Django middleware and authentication

**Use DataFlow when**:
- Building standalone Python applications
- Need workflow-based database operations
- Want automatic CRUD node generation
- Building microservices or APIs without Django framework

## Core Concepts Comparison

| Concept | Django ORM | DataFlow |
|---------|-----------|----------|
| **Models** | models.Model with Field types | @db.model with type hints |
| **Operations** | model.save(), Model.objects.create() | Workflow nodes (CreateNode, etc.) |
| **Queries** | Model.objects.filter() | ListNode with filters |
| **Relationships** | ForeignKey, ManyToManyField | Foreign key fields only |
| **Execution** | Immediate | runtime.execute(workflow.build()) |
| **Auto-fields** | auto_now, auto_now_add | Automatic created_at, updated_at |

## Basic Model Migration

### Django Model

```python
from django.db import models

class User(models.Model):
    # Django auto-creates 'id' as AutoField
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    age = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
```

### DataFlow Model

```python
from dataflow import DataFlow

db = DataFlow('postgresql://localhost/mydb')

@db.model
class User:
    id: str                  # Must explicitly define (MUST be named 'id')
    name: str
    email: str
    age: int
    is_active: bool
    # created_at: datetime  # Auto-managed - don't define
    # updated_at: datetime  # Auto-managed - don't define

# No Meta class needed
```

**Key Changes**:
1. ✅ Explicitly define `id` field (Django auto-creates, DataFlow requires explicit)
2. ❌ Remove Field types (CharField, EmailField) - use type hints
3. ❌ Remove field options (max_length, null, blank) - validation in application layer
4. ❌ Remove Meta class - configuration not needed
5. ✅ Omit auto_now/auto_now_add fields - DataFlow auto-manages timestamps

## Field Type Mapping

| Django ORM | DataFlow | Notes |
|------------|----------|-------|
| `CharField` | `str` | Validation in application layer |
| `EmailField` | `str` | Email validation in application layer |
| `IntegerField` | `int` | Integer type |
| `BooleanField` | `bool` | Boolean type |
| `DateTimeField` | `datetime` | Datetime type (if manually managed) |
| `JSONField` | `dict` | JSON stored as dict |
| `TextField` | `str` | Long text as string |
| `AutoField` | Not needed | Use `id: str` with manual generation |
| `ForeignKey` | `str` | Foreign key field (e.g., `organization_id: str`) |

**Not Supported**:
- `SlugField` → Use `str` with slug generation in application
- `FileField`, `ImageField` → Store file path as `str`
- `URLField` → Use `str` with URL validation
- Field options (`max_length`, `choices`, `validators`) → Application-level validation

## CRUD Operations Migration

### Create Operation

**Django ORM**:
```python
# Create user
user = User.objects.create(
    name="Alice",
    email="alice@example.com",
    age=30,
    is_active=True
)
# Auto-generates id, created_at, updated_at
```

**DataFlow**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {
    "id": str(uuid.uuid4()),  # Must generate ID manually
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

**Django ORM**:
```python
# Get user by ID
user = User.objects.get(id=123)

# Get or None
user = User.objects.filter(id=123).first()
```

**DataFlow**:
```python
workflow.add_node("UserReadNode", "read", {
    "id": "user-uuid-123"
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())
user = results["read"]  # Returns None if not found
```

### Update Operation

**Django ORM**:
```python
# Update instance
user = User.objects.get(id=123)
user.name = "Alice Updated"
user.save()  # updated_at auto-updated

# Bulk update
User.objects.filter(is_active=False).update(is_active=True)
```

**DataFlow**:
```python
# Update single record
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "Alice Updated"}
    # updated_at auto-updated
})

# Bulk update (requires fetching records first)
workflow.add_node("UserListNode", "get_inactive", {
    "filters": {"is_active": False}
})
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "records": "$get_inactive"  # Pass list of records to update
})
```

### Delete Operation

**Django ORM**:
```python
# Delete instance
user = User.objects.get(id=123)
user.delete()

# Bulk delete
User.objects.filter(is_active=False).delete()
```

**DataFlow**:
```python
# Delete single record
workflow.add_node("UserDeleteNode", "delete", {
    "id": "user-123"
})

# Bulk delete (requires fetching IDs first)
workflow.add_node("UserListNode", "get_inactive", {
    "filters": {"is_active": False}
})
workflow.add_node("UserBulkDeleteNode", "bulk_delete", {
    "ids": "$get_inactive"  # Pass list of IDs
})
```

## Query Migration

### Filter Queries

**Django ORM**:
```python
# Simple filter
users = User.objects.filter(is_active=True)

# Multiple conditions (AND)
users = User.objects.filter(is_active=True, age__gte=18)

# OR conditions
from django.db.models import Q
users = User.objects.filter(Q(age__gte=18) | Q(name__icontains='Admin'))
```

**DataFlow**:
```python
# Simple filter
workflow.add_node("UserListNode", "list", {
    "filters": {"is_active": True}
})

# Multiple conditions (AND)
workflow.add_node("UserListNode", "list", {
    "filters": {
        "is_active": True,
        "age__gte": 18
    }
})

# OR conditions (requires PythonCodeNode)
workflow.add_node("UserListNode", "get_all", {"filters": {}})
workflow.add_node("PythonCodeNode", "filter_or", {
    "code": """
return [u for u in users if u['age'] >= 18 or 'Admin' in u['name']]
    """,
    "inputs": {"users": "$get_all"}
})
```

### Ordering

**Django ORM**:
```python
# Order by age ascending
users = User.objects.order_by('age')

# Order by age descending
users = User.objects.order_by('-age')

# Multiple fields
users = User.objects.order_by('-created_at', 'name')
```

**DataFlow**:
```python
# Order by age ascending
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "age"
})

# Order by age descending
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "-age"
})

# Multiple fields (first takes precedence)
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "order_by": "-created_at"  # Single field only
})
```

### Pagination

**Django ORM**:
```python
# Slicing
users = User.objects.all()[10:30]  # Offset 10, limit 20

# Django Paginator
from django.core.paginator import Paginator
paginator = Paginator(User.objects.all(), 20)
page = paginator.get_page(2)
```

**DataFlow**:
```python
# Direct offset/limit
workflow.add_node("UserListNode", "list", {
    "filters": {},
    "offset": 10,
    "limit": 20
})

# Page-based (calculate offset)
page = 2
per_page = 20

workflow.add_node("UserListNode", "list", {
    "filters": {},
    "offset": (page - 1) * per_page,
    "limit": per_page
})
```

## Relationship Migration

### ForeignKey

**Django ORM**:
```python
class Organization(models.Model):
    name = models.CharField(max_length=255)

class User(models.Model):
    name = models.CharField(max_length=255)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users'
    )

# Access relationship
user = User.objects.get(id=1)
org = user.organization  # Auto-fetches via foreign key
users = org.users.all()  # Reverse relationship
```

**DataFlow**:
```python
@db.model
class Organization:
    id: str
    name: str

@db.model
class User:
    id: str
    name: str
    organization_id: str  # Foreign key field only

# Fetch relationship manually in workflow
workflow.add_node("UserReadNode", "get_user", {"id": "user-123"})
workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"
})

# Reverse relationship (users in organization)
workflow.add_node("UserListNode", "get_users", {
    "filters": {"organization_id": "org-456"}
})
```

### ManyToMany

**Django ORM**:
```python
class Role(models.Model):
    name = models.CharField(max_length=255)

class User(models.Model):
    name = models.CharField(max_length=255)
    roles = models.ManyToManyField(Role, related_name='users')

# Access relationship
user = User.objects.get(id=1)
roles = user.roles.all()
user.roles.add(role)
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
workflow.add_node("UserRoleListNode", "get_user_roles", {
    "filters": {"user_id": "user-123"}
})

# Add role to user
workflow.add_node("UserRoleCreateNode", "add_role", {
    "id": str(uuid.uuid4()),
    "user_id": "user-123",
    "role_id": "role-456"
})
```

## Django-Specific Features

### Managers and QuerySets

**Django ORM**:
```python
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

class User(models.Model):
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    objects = models.Manager()  # Default manager
    active = ActiveManager()  # Custom manager

# Usage
active_users = User.active.all()
```

**DataFlow**:
```python
# No custom managers - use helper functions instead
def get_active_users(db):
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {"is_active": True}
    })
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["list"]

active_users = get_active_users(db)
```

### Signals

**Django ORM**:
```python
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=User)
def user_created(sender, instance, created, **kwargs):
    if created:
        print(f"User {instance.name} created")
```

**DataFlow**:
```python
# No signals - handle in application code after workflow execution
workflow.add_node("UserCreateNode", "create", {...})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

# Handle post-create logic
user = results["create"]
print(f"User {user['name']} created")
send_welcome_email(user['email'])
```

### Model Methods

**Django ORM**:
```python
class User(models.Model):
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"
```

**DataFlow**:
```python
# No model methods - use helper functions
@db.model
class User:
    id: str
    first_name: str
    last_name: str

def get_full_name(user):
    return f"{user['first_name']} {user['last_name']}"

# Usage
workflow.add_node("UserReadNode", "read", {"id": "user-123"})
results, _ = runtime.execute(workflow.build())
full_name = get_full_name(results["read"])
```

## Complete Migration Example

**Before (Django ORM)**:

```python
# models.py
from django.db import models

class Organization(models.Model):
    name = models.CharField(max_length=255)

class User(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='users'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

# views.py or service.py
def create_user(name, email, org_id):
    user = User.objects.create(
        name=name,
        email=email,
        organization_id=org_id,
        is_active=True
    )
    return user

def get_active_users(org_id):
    return User.objects.filter(
        organization_id=org_id,
        is_active=True
    ).order_by('-created_at')
```

**After (DataFlow)**:

```python
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
import uuid

db = DataFlow('postgresql://localhost/mydb')

@db.model
class Organization:
    id: str
    name: str

@db.model
class User:
    id: str
    name: str
    email: str
    organization_id: str
    is_active: bool

def create_user(db, name, email, org_id):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "organization_id": org_id,
        "is_active": True
    })
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["create"]

def get_active_users(db, org_id):
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {
            "organization_id": org_id,
            "is_active": True
        },
        "order_by": "-created_at"
    })
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["list"]
```

## Migration Strategy

### Step 1: Keep Django for Web, Add DataFlow for Services

```python
# Django models (keep for web app)
class User(models.Model):
    name = models.CharField(max_length=255)

# DataFlow models (for standalone services)
@db.model
class User:
    id: str
    name: str

# Both access same database table
```

### Step 2: Extract Business Logic from Django

```python
# Before (Django-specific)
def get_active_users(request):
    users = User.objects.filter(is_active=True)
    return JsonResponse({"users": list(users.values())})

# After (DataFlow - framework-agnostic)
def get_active_users_service(db):
    workflow = WorkflowBuilder()
    workflow.add_node("UserListNode", "list", {
        "filters": {"is_active": True}
    })
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    return results["list"]

# Django view uses service
def get_active_users(request):
    users = get_active_users_service(db)
    return JsonResponse({"users": users})
```

### Step 3: Gradual Transition

Extract one service at a time:
1. User management → DataFlow
2. Organization management → DataFlow
3. Keep Django admin for backoffice
4. Migrate API endpoints to FastAPI + DataFlow

## Summary

**Key Migration Changes**:
1. ✅ Replace Field types with type hints
2. ✅ Use @db.model decorator (no models.Model)
3. ✅ Explicitly define `id` field (Django auto-creates)
4. ✅ Remove ForeignKey wrapper - use foreign key field
5. ✅ Replace QuerySets with workflow nodes
6. ✅ Omit auto_now/auto_now_add - auto-managed
7. ✅ Extract business logic into framework-agnostic functions

**When to Migrate**:
- Building microservices separate from Django
- Need workflow-based database operations
- Want to reduce Django dependency
- Building standalone Python applications

**Keep Django When**:
- Heavily using Django admin
- Integrated with Django forms/views
- Large existing Django codebase
- Django-specific features required
