#!/usr/bin/env python3
"""
Temporary test to validate main documentation updates in sdk-users/CLAUDE.md
"""

import sys
from pathlib import Path

# Add SDK src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_query_builder_imports():
    """Test that QueryBuilder imports work as documented"""
    try:
        from kailash.nodes.data.query_builder import QueryBuilder, create_query_builder

        print("✅ QueryBuilder imports successful")
        return True
    except ImportError as e:
        print(f"❌ QueryBuilder import failed: {e}")
        return False


def test_query_cache_imports():
    """Test that QueryCache imports work as documented"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        print("✅ QueryCache imports successful")
        return True
    except ImportError as e:
        print(f"❌ QueryCache import failed: {e}")
        return False


def test_query_builder_basic_usage():
    """Test basic QueryBuilder usage as documented"""
    try:
        from kailash.nodes.data.query_builder import create_query_builder

        # Test PostgreSQL builder
        builder = create_query_builder("postgresql")
        builder.table("users").where("age", "$gt", 18).where("status", "$eq", "active")
        sql, params = builder.build_select(["name", "email"])

        # Verify SQL is generated
        assert "SELECT" in sql
        assert "users" in sql
        assert "WHERE" in sql
        assert len(params) == 2

        print("✅ QueryBuilder basic usage successful")
        print(f"   Generated SQL: {sql}")
        print(f"   Parameters: {params}")
        return True
    except Exception as e:
        print(f"❌ QueryBuilder basic usage failed: {e}")
        return False


def test_query_cache_basic_usage():
    """Test basic QueryCache usage as documented"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

        # Test cache creation with pattern-based invalidation
        cache = QueryCache(
            redis_host="localhost",
            redis_port=6379,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        # Test that cache object is created properly
        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

        print("✅ QueryCache basic usage successful")
        print(f"   Cache host: {cache.redis_host}:{cache.redis_port}")
        print(f"   Strategy: {cache.invalidation_strategy}")
        return True
    except Exception as e:
        print(f"❌ QueryCache basic usage failed: {e}")
        return False


def test_enum_values():
    """Test that enum values are accessible"""
    try:
        from kailash.nodes.data.query_cache import CacheInvalidationStrategy

        # Test enum values
        assert CacheInvalidationStrategy.PATTERN_BASED.value == "pattern_based"
        assert CacheInvalidationStrategy.TTL.value == "ttl"
        assert CacheInvalidationStrategy.EVENT_BASED.value == "event_based"

        print("✅ Enum values accessible")
        return True
    except Exception as e:
        print(f"❌ Enum values test failed: {e}")
        return False


def main():
    """Run all documentation validation tests"""
    print("🧪 Testing documentation examples from sdk-users/CLAUDE.md")
    print("=" * 60)

    tests = [
        test_query_builder_imports,
        test_query_cache_imports,
        test_query_builder_basic_usage,
        test_query_cache_basic_usage,
        test_enum_values,
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

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All documentation examples validated successfully!")
        return 0
    else:
        print("💥 Some documentation examples failed validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())
