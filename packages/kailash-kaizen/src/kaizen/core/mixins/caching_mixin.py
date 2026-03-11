"""
Caching Mixin for BaseAgent.

Provides response caching for agent operations including:
- TTL-based cache with configurable expiration
- Hash-based cache key generation
- LRU eviction when cache is full
- Cache bypass for specific requests
"""

import functools
import hashlib
import inspect
import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from kaizen.core.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL cache with LRU eviction."""

    def __init__(self, maxsize: int = 100, ttl: int = 300):
        """
        Initialize TTL cache.

        Args:
            maxsize: Maximum number of entries
            ttl: Time-to-live in seconds
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache: OrderedDict[str, tuple] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            return None

        value, timestamp = self._cache[key]
        if time.time() - timestamp > self.ttl:
            # Expired
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
        """
        # Remove oldest if at capacity
        while len(self._cache) >= self.maxsize:
            self._cache.popitem(last=False)

        self._cache[key] = (value, time.time())

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()

    def __len__(self) -> int:
        """Return number of entries (may include expired)."""
        return len(self._cache)


class CachingMixin:
    """
    Mixin that adds response caching to agents.

    Caches agent responses based on input hash with:
    - Configurable TTL (default 300 seconds)
    - Configurable max size (default 100 entries)
    - LRU eviction when full
    - Deterministic hash-based keys

    Cache can be bypassed by passing cache_bypass=True to run().

    Example:
        config = BaseAgentConfig(caching_enabled=True, cache_ttl=600)
        agent = SimpleQAAgent(config)

        # First call - executes and caches
        result1 = await agent.run(question="test")

        # Second call - returns cached result
        result2 = await agent.run(question="test")

        # Bypass cache
        result3 = await agent.run(question="test", cache_bypass=True)
    """

    @classmethod
    def apply(cls, agent: "BaseAgent", max_size: int = 100, ttl: int = 300) -> None:
        """
        Apply caching behavior to agent.

        Args:
            agent: The agent instance to apply caching to
            max_size: Maximum cache entries (default 100)
            ttl: Cache TTL in seconds (default 300)
        """
        # Get TTL from config if available
        config_ttl = getattr(agent.config, "cache_ttl", None)
        if config_ttl is not None:
            ttl = config_ttl

        agent._cache = TTLCache(maxsize=max_size, ttl=ttl)

        # Store original run method
        original_run = agent.run
        is_async = inspect.iscoroutinefunction(original_run)
        agent_name = agent.__class__.__name__

        if is_async:

            @functools.wraps(original_run)
            async def cached_run_async(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped async run method with caching."""
                # Check for cache bypass
                cache_bypass = kwargs.pop("cache_bypass", False)

                if cache_bypass:
                    return await original_run(*args, **kwargs)

                # Generate cache key
                cache_key = cls._make_cache_key(agent, *args, **kwargs)

                # Check cache
                cached_result = agent._cache.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {agent_name}")
                    return cached_result

                # Execute and cache
                result = await original_run(*args, **kwargs)
                agent._cache.set(cache_key, result)
                logger.debug(f"Cached result for {agent_name}")

                return result

            agent.run = cached_run_async
        else:

            @functools.wraps(original_run)
            def cached_run_sync(*args: Any, **kwargs: Any) -> Dict[str, Any]:
                """Wrapped sync run method with caching."""
                # Check for cache bypass
                cache_bypass = kwargs.pop("cache_bypass", False)

                if cache_bypass:
                    return original_run(*args, **kwargs)

                # Generate cache key
                cache_key = cls._make_cache_key(agent, *args, **kwargs)

                # Check cache
                cached_result = agent._cache.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {agent_name}")
                    return cached_result

                # Execute and cache
                result = original_run(*args, **kwargs)
                agent._cache.set(cache_key, result)
                logger.debug(f"Cached result for {agent_name}")

                return result

            agent.run = cached_run_sync

    @classmethod
    def _make_cache_key(cls, agent: "BaseAgent", *args: Any, **kwargs: Any) -> str:
        """
        Generate deterministic cache key from inputs.

        Args:
            agent: The agent instance
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            SHA256 hash of inputs
        """
        key_data = {
            "agent_class": agent.__class__.__name__,
            "args": [str(a) for a in args] if args else [],
            "kwargs": {k: str(v) for k, v in sorted(kwargs.items())},
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()

    @classmethod
    def clear_cache(cls, agent: "BaseAgent") -> None:
        """
        Clear the agent's cache.

        Args:
            agent: The agent instance
        """
        cache = getattr(agent, "_cache", None)
        if cache:
            cache.clear()
