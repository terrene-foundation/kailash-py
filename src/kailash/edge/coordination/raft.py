"""Raft consensus protocol implementation for edge coordination."""

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class RaftState(Enum):
    """Raft node states."""

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class LogEntry:
    """Entry in the Raft log."""

    term: int
    index: int
    command: Dict[str, Any]


@dataclass
class PersistentState:
    """Persistent state that must survive restarts."""

    current_term: int
    voted_for: Optional[str]
    log: List[LogEntry]


@dataclass
class RequestVoteRequest:
    """Request vote RPC request."""

    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int


@dataclass
class RequestVoteResponse:
    """Request vote RPC response."""

    term: int
    vote_granted: bool


@dataclass
class AppendEntriesRequest:
    """Append entries RPC request."""

    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: List[LogEntry]
    leader_commit: int


@dataclass
class AppendEntriesResponse:
    """Append entries RPC response."""

    term: int
    success: bool


class RaftNode:
    """Raft consensus node implementation."""

    def __init__(
        self,
        node_id: str,
        peers: List[str],
        election_timeout_ms: int = 150,
        heartbeat_interval_ms: int = 50,
        rpc_handler: Optional[Callable] = None,
    ):
        """Initialize Raft node.

        Args:
            node_id: Unique identifier for this node
            peers: List of peer node IDs
            election_timeout_ms: Base election timeout in milliseconds
            heartbeat_interval_ms: Heartbeat interval in milliseconds
            rpc_handler: Optional RPC handler for communication
        """
        self.node_id = node_id
        self.peers = peers
        self.election_timeout_ms = election_timeout_ms
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self._send_rpc = rpc_handler

        # Persistent state
        self.current_term = 0
        self.voted_for: Optional[str] = None
        self.log: List[LogEntry] = []

        # Volatile state
        self.state = RaftState.FOLLOWER
        self.commit_index = 0
        self.last_applied = 0

        # Leader state
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}

        # Other state
        self.leader_id: Optional[str] = None
        self.last_heartbeat = datetime.now()
        self.votes_received = 0

        # Background tasks
        self._election_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger = logging.getLogger(f"RaftNode[{node_id}]")

    async def start(self):
        """Start the Raft node."""
        self._running = True
        self.last_heartbeat = datetime.now()

        # Start election timeout task
        self._election_task = asyncio.create_task(self._election_timeout_loop())

        self.logger.info(f"Started as {self.state.value}")

    async def stop(self):
        """Stop the Raft node."""
        self._running = False

        if self._election_task:
            self._election_task.cancel()
            try:
                await self._election_task
            except asyncio.CancelledError:
                pass

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Stopped")

    async def propose(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Propose a command to the Raft cluster.

        Args:
            command: Command to propose

        Returns:
            Dict with success status and details
        """
        if self.state != RaftState.LEADER:
            return {
                "success": False,
                "error": "Not the leader",
                "leader": self.leader_id,
            }

        # Append to log
        entry = LogEntry(
            term=self.current_term, index=len(self.log) + 1, command=command
        )
        self.log.append(entry)

        # Replicate to followers
        await self._replicate_log()

        return {"success": True, "index": entry.index, "term": entry.term}

    async def handle_request_vote(
        self, request: RequestVoteRequest
    ) -> RequestVoteResponse:
        """Handle request vote RPC."""
        # Update term if needed
        if request.term > self.current_term:
            self.current_term = request.term
            self.voted_for = None
            self._become_follower()

        # Check if we can grant vote
        vote_granted = False

        if request.term < self.current_term:
            # Reject old term
            pass
        elif self.voted_for is None or self.voted_for == request.candidate_id:
            # Check log up-to-date
            if self._is_log_up_to_date(request.last_log_index, request.last_log_term):
                vote_granted = True
                self.voted_for = request.candidate_id
                self.last_heartbeat = datetime.now()

        return RequestVoteResponse(term=self.current_term, vote_granted=vote_granted)

    async def handle_append_entries(
        self, request: AppendEntriesRequest
    ) -> AppendEntriesResponse:
        """Handle append entries RPC."""
        # Update term if needed
        if request.term > self.current_term:
            self.current_term = request.term
            self.voted_for = None
            self._become_follower()

        # Reset election timeout
        self.last_heartbeat = datetime.now()

        # Reject if term is old
        if request.term < self.current_term:
            return AppendEntriesResponse(term=self.current_term, success=False)

        # Accept leader
        self.leader_id = request.leader_id
        if self.state == RaftState.CANDIDATE:
            self._become_follower()

        # Check log consistency
        if request.prev_log_index > 0:
            if request.prev_log_index > len(self.log):
                return AppendEntriesResponse(term=self.current_term, success=False)

            prev_entry = self.log[request.prev_log_index - 1]
            if prev_entry.term != request.prev_log_term:
                # Delete conflicting entries
                self.log = self.log[: request.prev_log_index - 1]
                return AppendEntriesResponse(term=self.current_term, success=False)

        # Append new entries
        if request.entries:
            self.log = self.log[: request.prev_log_index]
            self.log.extend(request.entries)

        # Update commit index
        if request.leader_commit > self.commit_index:
            self.commit_index = min(request.leader_commit, len(self.log))

        return AppendEntriesResponse(term=self.current_term, success=True)

    def _become_follower(self):
        """Transition to follower state."""
        self.state = RaftState.FOLLOWER
        self.votes_received = 0

        # Cancel heartbeat task if leader
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        self.logger.info(f"Became follower in term {self.current_term}")

    def _become_candidate(self):
        """Transition to candidate state."""
        self.state = RaftState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes_received = 1  # Vote for self
        self.leader_id = None

        self.logger.info(f"Became candidate in term {self.current_term}")

    def _become_leader(self):
        """Transition to leader state."""
        self.state = RaftState.LEADER
        self.leader_id = self.node_id

        # Initialize leader state
        for peer in self.peers:
            self.next_index[peer] = len(self.log) + 1
            self.match_index[peer] = 0

        # Start heartbeat task
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        self.logger.info(f"Became leader in term {self.current_term}")

    async def _election_timeout_loop(self):
        """Background task for election timeout."""
        while self._running:
            try:
                if self.state != RaftState.LEADER:
                    # Check election timeout
                    if self._election_timeout_elapsed():
                        await self._start_election()

                # Sleep for a bit
                await asyncio.sleep(0.01)  # 10ms

            except Exception as e:
                self.logger.error(f"Election loop error: {e}")

    async def _heartbeat_loop(self):
        """Background task for sending heartbeats."""
        while self._running and self.state == RaftState.LEADER:
            try:
                await self._send_heartbeats()
                await asyncio.sleep(self.heartbeat_interval_ms / 1000)
            except Exception as e:
                self.logger.error(f"Heartbeat loop error: {e}")

    async def _start_election(self):
        """Start leader election."""
        self._become_candidate()
        self.last_heartbeat = datetime.now()

        # Request votes from all peers
        await self._collect_votes()

    async def _collect_votes(self):
        """Collect votes from peers."""
        # Prepare request
        last_log_index = len(self.log)
        last_log_term = self.log[-1].term if self.log else 0

        request = RequestVoteRequest(
            term=self.current_term,
            candidate_id=self.node_id,
            last_log_index=last_log_index,
            last_log_term=last_log_term,
        )

        # Send vote requests
        tasks = []
        for peer in self.peers:
            if self._send_rpc:
                task = asyncio.create_task(self._send_request_vote(peer, request))
                tasks.append(task)

        # Collect responses
        if tasks:
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            for response in responses:
                if isinstance(response, RequestVoteResponse):
                    if response.term > self.current_term:
                        self.current_term = response.term
                        self._become_follower()
                        return

                    if response.vote_granted and response.term == self.current_term:
                        self.votes_received += 1

        # Check if we won
        if self.votes_received > (len(self.peers) + 1) // 2:
            self._become_leader()
        else:
            # Split vote, will retry after timeout
            pass

    async def _send_request_vote(
        self, peer: str, request: RequestVoteRequest
    ) -> Optional[RequestVoteResponse]:
        """Send request vote RPC to peer."""
        if self._send_rpc:
            return await self._send_rpc(
                peer, {"type": "request_vote", "request": request}
            )
        return None

    async def _send_heartbeats(self):
        """Send heartbeats to all peers."""
        tasks = []
        for peer in self.peers:
            task = asyncio.create_task(self._send_append_entries(peer))
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_append_entries(self, peer: str) -> Optional[AppendEntriesResponse]:
        """Send append entries RPC to peer."""
        prev_log_index = self.next_index.get(peer, 1) - 1
        prev_log_term = 0

        if prev_log_index > 0 and prev_log_index <= len(self.log):
            prev_log_term = self.log[prev_log_index - 1].term

        # Get entries to send
        entries = []
        if prev_log_index < len(self.log):
            entries = self.log[prev_log_index:]

        request = AppendEntriesRequest(
            term=self.current_term,
            leader_id=self.node_id,
            prev_log_index=prev_log_index,
            prev_log_term=prev_log_term,
            entries=entries,
            leader_commit=self.commit_index,
        )

        if self._send_rpc:
            response = await self._send_rpc(
                peer, {"type": "append_entries", "request": request}
            )

            if response:
                if response.term > self.current_term:
                    self.current_term = response.term
                    self._become_follower()
                elif response.success:
                    # Update match index
                    if entries:
                        self.match_index[peer] = prev_log_index + len(entries)
                        self.next_index[peer] = self.match_index[peer] + 1
                else:
                    # Decrement next index
                    self.next_index[peer] = max(1, self.next_index[peer] - 1)

            return response
        return None

    async def _replicate_log(self):
        """Replicate log entries to followers."""
        await self._send_heartbeats()
        await self._update_commit_index()

    async def _update_commit_index(self):
        """Update commit index based on replication."""
        if self.state != RaftState.LEADER:
            return

        # Find highest index replicated on majority
        for n in range(len(self.log), self.commit_index, -1):
            if self.log[n - 1].term == self.current_term:
                # Count replicas
                replicas = 1  # Self
                for peer in self.peers:
                    if self.match_index.get(peer, 0) >= n:
                        replicas += 1

                if replicas > (len(self.peers) + 1) // 2:
                    self.commit_index = n
                    break

    def _election_timeout_elapsed(self) -> bool:
        """Check if election timeout has elapsed."""
        timeout = self._randomize_election_timeout()
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds() * 1000
        return elapsed > timeout

    def _randomize_election_timeout(self) -> int:
        """Get randomized election timeout."""
        # Randomize between T and 2T
        return random.randint(self.election_timeout_ms, self.election_timeout_ms * 2)

    def _is_log_up_to_date(self, last_log_index: int, last_log_term: int) -> bool:
        """Check if candidate's log is at least as up-to-date as ours."""
        our_last_index = len(self.log)
        our_last_term = self.log[-1].term if self.log else 0

        if last_log_term != our_last_term:
            return last_log_term > our_last_term

        return last_log_index >= our_last_index

    def _save_persistent_state(self) -> PersistentState:
        """Save persistent state."""
        return PersistentState(
            current_term=self.current_term,
            voted_for=self.voted_for,
            log=self.log.copy(),
        )

    def _load_persistent_state(self, state: PersistentState):
        """Load persistent state."""
        self.current_term = state.current_term
        self.voted_for = state.voted_for
        self.log = state.log.copy()
