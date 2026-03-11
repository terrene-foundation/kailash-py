"""
Enterprise Memory System implementation with intelligent tier management.

This module provides the main EnterpriseMemorySystem class that orchestrates
hot, warm, and cold memory tiers with intelligent data placement and movement.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .persistent_tiers import ColdMemoryTier, WarmMemoryTier
from .tiers import HotMemoryTier, TierManager

logger = logging.getLogger(__name__)


@dataclass
class MemorySystemConfig:
    """Configuration for the enterprise memory system"""

    # Hot tier config
    hot_max_size: int = 1000
    hot_eviction_policy: str = "lru"

    # Warm tier config
    warm_storage_path: Optional[str] = None
    warm_max_size_mb: int = 1000

    # Cold tier config
    cold_storage_path: Optional[str] = None
    cold_compression: bool = True

    # Tier management config
    hot_promotion_threshold: int = 5
    warm_promotion_threshold: int = 3
    access_window_seconds: int = 3600
    cold_demotion_threshold: int = 86400

    # Enterprise features
    multi_tenant_enabled: bool = False
    monitoring_enabled: bool = True
    backup_enabled: bool = False

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "MemorySystemConfig":
        """Create config from dictionary"""
        return cls(**{k: v for k, v in config.items() if k in cls.__annotations__})


class MemoryMonitor:
    """Monitors memory system performance and provides analytics"""

    def __init__(self):
        self._metrics = {
            "total_operations": 0,
            "tier_hits": {"hot": 0, "warm": 0, "cold": 0},
            "tier_misses": {"hot": 0, "warm": 0, "cold": 0},
            "promotions": {"warm_to_hot": 0, "cold_to_warm": 0, "cold_to_hot": 0},
            "demotions": {"hot_to_warm": 0, "warm_to_cold": 0},
            "performance_samples": [],
        }
        self._lock = threading.RLock()

    def record_hit(self, tier: str, key: str, response_time_ms: float = 0):
        """Record a cache hit"""
        with self._lock:
            self._metrics["total_operations"] += 1
            self._metrics["tier_hits"][tier] = (
                self._metrics["tier_hits"].get(tier, 0) + 1
            )

            if response_time_ms > 0:
                self._metrics["performance_samples"].append(
                    {
                        "tier": tier,
                        "key": key,
                        "response_time_ms": response_time_ms,
                        "timestamp": time.time(),
                        "operation": "hit",
                    }
                )

    def record_miss(self, key: str):
        """Record a cache miss"""
        with self._lock:
            self._metrics["total_operations"] += 1

    def record_promotion(self, from_tier: str, to_tier: str, key: str):
        """Record tier promotion"""
        with self._lock:
            promotion_key = f"{from_tier}_to_{to_tier}"
            self._metrics["promotions"][promotion_key] = (
                self._metrics["promotions"].get(promotion_key, 0) + 1
            )

    def record_demotion(self, from_tier: str, to_tier: str, key: str):
        """Record tier demotion"""
        with self._lock:
            demotion_key = f"{from_tier}_to_{to_tier}"
            self._metrics["demotions"][demotion_key] = (
                self._metrics["demotions"].get(demotion_key, 0) + 1
            )

    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        with self._lock:
            total_hits = sum(self._metrics["tier_hits"].values())
            total_ops = self._metrics["total_operations"]

            metrics = {
                "overall_hit_rate": total_hits / total_ops if total_ops > 0 else 0.0,
                "tier_hit_rates": {
                    tier: hits / total_ops if total_ops > 0 else 0.0
                    for tier, hits in self._metrics["tier_hits"].items()
                },
                "tier_distribution": {
                    tier: hits / total_hits if total_hits > 0 else 0.0
                    for tier, hits in self._metrics["tier_hits"].items()
                },
                **self._metrics,
            }

            # Calculate performance percentiles
            if self._metrics["performance_samples"]:
                response_times = [
                    s["response_time_ms"] for s in self._metrics["performance_samples"]
                ]
                response_times.sort()

                metrics["response_time_percentiles"] = {
                    "p50": self._percentile(response_times, 0.5),
                    "p90": self._percentile(response_times, 0.9),
                    "p95": self._percentile(response_times, 0.95),
                    "p99": self._percentile(response_times, 0.99),
                }

            return metrics

    def _percentile(self, data: List[float], percentile: float) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0.0
        index = int(percentile * len(data))
        return data[min(index, len(data) - 1)]


class EnterpriseMemorySystem:
    """Enterprise memory system with intelligent tier management"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = MemorySystemConfig.from_dict(config or {})

        # Initialize tiers
        self.hot_tier = HotMemoryTier(
            max_size=self.config.hot_max_size,
            eviction_policy=self.config.hot_eviction_policy,
        )

        self.warm_tier = WarmMemoryTier(
            storage_path=self.config.warm_storage_path,
            max_size_mb=self.config.warm_max_size_mb,
        )

        self.cold_tier = ColdMemoryTier(
            storage_path=self.config.cold_storage_path,
            compression=self.config.cold_compression,
        )

        # Initialize tier manager
        tier_config = {
            "hot_promotion_threshold": self.config.hot_promotion_threshold,
            "warm_promotion_threshold": self.config.warm_promotion_threshold,
            "access_window_seconds": self.config.access_window_seconds,
            "cold_demotion_threshold": self.config.cold_demotion_threshold,
        }
        self.tier_manager = TierManager(tier_config)

        # Initialize monitoring
        self.monitor = MemoryMonitor() if self.config.monitoring_enabled else None

        # Multi-tenancy support
        self._tenant_contexts: Dict[str, Dict[str, Any]] = {}
        self._current_tenant: Optional[str] = None
        self._lock = threading.RLock()

        logger.info("EnterpriseMemorySystem initialized with config: %s", self.config)

    async def get(self, key: str, tenant_id: Optional[str] = None) -> Optional[Any]:
        """Get data with intelligent tier checking"""
        start_time = time.perf_counter()
        effective_key = self._build_tenant_key(key, tenant_id)

        try:
            # Check hot tier first
            value = await self.hot_tier.get(effective_key)
            if value is not None:
                await self.tier_manager.record_access(effective_key, "hot")
                if self.monitor:
                    response_time = (time.perf_counter() - start_time) * 1000
                    self.monitor.record_hit("hot", effective_key, response_time)
                return value

            # Check warm tier
            value = await self.warm_tier.get(effective_key)
            if value is not None:
                await self.tier_manager.record_access(effective_key, "warm")

                # Consider promotion to hot tier
                if await self.tier_manager.should_promote(effective_key, "warm", "hot"):
                    await self.hot_tier.put(effective_key, value)
                    if self.monitor:
                        self.monitor.record_promotion("warm", "hot", effective_key)
                    logger.debug(f"Promoted key '{key}' from warm to hot tier")

                if self.monitor:
                    response_time = (time.perf_counter() - start_time) * 1000
                    self.monitor.record_hit("warm", effective_key, response_time)
                return value

            # Check cold tier
            value = await self.cold_tier.get(effective_key)
            if value is not None:
                await self.tier_manager.record_access(effective_key, "cold")

                # Consider promotion based on access patterns
                if await self.tier_manager.should_promote(
                    effective_key, "cold", "warm"
                ):
                    await self.warm_tier.put(effective_key, value)
                    if self.monitor:
                        self.monitor.record_promotion("cold", "warm", effective_key)
                    logger.debug(f"Promoted key '{key}' from cold to warm tier")
                elif await self.tier_manager.should_promote(
                    effective_key, "cold", "hot"
                ):
                    await self.hot_tier.put(effective_key, value)
                    if self.monitor:
                        self.monitor.record_promotion("cold", "hot", effective_key)
                    logger.debug(f"Promoted key '{key}' from cold to hot tier")

                if self.monitor:
                    response_time = (time.perf_counter() - start_time) * 1000
                    self.monitor.record_hit("cold", effective_key, response_time)
                return value

            # Not found in any tier
            if self.monitor:
                self.monitor.record_miss(effective_key)
            return None

        except Exception as e:
            logger.error(f"Error in EnterpriseMemorySystem.get({key}): {e}")
            if self.monitor:
                self.monitor.record_miss(effective_key)
            return None

    async def put(
        self,
        key: str,
        value: Any,
        tier_hint: Optional[str] = None,
        ttl: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Store data with intelligent tier placement"""
        effective_key = self._build_tenant_key(key, tenant_id)

        try:
            # Determine target tier
            target_tier = await self.tier_manager.determine_tier(
                effective_key, value, tier_hint
            )

            if target_tier == "hot":
                result = await self.hot_tier.put(effective_key, value, ttl)
                if result:
                    await self.tier_manager.record_access(effective_key, "hot")
            elif target_tier == "warm":
                result = await self.warm_tier.put(effective_key, value, ttl)
                if result:
                    await self.tier_manager.record_access(effective_key, "warm")
            else:  # cold
                result = await self.cold_tier.put(effective_key, value, ttl)
                if result:
                    await self.tier_manager.record_access(effective_key, "cold")

            if result:
                logger.debug(f"Stored key '{key}' in {target_tier} tier")

            return result

        except Exception as e:
            logger.error(f"Error in EnterpriseMemorySystem.put({key}): {e}")
            return False

    async def delete(self, key: str, tenant_id: Optional[str] = None) -> bool:
        """Delete data from all tiers"""
        effective_key = self._build_tenant_key(key, tenant_id)

        try:
            # Delete from all tiers
            results = await asyncio.gather(
                self.hot_tier.delete(effective_key),
                self.warm_tier.delete(effective_key),
                self.cold_tier.delete(effective_key),
                return_exceptions=True,
            )

            # Return True if deleted from any tier
            return any(isinstance(r, bool) and r for r in results)

        except Exception as e:
            logger.error(f"Error in EnterpriseMemorySystem.delete({key}): {e}")
            return False

    async def exists(self, key: str, tenant_id: Optional[str] = None) -> bool:
        """Check if key exists in any tier"""
        effective_key = self._build_tenant_key(key, tenant_id)

        try:
            # Check all tiers concurrently
            results = await asyncio.gather(
                self.hot_tier.exists(effective_key),
                self.warm_tier.exists(effective_key),
                self.cold_tier.exists(effective_key),
                return_exceptions=True,
            )

            return any(isinstance(r, bool) and r for r in results)

        except Exception as e:
            logger.error(f"Error in EnterpriseMemorySystem.exists({key}): {e}")
            return False

    async def clear(self, tenant_id: Optional[str] = None) -> bool:
        """Clear all data (optionally for specific tenant)"""
        try:
            if tenant_id:
                # Clear tenant-specific data (implementation would need key scanning)
                logger.warning("Tenant-specific clear not fully implemented yet")
                return False
            else:
                # Clear all tiers
                results = await asyncio.gather(
                    self.hot_tier.clear(),
                    self.warm_tier.clear(),
                    self.cold_tier.clear(),
                    return_exceptions=True,
                )

                return all(isinstance(r, bool) and r for r in results)

        except Exception as e:
            logger.error(f"Error in EnterpriseMemorySystem.clear(): {e}")
            return False

    async def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        try:
            # Get tier stats
            hot_stats = self.hot_tier.get_stats()
            warm_stats = self.warm_tier.get_stats()
            cold_stats = self.cold_tier.get_stats()

            # Get tier sizes
            sizes = await asyncio.gather(
                self.hot_tier.size(),
                self.warm_tier.size(),
                self.cold_tier.size(),
                return_exceptions=True,
            )

            hot_size, warm_size, cold_size = [
                s if isinstance(s, int) else 0 for s in sizes
            ]

            # Get monitoring metrics
            monitor_metrics = self.monitor.get_metrics() if self.monitor else {}

            return {
                "tiers": {
                    "hot": {**hot_stats, "size": hot_size},
                    "warm": {**warm_stats, "size": warm_size},
                    "cold": {**cold_stats, "size": cold_size},
                },
                "total_size": hot_size + warm_size + cold_size,
                "access_patterns": self.tier_manager.get_access_patterns(),
                "monitoring": monitor_metrics,
                "config": {
                    "hot_max_size": self.config.hot_max_size,
                    "warm_max_size_mb": self.config.warm_max_size_mb,
                    "multi_tenant_enabled": self.config.multi_tenant_enabled,
                    "monitoring_enabled": self.config.monitoring_enabled,
                },
            }

        except Exception as e:
            logger.error(f"Error getting system stats: {e}")
            return {}

    def set_tenant_context(self, tenant_id: str):
        """Set current tenant context for multi-tenancy"""
        self._current_tenant = tenant_id

    def clear_tenant_context(self):
        """Clear current tenant context"""
        self._current_tenant = None

    def _build_tenant_key(self, key: str, tenant_id: Optional[str] = None) -> str:
        """Build tenant-aware key"""
        if not self.config.multi_tenant_enabled:
            return key

        effective_tenant = tenant_id or self._current_tenant
        if effective_tenant:
            return f"tenant:{effective_tenant}:{key}"
        return key

    async def optimize_tiers(self):
        """Run optimization to promote/demote data between tiers"""
        try:
            access_patterns = self.tier_manager.get_access_patterns()

            for key, pattern in access_patterns.items():
                current_tier = pattern["current_tier"]

                # Check for demotions
                target_tier = await self.tier_manager.should_demote(key, current_tier)
                if target_tier:
                    await self._move_between_tiers(key, current_tier, target_tier)

            logger.debug("Tier optimization completed")

        except Exception as e:
            logger.error(f"Error during tier optimization: {e}")

    async def _move_between_tiers(self, key: str, from_tier: str, to_tier: str):
        """Move data between tiers"""
        try:
            # Get value from source tier
            source_tier = getattr(self, f"{from_tier}_tier")
            target_tier_obj = getattr(self, f"{to_tier}_tier")

            value = await source_tier.get(key)
            if value is not None:
                # Store in target tier
                if await target_tier_obj.put(key, value):
                    # Remove from source tier
                    await source_tier.delete(key)

                    if self.monitor:
                        self.monitor.record_demotion(from_tier, to_tier, key)

                    logger.debug(
                        f"Moved key '{key}' from {from_tier} to {to_tier} tier"
                    )

        except Exception as e:
            logger.error(f"Error moving key '{key}' from {from_tier} to {to_tier}: {e}")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        # Cleanup resources if needed
        pass
