#!/usr/bin/env python3
"""
DataFlow QueryCache Example

Demonstrates Redis query caching with pattern-based invalidation.
"""

import time

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash_dataflow import DataFlow

# Initialize DataFlow with Redis caching
db = DataFlow(
    enable_query_cache=True,
    redis_host="localhost",
    redis_port=6379,
    cache_invalidation_strategy="pattern_based",
    cache_ttl=300,  # 5 minutes
)


# Define a model
@db.model
class User:
    id: int
    name: str
    email: str
    age: int
    status: str
    created_at: str
    tenant_id: str


def cache_examples():
    """Demonstrate QueryCache capabilities"""

    print("⚡ Redis Query Caching Examples")
    print("=" * 40)

    cache = db.get_query_cache()

    if not cache:
        print("❌ Query cache not initialized. Make sure Redis is running.")
        return

    # Example 1: Basic caching
    print("\n1. Basic Query Caching")
    query = "SELECT * FROM users WHERE age > $1"
    parameters = [21]

    # Simulate query result
    result = {
        "users": [
            {"id": 1, "name": "John", "age": 25, "email": "john@example.com"},
            {"id": 2, "name": "Jane", "age": 30, "email": "jane@example.com"},
        ]
    }

    # Cache the result
    success = cache.set(query, parameters, result, ttl=600)
    print(f"Cache set: {success}")

    # Retrieve from cache
    cached_result = cache.get(query, parameters)
    if cached_result:
        print("✅ Cache hit!")
        print(f"Result: {cached_result['result']}")
        print(f"Cached at: {cached_result['cached_at']}")
    else:
        print("❌ Cache miss")

    # Example 2: Multi-tenant caching
    print("\n2. Multi-Tenant Caching")
    query = "SELECT * FROM users WHERE tenant_id = $1 AND status = $2"

    # Cache for different tenants
    tenants = ["tenant_123", "tenant_456", "tenant_789"]

    for tenant in tenants:
        parameters = [tenant, "active"]
        result = {
            "users": [{"id": 1, "name": f"User from {tenant}", "tenant_id": tenant}]
        }

        # Cache with tenant isolation
        success = cache.set(query, parameters, result, tenant_id=tenant)
        print(f"Cached for {tenant}: {success}")

    # Retrieve tenant-specific cache
    for tenant in tenants:
        parameters = [tenant, "active"]
        cached_result = cache.get(query, parameters, tenant_id=tenant)
        if cached_result:
            user_name = cached_result["result"]["users"][0]["name"]
            print(f"✅ Cache hit for {tenant}: {user_name}")

    # Example 3: Cache invalidation
    print("\n3. Cache Invalidation")

    # Cache multiple queries for users table
    queries = [
        ("SELECT * FROM users WHERE age > $1", [18]),
        ("SELECT * FROM users WHERE status = $1", ["active"]),
        ("SELECT COUNT(*) FROM users", []),
    ]

    for query, params in queries:
        cache.set(query, params, {"data": "sample"}, tenant_id="tenant_123")

    # Invalidate all cache entries for users table
    deleted_count = cache.invalidate_table("users", tenant_id="tenant_123")
    print(f"Invalidated {deleted_count} cache entries for users table")

    # Verify cache is empty
    for query, params in queries:
        cached_result = cache.get(query, params, tenant_id="tenant_123")
        if not cached_result:
            print(f"✅ Cache invalidated for: {query[:30]}...")


def cache_health_monitoring():
    """Demonstrate cache health monitoring"""

    print("\n\n📊 Cache Health Monitoring")
    print("=" * 35)

    cache = db.get_query_cache()

    if not cache:
        print("❌ Query cache not initialized")
        return

    # Health check
    health = cache.health_check()
    print(f"Cache Status: {health['status']}")
    print(f"Redis Ping: {health['redis_ping']}")
    print(f"Read/Write Test: {health['read_write_test']}")
    print(f"Connection: {health['connection']}")

    # Cache statistics
    stats = cache.get_stats()
    print("\nCache Statistics:")
    print(f"Total Keys: {stats['total_keys']}")
    print(f"Hit Rate: {stats['hit_rate']:.2%}")
    print(f"Redis Memory: {stats['redis_memory_used']}")
    print(f"Connected Clients: {stats['redis_connected_clients']}")
    print(f"Invalidation Strategy: {stats['invalidation_strategy']}")
    print(f"Default TTL: {stats['default_ttl']}s")

    # Performance analysis
    if stats["hit_rate"] < 0.5:
        print("⚠️  Low cache hit rate - consider increasing TTL")

    if stats["total_keys"] > 1000:
        print("⚠️  High key count - consider cache cleanup")


def cache_performance_test():
    """Demonstrate cache performance"""

    print("\n\n🚀 Cache Performance Test")
    print("=" * 30)

    cache = db.get_query_cache()

    if not cache:
        print("❌ Query cache not initialized")
        return

    # Performance test
    query = "SELECT * FROM users WHERE id = $1"
    result = {"id": 123, "name": "Test User"}

    # Test cache set performance
    start_time = time.time()
    for i in range(100):
        cache.set(query, [i], result, ttl=60)
    set_time = time.time() - start_time

    # Test cache get performance
    start_time = time.time()
    hits = 0
    for i in range(100):
        cached_result = cache.get(query, [i])
        if cached_result:
            hits += 1
    get_time = time.time() - start_time

    print(
        f"Cache SET: 100 operations in {set_time:.3f}s ({1000*set_time/100:.1f}ms avg)"
    )
    print(
        f"Cache GET: 100 operations in {get_time:.3f}s ({1000*get_time/100:.1f}ms avg)"
    )
    print(f"Hit Rate: {hits}/100 ({hits}%)")

    # Cleanup
    cache.clear_all()
    print("Cache cleared after performance test")


def workflow_cache_integration():
    """Demonstrate cache integration with workflows"""

    print("\n\n🔄 Workflow Cache Integration")
    print("=" * 35)

    # Create workflow with cached queries
    workflow = WorkflowBuilder()

    # Build cached query
    builder = db.build_query("users")
    builder.where("status", "$eq", "active")
    builder.where("age", "$gte", 21)
    sql, params = builder.build_select(["id", "name", "email"])

    # Add cached database node
    workflow.add_node(
        "PythonCodeNode",
        "cached_query",
        {
            "code": f"""
def execute(input_data):
    # Use DataFlow cached query
    result = db.execute_cached_query(
        "{sql}",
        {params},
        tenant_id=input_data.get("tenant_id"),
        ttl=300
    )
    return {{"result": result or "Cache miss - would execute query"}}
"""
        },
    )

    # Add cache invalidation node
    workflow.add_node(
        "PythonCodeNode",
        "invalidate_cache",
        {
            "code": """
def execute(input_data):
    cache = db.get_query_cache()
    if cache:
        deleted = cache.invalidate_table("users", tenant_id=input_data.get("tenant_id"))
        return {"deleted_keys": deleted}
    return {"deleted_keys": 0}
"""
        },
    )

    print("Workflow created with QueryCache integration!")
    print(f"Cached query: {sql}")
    print(f"Parameters: {params}")

    # Execute workflow
    runtime = LocalRuntime()
    print("\nWorkflow ready for execution with cache integration")


if __name__ == "__main__":
    # Run examples
    cache_examples()
    cache_health_monitoring()
    cache_performance_test()
    workflow_cache_integration()

    print("\n✅ QueryCache examples completed!")
    print("\nNext steps:")
    print("1. Start Redis server: redis-server")
    print("2. Run with real database queries")
    print("3. Monitor cache hit rates in production")
    print("4. Tune TTL values based on data patterns")
