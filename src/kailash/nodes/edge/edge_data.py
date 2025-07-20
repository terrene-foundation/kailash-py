"""Edge data node for distributed data management with consistency guarantees."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from kailash.edge.location import EdgeLocation
from kailash.nodes.base import NodeParameter, register_node

from .base import EdgeNode


class ConsistencyModel(Enum):
    """Data consistency models for edge operations."""

    STRONG = "strong"  # 2PC - All replicas must acknowledge
    EVENTUAL = "eventual"  # Async replication
    CAUSAL = "causal"  # Causally consistent updates
    BOUNDED_STALENESS = "bounded_staleness"  # Max staleness threshold


class ReplicationStatus:
    """Track replication status across edges."""

    def __init__(self):
        self.pending: Set[str] = set()
        self.completed: Set[str] = set()
        self.failed: Set[str] = set()
        self.start_time = datetime.now(UTC)

    @property
    def is_complete(self) -> bool:
        return len(self.pending) == 0

    @property
    def success_rate(self) -> float:
        total = len(self.completed) + len(self.failed)
        return len(self.completed) / total if total > 0 else 0.0


@register_node()
class EdgeDataNode(EdgeNode):
    """Distributed data node with multi-edge replication and consistency.

    Features:
    - Multiple consistency models
    - Automatic replication across edges
    - Conflict resolution
    - Compliance-aware data placement
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "action": NodeParameter(
                name="action",
                type=str,
                default="read",
                required=False,
                description="Operation to perform (read|write|replicate|sync)",
            ),
            "key": NodeParameter(
                name="key",
                type=str,
                required=False,
                description="Data key for operations",
            ),
            "data": NodeParameter(
                name="data", type=dict, required=False, description="Data to write"
            ),
            "target_edges": NodeParameter(
                name="target_edges",
                type=list,
                required=False,
                description="Target edges for replication",
            ),
            "keys": NodeParameter(
                name="keys", type=list, required=False, description="Keys to sync"
            ),
            "consistency": NodeParameter(
                name="consistency",
                type=str,
                default="eventual",
                required=False,
                description="Consistency model (strong|eventual|causal|bounded_staleness)",
            ),
            "replication_factor": NodeParameter(
                name="replication_factor",
                type=int,
                default=3,
                required=False,
                description="Number of edge replicas to maintain",
            ),
            "staleness_threshold_ms": NodeParameter(
                name="staleness_threshold_ms",
                type=int,
                default=5000,
                required=False,
                description="Max staleness for bounded consistency (ms)",
            ),
            "conflict_resolution": NodeParameter(
                name="conflict_resolution",
                type=str,
                default="last_write_wins",
                required=False,
                description="Conflict resolution strategy",
            ),
        }

    def __init__(self, **config):
        """Initialize edge data node."""
        super().__init__(**config)

        # Data storage per edge (simulated)
        self._edge_data: Dict[str, Dict[str, Any]] = {}
        self._data_versions: Dict[str, Dict[str, int]] = {}
        self._replication_tasks: Dict[str, asyncio.Task] = {}

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute edge data operation."""
        # Get action from kwargs first, then from config
        action = kwargs.get("action") or self.config.get("action", "read")

        if action == "write":
            return await self._handle_write(kwargs)
        elif action == "read":
            return await self._handle_read(kwargs)
        elif action == "replicate":
            return await self._handle_replicate(kwargs)
        elif action == "sync":
            return await self._handle_sync(kwargs)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _handle_write(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle write operation with consistency guarantees."""
        key = params.get("key")
        data = params.get("data")
        consistency = ConsistencyModel(params.get("consistency", "eventual"))

        if not key or data is None:
            raise ValueError("Write requires 'key' and 'data'")

        # Ensure compliance for data placement
        if not await self.ensure_compliance({"data": data}):
            return {"success": False, "error": "No compliant edge available for data"}

        # Generate version
        version = self._get_next_version(key)

        # Store locally first
        edge_name = self.current_edge.name
        if edge_name not in self._edge_data:
            self._edge_data[edge_name] = {}
            self._data_versions[edge_name] = {}

        self._edge_data[edge_name][key] = {
            "data": data,
            "version": version,
            "timestamp": datetime.now(UTC).isoformat(),
            "edge": edge_name,
        }
        self._data_versions[edge_name][key] = version

        # Handle consistency model
        replication_status = ReplicationStatus()

        if consistency == ConsistencyModel.STRONG:
            # Synchronous replication to all replicas
            await self._replicate_strong(key, data, version, replication_status)
        else:
            # Async replication for other models
            task = asyncio.create_task(
                self._replicate_async(
                    key, data, version, consistency, replication_status
                )
            )
            self._replication_tasks[f"{key}:{version}"] = task

        return {
            "success": True,
            "key": key,
            "version": version,
            "edge": edge_name,
            "consistency": consistency.value,
            "replication_status": {
                "pending": len(replication_status.pending),
                "completed": len(replication_status.completed),
                "failed": len(replication_status.failed),
            },
        }

    async def _handle_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle read operation with consistency awareness."""
        key = params.get("key")
        consistency = ConsistencyModel(params.get("consistency", "eventual"))

        if not key:
            raise ValueError("Read requires 'key'")

        # For strong consistency, ensure we have latest version
        if consistency == ConsistencyModel.STRONG:
            await self._ensure_latest_version(key)

        # Find edge with data
        edge_with_data = await self._find_edge_with_data(key)
        if not edge_with_data:
            return {"success": False, "error": f"Key '{key}' not found"}

        # Get data from edge
        edge_name, data_entry = edge_with_data

        # Check staleness for bounded consistency
        if consistency == ConsistencyModel.BOUNDED_STALENESS:
            staleness_ms = self._calculate_staleness(data_entry)
            threshold = params.get("staleness_threshold_ms", 5000)

            if staleness_ms > threshold:
                # Try to get fresher data
                await self._refresh_from_primary(key)
                edge_with_data = await self._find_edge_with_data(key)
                if edge_with_data:
                    edge_name, data_entry = edge_with_data

        return {
            "success": True,
            "key": key,
            "data": data_entry["data"],
            "version": data_entry["version"],
            "timestamp": data_entry["timestamp"],
            "edge": edge_name,
            "latency_ms": self._get_edge_latency(edge_name),
        }

    async def _handle_replicate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle manual replication request."""
        key = params.get("key")
        target_edges = params.get("target_edges", [])

        if not key:
            raise ValueError("Replicate requires 'key'")

        # Find source data
        edge_with_data = await self._find_edge_with_data(key)
        if not edge_with_data:
            return {"success": False, "error": f"Key '{key}' not found"}

        source_edge, data_entry = edge_with_data

        # Replicate to targets
        replication_results = {}
        for target in target_edges:
            success = await self._replicate_to_edge(
                target, key, data_entry["data"], data_entry["version"]
            )
            replication_results[target] = success

        return {
            "success": True,
            "key": key,
            "source_edge": source_edge,
            "replication_results": replication_results,
        }

    async def _handle_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle sync operation to ensure consistency."""
        keys = params.get("keys", [])

        sync_results = {}
        for key in keys:
            # Find all versions across edges
            versions = self._get_all_versions(key)

            if not versions:
                sync_results[key] = {"status": "not_found"}
                continue

            # Determine winning version
            winner_edge, winner_version = self._resolve_conflict(versions)

            # Sync winning version to all edges with the key
            edges_to_sync = [e for e, v in versions.items() if v < winner_version]

            if edges_to_sync:
                data_entry = self._edge_data.get(winner_edge, {}).get(key)
                if data_entry:
                    for edge in edges_to_sync:
                        await self._replicate_to_edge(
                            edge, key, data_entry["data"], winner_version
                        )

            sync_results[key] = {
                "status": "synced",
                "winner_edge": winner_edge,
                "winner_version": winner_version,
                "synced_edges": edges_to_sync,
            }

        return {"success": True, "sync_results": sync_results}

    async def _replicate_strong(
        self, key: str, data: Any, version: int, status: ReplicationStatus
    ):
        """Perform strong consistency replication (2PC)."""
        # Get target edges
        target_edges = await self._select_replication_targets()

        # Phase 1: Prepare
        prepare_tasks = []
        for edge in target_edges:
            status.pending.add(edge.name)
            prepare_tasks.append(self._prepare_replication(edge, key, data, version))

        prepare_results = await asyncio.gather(*prepare_tasks, return_exceptions=True)

        # Check if all prepared successfully
        prepared_edges = []
        for edge, result in zip(target_edges, prepare_results):
            if isinstance(result, Exception) or not result:
                status.failed.add(edge.name)
                status.pending.discard(edge.name)
            else:
                prepared_edges.append(edge)

        # Phase 2: Commit or Abort
        if len(prepared_edges) == len(target_edges):
            # All prepared - commit
            commit_tasks = []
            for edge in prepared_edges:
                commit_tasks.append(self._commit_replication(edge, key, version))

            await asyncio.gather(*commit_tasks, return_exceptions=True)

            for edge in prepared_edges:
                status.completed.add(edge.name)
                status.pending.discard(edge.name)
        else:
            # Some failed - abort
            abort_tasks = []
            for edge in prepared_edges:
                abort_tasks.append(self._abort_replication(edge, key, version))

            await asyncio.gather(*abort_tasks, return_exceptions=True)

            raise RuntimeError(
                f"Strong consistency replication failed. "
                f"Only {len(prepared_edges)}/{len(target_edges)} edges prepared."
            )

    async def _replicate_async(
        self,
        key: str,
        data: Any,
        version: int,
        consistency: ConsistencyModel,
        status: ReplicationStatus,
    ):
        """Perform async replication for eventual/causal/bounded consistency."""
        target_edges = await self._select_replication_targets()

        tasks = []
        for edge in target_edges:
            status.pending.add(edge.name)

            if consistency == ConsistencyModel.CAUSAL:
                # Add causal dependency tracking
                task = self._replicate_causal(edge, key, data, version)
            else:
                # Simple async replication
                task = self._replicate_to_edge(edge.name, key, data, version)

            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for edge, result in zip(target_edges, results):
            if isinstance(result, Exception) or not result:
                status.failed.add(edge.name)
            else:
                status.completed.add(edge.name)
            status.pending.discard(edge.name)

    async def _select_replication_targets(self) -> List[EdgeLocation]:
        """Select edges for replication based on strategy."""
        all_edges = self.edge_discovery.get_all_edges()

        # Remove current edge
        target_edges = [e for e in all_edges if e.name != self.current_edge.name]

        # Filter by compliance if needed
        if self.compliance_zones:
            target_edges = [
                e
                for e in target_edges
                if any(zone in e.compliance_zones for zone in self.compliance_zones)
            ]

        # Sort by strategy and take replication_factor - 1 (current edge is 1)
        target_edges = sorted(
            target_edges,
            key=lambda e: (e.metrics.latency_p50_ms, e.metrics.network_cost_per_gb),
        )

        return target_edges[: self.config.get("replication_factor", 3) - 1]

    async def _replicate_to_edge(
        self, edge_name: str, key: str, data: Any, version: int
    ) -> bool:
        """Replicate data to specific edge."""
        try:
            # Simulate network replication
            await asyncio.sleep(0.05)  # 50ms replication latency

            # Store in edge data
            if edge_name not in self._edge_data:
                self._edge_data[edge_name] = {}
                self._data_versions[edge_name] = {}

            self._edge_data[edge_name][key] = {
                "data": data,
                "version": version,
                "timestamp": datetime.now(UTC).isoformat(),
                "edge": edge_name,
            }
            self._data_versions[edge_name][key] = version

            return True

        except Exception as e:
            self.logger.error(f"Replication to {edge_name} failed: {e}")
            return False

    async def _prepare_replication(
        self, edge: EdgeLocation, key: str, data: Any, version: int
    ) -> bool:
        """Prepare phase of 2PC replication."""
        # Simulate prepare phase
        await asyncio.sleep(0.02)

        # Check if edge can accept the write
        if edge.metrics.storage_utilization > 0.95:  # 95% full
            return False

        return True

    async def _commit_replication(
        self, edge: EdgeLocation, key: str, version: int
    ) -> bool:
        """Commit phase of 2PC replication."""
        # Actually replicate the data
        data_entry = self._edge_data.get(self.current_edge.name, {}).get(key)
        if data_entry:
            return await self._replicate_to_edge(
                edge.name, key, data_entry["data"], version
            )
        return False

    async def _abort_replication(
        self, edge: EdgeLocation, key: str, version: int
    ) -> bool:
        """Abort phase of 2PC replication."""
        # Clean up any prepared state
        await asyncio.sleep(0.01)
        return True

    async def _replicate_causal(
        self, edge: EdgeLocation, key: str, data: Any, version: int
    ) -> bool:
        """Replicate with causal consistency tracking."""
        # Add causal dependency metadata
        causal_data = {
            "data": data,
            "version": version,
            "causal_deps": self._get_causal_dependencies(key),
            "timestamp": datetime.now(UTC).isoformat(),
        }

        return await self._replicate_to_edge(edge.name, key, causal_data, version)

    def _get_next_version(self, key: str) -> int:
        """Get next version number for a key."""
        max_version = 0

        for edge_versions in self._data_versions.values():
            if key in edge_versions:
                max_version = max(max_version, edge_versions[key])

        return max_version + 1

    async def _find_edge_with_data(
        self, key: str
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """Find edge that has the requested data."""
        # First check current edge
        if self.current_edge:
            edge_name = self.current_edge.name
            if edge_name in self._edge_data and key in self._edge_data[edge_name]:
                return (edge_name, self._edge_data[edge_name][key])

        # Check other edges by latency
        edges_by_latency = sorted(
            self.edge_discovery.get_all_edges(), key=lambda e: e.metrics.latency_p50_ms
        )

        for edge in edges_by_latency:
            if edge.name in self._edge_data and key in self._edge_data[edge.name]:
                return (edge.name, self._edge_data[edge.name][key])

        return None

    def _calculate_staleness(self, data_entry: Dict[str, Any]) -> float:
        """Calculate data staleness in milliseconds."""
        timestamp_str = data_entry["timestamp"]
        # Handle both timezone-aware and naive timestamps
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(timestamp_str)

        # Make sure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        staleness = datetime.now(UTC) - timestamp
        return staleness.total_seconds() * 1000

    def _get_edge_latency(self, edge_name: str) -> float:
        """Get latency to specific edge."""
        edge = self.edge_discovery.get_edge(edge_name)
        return edge.metrics.latency_p50_ms if edge else 0.0

    def _get_all_versions(self, key: str) -> Dict[str, int]:
        """Get all versions of a key across edges."""
        versions = {}

        for edge_name, edge_versions in self._data_versions.items():
            if key in edge_versions:
                versions[edge_name] = edge_versions[key]

        return versions

    def _resolve_conflict(self, versions: Dict[str, int]) -> tuple[str, int]:
        """Resolve version conflict using configured strategy."""
        # For now, last write wins (highest version)
        if not versions:
            return (None, 0)

        winner_edge = max(versions.items(), key=lambda x: x[1])
        return winner_edge

    async def _ensure_latest_version(self, key: str):
        """Ensure we have the latest version for strong consistency."""
        # In production, this would check with other edges
        await asyncio.sleep(0.01)  # Simulate version check

    async def _refresh_from_primary(self, key: str):
        """Refresh data from primary edge for bounded staleness."""
        # In production, this would fetch from primary
        await asyncio.sleep(0.02)  # Simulate refresh

    def _get_causal_dependencies(self, key: str) -> List[str]:
        """Get causal dependencies for a key."""
        # In production, track actual dependencies
        return []

    async def cleanup(self):
        """Cleanup resources including replication tasks."""
        # Cancel all replication tasks
        tasks_to_cancel = []
        for task_id, task in self._replication_tasks.items():
            if not task.done():
                task.cancel()
                tasks_to_cancel.append(task)

        # Wait for all cancelled tasks to complete
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

        # Clear the task registry
        self._replication_tasks.clear()
