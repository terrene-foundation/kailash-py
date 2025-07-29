# Query Cache Patterns

*Enterprise-grade query result caching with Redis for high-performance applications*

## ⚡ Basic Cache Operations

### Simple Query Caching
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

from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Create cache with TTL strategy
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.TTL,
    default_ttl=3600
)

# Cache a query result
query = "SELECT * FROM users WHERE age > $1"
parameters = [18]
result = {"users": [{"id": 1, "name": "John", "age": 25}]}

# Set cache entry
success = cache.set(query, parameters, result)

# Retrieve cached result
cached_result = cache.get(query, parameters)
if cached_result:
    print(f"Cache hit: {cached_result['result']}")
    print(f"Cached at: {cached_result['cached_at']}")
else:
    print("Cache miss - need to execute query")
```

### Cache with Custom TTL
```python
from kailash.nodes.data.query_cache import QueryCache

cache = QueryCache(redis_host="localhost", redis_port=6379)

# Cache with different TTL values
query = "SELECT * FROM users WHERE id = $1"
parameters = [123]
result = {"id": 123, "name": "John"}

# Cache for 30 minutes
cache.set(query, parameters, result, ttl=1800)

# Cache for 1 hour
cache.set(query, parameters, result, ttl=3600)

# Cache for 24 hours
cache.set(query, parameters, result, ttl=86400)
```

## 🏢 Multi-Tenant Cache Patterns

### Tenant-Isolated Caching
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Pattern-based invalidation for multi-tenant apps
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def cache_user_data(tenant_id, user_id):
    """Cache user data with tenant isolation."""
    query = "SELECT * FROM users WHERE tenant_id = $1 AND id = $2"
    parameters = [tenant_id, user_id]

    # Check cache with tenant isolation
    cached_result = cache.get(query, parameters, tenant_id=tenant_id)
    if cached_result:
        return cached_result["result"]

    # Simulate database query
    result = {"id": user_id, "name": "John", "tenant_id": tenant_id}

    # Cache with tenant isolation
    cache.set(query, parameters, result, tenant_id=tenant_id)

    return result

# Usage for different tenants
user_data_tenant1 = cache_user_data("tenant_1", 123)
user_data_tenant2 = cache_user_data("tenant_2", 123)  # Different cache entry
```

### Cross-Tenant Cache Management
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def manage_tenant_cache(tenant_id, operation):
    """Manage cache for specific tenant."""

    if operation == "clear":
        # Clear all cache entries for tenant
        deleted_count = cache.clear_all(tenant_id=tenant_id)
        print(f"Cleared {deleted_count} cache entries for tenant {tenant_id}")

    elif operation == "invalidate_users":
        # Invalidate users table cache for tenant
        deleted_count = cache.invalidate_table("users", tenant_id=tenant_id)
        print(f"Invalidated {deleted_count} user cache entries for tenant {tenant_id}")

    elif operation == "stats":
        # Get cache statistics (global)
        stats = cache.get_stats()
        print(f"Total cache keys: {stats['total_keys']}")
        print(f"Cache hit rate: {stats['hit_rate']:.2%}")

# Usage
manage_tenant_cache("tenant_123", "clear")
manage_tenant_cache("tenant_123", "invalidate_users")
manage_tenant_cache("tenant_123", "stats")
```

## 🔄 Cache Invalidation Strategies

### TTL-Based Invalidation
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# TTL-based invalidation (default)
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.TTL,
    default_ttl=3600
)

def cache_with_ttl_strategy():
    """Cache entries automatically expire after TTL."""
    query = "SELECT * FROM products WHERE category = $1"
    parameters = ["electronics"]
    result = {"products": [{"id": 1, "name": "Phone"}]}

    # Cache for 1 hour (default)
    cache.set(query, parameters, result)

    # Cache for 5 minutes
    cache.set(query, parameters, result, ttl=300)

    # Entries automatically expire - no manual invalidation needed
```

### Manual Cache Invalidation
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Manual invalidation for precise control
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.MANUAL
)

def update_product_with_manual_invalidation(product_id, updates):
    """Update product and manually invalidate cache."""

    # Execute update query
    # ... update database ...

    # Manually invalidate specific cache entries
    queries_to_invalidate = [
        ("SELECT * FROM products WHERE id = $1", [product_id]),
        ("SELECT * FROM products WHERE category = $1", ["electronics"]),
        ("SELECT COUNT(*) FROM products", [])
    ]

    for query, params in queries_to_invalidate:
        cache.invalidate(query, params)

    return {"updated": True}
```

### Pattern-Based Invalidation
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

# Pattern-based invalidation for complex relationships
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
)

def update_user_with_pattern_invalidation(tenant_id, user_id, updates):
    """Update user and invalidate related cache patterns."""

    # Execute update query
    # ... update database ...

    # Invalidate all cache entries for users table
    # This uses the internal index to find all related cache keys
    deleted_count = cache.invalidate_table("users", tenant_id=tenant_id)
    print(f"Invalidated {deleted_count} cache entries for users table")

    # Invalidate related tables
    cache.invalidate_table("user_profiles", tenant_id=tenant_id)
    cache.invalidate_table("user_permissions", tenant_id=tenant_id)

    return {"updated": True}
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

class EventDrivenCacheManager:
    """Manage cache invalidation based on events."""

    def __init__(self):
        self.cache = cache

    def on_user_created(self, event):
        """Handle user creation event."""
        tenant_id = event["tenant_id"]

        # Invalidate user list queries
        self.cache.invalidate_table("users", tenant_id=tenant_id)

        # Invalidate count queries
        count_queries = [
            ("SELECT COUNT(*) FROM users WHERE tenant_id = $1", [tenant_id]),
            ("SELECT COUNT(*) FROM users WHERE tenant_id = $1 AND status = $2", [tenant_id, "active"])
        ]

        for query, params in count_queries:
            self.cache.invalidate(query, params, tenant_id=tenant_id)

    def on_user_updated(self, event):
        """Handle user update event."""
        tenant_id = event["tenant_id"]
        user_id = event["user_id"]

        # Invalidate specific user cache
        self.cache.invalidate(
            "SELECT * FROM users WHERE tenant_id = $1 AND id = $2",
            [tenant_id, user_id],
            tenant_id=tenant_id
        )

        # Invalidate user lists
        self.cache.invalidate_table("users", tenant_id=tenant_id)

    def on_user_deleted(self, event):
        """Handle user deletion event."""
        tenant_id = event["tenant_id"]

        # Invalidate all user-related cache
        self.cache.invalidate_table("users", tenant_id=tenant_id)
        self.cache.invalidate_table("user_profiles", tenant_id=tenant_id)
        self.cache.invalidate_table("user_sessions", tenant_id=tenant_id)

# Usage
manager = EventDrivenCacheManager()
manager.on_user_created({"tenant_id": "tenant_123", "user_id": 456})
manager.on_user_updated({"tenant_id": "tenant_123", "user_id": 456})
manager.on_user_deleted({"tenant_id": "tenant_123", "user_id": 456})
```

## 🔧 Cache Patterns

### Cache-Aside Pattern
```python
from kailash.nodes.data.query_cache import QueryCache, CachePattern

# Cache-aside (lazy loading) - default pattern
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    cache_pattern=CachePattern.CACHE_ASIDE
)

def get_user_profile(user_id):
    """Get user profile with cache-aside pattern."""
    query = "SELECT * FROM user_profiles WHERE user_id = $1"
    parameters = [user_id]

    # 1. Check cache first
    cached_result = cache.get(query, parameters)
    if cached_result:
        return cached_result["result"]

    # 2. Cache miss - query database
    result = {"user_id": user_id, "name": "John", "email": "john@example.com"}

    # 3. Store in cache for next time
    cache.set(query, parameters, result, ttl=1800)

    return result
```

### Write-Through Pattern
```python
from kailash.nodes.data.query_cache import QueryCache, CachePattern

# Write-through caching
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    cache_pattern=CachePattern.WRITE_THROUGH
)

def update_user_profile_write_through(user_id, updates):
    """Update user profile with write-through caching."""

    # 1. Update database
    # ... execute update query ...

    # 2. Update cache immediately (write-through)
    query = "SELECT * FROM user_profiles WHERE user_id = $1"
    parameters = [user_id]

    # Get updated data
    updated_result = {"user_id": user_id, "name": updates.get("name", "John")}

    # Cache is automatically updated due to WRITE_THROUGH pattern
    cache.set(query, parameters, updated_result)

    return updated_result
```

### Write-Behind Pattern
```python
from kailash.nodes.data.query_cache import QueryCache, CachePattern

# Write-behind (write-back) caching
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    cache_pattern=CachePattern.WRITE_BEHIND
)

def update_user_profile_write_behind(user_id, updates):
    """Update user profile with write-behind caching."""

    # 1. Update cache immediately
    query = "SELECT * FROM user_profiles WHERE user_id = $1"
    parameters = [user_id]

    updated_result = {"user_id": user_id, "name": updates.get("name", "John")}
    cache.set(query, parameters, updated_result)

    # 2. Database update happens asynchronously (write-behind)
    # This would typically be handled by a background process

    return updated_result
```

### Refresh-Ahead Pattern
```python
from kailash.nodes.data.query_cache import QueryCache, CachePattern

# Refresh-ahead caching
cache = QueryCache(
    redis_host="localhost",
    redis_port=6379,
    cache_pattern=CachePattern.REFRESH_AHEAD
)

def get_user_profile_refresh_ahead(user_id):
    """Get user profile with refresh-ahead caching."""
    query = "SELECT * FROM user_profiles WHERE user_id = $1"
    parameters = [user_id]

    # Check cache
    cached_result = cache.get(query, parameters)

    if cached_result:
        # Cache hit - check if refresh is needed
        cached_time = cached_result["cached_at"]
        # ... check if cache is near expiration ...

        # If near expiration, trigger async refresh
        # This would typically be handled by a background process

        return cached_result["result"]
    else:
        # Cache miss - fetch from database
        result = {"user_id": user_id, "name": "John", "email": "john@example.com"}
        cache.set(query, parameters, result, ttl=1800)
        return result
```

## 📊 Cache Monitoring and Health

### Cache Health Monitoring
```python
from kailash.nodes.data.query_cache import QueryCache

cache = QueryCache(redis_host="localhost", redis_port=6379)

def monitor_cache_health():
    """Monitor cache health and performance."""

    # Comprehensive health check
    health = cache.health_check()

    print(f"Cache Status: {health['status']}")
    print(f"Redis Ping: {health['redis_ping']}")
    print(f"Read/Write Test: {health['read_write_test']}")
    print(f"Connection: {health['connection']}")

    # Alert on unhealthy cache
    if health["status"] != "healthy":
        print("🚨 Cache is unhealthy!")
        return False

    return True

def get_cache_statistics():
    """Get detailed cache statistics."""
    stats = cache.get_stats()

    print(f"Total Cache Keys: {stats['total_keys']}")
    print(f"Hit Rate: {stats['hit_rate']:.2%}")
    print(f"Redis Memory Used: {stats['redis_memory_used']}")
    print(f"Connected Clients: {stats['redis_connected_clients']}")
    print(f"Cache Pattern: {stats['cache_pattern']}")
    print(f"Invalidation Strategy: {stats['invalidation_strategy']}")
    print(f"Default TTL: {stats['default_ttl']}s")

    # Performance analysis
    if stats['hit_rate'] < 0.5:
        print("⚠️  Low cache hit rate - consider increasing TTL")

    if stats['total_keys'] > 10000:
        print("⚠️  High key count - consider cache cleanup")

    return stats

# Usage
if monitor_cache_health():
    get_cache_statistics()
```

### Cache Performance Optimization
```python
from kailash.nodes.data.query_cache import QueryCache, CacheInvalidationStrategy

def optimize_cache_performance():
    """Optimize cache configuration for performance."""

    # High-performance cache configuration
    cache = QueryCache(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0,
        default_ttl=1800,  # 30 minutes
        invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        key_prefix="app:v1:query"
    )

    # Cache warming for critical queries
    critical_queries = [
        ("SELECT * FROM users WHERE status = $1", ["active"]),
        ("SELECT * FROM products WHERE featured = $1", [True]),
        ("SELECT COUNT(*) FROM orders WHERE status = $1", ["pending"])
    ]

    for query, params in critical_queries:
        # Simulate database query
        result = {"data": "cached_data"}
        cache.set(query, params, result, ttl=3600)  # Cache for 1 hour

    print("Cache warmed with critical queries")

    return cache

# Usage
optimized_cache = optimize_cache_performance()
```

## 🛠️ Advanced Cache Patterns

### Distributed Cache with Failover
```python
from kailash.nodes.data.query_cache import QueryCache

class DistributedCacheManager:
    """Manage distributed cache with failover."""

    def __init__(self):
        self.primary_cache = QueryCache(
            redis_host="redis-primary",
            redis_port=6379
        )
        self.secondary_cache = QueryCache(
            redis_host="redis-secondary",
            redis_port=6379
        )

    def get_with_failover(self, query, parameters, tenant_id=None):
        """Get from cache with automatic failover."""
        try:
            # Try primary cache first
            result = self.primary_cache.get(query, parameters, tenant_id=tenant_id)
            if result:
                return result
        except Exception as e:
            print(f"Primary cache failed: {e}")

        try:
            # Fallback to secondary cache
            result = self.secondary_cache.get(query, parameters, tenant_id=tenant_id)
            if result:
                return result
        except Exception as e:
            print(f"Secondary cache failed: {e}")

        return None

    def set_with_replication(self, query, parameters, result, tenant_id=None, ttl=None):
        """Set cache with replication."""
        success_count = 0

        # Set in primary cache
        try:
            if self.primary_cache.set(query, parameters, result, tenant_id=tenant_id, ttl=ttl):
                success_count += 1
        except Exception as e:
            print(f"Primary cache set failed: {e}")

        # Set in secondary cache
        try:
            if self.secondary_cache.set(query, parameters, result, tenant_id=tenant_id, ttl=ttl):
                success_count += 1
        except Exception as e:
            print(f"Secondary cache set failed: {e}")

        return success_count > 0

# Usage
distributed_cache = DistributedCacheManager()
result = distributed_cache.get_with_failover("SELECT * FROM users", [])
distributed_cache.set_with_replication("SELECT * FROM users", [], {"users": []})
```

### Cache Partitioning
```python
from kailash.nodes.data.query_cache import QueryCache
import hashlib

class PartitionedCacheManager:
    """Manage partitioned cache across multiple Redis instances."""

    def __init__(self, cache_nodes):
        self.caches = [
            QueryCache(redis_host=node["host"], redis_port=node["port"])
            for node in cache_nodes
        ]

    def _get_partition(self, key):
        """Get partition for key using consistent hashing."""
        hash_value = int(hashlib.md5(key.encode()).hexdigest(), 16)
        return hash_value % len(self.caches)

    def get(self, query, parameters, tenant_id=None):
        """Get from partitioned cache."""
        cache_key = f"{query}:{str(parameters)}"
        if tenant_id:
            cache_key = f"{tenant_id}:{cache_key}"

        partition = self._get_partition(cache_key)
        return self.caches[partition].get(query, parameters, tenant_id=tenant_id)

    def set(self, query, parameters, result, tenant_id=None, ttl=None):
        """Set in partitioned cache."""
        cache_key = f"{query}:{str(parameters)}"
        if tenant_id:
            cache_key = f"{tenant_id}:{cache_key}"

        partition = self._get_partition(cache_key)
        return self.caches[partition].set(query, parameters, result, tenant_id=tenant_id, ttl=ttl)

# Usage
partitioned_cache = PartitionedCacheManager([
    {"host": "redis-1", "port": 6379},
    {"host": "redis-2", "port": 6379},
    {"host": "redis-3", "port": 6379}
])
result = partitioned_cache.get("SELECT * FROM users", [])
partitioned_cache.set("SELECT * FROM users", [], {"users": []})
```

## 🔒 Security and Best Practices

### Secure Cache Configuration
```python
from kailash.nodes.data.query_cache import QueryCache

# Secure cache configuration
cache = QueryCache(
    redis_host="redis.internal",
    redis_port=6379,
    redis_password="secure_password",
    redis_db=1,  # Use dedicated database
    key_prefix="myapp:prod:query"  # Namespace keys
)

def secure_cache_operations():
    """Demonstrate secure cache operations."""

    # Sanitize sensitive data before caching
    def sanitize_result(result):
        """Remove sensitive fields from cache."""
        if isinstance(result, dict):
            # Remove sensitive fields
            sanitized = {k: v for k, v in result.items()
                        if k not in ["password", "ssn", "credit_card"]}
            return sanitized
        return result

    # Cache with sanitization
    query = "SELECT * FROM users WHERE id = $1"
    parameters = [123]
    raw_result = {"id": 123, "name": "John", "password": "secret"}

    # Sanitize before caching
    sanitized_result = sanitize_result(raw_result)
    cache.set(query, parameters, sanitized_result, ttl=1800)

    return sanitized_result
```

### Cache Best Practices Summary
1. **Use appropriate TTL values** - Balance performance vs data freshness
2. **Implement proper invalidation** - Use pattern-based for complex relationships
3. **Monitor cache health** - Track hit rates and Redis performance
4. **Handle cache failures** - Implement graceful degradation
5. **Sanitize sensitive data** - Don't cache passwords or PII
6. **Use tenant isolation** - Prevent cross-tenant data leakage
7. **Optimize key naming** - Use consistent, descriptive cache keys
8. **Implement cache warming** - Pre-populate cache for critical queries
9. **Monitor memory usage** - Prevent Redis OOM conditions
10. **Use appropriate patterns** - Choose cache pattern based on use case
