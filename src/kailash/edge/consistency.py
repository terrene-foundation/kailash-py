"""Consistency models and managers for edge computing."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ConsistencyLevel(Enum):
    """Consistency levels for distributed operations."""

    ONE = 1  # At least one replica
    QUORUM = 2  # Majority of replicas
    ALL = 3  # All replicas
    LOCAL_QUORUM = 4  # Quorum within local region
    EACH_QUORUM = 5  # Quorum in each region


@dataclass
class ConsistencyMetrics:
    """Metrics for consistency operations."""

    writes_total: int = 0
    writes_succeeded: int = 0
    writes_failed: int = 0
    reads_total: int = 0
    reads_stale: int = 0
    conflicts_detected: int = 0
    conflicts_resolved: int = 0
    average_replication_lag_ms: float = 0.0
    max_replication_lag_ms: float = 0.0


@dataclass
class Version:
    """Version information for distributed data."""

    number: int
    timestamp: datetime
    edge_id: str
    vector_clock: Dict[str, int] = field(default_factory=dict)

    def is_newer_than(self, other: "Version") -> bool:
        """Check if this version is newer than another."""
        # First check vector clock for causal ordering
        if self.vector_clock and other.vector_clock:
            return self._dominates_vector_clock(other)

        # Fall back to timestamp comparison
        return self.timestamp > other.timestamp

    def _dominates_vector_clock(self, other: "Version") -> bool:
        """Check if this version dominates another via vector clock."""
        at_least_one_greater = False

        for node_id in set(self.vector_clock.keys()) | set(other.vector_clock.keys()):
            self_val = self.vector_clock.get(node_id, 0)
            other_val = other.vector_clock.get(node_id, 0)

            if self_val < other_val:
                return False
            elif self_val > other_val:
                at_least_one_greater = True

        return at_least_one_greater


class ConsistencyManager(ABC):
    """Abstract base class for consistency managers."""

    def __init__(self):
        self.metrics = ConsistencyMetrics()
        self.logger = logging.getLogger(
            f"{self.__class__.__module__}.{self.__class__.__name__}"
        )

    @abstractmethod
    async def write(
        self,
        key: str,
        value: Any,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> bool:
        """Write with consistency guarantees."""
        pass

    @abstractmethod
    async def read(
        self,
        key: str,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> Optional[Any]:
        """Read with consistency guarantees."""
        pass


class StrongConsistencyManager(ConsistencyManager):
    """Manager for strong consistency using Two-Phase Commit (2PC)."""

    def __init__(self, write_callback: Callable, read_callback: Callable):
        super().__init__()
        self.write_callback = write_callback
        self.read_callback = read_callback
        self.prepared_writes: Dict[str, Set[str]] = {}

    async def write(
        self,
        key: str,
        value: Any,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.ALL,
    ) -> bool:
        """Write with strong consistency (2PC)."""
        self.metrics.writes_total += 1

        transaction_id = f"{key}:{time.time()}"
        prepared_replicas = set()

        try:
            # Phase 1: Prepare
            prepare_tasks = []
            for replica in replicas:
                prepare_tasks.append(
                    self._prepare_write(transaction_id, replica, key, value)
                )

            prepare_results = await asyncio.gather(
                *prepare_tasks, return_exceptions=True
            )

            # Check prepare results
            for replica, result in zip(replicas, prepare_results):
                if isinstance(result, Exception):
                    self.logger.error(f"Prepare failed for {replica}: {result}")
                elif result:
                    prepared_replicas.add(replica)

            # Check if we have enough replicas
            if not self._check_consistency_level(
                len(prepared_replicas), len(replicas), level
            ):
                # Abort transaction
                await self._abort_transaction(transaction_id, prepared_replicas)
                self.metrics.writes_failed += 1
                return False

            # Phase 2: Commit
            commit_tasks = []
            for replica in prepared_replicas:
                commit_tasks.append(
                    self._commit_write(transaction_id, replica, key, value)
                )

            await asyncio.gather(*commit_tasks, return_exceptions=True)

            self.metrics.writes_succeeded += 1
            return True

        except Exception as e:
            self.logger.error(f"2PC write failed: {e}")
            await self._abort_transaction(transaction_id, prepared_replicas)
            self.metrics.writes_failed += 1
            return False

    async def read(
        self,
        key: str,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.ALL,
    ) -> Optional[Any]:
        """Read with strong consistency."""
        self.metrics.reads_total += 1

        # Read from all replicas
        read_tasks = []
        for replica in replicas:
            read_tasks.append(self.read_callback(replica, key))

        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        # Filter valid results
        valid_results = []
        for result in results:
            if not isinstance(result, Exception) and result is not None:
                valid_results.append(result)

        if not valid_results:
            return None

        # For strong consistency, all must agree
        first_value = valid_results[0]
        if all(r == first_value for r in valid_results):
            return first_value
        else:
            # Inconsistency detected
            self.metrics.conflicts_detected += 1
            # Return most recent value
            return max(valid_results, key=lambda x: x.get("timestamp", 0))

    async def _prepare_write(
        self, transaction_id: str, replica: str, key: str, value: Any
    ) -> bool:
        """Prepare phase of 2PC."""
        # Simulate prepare (in production, this would be an RPC)
        await asyncio.sleep(0.01)
        return True

    async def _commit_write(
        self, transaction_id: str, replica: str, key: str, value: Any
    ) -> bool:
        """Commit phase of 2PC."""
        return await self.write_callback(replica, key, value)

    async def _abort_transaction(
        self, transaction_id: str, prepared_replicas: Set[str]
    ):
        """Abort a prepared transaction."""
        abort_tasks = []
        for replica in prepared_replicas:
            abort_tasks.append(self._abort_replica(transaction_id, replica))

        await asyncio.gather(*abort_tasks, return_exceptions=True)

    async def _abort_replica(self, transaction_id: str, replica: str):
        """Abort on a single replica."""
        await asyncio.sleep(0.01)  # Simulate abort

    def _check_consistency_level(
        self, successful: int, total: int, level: ConsistencyLevel
    ) -> bool:
        """Check if consistency level is satisfied."""
        if level == ConsistencyLevel.ONE:
            return successful >= 1
        elif level == ConsistencyLevel.QUORUM:
            return successful > total // 2
        elif level == ConsistencyLevel.ALL:
            return successful == total
        else:
            # For LOCAL_QUORUM and EACH_QUORUM, simplified check
            return successful > total // 2


class EventualConsistencyManager(ConsistencyManager):
    """Manager for eventual consistency with async replication."""

    def __init__(self, write_callback: Callable, read_callback: Callable):
        super().__init__()
        self.write_callback = write_callback
        self.read_callback = read_callback
        self.replication_lag: Dict[str, float] = {}

    async def write(
        self,
        key: str,
        value: Any,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.ONE,
    ) -> bool:
        """Write with eventual consistency."""
        self.metrics.writes_total += 1

        # Write to primary first
        primary = replicas[0] if replicas else None
        if not primary:
            self.metrics.writes_failed += 1
            return False

        try:
            # Write to primary
            success = await self.write_callback(primary, key, value)
            if not success:
                self.metrics.writes_failed += 1
                return False

            # Async replication to secondaries
            if len(replicas) > 1:
                asyncio.create_task(self._replicate_async(key, value, replicas[1:]))

            self.metrics.writes_succeeded += 1
            return True

        except Exception as e:
            self.logger.error(f"Eventual write failed: {e}")
            self.metrics.writes_failed += 1
            return False

    async def read(
        self,
        key: str,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.ONE,
    ) -> Optional[Any]:
        """Read with eventual consistency."""
        self.metrics.reads_total += 1

        # Read from any available replica
        for replica in replicas:
            try:
                result = await self.read_callback(replica, key)
                if result is not None:
                    # Check staleness
                    if self._is_stale(replica, result):
                        self.metrics.reads_stale += 1

                    return result
            except Exception:
                continue

        return None

    async def _replicate_async(self, key: str, value: Any, replicas: List[str]):
        """Asynchronously replicate to secondary replicas."""
        start_time = time.time()

        tasks = []
        for replica in replicas:
            tasks.append(self.write_callback(replica, key, value))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Track replication lag
        lag = (time.time() - start_time) * 1000  # ms
        for replica in replicas:
            self.replication_lag[replica] = lag

        # Update metrics
        self._update_replication_metrics()

    def _is_stale(self, replica: str, data: Dict[str, Any]) -> bool:
        """Check if data from replica is stale."""
        if "timestamp" not in data:
            return False

        data_age = time.time() - data["timestamp"]
        return data_age > 5.0  # Consider stale if > 5 seconds

    def _update_replication_metrics(self):
        """Update replication lag metrics."""
        if self.replication_lag:
            lags = list(self.replication_lag.values())
            self.metrics.average_replication_lag_ms = sum(lags) / len(lags)
            self.metrics.max_replication_lag_ms = max(lags)


class CausalConsistencyManager(ConsistencyManager):
    """Manager for causal consistency with dependency tracking."""

    def __init__(self, write_callback: Callable, read_callback: Callable):
        super().__init__()
        self.write_callback = write_callback
        self.read_callback = read_callback
        self.vector_clocks: Dict[str, Dict[str, int]] = {}
        self.causal_dependencies: Dict[str, Set[str]] = {}

    async def write(
        self,
        key: str,
        value: Any,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> bool:
        """Write with causal consistency."""
        self.metrics.writes_total += 1

        # Update vector clock
        node_id = replicas[0]  # Primary
        if key not in self.vector_clocks:
            self.vector_clocks[key] = {}

        current_clock = self.vector_clocks[key].get(node_id, 0)
        self.vector_clocks[key][node_id] = current_clock + 1

        # Add causal metadata
        causal_value = {
            "data": value,
            "vector_clock": self.vector_clocks[key].copy(),
            "dependencies": list(self.causal_dependencies.get(key, set())),
            "timestamp": time.time(),
        }

        # Write with causal ordering
        success_count = 0
        write_tasks = []

        for replica in replicas:
            write_tasks.append(
                self._write_with_dependencies(replica, key, causal_value)
            )

        results = await asyncio.gather(*write_tasks, return_exceptions=True)

        for result in results:
            if not isinstance(result, Exception) and result:
                success_count += 1

        if self._check_consistency_level(success_count, len(replicas), level):
            self.metrics.writes_succeeded += 1
            return True
        else:
            self.metrics.writes_failed += 1
            return False

    async def read(
        self,
        key: str,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> Optional[Any]:
        """Read with causal consistency."""
        self.metrics.reads_total += 1

        # Read from multiple replicas
        read_tasks = []
        for replica in replicas:
            read_tasks.append(self.read_callback(replica, key))

        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        # Filter valid results with causal metadata
        valid_results = []
        for result in results:
            if not isinstance(result, Exception) and result is not None:
                valid_results.append(result)

        if not valid_results:
            return None

        # Select causally consistent value
        return self._select_causal_value(valid_results)

    async def _write_with_dependencies(
        self, replica: str, key: str, causal_value: Dict[str, Any]
    ) -> bool:
        """Write ensuring causal dependencies are satisfied."""
        # Check if dependencies are satisfied on replica
        deps = causal_value.get("dependencies", [])

        for dep_key in deps:
            dep_result = await self.read_callback(replica, dep_key)
            if dep_result is None:
                # Dependency not satisfied, delay write
                await asyncio.sleep(0.1)
                # Retry once
                dep_result = await self.read_callback(replica, dep_key)
                if dep_result is None:
                    return False

        # Dependencies satisfied, proceed with write
        return await self.write_callback(replica, key, causal_value)

    def _select_causal_value(self, results: List[Dict[str, Any]]) -> Any:
        """Select the causally most recent value."""
        if not results:
            return None

        # Find value with highest vector clock
        best_result = results[0]
        best_clock = best_result.get("vector_clock", {})

        for result in results[1:]:
            result_clock = result.get("vector_clock", {})
            if self._dominates(result_clock, best_clock):
                best_result = result
                best_clock = result_clock

        return best_result.get("data")

    def _dominates(self, clock1: Dict[str, int], clock2: Dict[str, int]) -> bool:
        """Check if clock1 dominates clock2."""
        at_least_one_greater = False

        all_nodes = set(clock1.keys()) | set(clock2.keys())
        for node in all_nodes:
            val1 = clock1.get(node, 0)
            val2 = clock2.get(node, 0)

            if val1 < val2:
                return False
            elif val1 > val2:
                at_least_one_greater = True

        return at_least_one_greater

    def _check_consistency_level(
        self, successful: int, total: int, level: ConsistencyLevel
    ) -> bool:
        """Check if consistency level is satisfied."""
        if level == ConsistencyLevel.ONE:
            return successful >= 1
        elif level == ConsistencyLevel.QUORUM:
            return successful > total // 2
        elif level == ConsistencyLevel.ALL:
            return successful == total
        else:
            return successful > total // 2


class BoundedStalenessManager(ConsistencyManager):
    """Manager for bounded staleness consistency."""

    def __init__(
        self,
        write_callback: Callable,
        read_callback: Callable,
        max_staleness_ms: int = 5000,
    ):
        super().__init__()
        self.write_callback = write_callback
        self.read_callback = read_callback
        self.max_staleness_ms = max_staleness_ms
        self.write_timestamps: Dict[str, float] = {}

    async def write(
        self,
        key: str,
        value: Any,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.QUORUM,
    ) -> bool:
        """Write with bounded staleness."""
        self.metrics.writes_total += 1

        # Add timestamp
        timestamped_value = {
            "data": value,
            "write_timestamp": time.time(),
            "primary_replica": replicas[0] if replicas else None,
        }

        # Track write time
        self.write_timestamps[key] = timestamped_value["write_timestamp"]

        # Write to replicas
        success_count = 0
        write_tasks = []

        for replica in replicas:
            write_tasks.append(self.write_callback(replica, key, timestamped_value))

        results = await asyncio.gather(*write_tasks, return_exceptions=True)

        for result in results:
            if not isinstance(result, Exception) and result:
                success_count += 1

        if self._check_consistency_level(success_count, len(replicas), level):
            self.metrics.writes_succeeded += 1
            return True
        else:
            self.metrics.writes_failed += 1
            return False

    async def read(
        self,
        key: str,
        replicas: List[str],
        level: ConsistencyLevel = ConsistencyLevel.ONE,
    ) -> Optional[Any]:
        """Read with bounded staleness guarantee."""
        self.metrics.reads_total += 1

        # Try to read from replicas in order
        for replica in replicas:
            try:
                result = await self.read_callback(replica, key)
                if result is None:
                    continue

                # Check staleness
                write_timestamp = result.get("write_timestamp", 0)
                staleness_ms = (time.time() - write_timestamp) * 1000

                if staleness_ms <= self.max_staleness_ms:
                    # Within bounds
                    return result.get("data")
                else:
                    # Too stale, try to refresh
                    self.metrics.reads_stale += 1

                    # Try primary replica
                    primary = result.get("primary_replica")
                    if primary and primary != replica:
                        fresh_result = await self.read_callback(primary, key)
                        if fresh_result:
                            return fresh_result.get("data")

            except Exception:
                continue

        return None

    def _check_consistency_level(
        self, successful: int, total: int, level: ConsistencyLevel
    ) -> bool:
        """Check if consistency level is satisfied."""
        if level == ConsistencyLevel.ONE:
            return successful >= 1
        elif level == ConsistencyLevel.QUORUM:
            return successful > total // 2
        elif level == ConsistencyLevel.ALL:
            return successful == total
        else:
            return successful > total // 2
