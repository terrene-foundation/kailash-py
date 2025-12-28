"""Tests for Query Cache."""

import json
import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from kailash.nodes.data.query_cache import (
    CacheInvalidationStrategy,
    CachePattern,
    QueryCache,
    QueryCacheKey,
    create_query_cache,
)
from redis.exceptions import RedisError


class TestQueryCacheKey:
    """Test QueryCacheKey functionality."""

    def test_initialization(self):
        """Test cache key generator initialization."""
        key_gen = QueryCacheKey()
        assert key_gen.prefix == "kailash:query"

        key_gen = QueryCacheKey("custom:prefix")
        assert key_gen.prefix == "custom:prefix"

    def test_generate_basic(self):
        """Test basic cache key generation."""
        key_gen = QueryCacheKey()

        query = "SELECT * FROM users WHERE id = $1"
        parameters = [123]

        key = key_gen.generate(query, parameters)
        assert key.startswith("kailash:query:")
        assert len(key.split(":")) == 3

    def test_generate_with_tenant(self):
        """Test cache key generation with tenant."""
        key_gen = QueryCacheKey()

        query = "SELECT * FROM users WHERE id = $1"
        parameters = [123]
        tenant_id = "tenant123"

        key = key_gen.generate(query, parameters, tenant_id)
        assert "tenant:tenant123" in key
        assert len(key.split(":")) == 5

    def test_generate_consistent(self):
        """Test that same query generates same key."""
        key_gen = QueryCacheKey()

        query = "SELECT * FROM users WHERE id = $1"
        parameters = [123]

        key1 = key_gen.generate(query, parameters)
        key2 = key_gen.generate(query, parameters)

        assert key1 == key2

    def test_generate_different_parameters(self):
        """Test that different parameters generate different keys."""
        key_gen = QueryCacheKey()

        query = "SELECT * FROM users WHERE id = $1"

        key1 = key_gen.generate(query, [123])
        key2 = key_gen.generate(query, [456])

        assert key1 != key2

    def test_generate_pattern(self):
        """Test cache key pattern generation."""
        key_gen = QueryCacheKey()

        pattern = key_gen.generate_pattern("users")
        assert pattern == "kailash:query:table:users:*"

    def test_generate_pattern_with_tenant(self):
        """Test cache key pattern generation with tenant."""
        key_gen = QueryCacheKey()

        pattern = key_gen.generate_pattern("users", "tenant123")
        assert pattern == "kailash:query:tenant:tenant123:table:users:*"

    def test_normalize_parameters(self):
        """Test parameter normalization."""
        key_gen = QueryCacheKey()

        # Test datetime normalization
        dt = datetime.now(timezone.utc)
        normalized = key_gen._normalize_parameters([dt])
        assert normalized[0] == dt.isoformat()

        # Test dict normalization
        dict_param = {"key": "value", "number": 123}
        normalized = key_gen._normalize_parameters([dict_param])
        assert normalized[0] == json.dumps(dict_param, sort_keys=True)

        # Test list normalization
        list_param = [1, 2, 3]
        normalized = key_gen._normalize_parameters([list_param])
        assert normalized[0] == json.dumps(list_param, sort_keys=True)

        # Test simple types
        normalized = key_gen._normalize_parameters([123, "string", 45.67])
        assert normalized == [123, "string", 45.67]


class TestQueryCache:
    """Test QueryCache functionality."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        with patch("kailash.nodes.data.query_cache.redis.Redis") as mock_redis_class:
            mock_redis = Mock()
            mock_redis_class.return_value = mock_redis

            # Mock Redis methods
            mock_redis.get.return_value = None
            mock_redis.setex.return_value = True
            mock_redis.delete.return_value = 1
            mock_redis.keys.return_value = []
            mock_redis.ping.return_value = True
            mock_redis.info.return_value = {
                "used_memory_human": "1.2M",
                "connected_clients": 5,
                "keyspace_hits": 100,
                "keyspace_misses": 20,
            }
            mock_redis.sadd.return_value = 1
            mock_redis.expire.return_value = True

            yield mock_redis

    def test_initialization(self):
        """Test query cache initialization."""
        cache = QueryCache()
        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.redis_db == 0
        assert cache.default_ttl == 3600
        assert cache.cache_pattern == CachePattern.CACHE_ASIDE
        assert cache.invalidation_strategy == CacheInvalidationStrategy.TTL

    def test_initialization_custom(self):
        """Test query cache initialization with custom parameters."""
        cache = QueryCache(
            redis_host="custom-host",
            redis_port=6380,
            redis_db=1,
            redis_password="password",
            default_ttl=7200,
            cache_pattern=CachePattern.WRITE_THROUGH,
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED,
        )

        assert cache.redis_host == "custom-host"
        assert cache.redis_port == 6380
        assert cache.redis_db == 1
        assert cache.redis_password == "password"
        assert cache.default_ttl == 7200
        assert cache.cache_pattern == CachePattern.WRITE_THROUGH
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED

    def test_get_cache_miss(self, mock_redis):
        """Test cache get with miss."""
        cache = QueryCache()
        mock_redis.get.return_value = None

        result = cache.get("SELECT * FROM users", [])
        assert result is None
        mock_redis.get.assert_called_once()

    def test_get_cache_hit(self, mock_redis):
        """Test cache get with hit."""
        cache = QueryCache()
        cached_data = {
            "result": {"rows": [{"id": 1, "name": "John"}]},
            "cached_at": "2024-01-01T12:00:00",
            "query_hash": "abc123",
        }
        mock_redis.get.return_value = json.dumps(cached_data)

        result = cache.get("SELECT * FROM users", [])
        assert result == cached_data
        mock_redis.get.assert_called_once()

    def test_get_redis_error(self, mock_redis):
        """Test cache get with Redis error."""
        cache = QueryCache()
        mock_redis.get.side_effect = RedisError("Connection failed")

        result = cache.get("SELECT * FROM users", [])
        assert result is None

    def test_get_json_error(self, mock_redis):
        """Test cache get with JSON decode error."""
        cache = QueryCache()
        mock_redis.get.return_value = "invalid json"

        result = cache.get("SELECT * FROM users", [])
        assert result is None

    def test_set_success(self, mock_redis):
        """Test cache set success."""
        cache = QueryCache()
        mock_redis.setex.return_value = True

        result_data = {"rows": [{"id": 1, "name": "John"}]}
        success = cache.set("SELECT * FROM users", [], result_data)

        assert success is True
        mock_redis.setex.assert_called_once()

        # Check the call arguments
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 3600  # TTL

    def test_set_custom_ttl(self, mock_redis):
        """Test cache set with custom TTL."""
        cache = QueryCache()
        mock_redis.setex.return_value = True

        result_data = {"rows": [{"id": 1, "name": "John"}]}
        success = cache.set("SELECT * FROM users", [], result_data, ttl=7200)

        assert success is True

        # Check the TTL
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 7200  # Custom TTL

    def test_set_with_tenant(self, mock_redis):
        """Test cache set with tenant."""
        cache = QueryCache()
        mock_redis.setex.return_value = True

        result_data = {"rows": [{"id": 1, "name": "John"}]}
        success = cache.set(
            "SELECT * FROM users", [], result_data, tenant_id="tenant123"
        )

        assert success is True
        mock_redis.setex.assert_called_once()

        # Check the cache key includes tenant
        call_args = mock_redis.setex.call_args
        cache_key = call_args[0][0]
        assert "tenant:tenant123" in cache_key

    def test_set_with_pattern_invalidation(self, mock_redis):
        """Test cache set with pattern-based invalidation."""
        cache = QueryCache(
            invalidation_strategy=CacheInvalidationStrategy.PATTERN_BASED
        )
        mock_redis.setex.return_value = True

        result_data = {"rows": [{"id": 1, "name": "John"}]}
        success = cache.set("SELECT * FROM users WHERE id = $1", [123], result_data)

        assert success is True
        mock_redis.setex.assert_called_once()
        mock_redis.sadd.assert_called_once()  # Should add to table index
        mock_redis.expire.assert_called_once()  # Should set index expiry

    def test_set_redis_error(self, mock_redis):
        """Test cache set with Redis error."""
        cache = QueryCache()
        # Set up the mock to raise an exception on setex
        mock_redis.setex.side_effect = RedisError("Connection failed")

        result_data = {"rows": [{"id": 1, "name": "John"}]}
        success = cache.set("SELECT * FROM users", [], result_data)

        assert success is False

    def test_invalidate_success(self, mock_redis):
        """Test cache invalidate success."""
        cache = QueryCache()
        mock_redis.delete.return_value = 1

        success = cache.invalidate("SELECT * FROM users", [])
        assert success is True
        mock_redis.delete.assert_called_once()

    def test_invalidate_not_found(self, mock_redis):
        """Test cache invalidate when key not found."""
        cache = QueryCache()
        mock_redis.delete.return_value = 0

        success = cache.invalidate("SELECT * FROM users", [])
        assert success is False

    def test_invalidate_redis_error(self, mock_redis):
        """Test cache invalidate with Redis error."""
        cache = QueryCache()
        mock_redis.delete.side_effect = RedisError("Connection failed")

        success = cache.invalidate("SELECT * FROM users", [])
        assert success is False

    def test_invalidate_table_success(self, mock_redis):
        """Test table invalidation success."""
        cache = QueryCache()
        mock_redis.keys.return_value = ["key1", "key2", "key3"]
        mock_redis.delete.return_value = 3

        count = cache.invalidate_table("users")
        assert count == 3
        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_called_once_with("key1", "key2", "key3")

    def test_invalidate_table_no_keys(self, mock_redis):
        """Test table invalidation with no keys."""
        cache = QueryCache()
        mock_redis.keys.return_value = []

        count = cache.invalidate_table("users")
        assert count == 0
        mock_redis.keys.assert_called_once()
        mock_redis.delete.assert_not_called()

    def test_invalidate_table_with_tenant(self, mock_redis):
        """Test table invalidation with tenant."""
        cache = QueryCache()
        mock_redis.keys.return_value = ["key1"]
        mock_redis.delete.return_value = 1

        count = cache.invalidate_table("users", tenant_id="tenant123")
        assert count == 1

        # Check the pattern includes tenant
        call_args = mock_redis.keys.call_args
        pattern = call_args[0][0]
        assert "tenant:tenant123" in pattern

    def test_clear_all_global(self, mock_redis):
        """Test clearing all cache globally."""
        cache = QueryCache()
        mock_redis.keys.return_value = ["key1", "key2"]
        mock_redis.delete.return_value = 2

        count = cache.clear_all()
        assert count == 2

        # Check the pattern is global
        call_args = mock_redis.keys.call_args
        pattern = call_args[0][0]
        assert pattern == "kailash:query:*"

    def test_clear_all_tenant(self, mock_redis):
        """Test clearing all cache for tenant."""
        cache = QueryCache()
        mock_redis.keys.return_value = ["key1"]
        mock_redis.delete.return_value = 1

        count = cache.clear_all(tenant_id="tenant123")
        assert count == 1

        # Check the pattern includes tenant
        call_args = mock_redis.keys.call_args
        pattern = call_args[0][0]
        assert "tenant:tenant123" in pattern

    def test_get_stats(self, mock_redis):
        """Test getting cache statistics."""
        cache = QueryCache()
        mock_redis.keys.return_value = ["key1", "key2", "key3"]

        stats = cache.get_stats()

        assert stats["total_keys"] == 3
        assert stats["redis_memory_used"] == "1.2M"
        assert stats["redis_connected_clients"] == 5
        assert stats["redis_keyspace_hits"] == 100
        assert stats["redis_keyspace_misses"] == 20
        assert stats["hit_rate"] == 100 / 120  # hits / (hits + misses)
        assert stats["cache_pattern"] == "cache_aside"
        assert stats["invalidation_strategy"] == "ttl"
        assert stats["default_ttl"] == 3600

    def test_get_stats_no_hits(self, mock_redis):
        """Test getting cache statistics with no hits."""
        cache = QueryCache()
        mock_redis.keys.return_value = []
        mock_redis.info.return_value = {"keyspace_hits": 0, "keyspace_misses": 0}

        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_get_stats_redis_error(self, mock_redis):
        """Test getting cache statistics with Redis error."""
        cache = QueryCache()
        mock_redis.info.side_effect = RedisError("Connection failed")

        stats = cache.get_stats()
        assert "error" in stats
        assert stats["total_keys"] == 0
        assert stats["hit_rate"] == 0.0

    def test_health_check_healthy(self, mock_redis):
        """Test health check when healthy."""
        cache = QueryCache()
        mock_redis.ping.return_value = True
        mock_redis.setex.return_value = True
        mock_redis.get.return_value = "test"
        mock_redis.delete.return_value = 1

        health = cache.health_check()

        assert health["status"] == "healthy"
        assert health["redis_ping"] is True
        assert health["read_write_test"] is True
        assert health["connection"] == "active"

    def test_health_check_ping_failed(self, mock_redis):
        """Test health check when ping fails."""
        cache = QueryCache()
        mock_redis.ping.return_value = False

        health = cache.health_check()

        assert health["status"] == "unhealthy"
        assert health["redis_ping"] is False
        assert "error" in health

    def test_health_check_redis_error(self, mock_redis):
        """Test health check with Redis error."""
        cache = QueryCache()
        mock_redis.ping.side_effect = RedisError("Connection failed")

        health = cache.health_check()

        assert health["status"] == "unhealthy"
        assert health["redis_ping"] is False
        assert "error" in health

    def test_extract_table_name_select(self):
        """Test table name extraction from SELECT."""
        cache = QueryCache()

        table_name = cache._extract_table_name("SELECT * FROM users WHERE id = $1")
        assert table_name == "users"

    def test_extract_table_name_insert(self):
        """Test table name extraction from INSERT."""
        cache = QueryCache()

        table_name = cache._extract_table_name("INSERT INTO users (name) VALUES ($1)")
        assert table_name == "users"

    def test_extract_table_name_update(self):
        """Test table name extraction from UPDATE."""
        cache = QueryCache()

        table_name = cache._extract_table_name(
            "UPDATE users SET name = $1 WHERE id = $2"
        )
        assert table_name == "users"

    def test_extract_table_name_delete(self):
        """Test table name extraction from DELETE."""
        cache = QueryCache()

        table_name = cache._extract_table_name("DELETE FROM users WHERE id = $1")
        assert table_name == "users"

    def test_extract_table_name_unsupported(self):
        """Test table name extraction from unsupported query."""
        cache = QueryCache()

        table_name = cache._extract_table_name("SHOW TABLES")
        assert table_name is None


class TestQueryCacheFactory:
    """Test query cache factory function."""

    def test_create_query_cache_default(self):
        """Test creating query cache with default config."""
        cache = create_query_cache()

        assert cache.redis_host == "localhost"
        assert cache.redis_port == 6379
        assert cache.redis_db == 0
        assert cache.default_ttl == 3600
        assert cache.cache_pattern == CachePattern.CACHE_ASIDE
        assert cache.invalidation_strategy == CacheInvalidationStrategy.TTL

    def test_create_query_cache_custom(self):
        """Test creating query cache with custom config."""
        config = {
            "redis_host": "custom-host",
            "redis_port": 6380,
            "redis_db": 1,
            "redis_password": "password",
            "default_ttl": 7200,
            "cache_pattern": "write_through",
            "invalidation_strategy": "pattern_based",
            "key_prefix": "custom:cache",
        }

        cache = create_query_cache(config)

        assert cache.redis_host == "custom-host"
        assert cache.redis_port == 6380
        assert cache.redis_db == 1
        assert cache.redis_password == "password"
        assert cache.default_ttl == 7200
        assert cache.cache_pattern == CachePattern.WRITE_THROUGH
        assert cache.invalidation_strategy == CacheInvalidationStrategy.PATTERN_BASED
        assert cache.key_generator.prefix == "custom:cache"
