"""Resource pool management for edge computing.

This module provides unified resource abstraction and management
across different types of computing resources.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class AllocationStrategy(Enum):
    """Resource allocation strategies."""

    FIRST_FIT = "first_fit"  # First available slot
    BEST_FIT = "best_fit"  # Smallest adequate slot
    WORST_FIT = "worst_fit"  # Largest available slot
    ROUND_ROBIN = "round_robin"  # Distribute evenly
    PRIORITY_BASED = "priority_based"  # Based on request priority
    FAIR_SHARE = "fair_share"  # Equal distribution


class ResourceUnit(Enum):
    """Units for different resource types."""

    CORES = "cores"  # CPU cores
    MEGABYTES = "MB"  # Memory
    GIGABYTES = "GB"  # Storage
    MBPS = "Mbps"  # Network bandwidth
    PERCENTAGE = "percent"  # Generic percentage
    COUNT = "count"  # Generic count


@dataclass
class ResourceSpec:
    """Specification for a resource type."""

    resource_type: str
    capacity: float
    unit: ResourceUnit
    shareable: bool = True
    preemptible: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourceRequest:
    """Request for resource allocation."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    requester: str = ""
    resources: Dict[str, float] = field(default_factory=dict)  # type -> amount
    priority: int = 5  # 1-10, higher is more important
    duration: Optional[int] = None  # Seconds, None = indefinite
    preemptible: bool = True
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "request_id": self.request_id,
            "requester": self.requester,
            "resources": self.resources,
            "priority": self.priority,
            "duration": self.duration,
            "preemptible": self.preemptible,
            "constraints": self.constraints,
            "metadata": self.metadata,
        }


@dataclass
class ResourceAllocation:
    """Allocated resource information."""

    allocation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = ""
    edge_node: str = ""
    resources: Dict[str, float] = field(default_factory=dict)
    allocated_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    status: str = "active"  # active, expired, released

    @property
    def is_expired(self) -> bool:
        """Check if allocation is expired."""
        if self.expires_at and datetime.now() > self.expires_at:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "allocation_id": self.allocation_id,
            "request_id": self.request_id,
            "edge_node": self.edge_node,
            "resources": self.resources,
            "allocated_at": self.allocated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status,
            "is_expired": self.is_expired,
        }


@dataclass
class AllocationResult:
    """Result of allocation attempt."""

    success: bool
    allocations: List[ResourceAllocation] = field(default_factory=list)
    reason: Optional[str] = None
    partial: bool = False
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "allocations": [a.to_dict() for a in self.allocations],
            "reason": self.reason,
            "partial": self.partial,
            "suggestions": self.suggestions,
        }


class ResourcePool:
    """Manages a pool of resources for an edge node."""

    def __init__(
        self,
        edge_node: str,
        resources: List[ResourceSpec],
        allocation_strategy: AllocationStrategy = AllocationStrategy.BEST_FIT,
        oversubscription_ratio: float = 1.0,
    ):
        """Initialize resource pool.

        Args:
            edge_node: Edge node identifier
            resources: Resource specifications
            allocation_strategy: Strategy for allocation
            oversubscription_ratio: Allow oversubscription (>1.0)
        """
        self.edge_node = edge_node
        self.allocation_strategy = allocation_strategy
        self.oversubscription_ratio = oversubscription_ratio

        # Resource tracking
        self.resources: Dict[str, ResourceSpec] = {
            r.resource_type: r for r in resources
        }
        self.allocated: Dict[str, float] = {r.resource_type: 0.0 for r in resources}
        self.allocations: Dict[str, ResourceAllocation] = {}

        # Request tracking for fair share
        self.request_history: Dict[str, List[float]] = {}

        # Locks for thread safety
        self._lock = asyncio.Lock()

        self.logger = logging.getLogger(__name__)

    async def allocate(self, request: ResourceRequest) -> AllocationResult:
        """Allocate resources for a request.

        Args:
            request: Resource request

        Returns:
            Allocation result
        """
        async with self._lock:
            # Check if resources are available
            available = await self._check_availability(request)

            if not available["sufficient"]:
                return AllocationResult(
                    success=False,
                    reason=available["reason"],
                    suggestions=await self._get_allocation_suggestions(request),
                )

            # Perform allocation
            allocation = await self._perform_allocation(request)

            return AllocationResult(success=True, allocations=[allocation])

    async def release(self, allocation_id: str) -> bool:
        """Release allocated resources.

        Args:
            allocation_id: Allocation to release

        Returns:
            Success status
        """
        async with self._lock:
            if allocation_id not in self.allocations:
                return False

            allocation = self.allocations[allocation_id]

            # Return resources to pool
            for rtype, amount in allocation.resources.items():
                self.allocated[rtype] -= amount

            # Update status
            allocation.status = "released"
            del self.allocations[allocation_id]

            self.logger.info(f"Released allocation {allocation_id}")
            return True

    async def get_utilization(self) -> Dict[str, Any]:
        """Get current resource utilization.

        Returns:
            Utilization information
        """
        utilization = {}

        for rtype, spec in self.resources.items():
            allocated = self.allocated.get(rtype, 0)
            capacity = spec.capacity * self.oversubscription_ratio

            utilization[rtype] = {
                "allocated": allocated,
                "capacity": capacity,
                "available": capacity - allocated,
                "utilization_percent": (
                    (allocated / capacity * 100) if capacity > 0 else 0
                ),
                "unit": spec.unit.value,
            }

        return {
            "edge_node": self.edge_node,
            "resources": utilization,
            "total_allocations": len(self.allocations),
            "active_allocations": len(
                [a for a in self.allocations.values() if not a.is_expired]
            ),
        }

    async def cleanup_expired(self) -> int:
        """Clean up expired allocations.

        Returns:
            Number of allocations cleaned
        """
        async with self._lock:
            expired = []

            for aid, allocation in self.allocations.items():
                if allocation.is_expired:
                    expired.append(aid)

            for aid in expired:
                await self.release(aid)

            return len(expired)

    async def preempt_resources(self, request: ResourceRequest) -> List[str]:
        """Preempt lower priority allocations if needed.

        Args:
            request: High priority request

        Returns:
            List of preempted allocation IDs
        """
        if request.priority < 8:  # Only high priority can preempt
            return []

        async with self._lock:
            preempted = []
            needed = dict(request.resources)

            # Sort allocations by priority (ascending)
            sorted_allocs = sorted(
                [
                    (aid, a)
                    for aid, a in self.allocations.items()
                    if a.status == "active"
                ],
                key=lambda x: x[1].metadata.get("priority", 5),
            )

            for aid, allocation in sorted_allocs:
                if allocation.metadata.get("priority", 5) >= request.priority:
                    continue  # Can't preempt equal or higher priority

                if not allocation.metadata.get("preemptible", True):
                    continue  # Can't preempt non-preemptible

                # Check if this helps
                helps = False
                for rtype, amount in allocation.resources.items():
                    if rtype in needed and needed[rtype] > 0:
                        helps = True
                        break

                if helps:
                    preempted.append(aid)
                    await self.release(aid)

                    # Update needed resources
                    for rtype, amount in allocation.resources.items():
                        if rtype in needed:
                            needed[rtype] = max(0, needed[rtype] - amount)

                    # Check if we have enough now
                    if all(n <= 0 for n in needed.values()):
                        break

            return preempted

    async def _check_availability(self, request: ResourceRequest) -> Dict[str, Any]:
        """Check if resources are available.

        Args:
            request: Resource request

        Returns:
            Availability information
        """
        insufficient_resources = []

        for rtype, requested in request.resources.items():
            if rtype not in self.resources:
                insufficient_resources.append(f"{rtype} not available")
                continue

            spec = self.resources[rtype]
            allocated = self.allocated.get(rtype, 0)
            capacity = spec.capacity * self.oversubscription_ratio
            available = capacity - allocated

            if requested > available:
                insufficient_resources.append(
                    f"{rtype}: requested {requested}, available {available:.2f}"
                )

        if insufficient_resources:
            return {
                "sufficient": False,
                "reason": "Insufficient resources: "
                + ", ".join(insufficient_resources),
            }

        return {"sufficient": True}

    async def _perform_allocation(self, request: ResourceRequest) -> ResourceAllocation:
        """Perform the actual allocation.

        Args:
            request: Resource request

        Returns:
            Resource allocation
        """
        # Update allocated amounts
        for rtype, amount in request.resources.items():
            self.allocated[rtype] += amount

        # Create allocation record
        allocation = ResourceAllocation(
            request_id=request.request_id,
            edge_node=self.edge_node,
            resources=dict(request.resources),
            expires_at=(
                datetime.now() + timedelta(seconds=request.duration)
                if request.duration
                else None
            ),
        )

        # Store metadata
        allocation.metadata = {
            "requester": request.requester,
            "priority": request.priority,
            "preemptible": request.preemptible,
        }

        self.allocations[allocation.allocation_id] = allocation

        # Track for fair share
        if request.requester not in self.request_history:
            self.request_history[request.requester] = []
        self.request_history[request.requester].append(sum(request.resources.values()))

        self.logger.info(
            f"Allocated resources for {request.requester}: "
            f"{request.resources} (allocation_id: {allocation.allocation_id})"
        )

        return allocation

    async def _get_allocation_suggestions(self, request: ResourceRequest) -> List[str]:
        """Get suggestions for failed allocation.

        Args:
            request: Failed resource request

        Returns:
            List of suggestions
        """
        suggestions = []

        # Check if reducing request would help
        for rtype, requested in request.resources.items():
            if rtype in self.resources:
                available = self.resources[rtype].capacity - self.allocated.get(
                    rtype, 0
                )
                if available > 0:
                    suggestions.append(
                        f"Reduce {rtype} request to {available:.2f} or less"
                    )

        # Check if waiting would help
        upcoming_releases = []
        for allocation in self.allocations.values():
            if allocation.expires_at and not allocation.is_expired:
                upcoming_releases.append(allocation.expires_at)

        if upcoming_releases:
            next_release = min(upcoming_releases)
            wait_time = (next_release - datetime.now()).total_seconds()
            suggestions.append(f"Wait {wait_time:.0f}s for resources to be released")

        # Suggest preemption if applicable
        if request.priority >= 8:
            preemptible_count = sum(
                1
                for a in self.allocations.values()
                if a.metadata.get("preemptible", True)
                and a.metadata.get("priority", 5) < request.priority
            )
            if preemptible_count > 0:
                suggestions.append(
                    f"Enable preemption to free resources from "
                    f"{preemptible_count} lower priority allocations"
                )

        return suggestions


class ResourcePoolManager:
    """Manages multiple resource pools across edge nodes."""

    def __init__(self):
        """Initialize resource pool manager."""
        self.pools: Dict[str, ResourcePool] = {}
        self.logger = logging.getLogger(__name__)

    def add_pool(self, pool: ResourcePool):
        """Add a resource pool.

        Args:
            pool: Resource pool to add
        """
        self.pools[pool.edge_node] = pool
        self.logger.info(f"Added resource pool for {pool.edge_node}")

    async def allocate(
        self, request: ResourceRequest, preferred_nodes: Optional[List[str]] = None
    ) -> AllocationResult:
        """Allocate resources across pools.

        Args:
            request: Resource request
            preferred_nodes: Preferred edge nodes

        Returns:
            Allocation result
        """
        # Try preferred nodes first
        if preferred_nodes:
            for node in preferred_nodes:
                if node in self.pools:
                    result = await self.pools[node].allocate(request)
                    if result.success:
                        return result

        # Try all nodes
        for node, pool in self.pools.items():
            if preferred_nodes and node in preferred_nodes:
                continue  # Already tried

            result = await pool.allocate(request)
            if result.success:
                return result

        # No allocation possible
        return AllocationResult(
            success=False,
            reason="No edge node has sufficient resources",
            suggestions=[
                "Consider splitting the request",
                "Wait for resources to be freed",
            ],
        )

    async def get_global_utilization(self) -> Dict[str, Any]:
        """Get utilization across all pools.

        Returns:
            Global utilization information
        """
        utilizations = {}
        total_by_type: Dict[str, Dict[str, float]] = {}

        for node, pool in self.pools.items():
            util = await pool.get_utilization()
            utilizations[node] = util

            # Aggregate by resource type
            for rtype, info in util["resources"].items():
                if rtype not in total_by_type:
                    total_by_type[rtype] = {"allocated": 0, "capacity": 0, "count": 0}

                total_by_type[rtype]["allocated"] += info["allocated"]
                total_by_type[rtype]["capacity"] += info["capacity"]
                total_by_type[rtype]["count"] += 1

        # Calculate aggregates
        aggregates = {}
        for rtype, totals in total_by_type.items():
            aggregates[rtype] = {
                "total_allocated": totals["allocated"],
                "total_capacity": totals["capacity"],
                "average_utilization": (
                    totals["allocated"] / totals["capacity"] * 100
                    if totals["capacity"] > 0
                    else 0
                ),
                "node_count": totals["count"],
            }

        return {
            "by_node": utilizations,
            "aggregates": aggregates,
            "total_nodes": len(self.pools),
        }

    async def find_best_node(
        self, request: ResourceRequest, strategy: str = "least_loaded"
    ) -> Optional[str]:
        """Find best node for allocation.

        Args:
            request: Resource request
            strategy: Selection strategy

        Returns:
            Best node ID or None
        """
        candidates = []

        for node, pool in self.pools.items():
            # Check basic availability
            available = await pool._check_availability(request)
            if available["sufficient"]:
                util = await pool.get_utilization()

                # Calculate score based on strategy
                if strategy == "least_loaded":
                    # Average utilization across resource types
                    utilizations = [
                        r["utilization_percent"] for r in util["resources"].values()
                    ]
                    avg_util = (
                        sum(utilizations) / len(utilizations) if utilizations else 0
                    )
                    score = 100 - avg_util  # Higher score = less loaded

                elif strategy == "most_capacity":
                    # Total available capacity
                    total_available = sum(
                        r["available"] for r in util["resources"].values()
                    )
                    score = total_available

                else:  # balanced
                    # Balance between utilization and capacity
                    utilizations = [
                        r["utilization_percent"] for r in util["resources"].values()
                    ]
                    avg_util = (
                        sum(utilizations) / len(utilizations) if utilizations else 0
                    )
                    total_capacity = sum(
                        r["capacity"] for r in util["resources"].values()
                    )
                    score = (100 - avg_util) * 0.5 + total_capacity * 0.5

                candidates.append((node, score))

        if not candidates:
            return None

        # Return node with highest score
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
