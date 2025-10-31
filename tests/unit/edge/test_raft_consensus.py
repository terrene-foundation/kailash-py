"""Unit tests for Raft consensus protocol implementation."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.edge.coordination.raft import (
    AppendEntriesRequest,
    AppendEntriesResponse,
    LogEntry,
    PersistentState,
    RaftNode,
    RaftState,
    RequestVoteRequest,
    RequestVoteResponse,
)


class TestRaftNode:
    """Test suite for RaftNode implementation."""

    @pytest.fixture
    def raft_node(self):
        """Create a RaftNode instance for testing."""
        node = RaftNode(
            node_id="node1",
            peers=["node2", "node3"],
            election_timeout_ms=150,
            heartbeat_interval_ms=50,
        )
        return node

    def test_initial_state(self, raft_node):
        """Test node starts as follower with term 0."""
        assert raft_node.state == RaftState.FOLLOWER
        assert raft_node.current_term == 0
        assert raft_node.voted_for is None
        assert raft_node.leader_id is None
        assert len(raft_node.log) == 0

    @pytest.mark.asyncio
    async def test_follower_to_candidate_transition(self, raft_node):
        """Test transition from follower to candidate on election timeout."""
        # Mock election timeout
        raft_node._election_timeout_elapsed = Mock(return_value=True)

        # Start election
        await raft_node._start_election()

        assert raft_node.state == RaftState.CANDIDATE
        assert raft_node.current_term == 1
        assert raft_node.voted_for == "node1"

    @pytest.mark.asyncio
    async def test_candidate_to_leader_election(self, raft_node):
        """Test successful leader election with majority votes."""
        raft_node.state = RaftState.CANDIDATE
        raft_node.current_term = 1
        raft_node.voted_for = "node1"
        raft_node.votes_received = 1  # Already voted for self

        # Mock RPC handler to return positive votes
        async def mock_rpc(peer, message):
            if message["type"] == "request_vote":
                return RequestVoteResponse(term=1, vote_granted=True)
            return None

        raft_node._send_rpc = mock_rpc

        await raft_node._collect_votes()

        # With 3 nodes total (self + 2 peers), need 2 votes to win
        # We start with 1 (self) and get 2 more = 3 total
        assert raft_node.votes_received == 3
        assert raft_node.state == RaftState.LEADER
        assert raft_node.leader_id == "node1"

    @pytest.mark.asyncio
    async def test_leader_to_follower_demotion(self, raft_node):
        """Test leader steps down when seeing higher term."""
        raft_node.state = RaftState.LEADER
        raft_node.current_term = 5
        raft_node.leader_id = "node1"

        # Receive append entries with higher term
        request = AppendEntriesRequest(
            term=6,
            leader_id="node2",
            prev_log_index=0,
            prev_log_term=0,
            entries=[],
            leader_commit=0,
        )

        response = await raft_node.handle_append_entries(request)

        assert raft_node.state == RaftState.FOLLOWER
        assert raft_node.current_term == 6
        assert raft_node.leader_id == "node2"
        assert response.success is True

    @pytest.mark.asyncio
    async def test_log_replication(self, raft_node):
        """Test log replication from leader to followers."""
        raft_node.state = RaftState.LEADER
        raft_node.current_term = 3

        # Add entries to leader's log
        entries = [
            LogEntry(term=3, index=1, command={"op": "set", "key": "x", "value": 1}),
            LogEntry(term=3, index=2, command={"op": "set", "key": "y", "value": 2}),
        ]
        raft_node.log.extend(entries)

        # Mock successful replication
        with patch.object(
            raft_node, "_send_append_entries", new_callable=AsyncMock
        ) as mock_send:
            mock_send.return_value = AppendEntriesResponse(term=3, success=True)

            await raft_node._replicate_log()

            # Verify append entries sent to all peers
            assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_commitment_rules(self, raft_node):
        """Test log entry commitment with majority acknowledgment."""
        raft_node.state = RaftState.LEADER
        raft_node.current_term = 2

        # Add uncommitted entries
        raft_node.log = [
            LogEntry(term=2, index=1, command={"op": "set", "key": "a", "value": 1}),
            LogEntry(term=2, index=2, command={"op": "set", "key": "b", "value": 2}),
        ]
        raft_node.commit_index = 0

        # Update match index for majority
        raft_node.match_index = {
            "node1": 2,  # Self
            "node2": 2,  # Peer 1 replicated
            "node3": 1,  # Peer 2 partially replicated
        }

        await raft_node._update_commit_index()

        # Should commit up to index 2 (majority have it)
        assert raft_node.commit_index == 2

    @pytest.mark.asyncio
    async def test_safety_properties(self, raft_node):
        """Test Raft safety properties are maintained."""
        # Test: Cannot vote for candidate with outdated log
        raft_node.current_term = 5
        raft_node.log = [
            LogEntry(term=3, index=1, command={"op": "set"}),
            LogEntry(term=4, index=2, command={"op": "set"}),
        ]

        # Candidate with older log
        vote_request = RequestVoteRequest(
            term=6, candidate_id="node2", last_log_index=1, last_log_term=3
        )

        response = await raft_node.handle_request_vote(vote_request)

        # Should not grant vote (our log is more up-to-date)
        assert response.vote_granted is False

    def test_persistent_state_save_load(self, raft_node):
        """Test persistent state is correctly saved and loaded."""
        # Set some state
        raft_node.current_term = 10
        raft_node.voted_for = "node2"
        raft_node.log = [
            LogEntry(term=9, index=1, command={"op": "set", "key": "x", "value": 1})
        ]

        # Save state
        state = raft_node._save_persistent_state()

        # Create new node and load state
        new_node = RaftNode("node1", ["node2", "node3"])
        new_node._load_persistent_state(state)

        assert new_node.current_term == 10
        assert new_node.voted_for == "node2"
        assert len(new_node.log) == 1
        assert new_node.log[0].term == 9

    @pytest.mark.asyncio
    async def test_election_timeout_randomization(self, raft_node):
        """Test election timeout is properly randomized."""
        timeouts = []

        for _ in range(10):
            timeout = raft_node._randomize_election_timeout()
            timeouts.append(timeout)

        # All timeouts should be different (with high probability)
        assert len(set(timeouts)) > 5

        # All should be within configured range
        for timeout in timeouts:
            assert 150 <= timeout <= 300  # 150-300ms range

    @pytest.mark.asyncio
    async def test_split_vote_handling(self, raft_node):
        """Test handling of split vote scenarios."""
        raft_node.state = RaftState.CANDIDATE
        raft_node.current_term = 1
        raft_node.votes_received = 1  # Self vote

        # Mock split vote (not enough votes)
        vote_responses = [
            RequestVoteResponse(
                term=1, vote_granted=False
            ),  # Peer 1 voted for someone else
            RequestVoteResponse(
                term=1, vote_granted=False
            ),  # Peer 2 voted for someone else
        ]

        with patch.object(
            raft_node, "_send_request_vote", new_callable=AsyncMock
        ) as mock_send:
            mock_send.side_effect = vote_responses

            await raft_node._collect_votes()

            # Should remain candidate (didn't win election)
            assert raft_node.state == RaftState.CANDIDATE
            # Term doesn't automatically increment on split vote - that happens on next election
            assert raft_node.votes_received == 1  # Only self vote
