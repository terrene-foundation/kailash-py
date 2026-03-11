# DataFlow Relationships Guide

## Overview

DataFlow provides automatic relationship detection and management between your models. When you define models with foreign key fields, DataFlow automatically creates relationship mappings that you can use in your workflows.

## Automatic Relationship Detection

DataFlow analyzes your model definitions and database schema to automatically detect relationships:

### Foreign Key Detection

```python
from dataflow import DataFlow

db = DataFlow()

@db.model
class Author:
    name: str
    bio: str = ""

@db.model
class Post:
    title: str
    content: str
    author_id: int  # DataFlow detects this as foreign key to authors table

# DataFlow automatically creates:
# - Post.author (belongs_to relationship)
# - Author.posts (has_many relationship)
```

### Relationship Types

DataFlow supports three relationship types:

#### 1. Belongs To (Many-to-One)

```python
@db.model
class Order:
    customer_id: int  # Foreign key
    total: float
    status: str = "pending"

# Auto-detected relationship:
# order.customer -> references customers table
```

#### 2. Has Many (One-to-Many)

```python
@db.model
class Customer:
    name: str
    email: str

# Auto-detected reverse relationship:
# customer.orders -> collection of orders where customer_id matches
```

#### 3. Many-to-Many (Junction Tables)

```python
@db.model
class PostTag:
    post_id: int
    tag_id: int

# Creates many-to-many relationship between posts and tags
```

## Using Relationships in Workflows

### Querying Related Data

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Get posts with author information
workflow.add_node("PostListNode", "get_posts", {
    "filter": {"published": True},
    "include_relations": ["author"]  # Include related author data
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Creating Related Records

```python
# Create author first
workflow.add_node("AuthorCreateNode", "create_author", {
    "name": "Jane Smith",
    "bio": "Technology writer"
})

# Create post with relationship
workflow.add_node("PostCreateNode", "create_post", {
    "title": "DataFlow Guide",
    "content": "A comprehensive guide...",
    # author_id will be provided via connection
})

# Connect the author creation to post creation
workflow.add_connection("create_author", "id", "create_post", "author_id")
```

## Relationship Configuration

### Custom Relationship Names

```python
@db.model
class BlogPost:
    author_user_id: int  # Custom foreign key name

    __dataflow__ = {
        'relationships': {
            'author': {
                'type': 'belongs_to',
                'foreign_key': 'author_user_id',
                'target_table': 'users'
            }
        }
    }
```

### Relationship Options

```python
@db.model
class Order:
    customer_id: int

    __dataflow__ = {
        'relationships': {
            'customer': {
                'type': 'belongs_to',
                'foreign_key': 'customer_id',
                'target_table': 'customers',
                'cascade_delete': False,  # Don't delete customer when order deleted
                'eager_load': True        # Always load customer with order
            }
        }
    }
```

## Querying Relationships

### Get Relationship Information

```python
# Get all relationships for a model
relationships = db.get_relationships("Post")
print(relationships)
# Output: {'author': {'type': 'belongs_to', 'target_table': 'authors', ...}}

# Check specific relationship
author_rel = db.get_relationships("Post").get("author")
if author_rel:
    print(f"Post belongs to {author_rel['target_table']}")
```

### Relationship Queries

```python
workflow = WorkflowBuilder()

# Query with relationship filters
workflow.add_node("PostListNode", "author_posts", {
    "filter": {
        "author.name": "Jane Smith",  # Filter by related field
        "published": True
    },
    "join": ["author"],  # Explicit join
    "order_by": ["-created_at"]
})
```

## Performance Considerations

### Eager Loading

```python
# Load posts with authors in single query
workflow.add_node("PostListNode", "posts_with_authors", {
    "eager_load": ["author"],
    "limit": 50
})
```

### Lazy Loading

```python
# Load relationships on demand
workflow.add_node("PostReadNode", "get_post", {"id": 123})
workflow.add_node("AuthorReadNode", "get_author")
workflow.add_connection("get_post", "author_id", "get_author", "id")
```

## Migration Patterns

### Adding Relationships to Existing Models

```python
# 1. Add foreign key column
workflow.add_node("SchemaModificationNode", "add_fk", {
    "table": "posts",
    "operation": "add_column",
    "column": "author_id",
    "type": "INTEGER",
    "references": "authors(id)"
})

# 2. Update existing records
workflow.add_node("PostBulkUpdateNode", "set_authors", {
    "filter": {"author_id": None},
    "update": {"author_id": 1}  # Default author
})
```

### Removing Relationships

```python
# Remove foreign key constraint
workflow.add_node("SchemaModificationNode", "remove_fk", {
    "table": "posts",
    "operation": "drop_constraint",
    "constraint": "fk_posts_author_id"
})
```

## Best Practices

### 1. Consistent Naming

```python
# Good: Clear foreign key naming
class Post:
    author_id: int      # Clear reference to authors table
    category_id: int    # Clear reference to categories table

# Avoid: Ambiguous naming
class Post:
    user: int           # Unclear - which user field?
    parent: int         # Unclear - parent what?
```

### 2. Index Foreign Keys

```python
@db.model
class Post:
    author_id: int
    category_id: int

    __indexes__ = [
        {'fields': ['author_id'], 'name': 'idx_posts_author'},
        {'fields': ['category_id'], 'name': 'idx_posts_category'},
        {'fields': ['author_id', 'category_id'], 'name': 'idx_posts_author_category'}
    ]
```

### 3. Handle Null References

```python
from typing import Optional

@db.model
class Post:
    title: str
    author_id: Optional[int] = None  # Allow posts without authors

    __dataflow__ = {
        'relationships': {
            'author': {
                'type': 'belongs_to',
                'nullable': True  # Handle null author_id gracefully
            }
        }
    }
```

## Troubleshooting

### Common Issues

#### Relationship Not Detected

```python
# Check if model is registered
models = db.get_models()
print("Registered models:", list(models.keys()))

# Check relationship detection
relationships = db.get_relationships("ModelName")
print("Detected relationships:", relationships)

# Force relationship detection
db.discover_schema()  # Re-analyze database schema
```

#### Foreign Key Constraint Errors

```python
# Ensure referenced record exists before creating
workflow.add_node("AuthorCreateNode", "ensure_author", {
    "name": "Default Author"
})
workflow.add_node("PostCreateNode", "create_post", {
    "title": "My Post",
    "content": "Content here"
})
workflow.add_connection("ensure_author", "id", "create_post", "author_id")
```

#### Performance Issues

```python
# Use eager loading for N+1 query prevention
workflow.add_node("PostListNode", "posts", {
    "eager_load": ["author", "category"],  # Load related data
    "limit": 100  # Limit result set
})

# Create appropriate indexes
workflow.add_node("SchemaModificationNode", "add_index", {
    "table": "posts",
    "operation": "create_index",
    "columns": ["author_id", "created_at"],
    "name": "idx_posts_author_date"
})
```

## Advanced Patterns

### Self-Referencing Relationships

```python
@db.model
class Category:
    name: str
    parent_id: Optional[int] = None  # Self-reference

    __dataflow__ = {
        'relationships': {
            'parent': {
                'type': 'belongs_to',
                'target_table': 'categories',
                'foreign_key': 'parent_id'
            },
            'children': {
                'type': 'has_many',
                'target_table': 'categories',
                'foreign_key': 'parent_id'
            }
        }
    }
```

### Polymorphic Relationships

```python
@db.model
class Comment:
    content: str
    commentable_type: str  # "Post" or "Article"
    commentable_id: int    # ID in respective table

    __dataflow__ = {
        'relationships': {
            'commentable': {
                'type': 'polymorphic',
                'type_field': 'commentable_type',
                'id_field': 'commentable_id'
            }
        }
    }
```

### Through Relationships

```python
@db.model
class UserRole:
    user_id: int
    role_id: int
    assigned_at: datetime

@db.model
class User:
    name: str

    __dataflow__ = {
        'relationships': {
            'roles': {
                'type': 'has_many',
                'through': 'user_roles',
                'target_table': 'roles'
            }
        }
    }
```

## Schema Discovery

DataFlow can analyze existing database schemas and generate relationship models:

```python
# Discover relationships from existing database
schema = db.discover_schema()
print("Discovered relationships:", schema)

# Generate model files with relationships
result = db.scaffold("models_with_relationships.py")
print(f"Generated {result['relationships_detected']} relationships")
```

The generated file will include detected relationships:

```python
# Generated models_with_relationships.py
@db.model
class User:
    name: str
    email: str
    # orders = db.has_many("orders", "user_id")

@db.model
class Order:
    user_id: int
    total: float
    # user = db.belongs_to("users", "user_id")
```

## Testing Relationships

```python
# Test relationship detection
def test_relationships():
    db = DataFlow(":memory:")

    @db.model
    class Author:
        name: str

    @db.model
    class Post:
        title: str
        author_id: int

    # Verify relationships detected
    post_rels = db.get_relationships("Post")
    assert "author" in post_rels
    assert post_rels["author"]["type"] == "belongs_to"

    author_rels = db.get_relationships("Author")
    assert "posts" in author_rels
    assert author_rels["posts"]["type"] == "has_many"
```

This comprehensive relationships guide covers all aspects of using relationships in DataFlow, from basic auto-detection to advanced patterns and troubleshooting.
