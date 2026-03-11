"""
Cache Backend Auto-Detection

Automatically detects Redis availability and falls back to in-memory cache
when Redis is not available or not connectable.

Usage:
    from dataflow.cache.auto_detection import CacheBackend

    # Auto-detect and create appropriate backend
    cache = CacheBackend.auto_detect()

    # With custom configuration
    cache = CacheBackend.auto_detect(
        redis_url="redis://localhost:6379/0",
        ttl=600,
        max_size=5000
    )
"""

import logging
from typing import Optional, Union

from .async_redis_adapter import AsyncRedisCacheAdapter
from .memory_cache import InMemoryCache
from .redis_manager import CacheConfig, RedisCacheManager

logger = logging.getLogger(__name__)

# Try to import redis module
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


def redis_available() -> bool:
    """
    Check if Redis module is available.

    Returns:
        True if redis module can be imported
    """
    return redis is not None


def test_redis_connection(redis_url: Optional[str] = None, timeout: int = 2) -> bool:
    """
    Test connection to Redis server.

    Args:
        redis_url: Redis connection URL (default: redis://localhost:6379/0)
        timeout: Connection timeout in seconds

    Returns:
        True if connection successful, False otherwise
    """
    if not redis_available():
        return False

    redis_url = redis_url or "redis://localhost:6379/0"

    try:
        # Parse Redis URL
        if redis_url.startswith("redis://"):
            # Extract host, port, db from URL
            url_parts = redis_url.replace("redis://", "").split("/")
            host_port = url_parts[0].split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 6379
            db = int(url_parts[1]) if len(url_parts) > 1 else 0
        else:
            host = "localhost"
            port = 6379
            db = 0

        # Test connection
        client = redis.Redis(
            host=host, port=port, db=db, socket_timeout=timeout, decode_responses=True
        )
        client.ping()
        client.close()
        return True
    except Exception as e:
        logger.debug(f"Redis connection test failed: {e}")
        return False


class CacheBackend:
    """Factory for creating appropriate cache backend."""

    @staticmethod
    def auto_detect(
        redis_url: Optional[str] = None,
        ttl: int = 300,
        max_size: int = 1000,
        **kwargs,
    ) -> Union[AsyncRedisCacheAdapter, InMemoryCache]:
        """
        Automatically detect and create appropriate cache backend.

        Detection Logic:
        1. Check if redis module is installed
        2. If yes, try to connect to Redis server
        3. If connection successful, use RedisCacheManager
        4. Otherwise, fallback to InMemoryCache

        Args:
            redis_url: Redis connection URL (default: redis://localhost:6379/0)
            ttl: Cache TTL in seconds (default: 300)
            max_size: Max cache size for in-memory cache (default: 1000)
            **kwargs: Additional configuration options

        Returns:
            AsyncRedisCacheAdapter if Redis available, InMemoryCache otherwise

        Both return types have async interfaces for consistent usage.

        Examples:
            # Auto-detect with defaults
            cache = CacheBackend.auto_detect()

            # Custom Redis URL
            cache = CacheBackend.auto_detect(
                redis_url="redis://localhost:6380/1"
            )

            # Custom TTL and max size
            cache = CacheBackend.auto_detect(ttl=600, max_size=5000)
        """
        # Check if Redis module is available
        if not redis_available():
            logger.info(
                "Redis module not installed - using in-memory cache. "
                "Install redis with: pip install redis"
            )
            return InMemoryCache(max_size=max_size, ttl=ttl)

        # Test Redis connection
        if not test_redis_connection(redis_url):
            logger.info(
                "Redis server not reachable - falling back to in-memory cache. "
                f"Attempted connection to: {redis_url or 'redis://localhost:6379/0'}"
            )
            return InMemoryCache(max_size=max_size, ttl=ttl)

        # Redis is available and connectable - create async Redis adapter
        logger.info(
            f"Redis server available - using async Redis adapter at {redis_url or 'redis://localhost:6379/0'}"
        )

        # Parse Redis URL to create CacheConfig
        redis_url = redis_url or "redis://localhost:6379/0"
        url_parts = redis_url.replace("redis://", "").split("/")
        host_port = url_parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 6379
        db = int(url_parts[1]) if len(url_parts) > 1 else 0

        # Create CacheConfig
        config = CacheConfig(
            host=host,
            port=port,
            db=db,
            default_ttl=ttl,
            **kwargs,
        )

        # Create sync Redis manager and wrap in async adapter
        redis_manager = RedisCacheManager(config)
        return AsyncRedisCacheAdapter(redis_manager)

    @staticmethod
    def create_redis(
        redis_url: str = "redis://localhost:6379/0", ttl: int = 300, **kwargs
    ) -> RedisCacheManager:
        """
        Explicitly create Redis cache backend.

        Args:
            redis_url: Redis connection URL
            ttl: Cache TTL in seconds
            **kwargs: Additional configuration options

        Returns:
            RedisCacheManager instance

        Raises:
            ImportError: If redis module is not installed
            ConnectionError: If Redis server is not reachable
        """
        if not redis_available():
            raise ImportError(
                "Redis module not installed. Install with: pip install redis"
            )

        # Parse Redis URL
        url_parts = redis_url.replace("redis://", "").split("/")
        host_port = url_parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 6379
        db = int(url_parts[1]) if len(url_parts) > 1 else 0

        # Create CacheConfig
        config = CacheConfig(
            host=host,
            port=port,
            db=db,
            default_ttl=ttl,
            **kwargs,
        )

        # Test connection
        manager = RedisCacheManager(config)
        if not manager.ping():
            raise ConnectionError(
                f"Failed to connect to Redis at {redis_url}. "
                "Ensure Redis server is running."
            )

        return manager

    @staticmethod
    def create_memory(ttl: int = 300, max_size: int = 1000) -> InMemoryCache:
        """
        Explicitly create in-memory cache backend.

        Args:
            ttl: Cache TTL in seconds
            max_size: Maximum cache size (LRU eviction)

        Returns:
            InMemoryCache instance
        """
        return InMemoryCache(max_size=max_size, ttl=ttl)
