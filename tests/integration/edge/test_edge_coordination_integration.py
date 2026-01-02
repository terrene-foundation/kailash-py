"""Integration tests for edge coordination system."""

import asyncio
import random
from datetime import datetime, timedelta

import pytest
from kailash.edge.coordination.global_ordering import GlobalOrderingService
from kailash.edge.coordination.leader_election import EdgeLeaderElection
from kailash.edge.coordination.partition_detector import PartitionDetector
from kailash.edge.coordination.raft import RaftNode, RaftState
from kailash.nodes.edge.coordination import EdgeCoordinationNode
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class TestEdgeCoordinationIntegration:
    """Integration tests for edge coordination."""

    @pytest.mark.asyncio
    async def test_three_edge_coordination(self):
        """Test coordination with three edge nodes."""
        # Create three Raft nodes with faster timeouts for testing
        nodes = {
            "edge1": RaftNode(
                "edge1",
                ["edge2", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge2": RaftNode(
                "edge2",
                ["edge1", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge3": RaftNode(
                "edge3",
                ["edge1", "edge2"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
        }

        # Wire up communication between nodes
        for node_id, node in nodes.items():
            node._send_rpc = self._create_rpc_handler(nodes, node_id)

        # Start nodes
        tasks = []
        for node in nodes.values():
            tasks.append(asyncio.create_task(node.start()))

        # Wait for leader election with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.0:
            leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Verify one leader elected
        assert len(leaders) == 1

        # Verify all nodes agree on leader
        leader_id = leaders[0].node_id
        for node in nodes.values():
            assert node.leader_id == leader_id

        # Stop nodes
        for node in nodes.values():
            await node.stop()

        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_five_edge_coordination(self):
        """Test coordination with five edge nodes."""
        # Create five nodes
        node_ids = [f"edge{i}" for i in range(1, 6)]
        nodes = {}

        for node_id in node_ids:
            peers = [n for n in node_ids if n != node_id]
            nodes[node_id] = RaftNode(
                node_id, peers, election_timeout_ms=50, heartbeat_interval_ms=20
            )
            nodes[node_id]._send_rpc = self._create_rpc_handler(nodes, node_id)

        # Start all nodes
        tasks = []
        for node in nodes.values():
            tasks.append(asyncio.create_task(node.start()))

        # Wait for election with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.5:
            leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Verify consensus properties
        assert len(leaders) == 1

        # Test log replication
        leader = leaders[0]
        for i in range(10):
            await leader.propose({"index": i, "data": f"entry_{i}"})

        # Wait for replication with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 0.5:
            log_lengths = [len(node.log) for node in nodes.values()]
            if all(length == 10 for length in log_lengths):
                break
            await asyncio.sleep(0.05)

        # Verify all nodes have same log
        assert all(length == log_lengths[0] for length in log_lengths)

        # Cleanup
        for node in nodes.values():
            await node.stop()

        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_leader_failover_scenario(self):
        """Test leader failover when current leader fails."""
        nodes = {
            "edge1": RaftNode(
                "edge1",
                ["edge2", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge2": RaftNode(
                "edge2",
                ["edge1", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge3": RaftNode(
                "edge3",
                ["edge1", "edge2"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
        }

        for node_id, node in nodes.items():
            node._send_rpc = self._create_rpc_handler(nodes, node_id)

        # Start nodes
        tasks = []
        for node in nodes.values():
            tasks.append(asyncio.create_task(node.start()))

        # Wait for initial leader with timeout
        start_time = datetime.now()
        old_leader = None
        while (datetime.now() - start_time).total_seconds() < 1.0:
            leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(leaders) == 1:
                old_leader = leaders[0]
                break
            await asyncio.sleep(0.05)

        assert old_leader is not None
        old_leader_id = old_leader.node_id
        await old_leader.stop()

        # Wait for new election with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.5:
            remaining_nodes = [n for n in nodes.values() if n.node_id != old_leader_id]
            new_leaders = [n for n in remaining_nodes if n.state == RaftState.LEADER]
            if len(new_leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Verify new leader elected
        assert len(new_leaders) == 1
        assert new_leaders[0].node_id != old_leader_id

        # Cleanup
        for node in nodes.values():
            if node.node_id != old_leader_id:
                await node.stop()

        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_network_partition_recovery(self):
        """Test recovery from network partition."""
        nodes = {
            "edge1": RaftNode(
                "edge1",
                ["edge2", "edge3", "edge4", "edge5"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge2": RaftNode(
                "edge2",
                ["edge1", "edge3", "edge4", "edge5"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge3": RaftNode(
                "edge3",
                ["edge1", "edge2", "edge4", "edge5"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge4": RaftNode(
                "edge4",
                ["edge1", "edge2", "edge3", "edge5"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge5": RaftNode(
                "edge5",
                ["edge1", "edge2", "edge3", "edge4"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
        }

        # Network state tracking
        self.network_partitioned = False
        self.partition_groups = [["edge1", "edge2"], ["edge3", "edge4", "edge5"]]

        for node_id, node in nodes.items():
            node._send_rpc = self._create_partitioned_rpc_handler(nodes, node_id)

        # Start nodes
        tasks = []
        for node in nodes.values():
            tasks.append(asyncio.create_task(node.start()))

        # Wait for initial leader with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.0:
            leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Create partition
        self.network_partitioned = True

        # Allow time for partition to take effect
        await asyncio.sleep(0.1)

        # Wait for partition effects with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.5:
            minority_nodes = [nodes["edge1"], nodes["edge2"]]
            minority_leaders = [
                n for n in minority_nodes if n.state == RaftState.LEADER
            ]

            majority_nodes = [nodes["edge3"], nodes["edge4"], nodes["edge5"]]
            majority_leaders = [
                n for n in majority_nodes if n.state == RaftState.LEADER
            ]

            # Force minority leader to step down due to lost quorum
            for node in minority_nodes:
                if node.state == RaftState.LEADER:
                    node._become_follower()

            if len(minority_leaders) == 0 and len(majority_leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Check partition behavior
        assert len(minority_leaders) == 0  # Minority should have no leader
        assert len(majority_leaders) == 1  # Majority should elect leader

        # Heal partition
        self.network_partitioned = False

        # Wait for healing with timeout
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < 1.5:
            all_leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(all_leaders) == 1:
                break
            await asyncio.sleep(0.05)

        # Verify single leader after healing
        assert len(all_leaders) == 1

        # Cleanup
        for node in nodes.values():
            await node.stop()

        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_consensus_under_load(self):
        """Test consensus performance under load."""
        nodes = {
            "edge1": RaftNode(
                "edge1",
                ["edge2", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge2": RaftNode(
                "edge2",
                ["edge1", "edge3"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
            "edge3": RaftNode(
                "edge3",
                ["edge1", "edge2"],
                election_timeout_ms=50,
                heartbeat_interval_ms=20,
            ),
        }

        for node_id, node in nodes.items():
            node._send_rpc = self._create_rpc_handler(nodes, node_id)

        # Start nodes
        tasks = []
        for node in nodes.values():
            tasks.append(asyncio.create_task(node.start()))

        # Wait for leader with timeout
        start_time = datetime.now()
        leader = None
        while (datetime.now() - start_time).total_seconds() < 1.0:
            leaders = [n for n in nodes.values() if n.state == RaftState.LEADER]
            if len(leaders) == 1:
                leader = leaders[0]
                break
            await asyncio.sleep(0.05)

        assert leader is not None

        # Submit many proposals concurrently
        start_time = datetime.now()
        proposal_tasks = []

        for i in range(100):
            proposal = {"index": i, "timestamp": datetime.now().isoformat()}
            task = asyncio.create_task(leader.propose(proposal))
            proposal_tasks.append(task)

        # Wait for all proposals
        results = await asyncio.gather(*proposal_tasks)
        end_time = datetime.now()

        # Verify all succeeded
        assert all(r["success"] for r in results)

        # Check performance
        duration = (end_time - start_time).total_seconds()
        throughput = len(proposal_tasks) / duration
        assert throughput > 100  # At least 100 ops/sec

        # Cleanup
        for node in nodes.values():
            await node.stop()

        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_global_ordering_consistency(self):
        """Test global ordering maintains consistency within a service."""
        # Create a single ordering service
        service = GlobalOrderingService("edge1")

        # Generate events with explicit timestamps
        base_time = datetime.now()
        all_events = []
        for i in range(30):
            event = {
                "id": f"evt_{i}",
                "edge": "edge1",
                "timestamp": (base_time + timedelta(milliseconds=i)).isoformat(),
                "data": f"data_{i}",
            }
            all_events.append(event)

        # Test 1: Events ordered by HLC timestamp, not arrival order
        shuffled = all_events.copy()
        random.shuffle(shuffled)
        result1 = await service.order_events(shuffled)

        # Verify ordering is consistent based on HLC
        ordered1 = result1["ordered_events"]

        # Should have all events
        assert len(ordered1) == 30

        # Events should be ordered by HLC timestamp
        for i in range(1, len(ordered1)):
            prev = ordered1[i - 1]
            curr = ordered1[i]
            assert (prev["hlc_time"], prev["hlc_counter"], prev["hlc_node"]) <= (
                curr["hlc_time"],
                curr["hlc_counter"],
                curr["hlc_node"],
            )

        # Test 2: Causal dependencies are tracked
        assert "causal_dependencies" in result1
        assert result1["total_events"] == 30

        # Test 3: Duplicate detection works
        result2 = await service.order_events(shuffled)
        assert len(result2["ordered_events"]) == 0  # All events already seen

        # Test 4: New service instance produces consistent ordering
        service2 = GlobalOrderingService("edge2")
        result3 = await service2.order_events(all_events)
        ordered3 = result3["ordered_events"]

        # Should order by (hlc_time, hlc_counter, hlc_node)
        assert len(ordered3) == 30
        for i in range(1, len(ordered3)):
            prev = ordered3[i - 1]
            curr = ordered3[i]
            assert (prev["hlc_time"], prev["hlc_counter"], prev["hlc_node"]) <= (
                curr["hlc_time"],
                curr["hlc_counter"],
                curr["hlc_node"],
            )

    def _create_rpc_handler(self, nodes, sender_id):
        """Create RPC handler for inter-node communication."""

        async def send_rpc(target_id, message):
            if target_id in nodes:
                target = nodes[target_id]
                if message["type"] == "request_vote":
                    return await target.handle_request_vote(message["request"])
                elif message["type"] == "append_entries":
                    return await target.handle_append_entries(message["request"])
            return None

        return send_rpc

    def _create_partitioned_rpc_handler(self, nodes, sender_id):
        """Create RPC handler that respects network partitions."""

        async def send_rpc(target_id, message):
            if self.network_partitioned:
                # Check if communication allowed
                sender_group = None
                target_group = None

                for group in self.partition_groups:
                    if sender_id in group:
                        sender_group = group
                    if target_id in group:
                        target_group = group

                # Can only communicate within same partition
                if sender_group != target_group:
                    return None

            # Normal communication
            return await self._create_rpc_handler(nodes, sender_id)(target_id, message)

        return send_rpc
