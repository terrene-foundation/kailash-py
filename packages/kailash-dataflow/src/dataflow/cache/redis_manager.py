"""
Redis Cache Manager

Manages Redis connections and cache operations.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Redis cache configuration."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    default_ttl: int = 300  # 5 minutes
    max_connections: int = 50
    socket_timeout: int = 5
    key_prefix: str = "dataflow"
    max_memory_mb: Optional[int] = None
    failover_mode: str = "degraded"  # degraded or fail
    circuit_breaker_enabled: bool = False
    circuit_breaker_threshold: int = 5

    def __post_init__(self):
        """Validate configuration parameters."""
        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        if self.default_ttl <= 0:
            raise ValueError("TTL must be positive")
        if self.max_connections <= 0:
            raise ValueError("Max connections must be positive")
        if self.db < 0:
            raise ValueError("Database index must be non-negative")
        if self.socket_timeout <= 0:
            raise ValueError("Socket timeout must be positive")
        if self.circuit_breaker_threshold <= 0:
            raise ValueError("Circuit breaker threshold must be positive")
        if self.max_memory_mb is not None and self.max_memory_mb <= 0:
            raise ValueError("Max memory must be positive")
        if self.failover_mode not in ["degraded", "fail"]:
            raise ValueError("Failover mode must be 'degraded' or 'fail'")
        if not self.host.strip():
            raise ValueError("Host cannot be empty")
        if not self.key_prefix.strip():
            raise ValueError("Key prefix cannot be empty")


class RedisCacheManager:
    """Manages Redis cache operations."""

    def __init__(self, config: CacheConfig):
        """
        Initialize Redis cache manager.

        Args:
            config: Cache configuration
        """
        self.config = config
        self.default_ttl = config.default_ttl
        self._redis_client = None
        self._circuit_breaker_failures = 0
        self._circuit_breaker_open = False

    @property
    def redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is None:
            if redis is None:
                logger.warning(
                    "Redis module not installed. Cache operations will be disabled."
                )
                return None

            try:
                self._redis_client = redis.Redis(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    decode_responses=True,
                    socket_timeout=self.config.socket_timeout,
                    max_connections=self.config.max_connections,
                )
                # Test connection
                self._redis_client.ping()
                self._circuit_breaker_failures = 0
                self._circuit_breaker_open = False
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._handle_connection_failure()
                return None

        return self._redis_client

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if self._circuit_breaker_open:
            return None

        try:
            client = self.redis_client
            if client is None:
                return None

            value = client.get(key)
            if value is None:
                return None

            # Deserialize JSON
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"Failed to decode cached value for key: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self._handle_operation_failure()
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        if self._circuit_breaker_open:
            return False

        try:
            client = self.redis_client
            if client is None:
                return False

            # Serialize to JSON
            serialized = json.dumps(value, default=self._json_serializer)

            # Set with TTL
            ttl = ttl or self.default_ttl
            result = client.set(key, serialized, ex=ttl)

            self._circuit_breaker_failures = 0
            return bool(result)
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self._handle_operation_failure()
            return False

    def delete(self, key: str) -> int:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            Number of keys deleted
        """
        if self._circuit_breaker_open:
            return 0

        try:
            client = self.redis_client
            if client is None:
                return 0

            return client.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            self._handle_operation_failure()
            return 0

    def delete_many(self, keys: List[str]) -> int:
        """
        Delete multiple keys.

        Args:
            keys: List of cache keys

        Returns:
            Number of keys deleted
        """
        if not keys or self._circuit_breaker_open:
            return 0

        try:
            client = self.redis_client
            if client is None:
                return 0

            return client.delete(*keys)
        except Exception as e:
            logger.error(f"Cache delete_many error: {e}")
            self._handle_operation_failure()
            return 0

    def exists(self, key: str) -> bool:
        """
        Check if key exists.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        if self._circuit_breaker_open:
            return False

        try:
            client = self.redis_client
            if client is None:
                return False

            return client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            self._handle_operation_failure()
            return False

    def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching pattern.

        Args:
            pattern: Key pattern (e.g., "cache:User:*")

        Returns:
            Number of keys deleted
        """
        if self._circuit_breaker_open:
            return 0

        try:
            client = self.redis_client
            if client is None:
                return 0

            # Find matching keys
            keys = list(client.scan_iter(match=pattern))
            if not keys:
                return 0

            # Delete in batch
            return client.delete(*keys)
        except Exception as e:
            logger.error(f"Cache clear_pattern error: {e}")
            self._handle_operation_failure()
            return 0

    def set_many(self, items: List[Tuple[str, Any, Optional[int]]]) -> bool:
        """
        Set multiple items using pipeline.

        Args:
            items: List of (key, value, ttl) tuples

        Returns:
            True if all successful
        """
        if not items or self._circuit_breaker_open:
            return False

        try:
            client = self.redis_client
            if client is None:
                return False

            pipeline = client.pipeline()

            for key, value, ttl in items:
                serialized = json.dumps(value, default=self._json_serializer)
                ttl = ttl or self.default_ttl
                pipeline.set(key, serialized, ex=ttl)

            results = pipeline.execute()
            return all(results)
        except Exception as e:
            logger.error(f"Cache set_many error: {e}")
            self._handle_operation_failure()
            return False

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """
        Get multiple values.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        if not keys or self._circuit_breaker_open:
            return {}

        try:
            client = self.redis_client
            if client is None:
                return {}

            # Get all values
            values = client.mget(keys)

            # Build result dict
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = None
                else:
                    result[key] = None

            return result
        except Exception as e:
            logger.error(f"Cache get_many error: {e}")
            self._handle_operation_failure()
            return {}

    def get_ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        if self._circuit_breaker_open:
            return -1

        try:
            client = self.redis_client
            if client is None:
                return -1

            return client.ttl(key)
        except Exception as e:
            logger.error(f"Cache get_ttl error: {e}")
            return -1

    def extend_ttl(self, key: str, ttl: int) -> bool:
        """Extend TTL for key."""
        if self._circuit_breaker_open:
            return False

        try:
            client = self.redis_client
            if client is None:
                return False

            return client.expire(key, ttl)
        except Exception as e:
            logger.error(f"Cache extend_ttl error: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if self._circuit_breaker_open:
            return {"status": "circuit_breaker_open"}

        try:
            client = self.redis_client
            if client is None:
                return {"status": "disconnected"}

            info = client.info()

            # Calculate hit rate
            hits = info.get("keyspace_hits", 0)
            misses = info.get("keyspace_misses", 0)
            total = hits + misses
            hit_rate = hits / total if total > 0 else 0.0

            return {
                "status": "connected",
                "memory_usage_mb": info.get("used_memory", 0) / (1024 * 1024),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "hit_rate": hit_rate,
                "keyspace_hits": hits,
                "keyspace_misses": misses,
                "circuit_breaker_open": self._circuit_breaker_open,
            }
        except Exception as e:
            logger.error(f"Cache get_stats error: {e}")
            return {"status": "error", "error": str(e)}

    def warmup(self, data: List[Tuple[str, Any]]) -> bool:
        """
        Warmup cache with data.

        Args:
            data: List of (key, value) tuples

        Returns:
            True if successful
        """
        if not data or self._circuit_breaker_open:
            return False

        items = [(key, value, None) for key, value in data]
        return self.set_many(items)

    def can_cache(self) -> bool:
        """Check if caching is possible."""
        if self._circuit_breaker_open:
            return False

        if self.config.max_memory_mb is None:
            return True

        try:
            stats = self.get_stats()
            current_mb = stats.get("memory_usage_mb", 0)
            return current_mb < self.config.max_memory_mb
        except:
            return True

    def ping(self) -> bool:
        """Test Redis connection."""
        try:
            client = self.redis_client
            if client is None:
                return False
            return client.ping()
        except:
            return False

    def _json_serializer(self, obj):
        """JSON serializer for complex types."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        else:
            return str(obj)

    def _handle_connection_failure(self):
        """Handle Redis connection failure."""
        self._circuit_breaker_failures += 1

        if (
            self.config.circuit_breaker_enabled
            and self._circuit_breaker_failures >= self.config.circuit_breaker_threshold
        ):
            self._circuit_breaker_open = True
            logger.warning("Circuit breaker opened due to repeated Redis failures")

    def _handle_operation_failure(self):
        """Handle Redis operation failure."""
        self._circuit_breaker_failures += 1

        if (
            self.config.circuit_breaker_enabled
            and self._circuit_breaker_failures >= self.config.circuit_breaker_threshold
        ):
            self._circuit_breaker_open = True
            logger.warning("Circuit breaker opened due to repeated Redis failures")
