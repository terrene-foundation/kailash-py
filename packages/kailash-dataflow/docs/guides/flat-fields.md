# Flat Fields Pattern in DataFlow: No Nested Objects

## What Is This

DataFlow requires **all model fields to be flat** (primitive types or simple collections). Nested objects, embedded documents, and complex structures are **not supported** in model definitions.

**Key Rule**: Use primitive types (`str`, `int`, `float`, `bool`, `datetime`) and simple collections (`list`, `dict`) only. Model relationships using foreign keys, not nested objects.

## Why This Matters

Using nested objects causes type validation errors at model registration:

```python
# ❌ WRONG - Causes type validation error
@db.model
class User:
    id: str
    name: str
    address: Address  # Error: Nested object not supported

# Error: TypeError: Field 'address' has unsupported type 'Address'.
# DataFlow models support only flat fields: str, int, float, bool, datetime, list, dict.
```

DataFlow's workflow-based architecture and automatic node generation require flat, serializable data structures that map directly to database columns.

## Supported Field Types

### ✅ Primitive Types

```python
from dataflow import DataFlow
from datetime import datetime

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str                 # ✅ String
    age: int               # ✅ Integer
    balance: float         # ✅ Float
    is_active: bool        # ✅ Boolean
    created_at: datetime   # ✅ Datetime (if manually managed)
    name: str              # ✅ String
```

### ✅ Simple Collections

```python
@db.model
class User:
    id: str
    name: str
    tags: list             # ✅ List of primitives
    metadata: dict         # ✅ Dictionary (JSON)
    roles: list            # ✅ List of strings
```

### ❌ Unsupported Types

```python
# ❌ WRONG - Nested objects
class Address:
    street: str
    city: str
    zip_code: str

@db.model
class User:
    id: str
    name: str
    address: Address  # ❌ Error: Nested object not supported

# ❌ WRONG - Custom classes
@db.model
class Order:
    id: str
    customer: Customer  # ❌ Error: Custom class not supported
    items: list[OrderItem]  # ❌ Error: List of custom objects not supported

# ❌ WRONG - Typed lists
from typing import List

@db.model
class User:
    id: str
    tags: List[str]  # ⚠️ Use `list` not `List[str]` (typing hint not needed)
```

## How to Model Relationships

Use **foreign keys** to model relationships between entities, not nested objects.

### Pattern: One-to-Many Relationship

Instead of embedding related objects, use foreign keys:

```python
# ❌ WRONG - Nested object approach
class User:
    id: str
    name: str
    organization: Organization  # Error!

# ✅ CORRECT - Foreign key approach
@db.model
class Organization:
    id: str
    name: str
    industry: str

@db.model
class User:
    id: str
    organization_id: str  # ✅ Foreign key reference
    name: str
    email: str
```

### Pattern: Querying Related Data

Fetch related data using separate queries with foreign key joins:

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()

# Step 1: Get user
workflow.add_node("UserReadNode", "get_user", {
    "id": "user-123"
})

# Step 2: Get organization using foreign key
workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"  # ✅ Use foreign key for lookup
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["get_user"]
organization = results["get_org"]

print(f"User {user['name']} belongs to {organization['name']}")
```

### Pattern: Many-to-Many Relationship

Use junction tables with foreign keys:

```python
@db.model
class User:
    id: str
    name: str
    email: str

@db.model
class Role:
    id: str
    name: str
    permissions: list  # ✅ List of permission strings

@db.model
class UserRole:
    id: str
    user_id: str       # ✅ Foreign key to User
    role_id: str       # ✅ Foreign key to Role
    assigned_at: str   # ISO 8601 timestamp
```

Querying many-to-many relationships:

```python
workflow = WorkflowBuilder()

# Step 1: Get user
workflow.add_node("UserReadNode", "get_user", {
    "id": "user-123"
})

# Step 2: Get user's role assignments
workflow.add_node("UserRoleListNode", "get_user_roles", {
    "filters": {"user_id": "user-123"}
})

# Step 3: Get role details for each assignment (requires cycle or multiple nodes)
# Simplified: Get first role
workflow.add_node("RoleReadNode", "get_role", {
    "id": "$get_user_roles.0.role_id"  # First role from list
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["get_user"]
user_roles = results["get_user_roles"]
role = results["get_role"]

print(f"User {user['name']} has role: {role['name']}")
```

## Using Dictionaries for Flexible Data

For semi-structured data, use `dict` fields stored as JSON:

```python
@db.model
class User:
    id: str
    name: str
    email: str
    metadata: dict  # ✅ Flexible JSON field

# Create user with metadata
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "metadata": {
        "preferences": {
            "theme": "dark",
            "language": "en"
        },
        "custom_fields": {
            "department": "Engineering",
            "location": "San Francisco"
        }
    }
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["create"]
print(user["metadata"]["preferences"]["theme"])  # "dark"
```

### Querying JSON Fields

Different databases have different JSON query capabilities:

```python
# PostgreSQL - JSON query support
workflow.add_node("UserListNode", "list", {
    "filters": {
        "metadata__preferences__theme": "dark"  # PostgreSQL jsonb query
    }
})

# SQLite/MySQL - Query on serialized JSON (limited)
# Better approach: Store searchable fields as top-level columns
@db.model
class User:
    id: str
    name: str
    theme: str  # ✅ Top-level field for queries
    metadata: dict  # ✅ Additional flexible data
```

## Using Lists for Collections

Store simple collections as list fields:

```python
@db.model
class User:
    id: str
    name: str
    email: str
    tags: list  # ✅ List of strings
    roles: list  # ✅ List of role names

# Create user with lists
workflow.add_node("UserCreateNode", "create", {
    "id": "user-123",
    "name": "Alice",
    "email": "alice@example.com",
    "tags": ["engineering", "senior", "python"],
    "roles": ["developer", "reviewer"]
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

user = results["create"]
print(user["tags"])  # ["engineering", "senior", "python"]
```

### Limitations of List Fields

**Warning**: List fields have limitations:
- No referential integrity (can't enforce foreign key constraints)
- Limited query capabilities (e.g., "find users with tag X")
- No JOIN support

**Recommendation**: For complex relationships, use junction tables instead of lists.

```python
# ⚠️ FRAGILE - List of IDs without integrity
@db.model
class User:
    id: str
    name: str
    role_ids: list  # ⚠️ No referential integrity

# ✅ BETTER - Junction table with integrity
@db.model
class UserRole:
    id: str
    user_id: str  # ✅ Foreign key with integrity
    role_id: str  # ✅ Foreign key with integrity
```

## Common Patterns and Anti-Patterns

### Anti-Pattern: Embedded Address

```python
# ❌ WRONG - Nested object
class Address:
    street: str
    city: str
    state: str
    zip_code: str

@db.model
class User:
    id: str
    name: str
    address: Address  # Error!

# ✅ CORRECT - Flatten fields
@db.model
class User:
    id: str
    name: str
    address_street: str
    address_city: str
    address_state: str
    address_zip_code: str

# ✅ BETTER - Separate table if reusable
@db.model
class Address:
    id: str
    street: str
    city: str
    state: str
    zip_code: str

@db.model
class User:
    id: str
    name: str
    address_id: str  # Foreign key
```

### Anti-Pattern: Embedded Order Items

```python
# ❌ WRONG - List of objects
class OrderItem:
    product_id: str
    quantity: int
    price: float

@db.model
class Order:
    id: str
    customer_id: str
    items: list[OrderItem]  # Error!

# ✅ CORRECT - Separate table
@db.model
class Order:
    id: str
    customer_id: str
    total: float
    status: str

@db.model
class OrderItem:
    id: str
    order_id: str       # ✅ Foreign key to Order
    product_id: str     # ✅ Foreign key to Product
    quantity: int
    price: float
```

### Anti-Pattern: Nested User Profile

```python
# ❌ WRONG - Nested object
class Profile:
    bio: str
    avatar_url: str
    social_links: dict

@db.model
class User:
    id: str
    name: str
    profile: Profile  # Error!

# ✅ CORRECT - Flatten or separate table
# Option 1: Flatten if 1:1 relationship
@db.model
class User:
    id: str
    name: str
    bio: str
    avatar_url: str
    social_links: dict  # ✅ JSON field

# Option 2: Separate table if large/optional
@db.model
class User:
    id: str
    name: str

@db.model
class UserProfile:
    id: str
    user_id: str  # ✅ Foreign key (1:1)
    bio: str
    avatar_url: str
    social_links: dict
```

## Migration from Other ORMs

### From MongoDB/Mongoose (Embedded Documents)

```python
# MongoDB pattern - embedded documents
{
    "_id": "user-123",
    "name": "Alice",
    "address": {  # ❌ Embedded document
        "street": "123 Main St",
        "city": "San Francisco",
        "state": "CA"
    },
    "orders": [  # ❌ Embedded array of objects
        {
            "order_id": "order-1",
            "total": 99.99
        }
    ]
}

# DataFlow pattern - flat fields + foreign keys
@db.model
class User:
    id: str
    name: str
    address_street: str  # ✅ Flattened
    address_city: str
    address_state: str

@db.model
class Order:
    id: str
    user_id: str  # ✅ Foreign key
    total: float
```

### From SQLAlchemy (Relationship Objects)

```python
# SQLAlchemy pattern
from sqlalchemy.orm import relationship

class User(Base):
    id = Column(String, primary_key=True)
    name = Column(String)
    organization_id = Column(String, ForeignKey('organizations.id'))
    organization = relationship("Organization")  # ❌ Relationship object

# DataFlow pattern
@db.model
class User:
    id: str
    name: str
    organization_id: str  # ✅ Foreign key only (no relationship object)

# Fetch related data in workflow
workflow.add_node("UserReadNode", "get_user", {"id": "user-123"})
workflow.add_node("OrganizationReadNode", "get_org", {
    "id": "$get_user.organization_id"
})
```

### From Django ORM (ForeignKey)

```python
# Django pattern
class Organization(models.Model):
    name = models.CharField(max_length=255)

class User(models.Model):
    name = models.CharField(max_length=255)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)  # ❌ ORM relationship

# DataFlow pattern
@db.model
class Organization:
    id: str
    name: str

@db.model
class User:
    id: str
    name: str
    organization_id: str  # ✅ Foreign key only
```

## Complex Example: E-Commerce Models

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")

# Flat models with foreign keys
@db.model
class Customer:
    id: str
    name: str
    email: str
    address_street: str  # ✅ Flattened address
    address_city: str
    address_state: str
    address_zip: str
    metadata: dict  # ✅ Flexible JSON for custom fields

@db.model
class Product:
    id: str
    name: str
    description: str
    price: float
    category_id: str  # ✅ Foreign key to Category
    images: list  # ✅ List of image URLs
    attributes: dict  # ✅ Flexible product attributes (color, size, etc.)

@db.model
class Category:
    id: str
    name: str
    parent_category_id: str  # ✅ Self-referencing foreign key (nullable)

@db.model
class Order:
    id: str
    customer_id: str  # ✅ Foreign key to Customer
    total: float
    status: str  # "pending", "paid", "shipped", "delivered"
    payment_method: str
    shipping_address_street: str  # ✅ Flattened shipping address
    shipping_address_city: str
    shipping_address_state: str
    shipping_address_zip: str

@db.model
class OrderItem:
    id: str
    order_id: str  # ✅ Foreign key to Order
    product_id: str  # ✅ Foreign key to Product
    quantity: int
    unit_price: float
    subtotal: float

# Create order workflow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()

# Step 1: Create order
workflow.add_node("OrderCreateNode", "create_order", {
    "id": "order-123",
    "customer_id": "customer-456",
    "total": 149.98,
    "status": "pending",
    "payment_method": "credit_card",
    "shipping_address_street": "123 Main St",
    "shipping_address_city": "San Francisco",
    "shipping_address_state": "CA",
    "shipping_address_zip": "94105"
})

# Step 2: Add order items
workflow.add_node("OrderItemBulkCreateNode", "create_items", {
    "records": [
        {
            "id": "item-1",
            "order_id": "order-123",
            "product_id": "product-789",
            "quantity": 2,
            "unit_price": 49.99,
            "subtotal": 99.98
        },
        {
            "id": "item-2",
            "order_id": "order-123",
            "product_id": "product-790",
            "quantity": 1,
            "unit_price": 50.00,
            "subtotal": 50.00
        }
    ]
})

runtime = LocalRuntime()
results, _ = runtime.execute(workflow.build())

order = results["create_order"]
items = results["create_items"]

print(f"Created order {order['id']} with {len(items)} items")
```

## Best Practices

1. **Use primitive types for all fields**
   ```python
   # ✅ CORRECT
   @db.model
   class User:
       id: str
       name: str
       age: int
       is_active: bool
   ```

2. **Model relationships with foreign keys**
   ```python
   # ✅ CORRECT
   @db.model
   class User:
       id: str
       name: str
       organization_id: str  # Foreign key
   ```

3. **Flatten nested structures**
   ```python
   # ✅ CORRECT
   @db.model
   class User:
       id: str
       name: str
       address_street: str  # Flattened
       address_city: str
       address_state: str
   ```

4. **Use dict for flexible JSON data**
   ```python
   # ✅ CORRECT
   @db.model
   class User:
       id: str
       name: str
       metadata: dict  # Flexible structure
   ```

5. **Use separate tables for complex relationships**
   ```python
   # ✅ CORRECT - Junction table
   @db.model
   class UserRole:
       id: str
       user_id: str
       role_id: str
   ```

6. **Store searchable data as top-level fields**
   ```python
   # ✅ CORRECT
   @db.model
   class Product:
       id: str
       name: str
       category: str  # Top-level for queries
       attributes: dict  # Additional flexible data
   ```

## Troubleshooting

### Error: "Field has unsupported type"

**Cause**: Using nested object or custom class as field type

**Fix**: Use foreign key or flatten fields

```python
# ❌ Before
@db.model
class User:
    id: str
    address: Address  # Error!

# ✅ After
@db.model
class User:
    id: str
    address_id: str  # Foreign key
```

### Error: "List[str] not supported"

**Cause**: Using typing hints instead of built-in `list`

**Fix**: Use `list` not `List[str]`

```python
# ❌ Before
from typing import List

@db.model
class User:
    id: str
    tags: List[str]  # Error!

# ✅ After
@db.model
class User:
    id: str
    tags: list  # Correct
```

### Complex nested data structure needed

**Solution**: Use dict field for JSON storage

```python
# ✅ Use dict for complex structures
@db.model
class Product:
    id: str
    name: str
    specifications: dict  # Complex nested data
```

## Related Guides

- [Primary Keys](primary-keys.md) - The `id` field requirement
- [Auto-Managed Fields](auto-managed-fields.md) - Timestamp handling
- [Migration from SQLAlchemy](from-sqlalchemy.md) - Converting ORM relationships
- [Migration from Django ORM](from-django-orm.md) - Converting Django models

## Summary

- **Flat fields only** - No nested objects or custom classes
- **Use foreign keys** - Model relationships with `_id` fields
- **Primitive types** - str, int, float, bool, datetime
- **Simple collections** - list and dict for flexible data
- **Separate tables** - For complex relationships (junction tables)
- **Flatten structures** - `address_street`, `address_city` instead of `address.street`
