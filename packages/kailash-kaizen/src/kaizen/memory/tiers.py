"""
Memory tier implementations for the enterprise memory system.

This module provides the core memory tier classes that form the foundation
of the enterprise memory system with hot, warm, and cold storage tiers.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MemoryTier(ABC):
    """Abstract base class for memory tiers"""

    def __init__(self, name: str):
        self.name = name
        self._stats = {"hits": 0, "misses": 0, "puts": 0, "deletes": 0, "evictions": 0}
        self._lock = threading.RLock()

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve data from tier"""
        pass

    @abstractmethod
    async def put(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store data in tier"""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete data from tier"""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in tier"""
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """Clear all data from tier"""
        pass

    @abstractmethod
    async def size(self) -> int:
        """Get current size of tier"""
        pass

    def get_stats(self) -> Dict[str, int]:
        """Get tier statistics"""
        with self._lock:
            return self._stats.copy()

    def _record_hit(self):
        """Record a cache hit"""
        with self._lock:
            self._stats["hits"] += 1

    def _record_miss(self):
        """Record a cache miss"""
        with self._lock:
            self._stats["misses"] += 1

    def _record_put(self):
        """Record a put operation"""
        with self._lock:
            self._stats["puts"] += 1

    def _record_delete(self):
        """Record a delete operation"""
        with self._lock:
            self._stats["deletes"] += 1

    def _record_eviction(self):
        """Record an eviction"""
        with self._lock:
            self._stats["evictions"] += 1


class HotMemoryTier(MemoryTier):
    """In-memory cache with <1ms access time"""

    def __init__(self, max_size: int = 1000, eviction_policy: str = "lru"):
        super().__init__("hot")
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._access_times: Dict[str, float] = {}
        self._ttl_data: Dict[str, float] = {}
        self.max_size = max_size
        self.eviction_policy = eviction_policy.lower()

        if self.eviction_policy not in ["lru", "lfu", "fifo"]:
            raise ValueError(f"Unsupported eviction policy: {eviction_policy}")

        if self.eviction_policy == "lfu":
            self._access_counts: Dict[str, int] = {}

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve data from hot tier with <1ms target"""
        start_time = time.perf_counter()

        try:
            with self._lock:
                # Check TTL first
                if key in self._ttl_data:
                    if time.time() > self._ttl_data[key]:
                        # Expired, remove it
                        self._remove_key(key)
                        self._record_miss()
                        return None

                if key in self._cache:
                    # Update access tracking
                    self._access_times[key] = time.time()
                    if self.eviction_policy == "lfu":
                        self._access_counts[key] = self._access_counts.get(key, 0) + 1

                    # Move to end for LRU
                    if self.eviction_policy == "lru":
                        self._cache.move_to_end(key)

                    value = self._cache[key]
                    self._record_hit()

                    # Log performance if it exceeds target
                    elapsed = (time.perf_counter() - start_time) * 1000  # ms
                    if elapsed > 1.0:
                        logger.warning(
                            f"Hot tier access took {elapsed:.2f}ms, exceeds <1ms target"
                        )

                    return value

                self._record_miss()
                return None

        except Exception as e:
            logger.error(f"Error in HotMemoryTier.get({key}): {e}")
            self._record_miss()
            return None

    async def put(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Store data in hot tier"""
        try:
            with self._lock:
                # Handle capacity
                if len(self._cache) >= self.max_size and key not in self._cache:
                    await self._evict_item()

                # Store the value
                self._cache[key] = value
                self._access_times[key] = time.time()

                if self.eviction_policy == "lfu":
                    self._access_counts[key] = self._access_counts.get(key, 0) + 1

                # Handle TTL
                if ttl:
                    self._ttl_data[key] = time.time() + ttl
                elif key in self._ttl_data:
                    del self._ttl_data[key]

                self._record_put()
                return True

        except Exception as e:
            logger.error(f"Error in HotMemoryTier.put({key}): {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete data from hot tier"""
        try:
            with self._lock:
                if key in self._cache:
                    self._remove_key(key)
                    self._record_delete()
                    return True
                return False

        except Exception as e:
            logger.error(f"Error in HotMemoryTier.delete({key}): {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in hot tier"""
        try:
            with self._lock:
                # Check TTL first
                if key in self._ttl_data:
                    if time.time() > self._ttl_data[key]:
                        self._remove_key(key)
                        return False

                return key in self._cache

        except Exception as e:
            logger.error(f"Error in HotMemoryTier.exists({key}): {e}")
            return False

    async def clear(self) -> bool:
        """Clear all data from hot tier"""
        try:
            with self._lock:
                self._cache.clear()
                self._access_times.clear()
                self._ttl_data.clear()
                if hasattr(self, "_access_counts"):
                    self._access_counts.clear()
                return True

        except Exception as e:
            logger.error(f"Error in HotMemoryTier.clear(): {e}")
            return False

    async def size(self) -> int:
        """Get current size of hot tier"""
        with self._lock:
            return len(self._cache)

    def _remove_key(self, key: str):
        """Remove key from all internal structures"""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_times:
            del self._access_times[key]
        if key in self._ttl_data:
            del self._ttl_data[key]
        if hasattr(self, "_access_counts") and key in self._access_counts:
            del self._access_counts[key]

    async def _evict_item(self):
        """Evict item based on configured policy"""
        if not self._cache:
            return

        if self.eviction_policy == "lru":
            # Remove least recently used (first item in OrderedDict)
            key = next(iter(self._cache))
        elif self.eviction_policy == "fifo":
            # Remove first in, first out
            key = next(iter(self._cache))
        elif self.eviction_policy == "lfu":
            # Remove least frequently used
            key = min(self._access_counts, key=self._access_counts.get)
        else:
            # Fallback to LRU
            key = next(iter(self._cache))

        self._remove_key(key)
        self._record_eviction()
        logger.debug(
            f"Evicted key '{key}' from hot tier using {self.eviction_policy} policy"
        )

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        with self._lock:
            stats = self.get_stats()
            total_ops = stats["hits"] + stats["misses"]

            return {
                "hit_rate": stats["hits"] / total_ops if total_ops > 0 else 0.0,
                "miss_rate": stats["misses"] / total_ops if total_ops > 0 else 0.0,
                "current_size": len(self._cache),
                "max_size": self.max_size,
                "utilization": (
                    len(self._cache) / self.max_size if self.max_size > 0 else 0.0
                ),
                "evictions": stats["evictions"],
                "policy": self.eviction_policy,
                **stats,
            }


class TierManager:
    """Manages data movement and policies between memory tiers"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._access_patterns: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Configuration for tier promotion/demotion
        self.hot_promotion_threshold = config.get(
            "hot_promotion_threshold", 5
        )  # accesses
        self.warm_promotion_threshold = config.get(
            "warm_promotion_threshold", 3
        )  # accesses
        self.access_window_seconds = config.get("access_window_seconds", 3600)  # 1 hour
        self.cold_demotion_threshold = config.get(
            "cold_demotion_threshold", 86400
        )  # 1 day

    async def record_access(self, key: str, tier: str):
        """Record access pattern for tier management"""
        current_time = time.time()

        with self._lock:
            if key not in self._access_patterns:
                self._access_patterns[key] = {
                    "accesses": [],
                    "current_tier": tier,
                    "last_access": current_time,
                    "created": current_time,
                }

            pattern = self._access_patterns[key]
            pattern["accesses"].append(current_time)
            pattern["current_tier"] = tier
            pattern["last_access"] = current_time

            # Clean old accesses outside window
            cutoff_time = current_time - self.access_window_seconds
            pattern["accesses"] = [t for t in pattern["accesses"] if t > cutoff_time]

    async def should_promote(self, key: str, from_tier: str, to_tier: str) -> bool:
        """Determine if key should be promoted to higher tier"""
        with self._lock:
            if key not in self._access_patterns:
                return False

            pattern = self._access_patterns[key]
            recent_accesses = len(pattern["accesses"])

            # Promote to hot tier
            if to_tier == "hot" and from_tier in ["warm", "cold"]:
                return recent_accesses >= self.hot_promotion_threshold

            # Promote to warm tier
            if to_tier == "warm" and from_tier == "cold":
                return recent_accesses >= self.warm_promotion_threshold

            return False

    async def should_demote(self, key: str, from_tier: str) -> Optional[str]:
        """Determine if key should be demoted to lower tier"""
        with self._lock:
            if key not in self._access_patterns:
                return None

            pattern = self._access_patterns[key]
            current_time = time.time()
            time_since_access = current_time - pattern["last_access"]

            # Clean old accesses outside window before checking
            cutoff_time = current_time - self.access_window_seconds
            pattern["accesses"] = [t for t in pattern["accesses"] if t > cutoff_time]

            # Demote from hot to warm after no recent accesses
            if from_tier == "hot" and len(pattern["accesses"]) == 0:
                return "warm"

            # Demote from warm to cold after extended inactivity
            if from_tier == "warm" and time_since_access > self.cold_demotion_threshold:
                return "cold"

            return None

    async def determine_tier(
        self, key: str, value: Any, tier_hint: Optional[str] = None
    ) -> str:
        """Determine appropriate tier for new data"""
        # Use hint if provided
        if tier_hint and tier_hint in ["hot", "warm", "cold"]:
            return tier_hint

        # Simple heuristics based on value characteristics
        try:
            # Small values go to hot tier
            value_size = len(str(value))
            if value_size < 1024:  # Less than 1KB
                return "hot"
            elif value_size < 100000:  # Less than 100KB
                return "warm"
            else:
                return "cold"
        except Exception as e:
            # Default to warm tier if size estimation fails
            logger.debug(f"Size estimation failed, defaulting to warm tier: {e}")
            return "warm"

    def get_access_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Get current access patterns for monitoring"""
        with self._lock:
            return {
                key: {
                    "recent_accesses": len(pattern["accesses"]),
                    "current_tier": pattern["current_tier"],
                    "last_access": pattern["last_access"],
                    "age_seconds": time.time() - pattern["created"],
                }
                for key, pattern in self._access_patterns.items()
            }
