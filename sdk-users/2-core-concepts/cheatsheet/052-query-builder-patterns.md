# Query Builder & Cache Patterns

*MongoDB-style query building with Redis caching for high-performance applications*

## 🔧 Query Builder Patterns

### Basic Query Building
```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

from kailash.nodes.data.query_builder import create_query_builder

# Create PostgreSQL query builder
builder = create_query_builder("postgresql")

# Basic SELECT query
builder.table("users")
builder.where("age", "$gt", 18)
builder.where("status", "$eq", "active")
sql, params = builder.build_select(["name", "email"])

# Result: SELECT name, email FROM users WHERE age > $1 AND status = $2
# Params: [18, "active"]
```

### MongoDB-Style Operators
```python
from kailash.nodes.data.query_builder import create_query_builder

builder = create_query_builder("postgresql")
builder.table("products")

# Comparison operators
builder.where("price", "$lt", 100)        # price < 100
builder.where("rating", "$gte", 4.5)      # rating >= 4.5
builder.where("stock", "$ne", 0)          # stock != 0

# Array operators
builder.where("category", "$in", ["electronics", "books"])
builder.where("tags", "$nin", ["deprecated", "discontinued"])

# Pattern matching
builder.where("name", "$like", "%phone%")
builder.where("description", "$ilike", "%SALE%")  # PostgreSQL only
builder.where("sku", "$regex", "^[A-Z]{3}-\d{4}$")

# JSON operators (PostgreSQL/MySQL)
builder.where("metadata", "$has_key", "warranty")

sql, params = builder.build_select()
```

### Multi-Tenant Query Isolation
```python
from kailash.nodes.data.query_builder import create_query_builder

def build_tenant_query(tenant_id, user_filters):
    """Build query with automatic tenant isolation."""
    builder = create_query_builder("postgresql")

    # Automatic tenant isolation
    builder.table("users").tenant(tenant_id)

    # Add user filters
    if user_filters.get("min_age"):
        builder.where("age", "$gte", user_filters["min_age"])

    if user_filters.get("status"):
        builder.where("status", "$in", user_filters["status"])

    if user_filters.get("search"):
        builder.where("name", "$ilike", f"%{user_filters['search']}%")

    return builder.build_select(["id", "name", "email", "created_at"])

# Usage
sql, params = build_tenant_query(
    tenant_id="tenant_123",
    user_filters={
        "min_age": 21,
        "status": ["active", "premium"],
        "search": "john"
    }
)
# Result: SELECT id, name, email, created_at FROM users
#         WHERE tenant_id = $1 AND age >= $2 AND status IN ($3, $4) AND name ILIKE $5
```

### Cross-Database Query Building
```python
from kailash.nodes.data.query_builder import create_query_builder

def build_cross_database_query(database_type, table, conditions):
    """Build same query for different databases."""
    builder = create_query_builder(database_type)
    builder.table(table)

    for field, operator, value in conditions:
        builder.where(field, operator, value)

    return builder.build_select()

# PostgreSQL
pg_sql, pg_params = build_cross_database_query(
    "postgresql", "users", [
        ("age", "$gt", 18),
        ("name", "$ilike", "%john%")
    ]
)

# MySQL
mysql_sql, mysql_params = build_cross_database_query(
    "mysql", "users", [
        ("age", "$gt", 18),
        ("name", "$like", "%john%")  # MySQL doesn't have $ilike
    ]
)

# SQLite
sqlite_sql, sqlite_params = build_cross_database_query(
    "sqlite", "users", [
        ("age", "$gt", 18),
        ("name", "$like", "%john%")
    ]
)
```

### Complex Query Composition
```python
from kailash.nodes.data.query_builder import create_query_builder

def build_complex_user_query(filters):
    """Build complex query with multiple conditions."""
    builder = create_query_builder("postgresql")
    builder.table("users").tenant(filters["tenant_id"])

    # Age range
    if filters.get("min_age"):
        builder.where("age", "$gte", filters["min_age"])
    if filters.get("max_age"):
        builder.where("age", "$lte", filters["max_age"])

    # Status filtering
    if filters.get("active_only"):
        builder.where("status", "$eq", "active")
    elif filters.get("status_list"):
        builder.where("status", "$in", filters["status_list"])

    # Metadata filtering
    if filters.get("has_preferences"):
        builder.where("preferences", "$has_key", "theme")

    # Search functionality
    if filters.get("search"):
        builder.where("name", "$ilike", f"%{filters['search']}%")

    # Date range
    if filters.get("created_after"):
        builder.where("created_at", "$gte", filters["created_after"])

    return builder.build_select([
        "id", "name", "email", "status", "created_at", "last_login"
    ])

# Usage
sql, params = build_complex_user_query({
    "tenant_id": "tenant_123",
    "min_age": 21,
    "max_age": 65,
    "active_only": True,
    "has_preferences": True,
    "search": "john",
    "created_after": "2024-01-01"
})
```

### Update and Delete Operations
```python
from kailash.nodes.data.query_builder import create_query_builder

# Update operations
builder = create_query_builder("postgresql")
builder.table("users").tenant("tenant_123")
builder.where("id", "$eq", 123)

sql, params = builder.build_update({
    "last_login": "2024-01-01T12:00:00Z",
    "login_count": 5,
    "updated_at": "2024-01-01T12:00:00Z"
})
# Result: UPDATE users SET last_login = $1, login_count = $2, updated_at = $3
#         WHERE tenant_id = $4 AND id = $5

# Delete operations
builder.reset().table("users").tenant("tenant_123")
builder.where("status", "$eq", "deleted")
builder.where("deleted_at", "$lt", "2023-01-01")

sql, params = builder.build_delete()
# Result: DELETE FROM users WHERE tenant_id = $1 AND status = $2 AND deleted_at < $3
```

## ⚡ Query Cache Patterns

### Basic Query Caching
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Create cache with TTL strategy
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.TTL,
    default_ttl=3600  # 1 hour
)

# Cache query result
query = "SELECT * FROM users WHERE age > $1"
parameters = [18]
result = {"users": [{"id": 1, "name": "John"}]}

# Set cache
success = cache.set(query, parameters, result)

# Get cached result
cached_result = cache.get(query, parameters)
if cached_result:
    print(f"Cache hit: {cached_result['result']}")
else:
    print("Cache miss - execute query")
```

### Multi-Tenant Query Caching
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Create cache with pattern-based invalidation
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def cached_user_query(tenant_id, user_id):
    """Execute query with tenant-isolated caching."""
    query = "SELECT * FROM users WHERE tenant_id = $1 AND id = $2"
    parameters = [tenant_id, user_id]

    # Try cache first
    cached_result = cache.get(query, parameters, tenant_id=tenant_id)
    if cached_result:
        return cached_result["result"]

    # Execute query (simulated)
    result = {"id": user_id, "name": "John", "tenant_id": tenant_id}

    # Cache result with tenant isolation
    cache.set(query, parameters, result, tenant_id=tenant_id, ttl=1800)

    return result

# Usage
user_data = cached_user_query("tenant_123", 456)
```

### Table-Based Cache Invalidation
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Pattern-based invalidation for complex apps
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def update_user_and_invalidate_cache(tenant_id, user_id, updates):
    """Update user data and invalidate related cache entries."""

    # 1. Execute update query (simulated)
    update_query = "UPDATE users SET name = $1, updated_at = $2 WHERE tenant_id = $3 AND id = $4"
    # ... execute update ...

    # 2. Invalidate all cached queries for users table in this tenant
    deleted_count = cache.invalidate_table("users", tenant_id=tenant_id)
    print(f"Invalidated {deleted_count} cache entries for users table")

    # 3. Optionally invalidate specific cache entry
    specific_query = "SELECT * FROM users WHERE tenant_id = $1 AND id = $2"
    cache.invalidate(specific_query, [tenant_id, user_id], tenant_id=tenant_id)

# Usage
update_user_and_invalidate_cache("tenant_123", 456, {"name": "Jane"})
```

### Cache Health Monitoring
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def monitor_cache_health():
    """Monitor cache health and performance."""

    # Check cache health
    health = cache.health_check()
    print(f"Cache status: {health['status']}")
    print(f"Redis connected: {health['redis_ping']}")
    print(f"Read/write test: {health['read_write_test']}")

    # Get cache statistics
    stats = cache.get_stats()
    print(f"Total keys: {stats['total_keys']}")
    print(f"Hit rate: {stats['hit_rate']:.2%}")
    print(f"Redis memory: {stats['redis_memory_used']}")
    print(f"Connected clients: {stats['redis_connected_clients']}")

    # Alert on low hit rate
    if stats['hit_rate'] < 0.5:
        print("⚠️  Cache hit rate is low - consider adjusting TTL or invalidation strategy")

    # Alert on high memory usage
    if "GB" in stats['redis_memory_used']:
        print("⚠️  High Redis memory usage - consider cache cleanup")

# Usage
monitor_cache_health()
```

### Combined Query Builder + Cache Pattern
```python
from kailash.nodes.data.query_builder import create_query_builder
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

class CachedQueryService:
    """Service combining query building with caching."""

    def __init__(self, database_type="postgresql"):
        self.cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
            default_ttl=3600
        )
        self.database_type = database_type

    def find_users(self, tenant_id, filters=None):
        """Find users with caching."""
        # Build query
        builder = create_query_builder(self.database_type)
        builder.table("users").tenant(tenant_id)

        if filters:
            if filters.get("min_age"):
                builder.where("age", "$gte", filters["min_age"])
            if filters.get("status"):
                builder.where("status", "$in", filters["status"])
            if filters.get("search"):
                builder.where("name", "$ilike", f"%{filters['search']}%")

        sql, params = builder.build_select(["id", "name", "email", "status"])

        # Check cache first
        cached_result = self.cache.get(sql, params, tenant_id=tenant_id)
        if cached_result:
            return cached_result["result"]

        # Execute query (simulated)
        result = [{"id": 1, "name": "John", "email": "john@example.com"}]

        # Cache result
        self.cache.set(sql, params, result, tenant_id=tenant_id)

        return result

    def update_user(self, tenant_id, user_id, updates):
        """Update user and invalidate cache."""
        # Build update query
        builder = create_query_builder(self.database_type)
        builder.table("users").tenant(tenant_id)
        builder.where("id", "$eq", user_id)

        sql, params = builder.build_update(updates)

        # Execute update (simulated)
        # ... execute update ...

        # Invalidate cache
        self.cache.invalidate_table("users", tenant_id=tenant_id)

        return {"updated": True}

# Usage
service = CachedQueryService("postgresql")
users = service.find_users("tenant_123", {"min_age": 21, "status": ["active"]})
service.update_user("tenant_123", 123, {"name": "Jane Doe"})
```

## 🔄 Advanced Cache Strategies

### Write-Through Caching
```python
from kailash.nodes.data.query_cache import QueryCache, CachePattern

# Write-through cache automatically updates cache on writes
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    cache_pattern=CachePattern.WRITE_THROUGH,
    default_ttl=3600
)

# Cache automatically updated when data changes
def update_user_write_through(user_id, updates):
    # Update database
    # ... execute update ...

    # Cache is automatically updated due to WRITE_THROUGH pattern
    pass
```

### Event-Based Invalidation
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Event-based invalidation for real-time applications
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.EVENT_BASED
)

def on_user_updated(event):
    """Handle user update event."""
    tenant_id = event["tenant_id"]
    user_id = event["user_id"]

    # Invalidate specific user cache
    cache.invalidate_table("users", tenant_id=tenant_id)

    # Invalidate related caches
    cache.invalidate_table("user_profiles", tenant_id=tenant_id)
    cache.invalidate_table("user_permissions", tenant_id=tenant_id)
```

## 🛡️ Best Practices

### Query Builder Best Practices
1. **Always use parameter binding** - QueryBuilder prevents SQL injection automatically
2. **Use tenant isolation** - Call `.tenant()` for multi-tenant applications
3. **Reset builder state** - Call `.reset()` when reusing builders
4. **Choose appropriate dialect** - Use correct database dialect for optimizations
5. **Validate inputs** - QueryBuilder validates operators and values

### Cache Best Practices
1. **Choose appropriate TTL** - Balance freshness vs performance
2. **Use pattern-based invalidation** - For complex applications with table relationships
3. **Monitor cache health** - Check hit rates and Redis memory usage
4. **Implement cache warming** - Pre-populate cache for critical queries
5. **Handle cache failures gracefully** - Degrade gracefully when Redis is unavailable

### Combined Usage Best Practices
1. **Cache expensive queries** - Use QueryCache for slow or frequently-executed queries
2. **Invalidate on updates** - Clear cache when underlying data changes
3. **Use tenant isolation** - Both QueryBuilder and QueryCache support multi-tenancy
4. **Monitor performance** - Track query execution times and cache hit rates
5. **Test with real data** - Validate query builders with actual database schemas
