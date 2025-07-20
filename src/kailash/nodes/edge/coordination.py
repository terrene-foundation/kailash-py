"""Edge coordination node for distributed consensus operations."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from kailash.edge.coordination import (
    EdgeLeaderElection,
    GlobalOrderingService,
    RaftNode,
    RaftState,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class EdgeCoordinationNode(AsyncNode):
    """Node providing distributed coordination operations for edge computing.

    This node enables:
    - Leader election among edge nodes
    - Distributed consensus via Raft
    - Global event ordering
    - Split-brain prevention

    Example:
        ```python
        # Elect leader for coordination group
        workflow.add_node("EdgeCoordinationNode", "coordinator", {
            "operation": "elect_leader",
            "coordination_group": "cache_cluster"
        })

        # Propose change through consensus
        workflow.add_node("EdgeCoordinationNode", "propose", {
            "operation": "propose",
            "coordination_group": "cache_cluster",
            "proposal": {"action": "invalidate", "keys": ["user:*"]}
        })
        ```
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get node parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform: elect_leader|get_leader|propose|global_order",
            ),
            "coordination_group": NodeParameter(
                name="coordination_group",
                type=str,
                default="default",
                required=False,
                description="Coordination group name for isolation",
            ),
            "node_id": NodeParameter(
                name="node_id",
                type=str,
                required=False,
                description="Unique node ID (auto-generated if not provided)",
            ),
            "peers": NodeParameter(
                name="peers",
                type=list,
                required=False,
                description="List of peer node IDs",
            ),
            "proposal": NodeParameter(
                name="proposal",
                type=dict,
                required=False,
                description="Proposal data for consensus",
            ),
            "events": NodeParameter(
                name="events",
                type=list,
                required=False,
                description="Events to order globally",
            ),
        }

    # Class-level coordination groups
    _coordination_groups: Dict[str, Dict[str, Any]] = {}

    def __init__(self, **config):
        """Initialize coordination node."""
        super().__init__(**config)

        self.coordination_group = config.get("coordination_group", "default")
        self.node_id = config.get("node_id", f"node_{id(self)}")
        self.peers = config.get("peers", [])

        # Get or create coordination group
        if self.coordination_group not in self._coordination_groups:
            self._coordination_groups[self.coordination_group] = {
                "raft_nodes": {},
                "leader_election": None,
                "ordering_service": None,
            }

        self.group = self._coordination_groups[self.coordination_group]

        # Initialize services lazily
        self.raft_node: Optional[RaftNode] = None
        self.leader_election: Optional[EdgeLeaderElection] = None
        self.ordering_service: Optional[GlobalOrderingService] = None

        # Metrics
        self.metrics = {
            "elections_started": 0,
            "consensus_proposals": 0,
            "ordering_requests": 0,
            "errors": 0,
        }

    async def _ensure_services(self):
        """Ensure required services are initialized."""
        # Initialize Raft node if needed
        if self.raft_node is None:
            if self.node_id in self.group["raft_nodes"]:
                self.raft_node = self.group["raft_nodes"][self.node_id]
            else:
                self.raft_node = RaftNode(self.node_id, self.peers or [])
                self.group["raft_nodes"][self.node_id] = self.raft_node
                await self.raft_node.start()

        # Initialize leader election service
        if self.leader_election is None:
            if self.group["leader_election"] is None:
                self.group["leader_election"] = EdgeLeaderElection(
                    self.group["raft_nodes"]
                )
            self.leader_election = self.group["leader_election"]

        # Initialize ordering service
        if self.ordering_service is None:
            if self.group["ordering_service"] is None:
                self.group["ordering_service"] = GlobalOrderingService(self.node_id)
            self.ordering_service = self.group["ordering_service"]

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute coordination operation."""
        await self._ensure_services()

        operation = kwargs.get("operation")

        try:
            if operation == "elect_leader":
                return await self._handle_elect_leader(kwargs)
            elif operation == "get_leader":
                return await self._handle_get_leader(kwargs)
            elif operation == "propose":
                return await self._handle_propose(kwargs)
            elif operation == "global_order":
                return await self._handle_global_order(kwargs)
            else:
                self.metrics["errors"] += 1
                return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            self.logger.error(f"Coordination operation failed: {e}")
            self.metrics["errors"] += 1
            return {"success": False, "error": str(e)}

    async def _handle_elect_leader(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle leader election operation."""
        self.metrics["elections_started"] += 1

        result = await self.leader_election.start_election()

        return {
            "success": True,
            "leader": result["leader"],
            "term": result["term"],
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_get_leader(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get current leader operation."""
        leader_info = self.leader_election.get_current_leader()

        return {
            "success": True,
            "leader": leader_info["leader"],
            "term": leader_info["term"],
            "stable": leader_info["stable"],
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_propose(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consensus proposal operation."""
        proposal = params.get("proposal")
        if not proposal:
            return {
                "success": False,
                "error": "Proposal required for propose operation",
            }

        # Check if we have a leader
        leader_info = self.leader_election.get_current_leader()
        if not leader_info["leader"]:
            return {
                "success": False,
                "error": "No leader elected - cannot process proposal",
            }

        self.metrics["consensus_proposals"] += 1

        # Submit proposal through Raft
        result = await self.raft_node.propose(proposal)

        return {
            "success": result["success"],
            "accepted": result["success"],
            "log_index": result.get("index"),
            "term": result.get("term"),
            "error": result.get("error"),
            "timestamp": datetime.now().isoformat(),
        }

    async def _handle_global_order(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle global ordering operation."""
        events = params.get("events", [])

        self.metrics["ordering_requests"] += 1

        # Order events
        result = await self.ordering_service.order_events(events)

        return {
            "success": True,
            "ordered_events": result["ordered_events"],
            "logical_clock": result["logical_clock"],
            "causal_dependencies": result.get("causal_dependencies", {}),
            "timestamp": datetime.now().isoformat(),
        }
