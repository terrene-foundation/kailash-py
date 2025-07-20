"""Edge leader election service using Raft consensus."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .raft import RaftNode, RaftState


class EdgeLeaderElection:
    """Leader election service for edge nodes using Raft consensus.

    This service manages leader election across edge nodes, providing:
    - Automatic leader election on startup
    - Leader failure detection and re-election
    - Stable leader information for coordination
    - Network partition handling
    """

    def __init__(self, raft_nodes: Dict[str, RaftNode]):
        """Initialize leader election service.

        Args:
            raft_nodes: Dictionary of node_id -> RaftNode instances
        """
        self.raft_nodes = raft_nodes
        self.current_leader: Optional[str] = None
        self.current_term: int = 0
        self.last_leader_change = datetime.now()
        self.stability_threshold = timedelta(seconds=5)
        self.logger = logging.getLogger("EdgeLeaderElection")

        # Election monitoring
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start leader election monitoring."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_leadership())
        self.logger.info("Leader election service started")

    async def stop(self):
        """Stop leader election monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Leader election service stopped")

    async def start_election(self) -> Dict[str, Any]:
        """Start a new leader election.

        Returns:
            Dict with election results including leader and term
        """
        self.logger.info("Starting new leader election")

        # Find a candidate node to trigger election
        candidate_nodes = [
            node for node in self.raft_nodes.values() if node.state != RaftState.LEADER
        ]

        if not candidate_nodes:
            # Current leader still active
            return self.get_current_leader()

        # Trigger election on first non-leader node
        candidate = candidate_nodes[0]
        candidate._become_candidate()
        await candidate._collect_votes()

        # Wait briefly for election to complete
        await asyncio.sleep(0.1)

        # Update and return leader info
        self._update_leader_info()
        return self.get_current_leader()

    def get_current_leader(self) -> Dict[str, Any]:
        """Get current leader information.

        Returns:
            Dict with leader ID, term, and stability status
        """
        self._update_leader_info()

        stable = False
        if self.current_leader:
            time_since_change = datetime.now() - self.last_leader_change
            stable = time_since_change > self.stability_threshold

        return {
            "leader": self.current_leader,
            "term": self.current_term,
            "stable": stable,
            "time_since_change": (
                datetime.now() - self.last_leader_change
            ).total_seconds(),
        }

    def force_election(self) -> None:
        """Force a new election by demoting current leader."""
        for node_id, node in self.raft_nodes.items():
            if node.state == RaftState.LEADER:
                node._become_follower()
                self.logger.info(f"Forced leader {node_id} to step down")
                break

    async def wait_for_stable_leader(self, timeout: float = 10.0) -> Dict[str, Any]:
        """Wait for a stable leader to be elected.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            Leader information once stable

        Raises:
            TimeoutError: If no stable leader within timeout
        """
        start_time = datetime.now()

        while (datetime.now() - start_time).total_seconds() < timeout:
            leader_info = self.get_current_leader()

            if leader_info["leader"] and leader_info["stable"]:
                return leader_info

            await asyncio.sleep(0.1)

        raise TimeoutError(f"No stable leader elected within {timeout} seconds")

    def _update_leader_info(self):
        """Update current leader information from Raft nodes."""
        new_leader = None
        new_term = 0

        for node_id, node in self.raft_nodes.items():
            if node.state == RaftState.LEADER:
                new_leader = node_id
                new_term = node.current_term
                break

        # Check if leader changed
        if new_leader != self.current_leader or new_term != self.current_term:
            self.current_leader = new_leader
            self.current_term = new_term
            self.last_leader_change = datetime.now()

            if new_leader:
                self.logger.info(f"New leader elected: {new_leader} (term {new_term})")
            else:
                self.logger.warning("No leader - cluster in election")

    async def _monitor_leadership(self):
        """Background task to monitor leadership stability."""
        while self._running:
            try:
                self._update_leader_info()

                # Check if we need to trigger election
                leader_info = self.get_current_leader()
                if not leader_info["leader"]:
                    # No leader for too long
                    time_without_leader = (
                        datetime.now() - self.last_leader_change
                    ).total_seconds()
                    if time_without_leader > 2.0:  # 2 seconds without leader
                        self.logger.warning(
                            "No leader for 2 seconds, triggering election"
                        )
                        await self.start_election()

                await asyncio.sleep(0.5)  # Check every 500ms

            except Exception as e:
                self.logger.error(f"Leadership monitor error: {e}")

    def get_cluster_health(self) -> Dict[str, Any]:
        """Get health information about the cluster.

        Returns:
            Dict with cluster health metrics
        """
        total_nodes = len(self.raft_nodes)
        leader_count = sum(
            1 for node in self.raft_nodes.values() if node.state == RaftState.LEADER
        )
        follower_count = sum(
            1 for node in self.raft_nodes.values() if node.state == RaftState.FOLLOWER
        )
        candidate_count = sum(
            1 for node in self.raft_nodes.values() if node.state == RaftState.CANDIDATE
        )

        # Check for split brain
        split_brain = leader_count > 1

        # Check for partitions
        has_quorum = (follower_count + leader_count) > total_nodes // 2

        return {
            "total_nodes": total_nodes,
            "leader_count": leader_count,
            "follower_count": follower_count,
            "candidate_count": candidate_count,
            "split_brain": split_brain,
            "has_quorum": has_quorum,
            "current_leader": self.current_leader,
            "current_term": self.current_term,
            "healthy": leader_count == 1 and has_quorum and not split_brain,
        }
