"""
DataFlow Cache Module

Provides query caching with automatic backend detection (Redis or in-memory)
and automatic invalidation on write operations.

Features:
- Auto-backend detection (Redis → In-memory fallback)
- LRU cache with TTL expiration
- Transparent query result caching
- Auto-invalidation on writes
- Cache metrics and monitoring
"""

from .async_redis_adapter import AsyncRedisCacheAdapter
from .auto_detection import CacheBackend
from .invalidation import CacheInvalidator, InvalidationPattern
from .key_generator import CacheKeyGenerator
from .list_node_integration import (
    CacheableListNode,
    ListNodeCacheIntegration,
    create_cache_integration,
)
from .memory_cache import InMemoryCache
from .redis_manager import CacheConfig, RedisCacheManager

__all__ = [
    # Backend detection
    "CacheBackend",
    # Cache implementations
    "RedisCacheManager",
    "InMemoryCache",
    "AsyncRedisCacheAdapter",
    # Configuration
    "CacheConfig",
    # Key generation
    "CacheKeyGenerator",
    # Invalidation
    "CacheInvalidator",
    "InvalidationPattern",
    # Integration
    "ListNodeCacheIntegration",
    "CacheableListNode",
    "create_cache_integration",
]
