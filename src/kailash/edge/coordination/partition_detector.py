"""Network partition detection for edge coordination."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


class PartitionDetector:
    """Detects network partitions in distributed edge systems.

    Uses heartbeat monitoring and cluster state analysis to detect:
    - Network partitions (split-brain scenarios)
    - Node failures
    - Connectivity issues
    - Quorum status
    """

    def __init__(
        self,
        node_id: str,
        peers: List[str],
        heartbeat_interval_ms: int = 100,
        failure_threshold_ms: int = 500,
    ):
        """Initialize partition detector.

        Args:
            node_id: This node's identifier
            peers: List of peer node IDs
            heartbeat_interval_ms: Heartbeat interval in milliseconds
            failure_threshold_ms: Time without heartbeat to consider failure
        """
        self.node_id = node_id
        self.peers = set(peers)
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.failure_threshold_ms = failure_threshold_ms

        # Heartbeat tracking
        self.last_heartbeats: Dict[str, datetime] = {}
        self.peer_connections: Dict[str, Set[str]] = defaultdict(set)
        self.my_connections: Set[str] = set()

        # Partition state
        self.current_partition: Optional[Set[str]] = None
        self.partition_start_time: Optional[datetime] = None
        self.partition_history: List[Dict[str, Any]] = []

        # Monitoring
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self.logger = logging.getLogger(f"PartitionDetector[{node_id}]")

    async def start(self):
        """Start partition detection."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_partitions())
        self.logger.info("Partition detector started")

    async def stop(self):
        """Stop partition detection."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Partition detector stopped")

    def record_heartbeat(self, from_node: str):
        """Record heartbeat from a peer node.

        Args:
            from_node: Node ID that sent heartbeat
        """
        self.last_heartbeats[from_node] = datetime.now()
        self.my_connections.add(from_node)

    def update_peer_connections(self, node_id: str, connections: Set[str]):
        """Update connectivity information for a peer.

        Args:
            node_id: Peer node ID
            connections: Set of nodes the peer can reach
        """
        self.peer_connections[node_id] = connections

    def get_partition_status(self) -> Dict[str, Any]:
        """Get current partition status.

        Returns:
            Dict with partition information
        """
        now = datetime.now()
        active_peers = self._get_active_peers(now)

        # Check for partition
        is_partitioned = self._detect_partition(active_peers)

        # Calculate quorum
        total_nodes = len(self.peers) + 1  # Include self
        reachable_nodes = len(active_peers) + 1  # Include self
        has_quorum = reachable_nodes > total_nodes // 2

        # Get partition groups
        groups = self._identify_partition_groups(active_peers)

        return {
            "is_partitioned": is_partitioned,
            "has_quorum": has_quorum,
            "reachable_nodes": reachable_nodes,
            "total_nodes": total_nodes,
            "active_peers": list(active_peers),
            "unreachable_peers": list(self.peers - active_peers),
            "partition_groups": groups,
            "current_partition": (
                list(self.current_partition) if self.current_partition else None
            ),
            "partition_duration": self._get_partition_duration(),
        }

    def _get_active_peers(self, now: datetime) -> Set[str]:
        """Get set of currently active peers.

        Args:
            now: Current time

        Returns:
            Set of active peer IDs
        """
        active = set()
        threshold = timedelta(milliseconds=self.failure_threshold_ms)

        for peer in self.peers:
            if peer in self.last_heartbeats:
                if now - self.last_heartbeats[peer] < threshold:
                    active.add(peer)

        return active

    def _detect_partition(self, active_peers: Set[str]) -> bool:
        """Detect if network is partitioned.

        Args:
            active_peers: Set of active peer IDs

        Returns:
            True if partition detected
        """
        # Simple detection: partition if we can't reach all peers
        # but some peers can reach each other
        if len(active_peers) < len(self.peers):
            # Check if unreachable peers can reach each other
            unreachable = self.peers - active_peers

            for peer in unreachable:
                if peer in self.peer_connections:
                    # Check if this peer can reach other unreachable peers
                    peer_reach = self.peer_connections[peer]
                    if peer_reach & unreachable:
                        # Partition detected
                        return True

        return False

    def _identify_partition_groups(self, active_peers: Set[str]) -> List[Set[str]]:
        """Identify partition groups in the network.

        Args:
            active_peers: Set of active peer IDs

        Returns:
            List of partition groups (sets of node IDs)
        """
        # Build connectivity graph
        graph = defaultdict(set)

        # Add self connections
        graph[self.node_id] = active_peers.copy()

        # Add peer connections
        for peer, connections in self.peer_connections.items():
            graph[peer] = connections.copy()

        # Find connected components
        visited = set()
        groups = []

        def dfs(node: str, group: Set[str]):
            if node in visited:
                return
            visited.add(node)
            group.add(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, group)

        # Start DFS from all nodes
        all_nodes = {self.node_id} | self.peers
        for node in all_nodes:
            if node not in visited:
                group = set()
                dfs(node, group)
                if group:
                    groups.append(group)

        return groups

    def _get_partition_duration(self) -> Optional[float]:
        """Get duration of current partition in seconds.

        Returns:
            Duration in seconds or None if not partitioned
        """
        if self.partition_start_time:
            return (datetime.now() - self.partition_start_time).total_seconds()
        return None

    async def _monitor_partitions(self):
        """Background task to monitor for partitions."""
        while self._running:
            try:
                status = self.get_partition_status()

                # Check for partition state change
                if status["is_partitioned"] and not self.current_partition:
                    # New partition detected
                    self.current_partition = set(status["active_peers"])
                    self.current_partition.add(self.node_id)
                    self.partition_start_time = datetime.now()

                    self.logger.warning(
                        f"Network partition detected! In partition with: {self.current_partition}"
                    )

                    # Record in history
                    self.partition_history.append(
                        {
                            "detected_at": self.partition_start_time,
                            "partition": list(self.current_partition),
                            "groups": status["partition_groups"],
                        }
                    )

                elif not status["is_partitioned"] and self.current_partition:
                    # Partition healed
                    duration = self._get_partition_duration()
                    self.logger.info(
                        f"Network partition healed after {duration:.2f} seconds"
                    )

                    # Update history
                    if self.partition_history:
                        self.partition_history[-1]["healed_at"] = datetime.now()
                        self.partition_history[-1]["duration"] = duration

                    self.current_partition = None
                    self.partition_start_time = None

                await asyncio.sleep(self.heartbeat_interval_ms / 1000)

            except Exception as e:
                self.logger.error(f"Partition monitor error: {e}")

    def should_participate_in_election(self) -> bool:
        """Check if this node should participate in leader election.

        Returns:
            True if node should participate (has quorum)
        """
        status = self.get_partition_status()
        return status["has_quorum"]

    def get_partition_metrics(self) -> Dict[str, Any]:
        """Get partition detection metrics.

        Returns:
            Dict with partition metrics
        """
        total_partitions = len(self.partition_history)
        total_duration = sum(p.get("duration", 0) for p in self.partition_history)

        current_duration = self._get_partition_duration()
        if current_duration:
            total_duration += current_duration

        return {
            "total_partitions": total_partitions,
            "total_partition_duration": total_duration,
            "current_partition_duration": current_duration,
            "partition_history_size": len(self.partition_history),
            "is_currently_partitioned": self.current_partition is not None,
        }
