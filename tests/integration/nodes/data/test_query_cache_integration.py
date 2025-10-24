"""
Integration tests for QueryCache with real Redis
"""

import time

import pytest
import redis
from kailash.nodes.data.query_cache import CacheInvalidationStrategy, QueryCache

from tests.utils.docker_config import get_redis_connection_params


@pytest.mark.integration
@pytest.mark.requires_redis
class TestQueryCacheIntegration:
    """Integration tests for QueryCache with real Redis"""

    def setup_method(self):
        """Set up test environment"""
        # Get Redis connection parameters
        redis_params = get_redis_connection_params()

        # Create cache with real Redis and pattern-based invalidation
        self.cache = QueryCache(
            redis_host=redis_params["host"],
            redis_port=redis_params["port"],
            redis_password=redis_params.get("password"),
            redis_db=redis_params.get("db", 0),
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        # Clear any existing test data
        self.cache.clear_all()

    def teardown_method(self):
        """Clean up test environment"""
        if hasattr(self, "cache"):
            self.cache.clear_all()

    def test_cache_set_and_get_real_redis(self):
        """Test cache set and get operations with real Redis"""
        query = "SELECT * FROM users WHERE id = %s"
        parameters = [123]
        result = {"id": 123, "name": "John", "email": "john@example.com"}

        # Set cache entry
        success = self.cache.set(query, parameters, result)
        assert success is True

        # Get cache entry
        cached_result = self.cache.get(query, parameters)
        assert cached_result is not None
        assert cached_result["result"] == result

    def test_cache_with_tenant_real_redis(self):
        """Test cache operations with tenant isolation using real Redis"""
        query = "SELECT * FROM users WHERE id = %s"
        parameters = [123]
        result1 = {"id": 123, "name": "John", "tenant": "tenant1"}
        result2 = {"id": 123, "name": "Jane", "tenant": "tenant2"}

        # Set cache entries for different tenants
        self.cache.set(query, parameters, result1, tenant_id="tenant1")
        self.cache.set(query, parameters, result2, tenant_id="tenant2")

        # Get cache entries for different tenants
        cached_result1 = self.cache.get(query, parameters, tenant_id="tenant1")
        cached_result2 = self.cache.get(query, parameters, tenant_id="tenant2")

        assert cached_result1 is not None
        assert cached_result2 is not None
        assert cached_result1["result"] == result1
        assert cached_result2["result"] == result2

        # Verify tenant isolation
        assert cached_result1["result"] != cached_result2["result"]

    def test_cache_ttl_real_redis(self):
        """Test cache TTL with real Redis"""
        query = "SELECT * FROM users WHERE id = %s"
        parameters = [123]
        result = {"id": 123, "name": "John"}

        # Set cache entry with 1 second TTL
        success = self.cache.set(query, parameters, result, ttl=1)
        assert success is True

        # Verify entry exists
        cached_result = self.cache.get(query, parameters)
        assert cached_result is not None
        assert cached_result["result"] == result

        # Wait for TTL to expire
        time.sleep(1.1)

        # Verify entry has expired
        cached_result = self.cache.get(query, parameters)
        assert cached_result is None

    def test_cache_invalidation_real_redis(self):
        """Test cache invalidation with real Redis"""
        query = "SELECT * FROM users WHERE id = %s"
        parameters = [123]
        result = {"id": 123, "name": "John"}

        # Set cache entry
        self.cache.set(query, parameters, result)

        # Verify entry exists
        cached_result = self.cache.get(query, parameters)
        assert cached_result is not None
        assert cached_result["result"] == result

        # Invalidate cache entry
        success = self.cache.invalidate(query, parameters)
        assert success is True

        # Verify entry is gone
        cached_result = self.cache.get(query, parameters)
        assert cached_result is None

    def test_cache_table_invalidation_real_redis(self):
        """Test table-based cache invalidation with real Redis"""
        # Set multiple cache entries for the same table
        queries = [
            "SELECT * FROM users WHERE id = %s",
            "SELECT name FROM users WHERE email = %s",
            "SELECT COUNT(*) FROM users",
        ]

        results = [{"id": 123, "name": "John"}, {"name": "Jane"}, {"count": 5}]

        parameters = [[123], ["jane@example.com"], []]

        # Set all cache entries
        for query, params, result in zip(queries, parameters, results):
            self.cache.set(query, params, result)

        # Verify all entries exist
        for query, params, result in zip(queries, parameters, results):
            cached_result = self.cache.get(query, params)
            assert cached_result is not None
            assert cached_result["result"] == result

        # Invalidate all entries for 'users' table
        deleted_count = self.cache.invalidate_table("users")
        assert deleted_count >= 0

        # Verify all entries are gone
        for query, params in zip(queries, parameters):
            cached_result = self.cache.get(query, params)
            assert cached_result is None

    def test_cache_stats_real_redis(self):
        """Test cache statistics with real Redis"""
        query = "SELECT * FROM users WHERE id = %s"
        parameters = [123]
        result = {"id": 123, "name": "John"}

        # Set cache entry
        self.cache.set(query, parameters, result)

        # Get cache hit
        cached_result = self.cache.get(query, parameters)
        assert cached_result is not None
        assert cached_result["result"] == result

        # Get cache miss
        miss_result = self.cache.get("SELECT * FROM posts", [])
        assert miss_result is None

        # Get stats
        stats = self.cache.get_stats()
        assert "redis_keyspace_hits" in stats
        assert "redis_keyspace_misses" in stats
        assert "hit_rate" in stats
        assert stats["redis_keyspace_hits"] >= 0
        assert stats["redis_keyspace_misses"] >= 0

    def test_cache_health_check_real_redis(self):
        """Test cache health check with real Redis"""
        health = self.cache.health_check()
        assert health["status"] == "healthy"
        assert health["redis_ping"] is True
        assert health["read_write_test"] is True
        assert health["connection"] == "active"

    def test_cache_clear_all_real_redis(self):
        """Test cache clear all with real Redis"""
        # Set multiple cache entries
        queries = [
            "SELECT * FROM users WHERE id = %s",
            "SELECT * FROM posts WHERE id = %s",
        ]

        for i, query in enumerate(queries):
            self.cache.set(query, [i], {"id": i, "data": f"test{i}"})

        # Verify entries exist
        for i, query in enumerate(queries):
            cached_result = self.cache.get(query, [i])
            assert cached_result is not None

        # Clear all cache
        deleted_count = self.cache.clear_all()
        assert deleted_count >= 0

        # Verify all entries are gone
        for i, query in enumerate(queries):
            cached_result = self.cache.get(query, [i])
            assert cached_result is None
