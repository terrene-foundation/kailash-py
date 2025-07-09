#!/usr/bin/env python3
"""
Temporary test to validate node selection guide updates
"""

import sys
from pathlib import Path

# Add SDK src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_node_selection_guide_query_builder():
    """Test query builder usage patterns from node selection guide"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        # Test multi-tenant complex queries
        builder = create_query_builder("postgresql")
        builder.table("users").tenant("tenant_123")
        builder.where("age", "$gt", 18).where("status", "$in", ["active", "premium"])
        sql, params = builder.build_select(["name", "email"])

        # Verify SQL is generated correctly
        assert "SELECT name, email FROM users" in sql
        assert "tenant_id" in sql
        assert "age >" in sql
        assert "status IN" in sql
        assert len(params) == 4  # tenant_id, age, status1, status2

        # Test cross-database compatibility
        mysql_builder = create_query_builder("mysql")
        postgres_builder = create_query_builder("postgresql")
        sqlite_builder = create_query_builder("sqlite")

        # Test that all builders work
        for builder_name, builder in [
            ("mysql", mysql_builder),
            ("postgresql", postgres_builder),
            ("sqlite", sqlite_builder),
        ]:
            builder.table("test").where("id", "$eq", 1)
            sql, params = builder.build_select(["name"])
            assert "SELECT name FROM test" in sql
            assert "WHERE id" in sql
            assert len(params) == 1

        print("✅ Query builder usage patterns successful")
        return True
    except Exception as e:
        print(f"❌ Query builder usage patterns failed: {e}")
        return False


def test_node_selection_guide_query_cache():
    """Test query cache usage patterns from node selection guide"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test pattern-based invalidation for complex apps
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        # Test configuration
        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

        # Test that methods exist for tenant isolation
        assert hasattr(cache, "set")
        assert hasattr(cache, "get")
        assert hasattr(cache, "invalidate_table")

        print("✅ Query cache usage patterns successful")
        return True
    except Exception as e:
        print(f"❌ Query cache usage patterns failed: {e}")
        return False


def test_decision_tree_imports():
    """Test that imports mentioned in decision tree work"""
    try:
        # Test imports from decision tree
        from kailash.nodes.data.query_builder import create_query_builder
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test basic functionality
        builder = create_query_builder("postgresql")
        builder.table("users").where("age", "$gt", 18)
        sql, params = builder.build_select(["name"])

        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.TTL,
        )

        print("✅ Decision tree imports successful")
        return True
    except Exception as e:
        print(f"❌ Decision tree imports failed: {e}")
        return False


def main():
    """Run all node selection guide documentation validation tests"""
    print(
        "🧪 Testing documentation examples from sdk-users/nodes/node-selection-guide.md"
    )
    print("=" * 75)

    tests = [
        test_node_selection_guide_query_builder,
        test_node_selection_guide_query_cache,
        test_decision_tree_imports,
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

    print("=" * 75)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print(
            "🎉 All node selection guide documentation examples validated successfully!"
        )
        return 0
    else:
        print("💥 Some node selection guide documentation examples failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
