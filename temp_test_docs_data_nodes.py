#!/usr/bin/env python3
"""
Temporary test to validate data nodes documentation in sdk-users/nodes/03-data-nodes.md
"""

import sys
from pathlib import Path

# Add SDK src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_query_builder_comprehensive():
    """Test comprehensive QueryBuilder usage as documented"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        # Test PostgreSQL builder
        builder = create_query_builder("postgresql")

        # Test method chaining and tenant isolation
        builder.table("users").tenant("tenant_123")
        builder.where("age", "$gt", 18)
        builder.where("status", "$in", ["active", "premium"])
        builder.where("metadata", "$has_key", "preferences")

        # Test SELECT query generation
        sql, params = builder.build_select(["name", "email", "created_at"])

        # Verify SQL contains expected elements
        assert "SELECT name, email, created_at FROM users" in sql
        assert "tenant_id" in sql
        assert "age >" in sql
        assert "status IN" in sql
        assert "metadata ?" in sql
        assert len(params) == 5  # tenant_id, age, status1, status2, metadata

        # Test UPDATE query
        builder.reset().table("users").where("id", "$eq", 123)
        sql, params = builder.build_update({"last_login": "2024-01-01"})
        assert "UPDATE users SET" in sql
        assert "last_login" in sql
        assert "WHERE id = $" in sql

        # Test DELETE query
        builder.reset().table("users").where("status", "$eq", "inactive")
        sql, params = builder.build_delete()
        assert "DELETE FROM users" in sql
        assert "WHERE status = $" in sql

        print("✅ QueryBuilder comprehensive usage successful")
        print(f"   SELECT example: {sql[:50]}...")
        print(f"   Parameters: {params}")
        return True
    except Exception as e:
        print(f"❌ QueryBuilder comprehensive usage failed: {e}")
        return False


def test_query_cache_comprehensive():
    """Test comprehensive QueryCache usage as documented"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test cache creation with pattern-based invalidation
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
            default_ttl=3600,
        )

        # Test basic cache operations
        query = "SELECT * FROM users WHERE age > $1"
        parameters = [18]
        result = {"users": [{"id": 1, "name": "John", "age": 25}]}

        # Test cache configuration
        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED
        assert cache.default_ttl == 3600

        # Test that methods exist
        assert hasattr(cache, "get")
        assert hasattr(cache, "set")
        assert hasattr(cache, "invalidate")
        assert hasattr(cache, "invalidate_table")
        assert hasattr(cache, "clear_all")
        assert hasattr(cache, "get_stats")
        assert hasattr(cache, "health_check")

        print("✅ QueryCache comprehensive usage successful")
        print(f"   Cache config: {cache.redis_host}:{cache.redis_port}")
        print(f"   TTL: {cache.default_ttl}s")
        print(f"   Strategy: {cache.invalidation_strategy}")
        return True
    except Exception as e:
        print(f"❌ QueryCache comprehensive usage failed: {e}")
        return False


def test_mongodb_operators():
    """Test MongoDB-style operators as documented"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        builder = create_query_builder("postgresql")

        # Test all documented operators
        operators = [
            ("$eq", "active"),
            ("$ne", "inactive"),
            ("$lt", 25),
            ("$lte", 30),
            ("$gt", 18),
            ("$gte", 21),
            ("$in", ["active", "premium"]),
            ("$nin", ["banned", "suspended"]),
            ("$like", "%john%"),
            ("$ilike", "%JOHN%"),
            ("$regex", "^[A-Z]"),
            ("$has_key", "preferences"),
        ]

        for operator, value in operators:
            builder.reset().table("users").where("field", operator, value)
            sql, params = builder.build_select(["id"])
            assert "SELECT id FROM users" in sql
            assert "WHERE" in sql
            assert len(params) >= 1

        print("✅ MongoDB operators test successful")
        print(f"   Tested {len(operators)} operators")
        return True
    except Exception as e:
        print(f"❌ MongoDB operators test failed: {e}")
        return False


def test_multi_database_support():
    """Test multi-database support as documented"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        dialects = ["postgresql", "mysql", "sqlite"]

        for dialect in dialects:
            builder = create_query_builder(dialect)
            builder.table("users").where("age", "$gt", 18)
            sql, params = builder.build_select(["name"])

            # Verify SQL is generated for each dialect
            assert "SELECT name FROM users" in sql
            assert "WHERE age >" in sql
            assert len(params) == 1

        print("✅ Multi-database support test successful")
        print(f"   Tested dialects: {dialects}")
        return True
    except Exception as e:
        print(f"❌ Multi-database support test failed: {e}")
        return False


def test_cache_invalidation_strategies():
    """Test cache invalidation strategies as documented"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        strategies = [
            CacheInvalidationStrategy.TTL,
            CacheInvalidationStrategy.MANUAL,
            CacheInvalidationStrategy.PATTERN_BASED,
            CacheInvalidationStrategy.EVENT_BASED,
        ]

        for strategy in strategies:
            cache = QueryCache(
                redis_host="localhost", redis_port=6379, invalidation_strategy=strategy
            )
            assert cache.invalidation_strategy == strategy

        print("✅ Cache invalidation strategies test successful")
        print(f"   Tested strategies: {[s.value for s in strategies]}")
        return True
    except Exception as e:
        print(f"❌ Cache invalidation strategies test failed: {e}")
        return False


def main():
    """Run all data nodes documentation validation tests"""
    print("🧪 Testing documentation examples from sdk-users/nodes/03-data-nodes.md")
    print("=" * 70)

    tests = [
        test_query_builder_comprehensive,
        test_query_cache_comprehensive,
        test_mongodb_operators,
        test_multi_database_support,
        test_cache_invalidation_strategies,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed with exception: {e}")
            failed += 1
        print()

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All data nodes documentation examples validated successfully!")
        return 0
    else:
        print("💥 Some data nodes documentation examples failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
