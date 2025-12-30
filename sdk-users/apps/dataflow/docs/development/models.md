# Model Definition Guide

Comprehensive guide to defining database models in DataFlow.

## Basic Model Definition

Models are defined using Python classes with type hints:

```python
from dataflow import DataFlow
from typing import Optional
from datetime import datetime

db = DataFlow()

@db.model
class User:
    # Required fields (no default value)
    name: str
    email: str

    # Optional fields (with defaults)
    active: bool = True
    role: str = "user"

    # 🚨 AUTO-MANAGED FIELDS - NEVER set these manually!
    # DataFlow sets created_at on creation and updated_at on every update
    # Including them in CreateNode or UpdateNode causes DF-104 error:
    # "multiple assignments to same column"
    created_at: datetime = None
    updated_at: datetime = None
```

## Type System

### Supported Python Types

| Python Type | SQL Type | Notes |
|------------|----------|-------|
| `str` | VARCHAR/TEXT | Length specified via metadata |
| `int` | INTEGER/BIGINT | Auto-detect size |
| `float` | FLOAT/DOUBLE | Precision configurable |
| `bool` | BOOLEAN | INTEGER(0,1) in SQLite |
| `datetime` | TIMESTAMP | Auto timezone handling |
| `date` | DATE | Date only |
| `time` | TIME | Time only |
| `bytes` | BLOB/BYTEA | Binary data |
| `dict` | JSON/JSONB | Structured data |
| `list` | JSON/JSONB | Array data |
| `Decimal` | DECIMAL | Precise numbers |
| `UUID` | UUID | Unique identifiers |

### Advanced Type Examples

```python
from decimal import Decimal
from uuid import UUID
from typing import List, Dict, Optional

@db.model
class Product:
    # Basic types
    name: str
    price: Decimal
    stock: int

    # Complex types
    metadata: dict  # Stored as JSON
    tags: List[str]  # JSON array

    # UUID primary key
    id: UUID = None

    # Optional with None default
    description: Optional[str] = None

    # Computed defaults
    sku: str = lambda: f"PROD-{uuid.uuid4().hex[:8]}"
```

## Field Metadata

Add constraints and metadata using field descriptors:

```python
from dataflow.fields import Field

@db.model
class Article:
    # String with length limit
    title: str = Field(max_length=200, nullable=False)

    # Text field (no length limit)
    content: str = Field(text=True)

    # Unique constraint
    slug: str = Field(unique=True, index=True)

    # Numeric constraints
    views: int = Field(default=0, min_value=0)
    rating: float = Field(min_value=0.0, max_value=5.0)

    # Foreign key
    author_id: int = Field(foreign_key="users.id", on_delete="CASCADE")

    # Custom column name
    is_published: bool = Field(column_name="published", default=False)
```

## Model Configuration

Configure model behavior using `__dataflow__`:

```python
@db.model
class Order:
    customer_id: int
    total: Decimal
    status: str = "pending"

    __dataflow__ = {
        # Table configuration
        'table_name': 'customer_orders',  # Custom table name
        'schema': 'sales',  # Database schema

        # Features
        'multi_tenant': True,  # Adds tenant_id field
        'soft_delete': True,   # Adds deleted_at field
        'versioned': True,     # Adds version field
        'audit_log': True,     # Track all changes
        'timestamps': True,    # Add created_at, updated_at

        # Performance
        'cache_enabled': True,
        'cache_ttl': 300,  # 5 minutes

        # Database-specific
        'postgresql': {
            'tablespace': 'fast_ssd',
            'partition_by': 'RANGE (created_at)'
        },
        'mysql': {
            'engine': 'InnoDB',
            'charset': 'utf8mb4'
        }
    }
```

## Indexes

Define indexes for better query performance:

```python
@db.model
class Post:
    title: str
    content: str
    author_id: int
    published: bool = False
    created_at: datetime = None

    __indexes__ = [
        # Simple index
        {"fields": ["author_id"]},

        # Composite index
        {"fields": ["author_id", "published", "created_at"]},

        # Unique index
        {"fields": ["slug"], "unique": True},

        # Partial index (PostgreSQL/SQLite)
        {
            "fields": ["created_at"],
            "where": "published = true",
            "name": "idx_published_posts"
        },

        # Full-text index
        {
            "fields": ["title", "content"],
            "type": "fulltext",  # MySQL
            "type": "gin",       # PostgreSQL with tsvector
        }
    ]
```

## Relationships

Define relationships between models:

```python
@db.model
class Author:
    name: str
    email: str

    # One-to-many relationship
    posts: List["Post"] = Field(back_populates="author")

@db.model
class Post:
    title: str
    content: str

    # Foreign key
    author_id: int = Field(foreign_key="authors.id")

    # Many-to-one relationship
    author: Author = Field(back_populates="posts")

    # Many-to-many through junction table
    tags: List["Tag"] = Field(
        secondary="post_tags",
        back_populates="posts"
    )

@db.model
class Tag:
    name: str = Field(unique=True)

    # Many-to-many
    posts: List[Post] = Field(
        secondary="post_tags",
        back_populates="tags"
    )

# Junction table (automatically created if not exists)
@db.model
class PostTag:
    post_id: int = Field(foreign_key="posts.id", primary_key=True)
    tag_id: int = Field(foreign_key="tags.id", primary_key=True)
    created_at: datetime = None
```

## Computed Fields

Add computed and virtual fields:

```python
@db.model
class Employee:
    first_name: str
    last_name: str
    salary: Decimal

    # Computed on insert/update
    full_name: str = Field(
        computed=lambda obj: f"{obj.first_name} {obj.last_name}"
    )

    # Virtual field (not stored)
    annual_salary: Decimal = Field(
        virtual=True,
        getter=lambda obj: obj.salary * 12
    )

    # Database-computed (PostgreSQL)
    search_vector: str = Field(
        generated="to_tsvector('english', first_name || ' ' || last_name)",
        stored=True
    )
```

## Validation

Add model-level validation:

```python
from dataflow.validators import validate_email, validate_phone

@db.model
class Contact:
    name: str = Field(min_length=2, max_length=100)
    email: str = Field(validator=validate_email)
    phone: str = Field(validator=validate_phone, nullable=True)
    age: int = Field(min_value=0, max_value=150)

    def validate(self):
        """Custom validation logic."""
        if self.age < 18 and not self.parent_consent:
            raise ValueError("Minors require parent consent")

        if self.email.endswith("example.com"):
            raise ValueError("Example domains not allowed")
```

## Inheritance

Use inheritance for shared fields:

```python
# Base model
class TimestampedModel:
    created_at: datetime = None
    updated_at: datetime = None

    class Meta:
        abstract = True  # Don't create table

# Inherit base fields
@db.model
class Article(TimestampedModel):
    title: str
    content: str

@db.model
class Comment(TimestampedModel):
    article_id: int
    content: str
```

## Multi-Tenant Models

Enable automatic tenant isolation:

```python
@db.model
class Document:
    title: str
    content: str

    __dataflow__ = {
        'multi_tenant': True
    }

# Automatically adds:
# - tenant_id field
# - Filters all queries by current tenant
# - Validates tenant access on updates/deletes
```

## Soft Delete

Enable soft deletes to preserve data:

```python
@db.model
class Customer:
    name: str
    email: str

    __dataflow__ = {
        'soft_delete': True
    }

# Automatically adds:
# - deleted_at field
# - Filters out deleted records by default
# - Delete operations set deleted_at instead of removing
```

## Audit Logging

Track all changes to sensitive data:

```python
@db.model
class PaymentMethod:
    customer_id: int
    card_number: str = Field(encrypted=True)
    expires: str

    __dataflow__ = {
        'audit_log': True,
        'audit_fields': ['card_number', 'expires'],  # Track specific fields
        'audit_exclude': ['updated_at']  # Don't track these
    }
```

## Migration Handling

Models automatically generate migrations:

```python
# Initial model
@db.model
class Product:
    name: str
    price: Decimal

# Later: Add field (auto-migration detects)
@db.model
class Product:
    name: str
    price: Decimal
    category: str = "general"  # New field with default

# Run migration
db.auto_migrate()  # Detects and applies changes
```

## Best Practices

### 1. Use Type Hints
```python
# Good
name: str
age: int
tags: List[str]

# Bad
name = ""  # No type hint
```

### 2. Provide Defaults
```python
# Good
status: str = "active"
created_at: datetime = None

# Bad
status: str  # Required field might be forgotten
```

### 3. Index Frequently Queried Fields
```python
@db.model
class User:
    email: str = Field(unique=True, index=True)  # Queried often
    last_login: datetime = Field(index=True)  # Used in filters
```

### 4. Use Appropriate Types
```python
# Good
price: Decimal  # For money
metadata: dict  # For JSON data
tags: List[str]  # For arrays

# Bad
price: float  # Precision issues
metadata: str  # Requires manual JSON handling
```

### 5. Plan for Growth
```python
__dataflow__ = {
    'multi_tenant': True,  # Easy to add tenancy later
    'soft_delete': True,   # Preserve data
    'audit_log': True      # Compliance ready
}
```

## Common Patterns

### User Model
```python
@db.model
class User:
    # Authentication
    email: str = Field(unique=True, index=True)
    username: str = Field(unique=True, index=True)
    password_hash: str = Field(excluded=True)  # Never return

    # Profile
    first_name: str
    last_name: str
    avatar_url: Optional[str] = None

    # Status
    active: bool = True
    verified: bool = False
    role: str = "user"

    # Timestamps
    created_at: datetime = None
    updated_at: datetime = None
    last_login: Optional[datetime] = None

    __dataflow__ = {
        'soft_delete': True,
        'audit_log': True
    }
```

### Product Model
```python
@db.model
class Product:
    # Identity
    sku: str = Field(unique=True, index=True)
    name: str = Field(max_length=200)
    slug: str = Field(unique=True)

    # Details
    description: str = Field(text=True)
    category_id: int = Field(foreign_key="categories.id")

    # Pricing
    price: Decimal = Field(decimal_places=2)
    cost: Decimal = Field(decimal_places=2)

    # Inventory
    stock: int = Field(default=0, min_value=0)
    low_stock_threshold: int = Field(default=10)

    # Metadata
    attributes: dict = Field(default={})
    tags: List[str] = Field(default=[])

    # Status
    active: bool = True
    featured: bool = False

    __indexes__ = [
        {"fields": ["category_id", "active"]},
        {"fields": ["price", "active"]},
        {"fields": ["created_at"], "where": "featured = true"}
    ]
```

---

**Next**: See [Generated Nodes](nodes.md) to learn about the 9 auto-generated nodes for each model.
