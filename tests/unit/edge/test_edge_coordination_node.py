"""Unit tests for EdgeCoordinationNode."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.edge.coordination.global_ordering import GlobalOrderingService
from kailash.edge.coordination.leader_election import EdgeLeaderElection
from kailash.edge.coordination.raft import RaftNode, RaftState
from kailash.nodes.edge.coordination import EdgeCoordinationNode


@pytest.fixture
def coordination_node():
    """Create EdgeCoordinationNode instance for testing."""
    node = EdgeCoordinationNode(
        coordination_group="test-group", node_id="edge1", peers=["edge2", "edge3"]
    )

    # Mock dependencies
    node.raft_node = Mock(spec=RaftNode)
    node.leader_election = Mock(spec=EdgeLeaderElection)
    node.ordering_service = Mock(spec=GlobalOrderingService)

    return node


class TestEdgeCoordinationNode:
    """Test suite for EdgeCoordinationNode."""

    def test_get_parameters(self, coordination_node):
        """Test node parameter definitions."""
        params = coordination_node.get_parameters()

        assert "operation" in params
        assert params["operation"].required is True
        assert params["operation"].type == str

        assert "coordination_group" in params
        assert params["coordination_group"].default == "default"

        assert "proposal" in params
        assert params["proposal"].required is False

    @pytest.mark.asyncio
    async def test_elect_leader_operation(self, coordination_node):
        """Test leader election operation."""
        coordination_node.leader_election.start_election = AsyncMock(
            return_value={"leader": "edge2", "term": 5}
        )

        result = await coordination_node.execute_async(operation="elect_leader")

        assert result["success"] is True
        assert result["leader"] == "edge2"
        assert result["term"] == 5
        coordination_node.leader_election.start_election.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_leader_operation(self, coordination_node):
        """Test get current leader operation."""
        coordination_node.leader_election.get_current_leader.return_value = {
            "leader": "edge1",
            "term": 3,
            "stable": True,
        }

        result = await coordination_node.execute_async(operation="get_leader")

        assert result["success"] is True
        assert result["leader"] == "edge1"
        assert result["term"] == 3
        assert result["stable"] is True

    @pytest.mark.asyncio
    async def test_propose_operation(self, coordination_node):
        """Test consensus proposal operation."""
        proposal = {"action": "update_config", "data": {"max_replicas": 5}}

        # Setup leader for proposal
        coordination_node.leader_election.get_current_leader.return_value = {
            "leader": "edge1",
            "term": 7,
            "stable": True,
        }

        coordination_node.raft_node.propose = AsyncMock(
            return_value={"success": True, "index": 42, "term": 7}
        )

        result = await coordination_node.execute_async(
            operation="propose", proposal=proposal
        )

        assert result["success"] is True
        assert result["accepted"] is True
        assert result["log_index"] == 42
        coordination_node.raft_node.propose.assert_called_with(proposal)

    @pytest.mark.asyncio
    async def test_global_order_operation(self, coordination_node):
        """Test global ordering operation."""
        events = [
            {"id": "evt1", "timestamp": "2024-01-01T00:00:00Z"},
            {"id": "evt2", "timestamp": "2024-01-01T00:00:01Z"},
        ]

        coordination_node.ordering_service.order_events = AsyncMock(
            return_value={
                "ordered_events": events,
                "logical_clock": 100,
                "causal_dependencies": {},
            }
        )

        result = await coordination_node.execute_async(
            operation="global_order", events=events
        )

        assert result["success"] is True
        assert len(result["ordered_events"]) == 2
        assert result["logical_clock"] == 100

    @pytest.mark.asyncio
    async def test_invalid_operation(self, coordination_node):
        """Test handling of invalid operation."""
        result = await coordination_node.execute_async(operation="invalid_op")

        assert result["success"] is False
        assert "error" in result
        assert "Unknown operation" in result["error"]

    @pytest.mark.asyncio
    async def test_propose_without_proposal(self, coordination_node):
        """Test propose operation without proposal data."""
        result = await coordination_node.execute_async(operation="propose")

        assert result["success"] is False
        assert "Proposal required" in result["error"]

    @pytest.mark.asyncio
    async def test_leader_required_operation_without_leader(self, coordination_node):
        """Test operations that require leader when no leader exists."""
        coordination_node.leader_election.get_current_leader.return_value = {
            "leader": None,
            "term": 0,
            "stable": False,
        }

        coordination_node.raft_node.propose = AsyncMock()

        result = await coordination_node.execute_async(
            operation="propose", proposal={"data": "test"}
        )

        assert result["success"] is False
        assert "No leader elected" in result["error"]
        coordination_node.raft_node.propose.assert_not_called()

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, coordination_node):
        """Test metrics are properly tracked."""
        coordination_node.leader_election.start_election = AsyncMock(
            return_value={"leader": "edge1", "term": 1}
        )

        # Setup leader for propose operation
        coordination_node.leader_election.get_current_leader.return_value = {
            "leader": "edge1",
            "term": 1,
            "stable": True,
        }

        # Mock raft propose
        coordination_node.raft_node.propose = AsyncMock(
            return_value={"success": True, "index": 1, "term": 1}
        )

        # Mock ordering service
        coordination_node.ordering_service.order_events = AsyncMock(
            return_value={
                "ordered_events": [],
                "logical_clock": 0,
                "causal_dependencies": {},
            }
        )

        # Reset metrics
        coordination_node.metrics = {
            "elections_started": 0,
            "consensus_proposals": 0,
            "ordering_requests": 0,
            "errors": 0,
        }

        # Perform operations
        await coordination_node.execute_async(operation="elect_leader")
        await coordination_node.execute_async(
            operation="propose", proposal={"test": "data"}
        )
        await coordination_node.execute_async(operation="global_order", events=[])

        assert coordination_node.metrics["elections_started"] == 1
        assert coordination_node.metrics["consensus_proposals"] == 1
        assert coordination_node.metrics["ordering_requests"] == 1

    @pytest.mark.asyncio
    async def test_coordination_group_isolation(self, coordination_node):
        """Test coordination groups are properly isolated."""
        # Create two nodes in different groups
        node1 = EdgeCoordinationNode(coordination_group="group1", node_id="edge1")
        node2 = EdgeCoordinationNode(coordination_group="group2", node_id="edge1")

        # Ensure services are initialized
        await node1._ensure_services()
        await node2._ensure_services()

        # They should have different Raft instances
        assert node1.coordination_group != node2.coordination_group
        assert node1.raft_node is not node2.raft_node
