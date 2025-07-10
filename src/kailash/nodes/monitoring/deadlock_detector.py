"""Deadlock detection and resolution node for database operations.

This module provides comprehensive deadlock detection capabilities with
graph-based analysis, automatic resolution strategies, and detailed reporting.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class DeadlockType(Enum):
    """Types of deadlocks that can be detected."""

    RESOURCE_LOCK = "resource_lock"
    WAIT_FOR_GRAPH = "wait_for_graph"
    TIMEOUT_INFERRED = "timeout_inferred"
    CIRCULAR_DEPENDENCY = "circular_dependency"


class ResolutionStrategy(Enum):
    """Deadlock resolution strategies."""

    VICTIM_SELECTION = "victim_selection"
    TIMEOUT_ROLLBACK = "timeout_rollback"
    PRIORITY_BASED = "priority_based"
    COST_BASED = "cost_based"
    MANUAL = "manual"


@dataclass
class ResourceLock:
    """Represents a resource lock in the system."""

    resource_id: str
    lock_type: str  # shared, exclusive, update
    holder_transaction_id: str
    requested_at: float
    granted_at: Optional[float] = None
    timeout: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransactionWait:
    """Represents a transaction waiting for a resource."""

    transaction_id: str
    waiting_for_transaction_id: str
    resource_id: str
    wait_start_time: float
    timeout: Optional[float] = None
    priority: int = 0
    cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DeadlockDetection:
    """Represents a detected deadlock."""

    detection_id: str
    deadlock_type: DeadlockType
    involved_transactions: List[str]
    involved_resources: List[str]
    detection_time: float
    wait_chain: List[TransactionWait]
    victim_candidates: List[str] = field(default_factory=list)
    recommended_strategy: Optional[ResolutionStrategy] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@register_node()
class DeadlockDetectorNode(AsyncNode):
    """Node for detecting and resolving database deadlocks.

    This node provides comprehensive deadlock detection including:
    - Graph-based cycle detection in wait-for graphs
    - Timeout-based deadlock inference
    - Victim selection with multiple strategies
    - Automatic deadlock resolution
    - Detailed deadlock reporting and analysis
    - Integration with database transaction monitoring

    Design Purpose:
    - Prevent and resolve database deadlocks in production
    - Provide actionable insights for deadlock prevention
    - Support multiple resolution strategies
    - Enable proactive deadlock monitoring

    Examples:
        >>> # Register active transaction locks
        >>> detector = DeadlockDetectorNode()
        >>> result = await detector.execute(
        ...     operation="register_lock",
        ...     transaction_id="txn_123",
        ...     resource_id="table_orders",
        ...     lock_type="exclusive"
        ... )

        >>> # Register transaction wait
        >>> result = await detector.execute(
        ...     operation="register_wait",
        ...     transaction_id="txn_456",
        ...     waiting_for_transaction_id="txn_123",
        ...     resource_id="table_orders"
        ... )

        >>> # Detect deadlocks
        >>> result = await detector.execute(
        ...     operation="detect_deadlocks",
        ...     detection_algorithm="wait_for_graph"
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the deadlock detector node."""
        super().__init__(**kwargs)
        self._active_locks: Dict[str, ResourceLock] = {}
        self._active_waits: Dict[str, TransactionWait] = {}
        self._wait_for_graph: Dict[str, Set[str]] = defaultdict(set)
        self._transaction_resources: Dict[str, Set[str]] = defaultdict(set)
        self._resource_holders: Dict[str, str] = {}
        self._detected_deadlocks: List[DeadlockDetection] = []
        self._detection_history: List[Dict[str, Any]] = []
        self._monitoring_active = False
        self._background_tasks: Set[asyncio.Task] = set()
        self.logger.info(f"Initialized DeadlockDetectorNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation (register_lock, register_wait, detect_deadlocks, resolve_deadlock, get_status)",
            ),
            "transaction_id": NodeParameter(
                name="transaction_id",
                type=str,
                required=False,
                description="Transaction identifier",
            ),
            "resource_id": NodeParameter(
                name="resource_id",
                type=str,
                required=False,
                description="Resource identifier (table, row, etc.)",
            ),
            "lock_type": NodeParameter(
                name="lock_type",
                type=str,
                required=False,
                default="exclusive",
                description="Type of lock (shared, exclusive, update)",
            ),
            "waiting_for_transaction_id": NodeParameter(
                name="waiting_for_transaction_id",
                type=str,
                required=False,
                description="Transaction ID that this transaction is waiting for",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=float,
                required=False,
                description="Timeout for lock or wait in seconds",
            ),
            "priority": NodeParameter(
                name="priority",
                type=int,
                required=False,
                default=0,
                description="Transaction priority for victim selection",
            ),
            "cost": NodeParameter(
                name="cost",
                type=float,
                required=False,
                default=0.0,
                description="Transaction cost for victim selection",
            ),
            "detection_algorithm": NodeParameter(
                name="detection_algorithm",
                type=str,
                required=False,
                default="wait_for_graph",
                description="Detection algorithm (wait_for_graph, timeout_based, combined)",
            ),
            "resolution_strategy": NodeParameter(
                name="resolution_strategy",
                type=str,
                required=False,
                default="victim_selection",
                description="Resolution strategy (victim_selection, timeout_rollback, priority_based, cost_based)",
            ),
            "deadlock_id": NodeParameter(
                name="deadlock_id",
                type=str,
                required=False,
                description="Deadlock detection ID for resolution",
            ),
            "victim_transaction_id": NodeParameter(
                name="victim_transaction_id",
                type=str,
                required=False,
                description="Transaction to abort as deadlock victim",
            ),
            "enable_monitoring": NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=False,
                description="Enable continuous deadlock monitoring",
            ),
            "monitoring_interval": NodeParameter(
                name="monitoring_interval",
                type=float,
                required=False,
                default=1.0,
                description="Monitoring interval in seconds",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                default={},
                description="Additional metadata for the operation",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node."""
        return {
            "deadlocks_detected": NodeParameter(
                name="deadlocks_detected",
                type=list,
                description="List of detected deadlocks",
            ),
            "deadlock_count": NodeParameter(
                name="deadlock_count",
                type=int,
                description="Number of deadlocks detected",
            ),
            "active_locks": NodeParameter(
                name="active_locks", type=int, description="Number of active locks"
            ),
            "active_waits": NodeParameter(
                name="active_waits", type=int, description="Number of active waits"
            ),
            "resolution_actions": NodeParameter(
                name="resolution_actions",
                type=list,
                description="Recommended or taken resolution actions",
            ),
            "wait_for_graph": NodeParameter(
                name="wait_for_graph",
                type=dict,
                description="Current wait-for graph structure",
            ),
            "monitoring_status": NodeParameter(
                name="monitoring_status",
                type=str,
                description="Current monitoring status",
            ),
            "timestamp": NodeParameter(
                name="timestamp", type=str, description="ISO timestamp of operation"
            ),
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute deadlock detection operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "initialize":
                return await self._initialize(**kwargs)
            elif operation == "register_lock":
                return await self._register_lock(**kwargs)
            elif operation == "acquire_resource":
                return await self._register_lock(**kwargs)  # Same as register_lock
            elif operation == "request_resource":
                return await self._request_resource(**kwargs)  # Custom implementation
            elif operation == "register_wait":
                return await self._register_wait(**kwargs)
            elif operation == "release_lock":
                return await self._release_lock(**kwargs)
            elif operation == "release_resource":
                return await self._release_lock(**kwargs)  # Same as release_lock
            elif operation == "detect_deadlocks":
                return await self._detect_deadlocks(**kwargs)
            elif operation == "resolve_deadlock":
                return await self._resolve_deadlock(**kwargs)
            elif operation == "get_status":
                return await self._get_status(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Deadlock detection operation failed: {str(e)}")
            raise NodeExecutionError(f"Failed to execute deadlock detection: {str(e)}")

    async def _register_lock(self, **kwargs) -> Dict[str, Any]:
        """Register a new resource lock."""
        transaction_id = kwargs.get("transaction_id")
        resource_id = kwargs.get("resource_id")
        lock_type = kwargs.get("lock_type", "exclusive")
        timeout = kwargs.get("timeout")
        metadata = kwargs.get("metadata", {})

        if not transaction_id or not resource_id:
            raise ValueError("transaction_id and resource_id are required")

        current_time = time.time()
        lock_id = f"{transaction_id}:{resource_id}"

        # Create lock record
        lock = ResourceLock(
            resource_id=resource_id,
            lock_type=lock_type,
            holder_transaction_id=transaction_id,
            requested_at=current_time,
            granted_at=current_time,
            timeout=timeout,
            metadata=metadata,
        )

        # Register lock
        self._active_locks[lock_id] = lock
        self._transaction_resources[transaction_id].add(resource_id)
        self._resource_holders[resource_id] = transaction_id

        self.logger.debug(
            f"Registered lock: {transaction_id} -> {resource_id} ({lock_type})"
        )

        return {
            "deadlocks_detected": [],
            "deadlock_count": 0,
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _register_wait(self, **kwargs) -> Dict[str, Any]:
        """Register a transaction wait."""
        transaction_id = kwargs.get("transaction_id")
        waiting_for_transaction_id = kwargs.get("waiting_for_transaction_id")
        resource_id = kwargs.get("resource_id")
        timeout = kwargs.get("timeout")
        priority = kwargs.get("priority", 0)
        cost = kwargs.get("cost", 0.0)
        metadata = kwargs.get("metadata", {})

        if not transaction_id or not waiting_for_transaction_id:
            raise ValueError(
                "transaction_id and waiting_for_transaction_id are required"
            )

        current_time = time.time()
        wait_id = f"{transaction_id}:{waiting_for_transaction_id}"

        # Create wait record
        wait = TransactionWait(
            transaction_id=transaction_id,
            waiting_for_transaction_id=waiting_for_transaction_id,
            resource_id=resource_id or "unknown",
            wait_start_time=current_time,
            timeout=timeout,
            priority=priority,
            cost=cost,
            metadata=metadata,
        )

        # Register wait and update wait-for graph
        self._active_waits[wait_id] = wait
        self._wait_for_graph[transaction_id].add(waiting_for_transaction_id)

        self.logger.debug(
            f"Registered wait: {transaction_id} -> {waiting_for_transaction_id}"
        )

        # Check for immediate deadlock
        deadlocks = await self._detect_cycles_in_wait_graph()

        return {
            "deadlocks_detected": [self._serialize_deadlock(d) for d in deadlocks],
            "deadlock_count": len(deadlocks),
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _release_lock(self, **kwargs) -> Dict[str, Any]:
        """Release a resource lock."""
        transaction_id = kwargs.get("transaction_id")
        resource_id = kwargs.get("resource_id")

        if not transaction_id:
            raise ValueError("transaction_id is required")

        # Remove specific lock or all locks for transaction
        if resource_id:
            lock_id = f"{transaction_id}:{resource_id}"
            if lock_id in self._active_locks:
                del self._active_locks[lock_id]
                self._transaction_resources[transaction_id].discard(resource_id)
                if self._resource_holders.get(resource_id) == transaction_id:
                    del self._resource_holders[resource_id]
        else:
            # Remove all locks for transaction
            to_remove = [
                lock_id
                for lock_id in self._active_locks
                if self._active_locks[lock_id].holder_transaction_id == transaction_id
            ]
            for lock_id in to_remove:
                lock = self._active_locks[lock_id]
                del self._active_locks[lock_id]
                self._transaction_resources[transaction_id].discard(lock.resource_id)
                if self._resource_holders.get(lock.resource_id) == transaction_id:
                    del self._resource_holders[lock.resource_id]

        # Remove waits involving this transaction
        to_remove_waits = [
            wait_id
            for wait_id in self._active_waits
            if (
                self._active_waits[wait_id].transaction_id == transaction_id
                or self._active_waits[wait_id].waiting_for_transaction_id
                == transaction_id
            )
        ]
        for wait_id in to_remove_waits:
            wait = self._active_waits[wait_id]
            del self._active_waits[wait_id]
            self._wait_for_graph[wait.transaction_id].discard(
                wait.waiting_for_transaction_id
            )

        # Clean up empty graph entries
        if (
            transaction_id in self._wait_for_graph
            and not self._wait_for_graph[transaction_id]
        ):
            del self._wait_for_graph[transaction_id]

        self.logger.debug(f"Released locks for transaction: {transaction_id}")

        return {
            "deadlocks_detected": [],
            "deadlock_count": 0,
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [f"Released locks for {transaction_id}"],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _detect_deadlocks(self, **kwargs) -> Dict[str, Any]:
        """Detect deadlocks using specified algorithm."""
        algorithm = kwargs.get("detection_algorithm", "wait_for_graph")

        deadlocks = []

        if algorithm in ["wait_for_graph", "combined"]:
            cycle_deadlocks = await self._detect_cycles_in_wait_graph()
            deadlocks.extend(cycle_deadlocks)

        if algorithm in ["timeout_based", "combined"]:
            timeout_deadlocks = await self._detect_timeout_deadlocks()
            deadlocks.extend(timeout_deadlocks)

        # Store detected deadlocks
        self._detected_deadlocks.extend(deadlocks)

        # Add to detection history
        self._detection_history.append(
            {
                "timestamp": time.time(),
                "algorithm": algorithm,
                "deadlocks_found": len(deadlocks),
                "deadlock_ids": [d.detection_id for d in deadlocks],
            }
        )

        # Generate resolution recommendations
        resolution_actions = []
        for deadlock in deadlocks:
            deadlock.victim_candidates = self._select_victim_candidates(deadlock)
            deadlock.recommended_strategy = self._recommend_resolution_strategy(
                deadlock
            )
            resolution_actions.append(
                {
                    "deadlock_id": deadlock.detection_id,
                    "recommended_strategy": deadlock.recommended_strategy.value,
                    "victim_candidates": deadlock.victim_candidates,
                }
            )

        self.logger.info(
            f"Detected {len(deadlocks)} deadlocks using {algorithm} algorithm"
        )

        return {
            "deadlocks_detected": [self._serialize_deadlock(d) for d in deadlocks],
            "deadlock_count": len(deadlocks),
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": resolution_actions,
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _detect_cycles_in_wait_graph(self) -> List[DeadlockDetection]:
        """Detect cycles in the wait-for graph using DFS."""
        deadlocks = []
        visited = set()
        rec_stack = set()

        def dfs_cycle_detection(node: str, path: List[str]) -> Optional[List[str]]:
            """DFS-based cycle detection."""
            if node in rec_stack:
                # Found cycle - extract it
                cycle_start_idx = path.index(node)
                return path[cycle_start_idx:] + [node]

            if node in visited:
                return None

            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._wait_for_graph.get(node, set()):
                cycle = dfs_cycle_detection(neighbor, path)
                if cycle:
                    return cycle

            rec_stack.remove(node)
            path.pop()
            return None

        # Check each unvisited node
        for transaction_id in self._wait_for_graph:
            if transaction_id not in visited:
                cycle = dfs_cycle_detection(transaction_id, [])
                if cycle:
                    # Create deadlock detection
                    deadlock = self._create_deadlock_from_cycle(cycle)
                    deadlocks.append(deadlock)

        return deadlocks

    async def _detect_timeout_deadlocks(self) -> List[DeadlockDetection]:
        """Detect deadlocks based on wait timeouts."""
        deadlocks = []
        current_time = time.time()

        # Group waits that have exceeded their timeout
        timeout_waits = []
        for wait in self._active_waits.values():
            if wait.timeout and (current_time - wait.wait_start_time) > wait.timeout:
                timeout_waits.append(wait)

        # Create deadlock detection for timeout-based inference
        if timeout_waits:
            detection_id = f"timeout_deadlock_{int(current_time)}"
            involved_transactions = list(set(w.transaction_id for w in timeout_waits))
            involved_resources = list(set(w.resource_id for w in timeout_waits))

            deadlock = DeadlockDetection(
                detection_id=detection_id,
                deadlock_type=DeadlockType.TIMEOUT_INFERRED,
                involved_transactions=involved_transactions,
                involved_resources=involved_resources,
                detection_time=current_time,
                wait_chain=timeout_waits,
                metadata={
                    "timeout_count": len(timeout_waits),
                    "max_wait_time": max(
                        current_time - w.wait_start_time for w in timeout_waits
                    ),
                },
            )

            deadlocks.append(deadlock)

        return deadlocks

    def _create_deadlock_from_cycle(self, cycle: List[str]) -> DeadlockDetection:
        """Create a deadlock detection from a detected cycle."""
        current_time = time.time()
        detection_id = f"cycle_deadlock_{int(current_time)}_{len(cycle)}"

        # Build wait chain from cycle
        wait_chain = []
        involved_resources = set()

        for i in range(len(cycle) - 1):
            current_txn = cycle[i]
            next_txn = cycle[i + 1]

            # Find the wait relationship
            wait_id = f"{current_txn}:{next_txn}"
            if wait_id in self._active_waits:
                wait = self._active_waits[wait_id]
                wait_chain.append(wait)
                involved_resources.add(wait.resource_id)

        return DeadlockDetection(
            detection_id=detection_id,
            deadlock_type=DeadlockType.WAIT_FOR_GRAPH,
            involved_transactions=cycle[:-1],  # Remove duplicate last element
            involved_resources=list(involved_resources),
            detection_time=current_time,
            wait_chain=wait_chain,
            metadata={"cycle_length": len(cycle) - 1, "cycle_path": " -> ".join(cycle)},
        )

    def _select_victim_candidates(self, deadlock: DeadlockDetection) -> List[str]:
        """Select victim candidates for deadlock resolution."""
        candidates = []

        # Priority-based selection (lower priority = better victim)
        if deadlock.wait_chain:
            wait_priorities = [
                (w.transaction_id, w.priority) for w in deadlock.wait_chain
            ]
            min_priority = min(p for _, p in wait_priorities)
            candidates.extend([txn for txn, p in wait_priorities if p == min_priority])

        # Cost-based selection (lower cost = better victim)
        if deadlock.wait_chain and not candidates:
            wait_costs = [(w.transaction_id, w.cost) for w in deadlock.wait_chain]
            min_cost = min(c for _, c in wait_costs)
            candidates.extend([txn for txn, c in wait_costs if c == min_cost])

        # Default: select transaction with shortest wait time
        if deadlock.wait_chain and not candidates:
            wait_times = [
                (w.transaction_id, w.wait_start_time) for w in deadlock.wait_chain
            ]
            latest_start = max(t for _, t in wait_times)
            candidates.extend([txn for txn, t in wait_times if t == latest_start])

        # Fallback: first transaction in the list
        if not candidates and deadlock.involved_transactions:
            candidates.append(deadlock.involved_transactions[0])

        return list(set(candidates))  # Remove duplicates

    def _recommend_resolution_strategy(
        self, deadlock: DeadlockDetection
    ) -> ResolutionStrategy:
        """Recommend a resolution strategy for the deadlock."""
        if deadlock.deadlock_type == DeadlockType.TIMEOUT_INFERRED:
            return ResolutionStrategy.TIMEOUT_ROLLBACK

        if deadlock.wait_chain:
            # Check if we have priority information
            has_priorities = any(w.priority != 0 for w in deadlock.wait_chain)
            if has_priorities:
                return ResolutionStrategy.PRIORITY_BASED

            # Check if we have cost information
            has_costs = any(w.cost != 0.0 for w in deadlock.wait_chain)
            if has_costs:
                return ResolutionStrategy.COST_BASED

        return ResolutionStrategy.VICTIM_SELECTION

    async def _resolve_deadlock(self, **kwargs) -> Dict[str, Any]:
        """Resolve a detected deadlock."""
        deadlock_id = kwargs.get("deadlock_id")
        victim_transaction_id = kwargs.get("victim_transaction_id")
        strategy = kwargs.get("resolution_strategy", "victim_selection")

        if not deadlock_id:
            raise ValueError("deadlock_id is required")

        # Find the deadlock
        deadlock = next(
            (d for d in self._detected_deadlocks if d.detection_id == deadlock_id), None
        )
        if not deadlock:
            raise ValueError(f"Deadlock {deadlock_id} not found")

        resolution_actions = []

        # Determine victim if not specified
        if not victim_transaction_id:
            if deadlock.victim_candidates:
                victim_transaction_id = deadlock.victim_candidates[0]
            else:
                victim_transaction_id = deadlock.involved_transactions[0]

        # Execute resolution strategy
        if strategy in ["victim_selection", "priority_based", "cost_based"]:
            # Abort victim transaction
            await self._release_lock(transaction_id=victim_transaction_id)
            resolution_actions.append(
                {
                    "action": "abort_transaction",
                    "transaction_id": victim_transaction_id,
                    "reason": f"Deadlock victim selected using {strategy} strategy",
                }
            )

        elif strategy == "timeout_rollback":
            # Rollback all transactions involved in timeout deadlock
            for txn_id in deadlock.involved_transactions:
                await self._release_lock(transaction_id=txn_id)
                resolution_actions.append(
                    {
                        "action": "timeout_rollback",
                        "transaction_id": txn_id,
                        "reason": "Timeout-based deadlock resolution",
                    }
                )

        # Mark deadlock as resolved
        deadlock.metadata["resolved"] = True
        deadlock.metadata["resolution_time"] = time.time()
        deadlock.metadata["resolution_strategy"] = strategy
        deadlock.metadata["victim_transaction"] = victim_transaction_id

        self.logger.info(
            f"Resolved deadlock {deadlock_id} using {strategy} strategy, victim: {victim_transaction_id}"
        )

        return {
            "deadlocks_detected": [],
            "deadlock_count": 0,
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": resolution_actions,
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _request_resource(self, **kwargs) -> Dict[str, Any]:
        """Request a resource - simplified version for E2E testing."""
        transaction_id = kwargs.get("transaction_id")
        resource_id = kwargs.get("resource_id")
        resource_type = kwargs.get("resource_type", "database_table")
        lock_type = kwargs.get("lock_type", "SHARED")

        if not transaction_id or not resource_id:
            raise ValueError("transaction_id and resource_id are required")

        # For E2E testing, just track the request
        current_time = time.time()

        # Return status for tracking
        return {
            "deadlocks_detected": [
                self._serialize_deadlock(d) for d in self._detected_deadlocks
            ],
            "deadlock_count": len(self._detected_deadlocks),
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": f"requested_{resource_type}_{lock_type}".lower(),
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _initialize(self, **kwargs) -> Dict[str, Any]:
        """Initialize the deadlock detector."""
        # Reset internal state
        self._active_locks.clear()
        self._active_waits.clear()
        self._detected_deadlocks.clear()
        self._monitoring_active = False

        # Initialize with provided configuration
        if "deadlock_timeout" in kwargs:
            self._deadlock_timeout = kwargs["deadlock_timeout"]
        if "cycle_detection_enabled" in kwargs:
            self._cycle_detection_enabled = kwargs["cycle_detection_enabled"]
        if "timeout_detection_enabled" in kwargs:
            self._timeout_detection_enabled = kwargs["timeout_detection_enabled"]

        return {
            "deadlocks_detected": [
                self._serialize_deadlock(d) for d in self._detected_deadlocks
            ],
            "deadlock_count": len(self._detected_deadlocks),
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "initialized",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _get_status(self, **kwargs) -> Dict[str, Any]:
        """Get current deadlock detector status."""
        return {
            "deadlocks_detected": [
                self._serialize_deadlock(d) for d in self._detected_deadlocks
            ],
            "deadlock_count": len(self._detected_deadlocks),
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start continuous deadlock monitoring."""
        interval = kwargs.get("monitoring_interval", 1.0)

        if not self._monitoring_active:
            self._monitoring_active = True
            monitoring_task = asyncio.create_task(self._monitoring_loop(interval))
            self._background_tasks.add(monitoring_task)
            monitoring_task.add_done_callback(self._background_tasks.discard)

        return {
            "deadlocks_detected": [],
            "deadlock_count": 0,
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "monitoring",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop continuous deadlock monitoring."""
        self._monitoring_active = False

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        self._background_tasks.clear()

        return {
            "deadlocks_detected": [],
            "deadlock_count": 0,
            "active_locks": len(self._active_locks),
            "active_waits": len(self._active_waits),
            "resolution_actions": [],
            "wait_for_graph": {k: list(v) for k, v in self._wait_for_graph.items()},
            "monitoring_status": "stopped",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _monitoring_loop(self, interval: float):
        """Background monitoring loop for continuous deadlock detection."""
        while self._monitoring_active:
            try:
                await asyncio.sleep(interval)

                # Detect deadlocks
                deadlocks = await self._detect_cycles_in_wait_graph()
                timeout_deadlocks = await self._detect_timeout_deadlocks()

                all_deadlocks = deadlocks + timeout_deadlocks

                if all_deadlocks:
                    self.logger.warning(
                        f"Monitoring detected {len(all_deadlocks)} deadlocks"
                    )

                    # Store detected deadlocks
                    self._detected_deadlocks.extend(all_deadlocks)

                    # TODO: Send alerts or take automatic resolution actions

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")

    def _serialize_deadlock(self, deadlock: DeadlockDetection) -> Dict[str, Any]:
        """Serialize a deadlock detection to dictionary."""
        return {
            "detection_id": deadlock.detection_id,
            "deadlock_type": deadlock.deadlock_type.value,
            "involved_transactions": deadlock.involved_transactions,
            "involved_resources": deadlock.involved_resources,
            "detection_time": deadlock.detection_time,
            "wait_chain": [
                {
                    "transaction_id": w.transaction_id,
                    "waiting_for_transaction_id": w.waiting_for_transaction_id,
                    "resource_id": w.resource_id,
                    "wait_start_time": w.wait_start_time,
                    "timeout": w.timeout,
                    "priority": w.priority,
                    "cost": w.cost,
                }
                for w in deadlock.wait_chain
            ],
            "victim_candidates": deadlock.victim_candidates,
            "recommended_strategy": (
                deadlock.recommended_strategy.value
                if deadlock.recommended_strategy
                else None
            ),
            "metadata": deadlock.metadata,
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

    async def cleanup(self):
        """Cleanup resources when node is destroyed."""
        await self._stop_monitoring()
        await super().cleanup() if hasattr(super(), "cleanup") else None
