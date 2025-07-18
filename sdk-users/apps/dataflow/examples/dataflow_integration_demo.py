#!/usr/bin/env python3
"""
DataFlow Integration Demo

Demonstrates QueryBuilder and QueryCache integration with DataFlow engine.
"""

import sys
from pathlib import Path

# Add SDK src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from kailash.nodes.data.query_builder import create_query_builder
from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache


def demo_query_builder_integration():
    """Demonstrate QueryBuilder integration patterns"""

    print("🔧 DataFlow QueryBuilder Integration Demo")
    print("=" * 50)

    # Simulate DataFlow's query builder initialization
    print("\n1. Database Type Detection & Builder Creation")

    database_configs = [
        ("postgresql://localhost/dataflow", "postgresql"),
        ("mysql://localhost/dataflow", "mysql"),
        ("sqlite:///dataflow.db", "sqlite"),
    ]

    for db_url, expected_type in database_configs:
        print(f"\nDatabase URL: {db_url}")

        # Simulate DataFlow's database type detection
        if "postgresql" in db_url or "postgres" in db_url:
            builder = create_query_builder("postgresql")
        elif "mysql" in db_url:
            builder = create_query_builder("mysql")
        else:
            builder = create_query_builder("sqlite")

        print(f"Builder Type: {builder.__class__.__name__}")

        # Test query building
        builder.table("users")
        builder.where("age", "$gt", 18)
        builder.where("status", "$eq", "active")
        sql, params = builder.build_select(["id", "name", "email"])

        print(f"Query: {sql}")
        print(f"Parameters: {params}")


def demo_query_cache_integration():
    """Demonstrate QueryCache integration patterns"""

    print("\n\n⚡ DataFlow QueryCache Integration Demo")
    print("=" * 50)

    # Simulate DataFlow's cache configuration
    cache_configs = [
        ("ttl", CacheInvalidationStrategy.TTL),
        ("manual", CacheInvalidationStrategy.MANUAL),
        ("pattern_based", CacheInvalidationStrategy.PATTERN_BASED),
        ("event_based", CacheInvalidationStrategy.EVENT_BASED),
    ]

    for strategy_name, strategy_enum in cache_configs:
        print(f"\n{strategy_name.upper()} Strategy:")

        # Simulate DataFlow's cache initialization
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            redis_db=0,
            invalidation_strategy=strategy_enum,
            default_ttl=300,
            key_prefix="dataflow:query",
        )

        print(f"Strategy: {cache.invalidation_strategy}")
        print(f"Default TTL: {cache.default_ttl}s")
        print(f"Redis Host: {cache.redis_host}:{cache.redis_port}")

        # Test cache operations
        query = f"SELECT * FROM users WHERE strategy = '{strategy_name}'"
        parameters = [strategy_name]
        result = {"users": [{"id": 1, "name": f"User_{strategy_name}"}]}

        try:
            # Test cache set
            success = cache.set(query, parameters, result, ttl=60)
            print(f"Cache Set: {'Success' if success else 'Failed'}")

            # Test cache get
            cached_result = cache.get(query, parameters)
            if cached_result:
                print(f"Cache Get: Hit - {cached_result['result']}")
            else:
                print("Cache Get: Miss")

        except Exception as e:
            print(f"Cache Test: Failed - {e} (Redis not available)")


def demo_model_enhancement():
    """Demonstrate model enhancement with query features"""

    print("\n\n🎯 DataFlow Model Enhancement Demo")
    print("=" * 45)

    # Simulate DataFlow's model enhancement
    class MockDataFlow:
        def __init__(self):
            self.query_builder = create_query_builder("postgresql")
            self.query_cache = QueryCache(
                redis_host="localhost",
                redis_port=6379,
                invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
                default_ttl=300,
            )

        def build_query(self, table, conditions=None, tenant_id=None):
            """Build a query using the query builder"""
            builder = create_query_builder("postgresql")
            builder.table(table)

            if tenant_id:
                builder.tenant(tenant_id)

            if conditions:
                for field, operator, value in conditions:
                    builder.where(field, operator, value)

            return builder

        def execute_cached_query(self, query, parameters=None, tenant_id=None):
            """Execute a cached query"""
            parameters = parameters or []

            try:
                cached_result = self.query_cache.get(
                    query, parameters, tenant_id=tenant_id
                )
                if cached_result:
                    return cached_result["result"]

                # Simulate query execution
                result = {"message": "Query executed", "query": query[:50] + "..."}
                self.query_cache.set(query, parameters, result, tenant_id=tenant_id)
                return result

            except Exception as e:
                print(f"Cache operation failed: {e}")
                return {
                    "message": "Direct query execution",
                    "query": query[:50] + "...",
                }

    # Create mock DataFlow instance
    db = MockDataFlow()

    # Simulate model enhancement
    class User:
        _dataflow = db
        _table_name = "users"

        @classmethod
        def query_builder(cls):
            """Get query builder for this model's table"""
            return cls._dataflow.build_query(cls._table_name)

        @classmethod
        def cached_query(cls, query, parameters=None, tenant_id=None):
            """Execute cached query for this model"""
            return cls._dataflow.execute_cached_query(query, parameters, tenant_id)

    # Demonstrate enhanced model usage
    print("\n1. Model Query Builder:")
    builder = User.query_builder()
    builder.where("age", "$gt", 18)
    builder.where("status", "$eq", "active")
    sql, params = builder.build_select(["id", "name", "email"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    print("\n2. Model Cached Query:")
    result = User.cached_query(
        "SELECT * FROM users WHERE age > $1", [21], tenant_id="tenant_123"
    )
    print(f"Result: {result}")

    print("\n3. Multi-tenant Query:")
    builder = db.build_query("users", tenant_id="tenant_456")
    builder.where("status", "$in", ["active", "premium"])
    sql, params = builder.build_select(["id", "name"])
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")


def demo_workflow_integration():
    """Demonstrate workflow integration patterns"""

    print("\n\n🔄 DataFlow Workflow Integration Demo")
    print("=" * 45)

    # Simulate workflow integration
    builder = create_query_builder("postgresql")
    builder.table("users")
    builder.where("status", "$eq", "active")
    builder.where("age", "$gte", 21)
    sql, params = builder.build_select(["id", "name", "email"])

    print("1. Query Built for Workflow:")
    print(f"SQL: {sql}")
    print(f"Parameters: {params}")

    # Simulate workflow node configuration
    node_config = {
        "node_type": "AsyncSQLDatabaseNode",
        "parameters": {
            "connection_string": "postgresql://localhost/dataflow",
            "query_template": sql,
            "query_parameters": params,
        },
    }

    print("\n2. Workflow Node Configuration:")
    print(f"Node Type: {node_config['node_type']}")
    print(f"Query Template: {node_config['parameters']['query_template']}")
    print(f"Query Parameters: {node_config['parameters']['query_parameters']}")

    # Simulate cache integration in workflow
    cache_config = {
        "cache_enabled": True,
        "cache_key": f"query:{hash(sql)}",
        "cache_ttl": 300,
        "invalidation_strategy": "pattern_based",
    }

    print("\n3. Cache Integration:")
    print(f"Cache Enabled: {cache_config['cache_enabled']}")
    print(f"Cache Key: {cache_config['cache_key']}")
    print(f"Cache TTL: {cache_config['cache_ttl']}s")
    print(f"Invalidation: {cache_config['invalidation_strategy']}")


def demo_performance_considerations():
    """Demonstrate performance considerations"""

    print("\n\n🚀 DataFlow Performance Demo")
    print("=" * 35)

    # Query complexity examples
    complexity_examples = [
        ("Simple", [("status", "$eq", "active")]),
        ("Medium", [("age", "$gte", 18), ("status", "$in", ["active", "premium"])]),
        (
            "Complex",
            [
                ("age", "$gte", 18),
                ("status", "$in", ["active", "premium"]),
                ("metadata", "$has_key", "preferences"),
                ("name", "$ilike", "%john%"),
            ],
        ),
    ]

    for complexity, conditions in complexity_examples:
        print(f"\n{complexity} Query:")

        builder = create_query_builder("postgresql")
        builder.table("users")

        for field, operator, value in conditions:
            builder.where(field, operator, value)

        sql, params = builder.build_select(["id", "name", "email"])
        print(f"Conditions: {len(conditions)}")
        print(f"Parameters: {len(params)}")
        print(f"SQL Length: {len(sql)} chars")

        # Simulate cache key generation
        cache_key = f"users:{hash(sql)}:{hash(str(params))}"
        print(f"Cache Key: {cache_key[:50]}...")

    # Cache strategy recommendations
    print("\n\nCache Strategy Recommendations:")
    print("• TTL: Best for data that changes predictably")
    print("• Pattern-based: Best for complex multi-table apps")
    print("• Event-based: Best for real-time applications")
    print("• Manual: Best for precise control requirements")


if __name__ == "__main__":
    # Run all demos
    demo_query_builder_integration()
    demo_query_cache_integration()
    demo_model_enhancement()
    demo_workflow_integration()
    demo_performance_considerations()

    print("\n" + "=" * 80)
    print("✅ DataFlow Integration Demo Complete!")
    print("\nKey Integration Points:")
    print("1. Automatic database type detection")
    print("2. QueryBuilder integrated with model classes")
    print("3. Redis cache with tenant isolation")
    print("4. Workflow-ready query generation")
    print("5. Performance-optimized caching strategies")
    print("\nNext Steps:")
    print("• Implement in real DataFlow app")
    print("• Add production monitoring")
    print("• Optimize cache hit rates")
    print("• Test with different database types")
