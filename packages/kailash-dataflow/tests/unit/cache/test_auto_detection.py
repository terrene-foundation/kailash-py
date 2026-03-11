"""
Unit Tests for Cache Backend Auto-Detection

Tests the automatic detection of Redis availability and fallback
to in-memory cache when Redis is not available.

Tier: 1 (Unit - No external dependencies)
"""

from unittest.mock import MagicMock, patch

import pytest


class TestCacheBackendDetection:
    """Test cache backend auto-detection logic."""

    def test_redis_available_and_connected(self):
        """Test that AsyncRedisCacheAdapter is returned when Redis is available and connectable."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=True):
            with patch(
                "dataflow.cache.auto_detection.test_redis_connection", return_value=True
            ):
                backend = CacheBackend.auto_detect()

                # Should return AsyncRedisCacheAdapter (wraps RedisCacheManager)
                assert backend.__class__.__name__ == "AsyncRedisCacheAdapter"

    def test_redis_module_not_installed(self):
        """Test that InMemoryCache is returned when Redis module is not installed."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=False):
            backend = CacheBackend.auto_detect()

            # Should return InMemoryCache
            assert backend.__class__.__name__ == "InMemoryCache"

    def test_redis_available_but_not_connectable(self):
        """Test fallback to InMemoryCache when Redis module exists but server is unreachable."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=True):
            with patch(
                "dataflow.cache.auto_detection.test_redis_connection",
                return_value=False,
            ):
                backend = CacheBackend.auto_detect()

                # Should fallback to InMemoryCache
                assert backend.__class__.__name__ == "InMemoryCache"

    def test_auto_detect_with_custom_redis_url(self):
        """Test auto-detection with custom Redis URL."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=True):
            with patch(
                "dataflow.cache.auto_detection.test_redis_connection", return_value=True
            ):
                backend = CacheBackend.auto_detect(
                    redis_url="redis://custom-host:6380/0"
                )

                # Should return AsyncRedisCacheAdapter (wraps RedisCacheManager)
                assert backend.__class__.__name__ == "AsyncRedisCacheAdapter"

    def test_auto_detect_with_custom_ttl(self):
        """Test auto-detection with custom TTL configuration."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=False):
            backend = CacheBackend.auto_detect(ttl=600)

            # Should be InMemoryCache with custom TTL
            assert backend.__class__.__name__ == "InMemoryCache"
            assert backend.ttl == 600

    def test_auto_detect_with_custom_max_size(self):
        """Test auto-detection with custom max size for in-memory cache."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=False):
            backend = CacheBackend.auto_detect(max_size=5000)

            # Should be InMemoryCache with custom max_size
            assert backend.__class__.__name__ == "InMemoryCache"
            assert backend.max_size == 5000


class TestRedisAvailabilityCheck:
    """Test Redis availability checking functions."""

    def test_redis_available_when_module_exists(self):
        """Test redis_available returns True when redis module can be imported."""
        from dataflow.cache.auto_detection import redis_available

        with patch("dataflow.cache.auto_detection.redis", MagicMock()):
            assert redis_available() is True

    def test_redis_not_available_when_module_missing(self):
        """Test redis_available returns False when redis module cannot be imported."""
        from dataflow.cache.auto_detection import redis_available

        with patch("dataflow.cache.auto_detection.redis", None):
            assert redis_available() is False

    def test_redis_connection_test_success(self):
        """Test successful Redis connection test."""
        from dataflow.cache.auto_detection import test_redis_connection

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with patch(
            "dataflow.cache.auto_detection.redis.Redis", return_value=mock_redis
        ):
            assert test_redis_connection() is True

    def test_redis_connection_test_failure(self):
        """Test Redis connection test failure."""
        from dataflow.cache.auto_detection import test_redis_connection

        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("Connection refused")

        with patch(
            "dataflow.cache.auto_detection.redis.Redis", return_value=mock_redis
        ):
            assert test_redis_connection() is False

    def test_redis_connection_test_with_custom_url(self):
        """Test Redis connection test with custom URL."""
        from dataflow.cache.auto_detection import test_redis_connection

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with patch(
            "dataflow.cache.auto_detection.redis.Redis", return_value=mock_redis
        ) as mock_redis_cls:
            result = test_redis_connection("redis://custom:6380/1")
            assert result is True


class TestCacheBackendProperties:
    """Test properties and methods of detected backends."""

    @pytest.mark.asyncio
    async def test_redis_backend_has_required_methods(self):
        """Test that Redis backend has required cache methods."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=True):
            with patch(
                "dataflow.cache.auto_detection.test_redis_connection", return_value=True
            ):
                backend = CacheBackend.auto_detect()

                # Check required methods exist
                assert hasattr(backend, "get")
                assert hasattr(backend, "set")
                assert hasattr(backend, "delete")
                assert hasattr(backend, "clear_pattern")
                assert hasattr(backend, "get_stats")
                assert hasattr(backend, "ping")

    @pytest.mark.asyncio
    async def test_memory_backend_has_required_methods(self):
        """Test that in-memory backend has required cache methods."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=False):
            backend = CacheBackend.auto_detect()

            # Check required methods exist
            assert hasattr(backend, "get")
            assert hasattr(backend, "set")
            assert hasattr(backend, "delete")
            assert hasattr(backend, "clear")
            assert hasattr(backend, "get_metrics")
            assert hasattr(backend, "ping")


class TestCacheBackendIntegration:
    """Test integration patterns with detected backends."""

    @pytest.mark.asyncio
    async def test_backend_basic_operations_memory(self):
        """Test basic operations work with in-memory backend."""
        from dataflow.cache.auto_detection import CacheBackend

        with patch("dataflow.cache.auto_detection.redis_available", return_value=False):
            backend = CacheBackend.auto_detect()

            # Test set/get
            await backend.set("test_key", {"data": "value"})
            result = await backend.get("test_key")

            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_backend_basic_operations_redis(self):
        """Test basic operations work with Redis backend."""
        from dataflow.cache.auto_detection import CacheBackend

        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.set.return_value = True
        mock_redis.get.return_value = '{"data": "value"}'

        with patch("dataflow.cache.auto_detection.redis_available", return_value=True):
            with patch(
                "dataflow.cache.auto_detection.test_redis_connection", return_value=True
            ):
                with patch(
                    "dataflow.cache.auto_detection.redis.Redis", return_value=mock_redis
                ):
                    backend = CacheBackend.auto_detect()

                    # Test set/get (now async)
                    await backend.set("test_key", {"data": "value"})
                    result = await backend.get("test_key")

                    assert result == {"data": "value"}
