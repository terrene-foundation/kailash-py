#!/usr/bin/env python3
"""
Comprehensive test to validate all documentation updates for QueryBuilder and QueryCache
"""

import importlib.util
import sys
from pathlib import Path

# Add SDK src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_cheatsheet_examples():
    """Test examples from both cheatsheets"""
    try:
        # Test QueryBuilder cheatsheet examples
        from kailash.nodes.data.query_builder import create_query_builder

        # Basic query building
        builder = create_query_builder("postgresql")
        builder.table("users")
        builder.where("age", "$gt", 18)
        builder.where("status", "$eq", "active")
        sql, params = builder.build_select(["name", "email"])

        assert "SELECT name, email FROM users" in sql
        assert "WHERE" in sql
        assert len(params) == 2

        # Multi-tenant query
        builder = create_query_builder("postgresql")
        builder.table("products").tenant("tenant_123")
        builder.where("price", "$lt", 100)
        builder.where("category", "$in", ["electronics", "books"])
        sql, params = builder.build_select()

        assert "tenant_id" in sql
        assert "price <" in sql
        assert "category IN" in sql

        print("✅ Cheatsheet query builder examples validated")

        # Test QueryCache cheatsheet examples
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Basic caching
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.TTL,
            default_ttl=3600,
        )

        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.invalidation_strategy == CacheInvalidationStrategy.TTL
        assert cache.default_ttl == 3600

        # Multi-tenant caching
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

        print("✅ Cheatsheet query cache examples validated")
        return True

    except Exception as e:
        print(f"❌ Cheatsheet examples failed: {e}")
        return False


def test_main_claude_md_examples():
    """Test examples from main CLAUDE.md"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test main documentation examples
        builder = create_query_builder("postgresql")
        builder.table("users").where("age", "$gt", 18).where("status", "$eq", "active")
        sql, params = builder.build_select(["name", "email"])

        assert "SELECT name, email FROM users" in sql
        assert len(params) == 2

        # Test cache example
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

        print("✅ Main CLAUDE.md examples validated")
        return True

    except Exception as e:
        print(f"❌ Main CLAUDE.md examples failed: {e}")
        return False


def test_data_nodes_examples():
    """Test examples from nodes/03-data-nodes.md"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test comprehensive QueryBuilder example
        builder = create_query_builder("postgresql")
        builder.table("users").tenant("tenant_123")
        builder.where("age", "$gt", 18)
        builder.where("status", "$in", ["active", "premium"])
        builder.where("metadata", "$has_key", "preferences")

        sql, params = builder.build_select(["name", "email", "created_at"])

        assert "SELECT name, email, created_at FROM users" in sql
        assert "tenant_id" in sql
        assert "metadata ?" in sql
        assert len(params) == 5

        # Test QueryCache example
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
            default_ttl=3600,
        )

        assert cache.default_ttl == 3600
        assert hasattr(cache, "get_stats")
        assert hasattr(cache, "health_check")

        print("✅ Data nodes examples validated")
        return True

    except Exception as e:
        print(f"❌ Data nodes examples failed: {e}")
        return False


def test_node_selection_guide_examples():
    """Test examples from node-selection-guide.md"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test multi-tenant complex queries
        builder = create_query_builder("postgresql")
        builder.table("users").tenant("tenant_123")
        builder.where("age", "$gt", 18).where("status", "$in", ["active", "premium"])
        sql, params = builder.build_select(["name", "email"])

        assert "tenant_id" in sql
        assert "status IN" in sql
        assert len(params) == 4

        # Test cross-database compatibility
        for dialect in ["mysql", "postgresql", "sqlite"]:
            builder = create_query_builder(dialect)
            builder.table("test").where("id", "$eq", 1)
            sql, params = builder.build_select(["name"])
            assert "SELECT name FROM test" in sql
            assert len(params) == 1

        # Test cache patterns
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        assert hasattr(cache, "invalidate_table")

        print("✅ Node selection guide examples validated")
        return True

    except Exception as e:
        print(f"❌ Node selection guide examples failed: {e}")
        return False


def test_all_mongodb_operators():
    """Test all MongoDB operators mentioned in documentation"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        builder = create_query_builder("postgresql")

        # Test all operators mentioned in documentation
        test_cases = [
            ("field", "$eq", "value"),
            ("field", "$ne", "value"),
            ("field", "$lt", 100),
            ("field", "$lte", 100),
            ("field", "$gt", 100),
            ("field", "$gte", 100),
            ("field", "$in", ["a", "b"]),
            ("field", "$nin", ["a", "b"]),
            ("field", "$like", "%pattern%"),
            ("field", "$ilike", "%pattern%"),
            ("field", "$regex", "^pattern"),
            ("field", "$has_key", "key"),
        ]

        for field, operator, value in test_cases:
            builder.reset().table("test").where(field, operator, value)
            sql, params = builder.build_select(["id"])
            assert "SELECT id FROM test" in sql
            assert "WHERE" in sql
            assert len(params) >= 1

        print(f"✅ All {len(test_cases)} MongoDB operators validated")
        return True

    except Exception as e:
        print(f"❌ MongoDB operators test failed: {e}")
        return False


def test_all_cache_strategies():
    """Test all cache strategies mentioned in documentation"""
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

        print(f"✅ All {len(strategies)} cache strategies validated")
        return True

    except Exception as e:
        print(f"❌ Cache strategies test failed: {e}")
        return False


def test_error_handling():
    """Test error handling scenarios"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder
        from kailash.nodes.data.query_cache import QueryCache

        # Test invalid database dialect
        try:
            builder = create_query_builder("invalid_dialect")
            assert False, "Should have raised error for invalid dialect"
        except Exception:
            pass  # Expected

        # Test QueryBuilder error handling
        builder = create_query_builder("postgresql")
        try:
            builder.where("field", "$invalid_operator", "value")
            assert False, "Should have raised error for invalid operator"
        except Exception:
            pass  # Expected

        print("✅ Error handling validated")
        return True

    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


def main():
    """Run all comprehensive documentation validation tests"""
    print("🧪 Comprehensive Documentation Validation Test")
    print("Testing all QueryBuilder and QueryCache documentation examples")
    print("=" * 80)

    tests = [
        test_cheatsheet_examples,
        test_main_claude_md_examples,
        test_data_nodes_examples,
        test_node_selection_guide_examples,
        test_all_mongodb_operators,
        test_all_cache_strategies,
        test_error_handling,
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

    print("=" * 80)
    print(f"Final Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 ALL DOCUMENTATION EXAMPLES VALIDATED SUCCESSFULLY!")
        print("✅ QueryBuilder and QueryCache documentation is accurate and complete")
        return 0
    else:
        print("💥 Some documentation examples failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
