# DataFlow Query Patterns

Advanced query patterns and optimization techniques for DataFlow applications.

## ⚠️ Important: Filter Operators Fixed in v0.6.2

**If using v0.6.1 or earlier:** All MongoDB-style filter operators except `$eq` were broken due to a Python truthiness bug.

**Solution:** Upgrade to v0.6.2 or later:
```bash
pip install --upgrade kailash-dataflow>=0.6.3
```

**Fixed Operators:**
- ✅ $ne (not equal)
- ✅ $nin (not in)
- ✅ $in (in)
- ✅ $not (logical NOT)
- ✅ All comparison operators ($gt, $lt, $gte, $lte)

**Root Cause:** Python truthiness check `if filter_dict:` treated empty dict `{}` as False, causing all advanced operators to be skipped.

**Affected Versions:**
- ❌ v0.5.4 - v0.6.1: Broken
- ✅ v0.6.2+: All operators work correctly

---

## Overview

DataFlow provides a powerful query builder that supports MongoDB-style operators while generating optimized SQL queries for your database.

## Basic Query Patterns

### Simple Filters

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Simple equality filter
workflow.add_node("UserListNode", "get_active_users", {
    "filter": {"active": True}
})

# Multiple conditions (implicit AND)
workflow.add_node("UserListNode", "get_adult_users", {
    "filter": {
        "active": True,
        "age": {"$gte": 18}
    }
})

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

### Comparison Operators

```python
# All comparison operators
workflow.add_node("ProductListNode", "query_products", {
    "filter": {
        "price": {"$gt": 10.00},      # Greater than
        "stock": {"$gte": 5},         # Greater than or equal
        "cost": {"$lt": 100.00},      # Less than
        "weight": {"$lte": 50.0},     # Less than or equal
        "category": {"$ne": "draft"}   # Not equal
    }
})

# Range queries
workflow.add_node("OrderListNode", "get_orders_in_range", {
    "filter": {
        "created_at": {
            "$gte": "2024-01-01",
            "$lt": "2024-02-01"
        }
    }
})
```

### Logical Operators

```python
# OR conditions
workflow.add_node("UserListNode", "get_users_or", {
    "filter": {
        "$or": [
            {"role": "admin"},
            {"role": "manager"},
            {"super_user": True}
        ]
    }
})

# AND with OR
workflow.add_node("ProductListNode", "complex_query", {
    "filter": {
        "$and": [
            {"active": True},
            {
                "$or": [
                    {"featured": True},
                    {"views": {"$gt": 1000}}
                ]
            }
        ]
    }
})

# NOT conditions
workflow.add_node("UserListNode", "exclude_users", {
    "filter": {
        "$not": {
            "status": "suspended"
        }
    }
})
```

## Advanced Query Patterns

### Array Operations

```python
# IN operator
workflow.add_node("ProductListNode", "get_products_in_categories", {
    "filter": {
        "category": {"$in": ["electronics", "computers", "phones"]}
    }
})

# NOT IN operator
workflow.add_node("UserListNode", "exclude_roles", {
    "filter": {
        "role": {"$nin": ["guest", "banned"]}
    }
})

# Array contains
workflow.add_node("ProductListNode", "products_with_tag", {
    "filter": {
        "tags": {"$contains": "featured"}
    }
})

# Array overlap
workflow.add_node("ProductListNode", "products_with_any_tag", {
    "filter": {
        "tags": {"$overlap": ["sale", "featured", "new"]}
    }
})
```

### Text Search

```python
# Basic text search
workflow.add_node("ProductListNode", "search_products", {
    "filter": {
        "name": {"$regex": "laptop"}
    }
})

# Case-insensitive search
workflow.add_node("UserListNode", "search_users", {
    "filter": {
        "email": {"$regex": "john", "$options": "i"}
    }
})

# Full-text search (if supported)
workflow.add_node("ProductListNode", "fulltext_search", {
    "filter": {
        "$text": {"$search": "gaming laptop RTX"}
    }
})
```

### JSON/JSONB Queries

```python
# Query JSON fields
workflow.add_node("ProductListNode", "query_json_attributes", {
    "filter": {
        "attributes.color": "red",
        "attributes.size": {"$in": ["M", "L", "XL"]},
        "specifications.weight": {"$lt": 2.5}
    }
})

# Nested JSON queries
workflow.add_node("OrderListNode", "query_nested_json", {
    "filter": {
        "shipping_address.country": "US",
        "shipping_address.state": {"$in": ["CA", "NY", "TX"]}
    }
})
```

## Aggregation Patterns

### Basic Aggregations

```python
# Count with grouping
workflow.add_node("OrderListNode", "orders_by_status", {
    "group_by": "status",
    "aggregations": {
        "count": {"$count": "*"},
        "total_amount": {"$sum": "total"},
        "avg_amount": {"$avg": "total"}
    }
})

# Multiple grouping
workflow.add_node("ProductListNode", "products_by_category_status", {
    "group_by": ["category", "active"],
    "aggregations": {
        "count": {"$count": "*"},
        "total_stock": {"$sum": "stock"},
        "avg_price": {"$avg": "price"},
        "min_price": {"$min": "price"},
        "max_price": {"$max": "price"}
    }
})
```

### Having Clauses

```python
# Filter aggregated results
workflow.add_node("ProductListNode", "popular_categories", {
    "group_by": "category",
    "aggregations": {
        "product_count": {"$count": "*"},
        "total_views": {"$sum": "views"}
    },
    "having": {
        "product_count": {"$gt": 10},
        "total_views": {"$gte": 1000}
    }
})
```

## Query Optimization

### Field Selection

```python
# Select specific fields (reduces data transfer)
workflow.add_node("UserListNode", "get_user_names", {
    "fields": ["id", "name", "email"],
    "filter": {"active": True}
})

# Exclude fields
workflow.add_node("ProductListNode", "products_without_description", {
    "exclude_fields": ["description", "long_description"],
    "filter": {"active": True}
})
```

### Pagination Strategies

```python
# Offset-based pagination
workflow.add_node("ProductListNode", "paginated_products", {
    "filter": {"active": True},
    "order_by": ["created_at"],
    "offset": 20,
    "limit": 10
})

# Cursor-based pagination (more efficient)
workflow.add_node("ProductListNode", "cursor_pagination", {
    "filter": {
        "active": True,
        "id": {"$gt": last_id}  # Use last ID from previous page
    },
    "order_by": ["id"],
    "limit": 10
})

# Keyset pagination
workflow.add_node("OrderListNode", "keyset_pagination", {
    "filter": {
        "$or": [
            {"created_at": {"$lt": last_created_at}},
            {
                "created_at": last_created_at,
                "id": {"$gt": last_id}
            }
        ]
    },
    "order_by": ["-created_at", "id"],
    "limit": 20
})
```

### Index Usage

```python
# Use index hints
workflow.add_node("UserListNode", "indexed_query", {
    "filter": {"email": "user@example.com"},
    "use_index": "idx_email"  # Force specific index
})

# Multi-column index optimization
workflow.add_node("OrderListNode", "optimized_order_query", {
    "filter": {
        "user_id": 123,
        "status": "completed",
        "created_at": {"$gte": "2024-01-01"}
    },
    "order_by": ["-created_at"],
    # Matches index: (user_id, status, created_at)
})
```

## Complex Query Examples

### Dashboard Queries

```python
# Dashboard statistics
workflow = WorkflowBuilder()

# Active users count
workflow.add_node("UserListNode", "active_users", {
    "filter": {"active": True, "last_login": {"$gte": "30 days ago"}},
    "count_only": True
})

# Revenue by category
workflow.add_node("OrderListNode", "revenue_by_category", {
    "filter": {"status": "completed"},
    "join": {
        "table": "order_items",
        "on": "order_items.order_id = orders.id"
    },
    "group_by": "order_items.category",
    "aggregations": {
        "revenue": {"$sum": "order_items.total"},
        "order_count": {"$count": "DISTINCT orders.id"}
    }
})

# Top products
workflow.add_node("ProductListNode", "top_products", {
    "filter": {"active": True},
    "order_by": ["-views", "-sales"],
    "limit": 10,
    "fields": ["id", "name", "price", "views", "sales"]
})
```

### Report Generation

```python
# Monthly sales report
workflow.add_node("OrderListNode", "monthly_sales_report", {
    "filter": {
        "created_at": {
            "$gte": "2024-01-01",
            "$lt": "2024-02-01"
        },
        "status": {"$in": ["completed", "shipped"]}
    },
    "group_by": ["DATE(created_at)", "payment_method"],
    "aggregations": {
        "orders": {"$count": "*"},
        "revenue": {"$sum": "total"},
        "avg_order": {"$avg": "total"},
        "unique_customers": {"$count": "DISTINCT user_id"}
    },
    "order_by": ["DATE(created_at)"]
})
```

### Search with Facets

```python
# Product search with faceted filters
workflow = WorkflowBuilder()

# Main search results
workflow.add_node("ProductListNode", "search_results", {
    "filter": {
        "$and": [
            {"active": True},
            {"name": {"$regex": search_term}},
            {"price": {"$gte": min_price, "$lte": max_price}}
        ]
    },
    "order_by": ["-relevance", "-views"],
    "limit": 20
})

# Category facets
workflow.add_node("ProductListNode", "category_facets", {
    "filter": {
        "active": True,
        "name": {"$regex": search_term}
    },
    "group_by": "category",
    "aggregations": {"count": {"$count": "*"}},
    "order_by": ["-count"],
    "limit": 10
})

# Price range facets
workflow.add_node("ProductListNode", "price_facets", {
    "filter": {
        "active": True,
        "name": {"$regex": search_term}
    },
    "aggregations": {
        "min_price": {"$min": "price"},
        "max_price": {"$max": "price"},
        "avg_price": {"$avg": "price"}
    }
})
```

## Performance Best Practices

### 1. Use Appropriate Indexes

```python
@db.model
class OptimizedProduct:
    name: str
    category: str
    price: float
    active: bool
    created_at: datetime

    __dataflow__ = {
        'indexes': [
            # Single column indexes
            {'name': 'idx_category', 'fields': ['category']},
            {'name': 'idx_active', 'fields': ['active']},

            # Composite indexes for common queries
            {'name': 'idx_active_category', 'fields': ['active', 'category']},
            {'name': 'idx_category_price', 'fields': ['category', 'price']},

            # Covering index
            {'name': 'idx_listing', 'fields': ['active', 'category', 'created_at'],
             'include': ['name', 'price']}
        ]
    }
```

### 2. Optimize Query Structure

```python
# Good: Let database filter first
workflow.add_node("ProductListNode", "efficient_query", {
    "filter": {
        "active": True,  # Most selective first
        "category": "electronics",
        "price": {"$lt": 1000}
    },
    "limit": 100
})

# Avoid: Processing in application
# Don't fetch all then filter in Python
```

### 3. Use Query Caching

```python
# Enable query caching for frequently accessed data
workflow.add_node("ProductListNode", "cached_categories", {
    "filter": {"active": True},
    "group_by": "category",
    "cache": {
        "enabled": True,
        "ttl": 3600,  # 1 hour
        "key": "product_categories"
    }
})
```

### 4. Batch Operations

```python
# Instead of multiple queries
for user_id in user_ids:
    workflow.add_node("UserReadNode", f"get_user_{user_id}", {"id": user_id})

# Use single query with IN
workflow.add_node("UserListNode", "get_users_batch", {
    "filter": {"id": {"$in": user_ids}}
})
```

## Next Steps

- **Bulk Operations**: [Bulk Operations Guide](bulk-operations.md)
- **Performance Tuning**: [Performance Guide](../production/performance.md)
- **Database Optimization**: [Database Guide](../advanced/database-optimization.md)

Query patterns are essential for building efficient DataFlow applications. Choose the right pattern for your use case and always consider performance implications.
