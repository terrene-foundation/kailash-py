"""Race condition detection and analysis node for concurrent operations.

This module provides comprehensive race condition detection capabilities with
concurrent access pattern analysis, timing-based detection, and preventive suggestions.
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError

logger = logging.getLogger(__name__)


class RaceConditionType(Enum):
    """Types of race conditions that can be detected."""

    READ_WRITE_RACE = "read_write_race"
    WRITE_WRITE_RACE = "write_write_race"
    CHECK_THEN_ACT = "check_then_act"
    LOST_UPDATE = "lost_update"
    DIRTY_READ = "dirty_read"
    PHANTOM_READ = "phantom_read"
    TIMING_DEPENDENT = "timing_dependent"


class AccessType(Enum):
    """Types of resource access."""

    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"
    DELETE = "delete"
    CREATE = "create"


class PreventionStrategy(Enum):
    """Race condition prevention strategies."""

    OPTIMISTIC_LOCKING = "optimistic_locking"
    PESSIMISTIC_LOCKING = "pessimistic_locking"
    ATOMIC_OPERATIONS = "atomic_operations"
    SERIALIZATION = "serialization"
    IMMUTABLE_DATA = "immutable_data"
    MESSAGE_PASSING = "message_passing"
    SYNCHRONIZATION = "synchronization"


@dataclass
class ResourceAccess:
    """Represents a resource access event."""

    access_id: str
    resource_id: str
    operation_id: str
    thread_id: str
    process_id: str
    access_type: AccessType
    start_time: float
    end_time: Optional[float] = None
    duration: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConcurrentOperation:
    """Represents a concurrent operation with multiple accesses."""

    operation_id: str
    start_time: float
    thread_id: str
    process_id: str
    end_time: Optional[float] = None
    accesses: List[ResourceAccess] = field(default_factory=list)
    total_resources: int = 0
    conflicting_operations: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RaceConditionDetection:
    """Represents a detected race condition."""

    detection_id: str
    race_type: RaceConditionType
    involved_operations: List[str]
    involved_resources: List[str]
    conflicting_accesses: List[ResourceAccess]
    detection_time: float
    confidence_score: float  # 0.0 to 1.0
    severity: str  # low, medium, high, critical
    potential_impact: str
    recommended_prevention: List[PreventionStrategy] = field(default_factory=list)
    timing_analysis: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@register_node()
class RaceConditionDetectorNode(AsyncNode):
    """Node for detecting race conditions in concurrent operations.

    This node provides comprehensive race condition detection including:
    - Concurrent access pattern analysis
    - Timing-based race condition detection
    - Read-write conflict identification
    - Lost update detection
    - Dirty read detection
    - Check-then-act race detection
    - Prevention strategy recommendations

    Design Purpose:
    - Detect potential race conditions in production systems
    - Provide actionable insights for race prevention
    - Support concurrent system troubleshooting
    - Enable proactive race condition monitoring

    Examples:
        >>> # Register resource access
        >>> detector = RaceConditionDetectorNode()
        >>> result = await detector.execute(
        ...     operation="register_access",
        ...     resource_id="user_account_123",
        ...     operation_id="op_456",
        ...     thread_id="thread_1",
        ...     access_type="read",
        ...     metadata={"query": "SELECT balance FROM accounts"}
        ... )

        >>> # End resource access
        >>> result = await detector.execute(
        ...     operation="end_access",
        ...     access_id="access_789",
        ...     success=True
        ... )

        >>> # Detect race conditions
        >>> result = await detector.execute(
        ...     operation="detect_races",
        ...     detection_window=5.0,
        ...     min_confidence=0.7
        ... )
    """

    def __init__(self, **kwargs):
        """Initialize the race condition detector node."""
        super().__init__(**kwargs)
        self._active_accesses: Dict[str, ResourceAccess] = {}
        self._completed_accesses: List[ResourceAccess] = []
        self._active_operations: Dict[str, ConcurrentOperation] = {}
        self._resource_access_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._detected_races: List[RaceConditionDetection] = []
        self._monitoring_active = False
        self._background_tasks: Set[asyncio.Task] = set()
        self._detection_thresholds = {
            "min_confidence": 0.5,
            "timing_threshold": 0.001,  # 1ms
            "overlap_threshold": 0.5,
        }
        self.logger.info(f"Initialized RaceConditionDetectorNode: {self.id}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation (register_access, end_access, register_operation, end_operation, detect_races, get_status)",
            ),
            "access_id": NodeParameter(
                name="access_id",
                type=str,
                required=False,
                description="Unique access identifier",
            ),
            "resource_id": NodeParameter(
                name="resource_id",
                type=str,
                required=False,
                description="Resource being accessed (table, file, object, etc.)",
            ),
            "operation_id": NodeParameter(
                name="operation_id",
                type=str,
                required=False,
                description="Operation identifier grouping multiple accesses",
            ),
            "thread_id": NodeParameter(
                name="thread_id",
                type=str,
                required=False,
                description="Thread identifier",
            ),
            "process_id": NodeParameter(
                name="process_id",
                type=str,
                required=False,
                description="Process identifier",
            ),
            "access_type": NodeParameter(
                name="access_type",
                type=str,
                required=False,
                default="read",
                description="Type of access (read, write, read_write, delete, create)",
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=False,
                default=True,
                description="Whether the access was successful",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if access failed",
            ),
            "detection_window": NodeParameter(
                name="detection_window",
                type=float,
                required=False,
                default=5.0,
                description="Time window for race detection in seconds",
            ),
            "min_confidence": NodeParameter(
                name="min_confidence",
                type=float,
                required=False,
                default=0.5,
                description="Minimum confidence score for race detection (0.0-1.0)",
            ),
            "resource_filters": NodeParameter(
                name="resource_filters",
                type=list,
                required=False,
                default=[],
                description="List of resource patterns to filter detection",
            ),
            "timing_threshold": NodeParameter(
                name="timing_threshold",
                type=float,
                required=False,
                default=0.001,
                description="Timing threshold for race detection in seconds",
            ),
            "enable_monitoring": NodeParameter(
                name="enable_monitoring",
                type=bool,
                required=False,
                default=False,
                description="Enable continuous race condition monitoring",
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
            "races_detected": NodeParameter(
                name="races_detected",
                type=list,
                description="List of detected race conditions",
            ),
            "race_count": NodeParameter(
                name="race_count", type=int, description="Number of races detected"
            ),
            "active_accesses": NodeParameter(
                name="active_accesses",
                type=int,
                description="Number of active accesses",
            ),
            "active_operations": NodeParameter(
                name="active_operations",
                type=int,
                description="Number of active operations",
            ),
            "prevention_suggestions": NodeParameter(
                name="prevention_suggestions",
                type=list,
                description="Recommended prevention strategies",
            ),
            "resource_conflicts": NodeParameter(
                name="resource_conflicts",
                type=dict,
                description="Resource-level conflict analysis",
            ),
            "timing_analysis": NodeParameter(
                name="timing_analysis",
                type=dict,
                description="Timing-based analysis results",
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
        """Execute race condition detection operation."""
        operation = kwargs.get("operation")

        try:
            if operation == "register_access":
                return await self._register_access(**kwargs)
            elif operation == "end_access":
                return await self._end_access(**kwargs)
            elif operation == "register_operation":
                return await self._register_operation(**kwargs)
            elif operation == "end_operation":
                return await self._end_operation(**kwargs)
            elif operation == "detect_races":
                return await self._detect_races(**kwargs)
            elif operation == "get_status":
                return await self._get_status(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            elif operation == "report_operation":
                return await self._report_operation(**kwargs)
            elif operation == "complete_operation":
                return await self._complete_operation(**kwargs)
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            self.logger.error(f"Race condition detection operation failed: {str(e)}")
            raise NodeExecutionError(f"Failed to execute race detection: {str(e)}")

    async def _register_access(self, **kwargs) -> Dict[str, Any]:
        """Register a new resource access."""
        resource_id = kwargs.get("resource_id")
        operation_id = kwargs.get("operation_id")
        thread_id = kwargs.get("thread_id", "unknown")
        process_id = kwargs.get("process_id", "unknown")
        access_type = AccessType(kwargs.get("access_type", "read"))
        metadata = kwargs.get("metadata", {})

        if not resource_id:
            raise ValueError("resource_id is required")

        current_time = time.time()
        access_id = kwargs.get("access_id") or f"access_{int(current_time * 1000000)}"

        # Create access record
        access = ResourceAccess(
            access_id=access_id,
            resource_id=resource_id,
            operation_id=operation_id or "unknown",
            thread_id=thread_id,
            process_id=process_id,
            access_type=access_type,
            start_time=current_time,
            metadata=metadata,
        )

        # Register access
        self._active_accesses[access_id] = access
        self._resource_access_history[resource_id].append(access)

        # Update operation if specified
        if operation_id and operation_id in self._active_operations:
            operation = self._active_operations[operation_id]
            operation.accesses.append(access)
            operation.total_resources += 1

        # Check for immediate race conditions
        races = await self._analyze_concurrent_access(resource_id, access)

        self.logger.debug(
            f"Registered access {access_id} for resource {resource_id} ({access_type.value})"
        )

        return {
            "races_detected": [self._serialize_race(r) for r in races],
            "race_count": len(races),
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _end_access(self, **kwargs) -> Dict[str, Any]:
        """End a resource access."""
        access_id = kwargs.get("access_id")
        success = kwargs.get("success", True)
        error = kwargs.get("error")

        if not access_id:
            raise ValueError("access_id is required")

        if access_id not in self._active_accesses:
            raise ValueError(f"Access {access_id} not found")

        access = self._active_accesses.pop(access_id)

        # Complete access
        access.end_time = time.time()
        access.duration = access.end_time - access.start_time
        access.success = success
        access.error = error

        # Store completed access
        self._completed_accesses.append(access)

        # Clean old accesses (keep last hour)
        cutoff_time = time.time() - 3600
        self._completed_accesses = [
            a for a in self._completed_accesses if a.start_time > cutoff_time
        ]

        self.logger.debug(
            f"Ended access {access_id} with duration {access.duration:.3f}s, success: {success}"
        )

        return {
            "races_detected": [],
            "race_count": 0,
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {"access_duration": access.duration},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _register_operation(self, **kwargs) -> Dict[str, Any]:
        """Register a new concurrent operation."""
        operation_id = kwargs.get("operation_id")
        thread_id = kwargs.get("thread_id", "unknown")
        process_id = kwargs.get("process_id", "unknown")
        metadata = kwargs.get("metadata", {})

        if not operation_id:
            raise ValueError("operation_id is required")

        current_time = time.time()

        # Create operation record
        operation = ConcurrentOperation(
            operation_id=operation_id,
            start_time=current_time,
            thread_id=thread_id,
            process_id=process_id,
            metadata=metadata,
        )

        self._active_operations[operation_id] = operation

        self.logger.debug(f"Registered operation {operation_id}")

        return {
            "races_detected": [],
            "race_count": 0,
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _end_operation(self, **kwargs) -> Dict[str, Any]:
        """End a concurrent operation."""
        operation_id = kwargs.get("operation_id")

        if not operation_id:
            raise ValueError("operation_id is required")

        if operation_id not in self._active_operations:
            raise ValueError(f"Operation {operation_id} not found")

        operation = self._active_operations.pop(operation_id)
        operation.end_time = time.time()

        # Analyze operation for race conditions
        races = await self._analyze_operation_races(operation)

        self.logger.debug(
            f"Ended operation {operation_id} with {len(operation.accesses)} accesses"
        )

        return {
            "races_detected": [self._serialize_race(r) for r in races],
            "race_count": len(races),
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [
                self._get_prevention_strategies(r) for r in races
            ],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _detect_races(self, **kwargs) -> Dict[str, Any]:
        """Detect race conditions in recent accesses."""
        detection_window = kwargs.get("detection_window", 5.0)
        min_confidence = kwargs.get("min_confidence", 0.5)
        resource_filters = kwargs.get("resource_filters", [])
        timing_threshold = kwargs.get("timing_threshold", 0.001)

        current_time = time.time()
        window_start = current_time - detection_window

        # Analyze recent accesses for race conditions
        races = []

        # Group accesses by resource within time window
        resource_accesses = defaultdict(list)
        for access in self._completed_accesses:
            if access.start_time >= window_start:
                if not resource_filters or any(
                    f in access.resource_id for f in resource_filters
                ):
                    resource_accesses[access.resource_id].append(access)

        # Detect races for each resource
        for resource_id, accesses in resource_accesses.items():
            if len(accesses) > 1:
                resource_races = await self._detect_resource_races(
                    resource_id, accesses, timing_threshold, min_confidence
                )
                races.extend(resource_races)

        # Store detected races
        self._detected_races.extend(races)

        # Generate prevention suggestions
        prevention_suggestions = []
        for race in races:
            strategies = self._get_prevention_strategies(race)
            prevention_suggestions.extend(strategies)

        # Analyze resource conflicts
        resource_conflicts = self._analyze_resource_conflicts(resource_accesses)

        # Generate timing analysis
        timing_analysis = self._generate_timing_analysis(resource_accesses)

        self.logger.info(
            f"Detected {len(races)} race conditions in {detection_window}s window"
        )

        return {
            "races_detected": [self._serialize_race(r) for r in races],
            "race_count": len(races),
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": list(set(prevention_suggestions)),
            "resource_conflicts": resource_conflicts,
            "timing_analysis": timing_analysis,
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _analyze_concurrent_access(
        self, resource_id: str, new_access: ResourceAccess
    ) -> List[RaceConditionDetection]:
        """Analyze for immediate race conditions with new access."""
        races = []
        current_time = time.time()

        # Check concurrent accesses to the same resource
        concurrent_accesses = [
            access
            for access in self._active_accesses.values()
            if (
                access.resource_id == resource_id
                and access.access_id != new_access.access_id
                and access.thread_id != new_access.thread_id
            )
        ]

        for concurrent_access in concurrent_accesses:
            # Check for write-write or read-write conflicts
            if new_access.access_type in [
                AccessType.WRITE,
                AccessType.READ_WRITE,
                AccessType.DELETE,
            ] or concurrent_access.access_type in [
                AccessType.WRITE,
                AccessType.READ_WRITE,
                AccessType.DELETE,
            ]:
                race = await self._create_race_detection(
                    [new_access, concurrent_access], current_time
                )
                if race:
                    races.append(race)

        return races

    async def _analyze_operation_races(
        self, operation: ConcurrentOperation
    ) -> List[RaceConditionDetection]:
        """Analyze an operation for race conditions."""
        races = []

        # Check for check-then-act patterns
        read_accesses = [
            a for a in operation.accesses if a.access_type == AccessType.READ
        ]
        write_accesses = [
            a for a in operation.accesses if a.access_type == AccessType.WRITE
        ]

        for read_access in read_accesses:
            for write_access in write_accesses:
                if (
                    read_access.resource_id == write_access.resource_id
                    and write_access.start_time > read_access.end_time
                ):
                    # Potential check-then-act race
                    race = RaceConditionDetection(
                        detection_id=f"race_{int(time.time() * 1000000)}",
                        race_type=RaceConditionType.CHECK_THEN_ACT,
                        involved_operations=[operation.operation_id],
                        involved_resources=[read_access.resource_id],
                        conflicting_accesses=[read_access, write_access],
                        detection_time=time.time(),
                        confidence_score=0.8,
                        severity="medium",
                        potential_impact="Data inconsistency from stale reads",
                        recommended_prevention=[
                            PreventionStrategy.ATOMIC_OPERATIONS,
                            PreventionStrategy.OPTIMISTIC_LOCKING,
                        ],
                        timing_analysis={
                            "gap_duration": write_access.start_time
                            - read_access.end_time
                        },
                    )
                    races.append(race)

        return races

    async def _detect_resource_races(
        self,
        resource_id: str,
        accesses: List[ResourceAccess],
        timing_threshold: float,
        min_confidence: float,
    ) -> List[RaceConditionDetection]:
        """Detect race conditions for a specific resource."""
        races = []

        # Sort accesses by start time
        sorted_accesses = sorted(accesses, key=lambda a: a.start_time)

        # Check for overlapping accesses
        for i in range(len(sorted_accesses)):
            for j in range(i + 1, len(sorted_accesses)):
                access1 = sorted_accesses[i]
                access2 = sorted_accesses[j]

                # Check if accesses overlap or are very close in time
                if (
                    access1.end_time
                    and access2.start_time <= access1.end_time + timing_threshold
                ):
                    race_type = self._determine_race_type(access1, access2)
                    if race_type:
                        confidence = self._calculate_confidence(access1, access2)
                        if confidence >= min_confidence:
                            race = RaceConditionDetection(
                                detection_id=f"race_{int(time.time() * 1000000)}_{i}_{j}",
                                race_type=race_type,
                                involved_operations=[
                                    access1.operation_id,
                                    access2.operation_id,
                                ],
                                involved_resources=[resource_id],
                                conflicting_accesses=[access1, access2],
                                detection_time=time.time(),
                                confidence_score=confidence,
                                severity=self._determine_severity(
                                    race_type, confidence
                                ),
                                potential_impact=self._get_potential_impact(race_type),
                                recommended_prevention=self._get_recommended_prevention(
                                    race_type
                                ),
                                timing_analysis={
                                    "overlap_duration": (
                                        access1.end_time - access2.start_time
                                        if access1.end_time
                                        else 0.0
                                    ),
                                    "timing_gap": access2.start_time
                                    - access1.start_time,
                                },
                            )
                            races.append(race)

        return races

    def _determine_race_type(
        self, access1: ResourceAccess, access2: ResourceAccess
    ) -> Optional[RaceConditionType]:
        """Determine the type of race condition between two accesses."""
        if access1.thread_id == access2.thread_id:
            return None  # Same thread, no race

        # Write-Write race
        if access1.access_type in [
            AccessType.WRITE,
            AccessType.DELETE,
        ] and access2.access_type in [AccessType.WRITE, AccessType.DELETE]:
            return RaceConditionType.WRITE_WRITE_RACE

        # Read-Write race
        if (
            access1.access_type == AccessType.READ
            and access2.access_type in [AccessType.WRITE, AccessType.DELETE]
        ) or (
            access1.access_type in [AccessType.WRITE, AccessType.DELETE]
            and access2.access_type == AccessType.READ
        ):
            return RaceConditionType.READ_WRITE_RACE

        # Lost update (both read then write)
        if (
            access1.access_type == AccessType.READ_WRITE
            and access2.access_type == AccessType.READ_WRITE
        ):
            return RaceConditionType.LOST_UPDATE

        return RaceConditionType.TIMING_DEPENDENT

    def _calculate_confidence(
        self, access1: ResourceAccess, access2: ResourceAccess
    ) -> float:
        """Calculate confidence score for race condition detection."""
        confidence = 0.5  # Base confidence

        # Increase confidence for write conflicts
        if access1.access_type in [
            AccessType.WRITE,
            AccessType.DELETE,
        ] or access2.access_type in [
            AccessType.WRITE,
            AccessType.DELETE,
        ]:
            confidence += 0.3

        # Increase confidence for closer timing
        if access1.end_time:
            timing_gap = abs(access2.start_time - access1.start_time)
            if timing_gap < 0.001:  # < 1ms
                confidence += 0.2
            elif timing_gap < 0.01:  # < 10ms
                confidence += 0.1

        # Increase confidence for different processes
        if access1.process_id != access2.process_id:
            confidence += 0.1

        return min(confidence, 1.0)

    def _determine_severity(
        self, race_type: RaceConditionType, confidence: float
    ) -> str:
        """Determine severity of race condition."""
        if race_type in [
            RaceConditionType.WRITE_WRITE_RACE,
            RaceConditionType.LOST_UPDATE,
        ]:
            return "critical" if confidence > 0.8 else "high"
        elif race_type == RaceConditionType.READ_WRITE_RACE:
            return "high" if confidence > 0.7 else "medium"
        else:
            return "medium" if confidence > 0.6 else "low"

    def _get_potential_impact(self, race_type: RaceConditionType) -> str:
        """Get potential impact description for race type."""
        impact_map = {
            RaceConditionType.WRITE_WRITE_RACE: "Data corruption, lost writes, inconsistent state",
            RaceConditionType.READ_WRITE_RACE: "Stale data reads, inconsistent views",
            RaceConditionType.LOST_UPDATE: "Lost updates, data inconsistency",
            RaceConditionType.CHECK_THEN_ACT: "Logic errors, invalid state transitions",
            RaceConditionType.DIRTY_READ: "Reading uncommitted data, inconsistent views",
            RaceConditionType.PHANTOM_READ: "Inconsistent query results",
            RaceConditionType.TIMING_DEPENDENT: "Unpredictable behavior, intermittent bugs",
        }
        return impact_map.get(race_type, "Unknown impact")

    def _get_recommended_prevention(
        self, race_type: RaceConditionType
    ) -> List[PreventionStrategy]:
        """Get recommended prevention strategies for race type."""
        prevention_map = {
            RaceConditionType.WRITE_WRITE_RACE: [
                PreventionStrategy.PESSIMISTIC_LOCKING,
                PreventionStrategy.ATOMIC_OPERATIONS,
            ],
            RaceConditionType.READ_WRITE_RACE: [
                PreventionStrategy.OPTIMISTIC_LOCKING,
                PreventionStrategy.IMMUTABLE_DATA,
            ],
            RaceConditionType.LOST_UPDATE: [
                PreventionStrategy.OPTIMISTIC_LOCKING,
                PreventionStrategy.ATOMIC_OPERATIONS,
            ],
            RaceConditionType.CHECK_THEN_ACT: [
                PreventionStrategy.ATOMIC_OPERATIONS,
                PreventionStrategy.PESSIMISTIC_LOCKING,
            ],
            RaceConditionType.TIMING_DEPENDENT: [
                PreventionStrategy.SYNCHRONIZATION,
                PreventionStrategy.MESSAGE_PASSING,
            ],
        }
        return prevention_map.get(race_type, [PreventionStrategy.SYNCHRONIZATION])

    def _get_prevention_strategies(self, race: RaceConditionDetection) -> List[str]:
        """Get prevention strategy names for a race condition."""
        return [strategy.value for strategy in race.recommended_prevention]

    def _analyze_resource_conflicts(
        self, resource_accesses: Dict[str, List[ResourceAccess]]
    ) -> Dict[str, Any]:
        """Analyze conflicts per resource."""
        conflicts = {}

        for resource_id, accesses in resource_accesses.items():
            write_count = sum(
                1
                for a in accesses
                if a.access_type in [AccessType.WRITE, AccessType.DELETE]
            )
            read_count = sum(1 for a in accesses if a.access_type == AccessType.READ)
            unique_threads = len(set(a.thread_id for a in accesses))

            conflicts[resource_id] = {
                "total_accesses": len(accesses),
                "write_accesses": write_count,
                "read_accesses": read_count,
                "concurrent_threads": unique_threads,
                "conflict_potential": (
                    "high"
                    if write_count > 1 and unique_threads > 1
                    else "medium" if write_count > 0 and unique_threads > 1 else "low"
                ),
            }

        return conflicts

    def _generate_timing_analysis(
        self, resource_accesses: Dict[str, List[ResourceAccess]]
    ) -> Dict[str, Any]:
        """Generate timing analysis for race detection."""
        analysis = {}

        for resource_id, accesses in resource_accesses.items():
            if len(accesses) > 1:
                durations = [a.duration for a in accesses if a.duration]
                start_times = [a.start_time for a in accesses]

                analysis[resource_id] = {
                    "access_count": len(accesses),
                    "avg_duration": sum(durations) / len(durations) if durations else 0,
                    "max_duration": max(durations) if durations else 0,
                    "time_span": max(start_times) - min(start_times),
                    "concurrency_level": len(accesses),
                }

        return analysis

    async def _create_race_detection(
        self, accesses: List[ResourceAccess], detection_time: float
    ) -> Optional[RaceConditionDetection]:
        """Create a race condition detection from conflicting accesses."""
        if len(accesses) < 2:
            return None

        race_type = self._determine_race_type(accesses[0], accesses[1])
        if not race_type:
            return None

        confidence = self._calculate_confidence(accesses[0], accesses[1])

        return RaceConditionDetection(
            detection_id=f"race_{int(detection_time * 1000000)}",
            race_type=race_type,
            involved_operations=list(set(a.operation_id for a in accesses)),
            involved_resources=list(set(a.resource_id for a in accesses)),
            conflicting_accesses=accesses,
            detection_time=detection_time,
            confidence_score=confidence,
            severity=self._determine_severity(race_type, confidence),
            potential_impact=self._get_potential_impact(race_type),
            recommended_prevention=self._get_recommended_prevention(race_type),
        )

    async def _get_status(self, **kwargs) -> Dict[str, Any]:
        """Get current race detector status."""
        return {
            "races_detected": [self._serialize_race(r) for r in self._detected_races],
            "race_count": len(self._detected_races),
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "monitoring" if self._monitoring_active else "idle",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start continuous race condition monitoring."""
        interval = kwargs.get("monitoring_interval", 1.0)

        if not self._monitoring_active:
            self._monitoring_active = True
            monitoring_task = asyncio.create_task(self._monitoring_loop(interval))
            self._background_tasks.add(monitoring_task)
            monitoring_task.add_done_callback(self._background_tasks.discard)

        return {
            "races_detected": [],
            "race_count": 0,
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "monitoring",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop continuous race condition monitoring."""
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
            "races_detected": [],
            "race_count": 0,
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "stopped",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _monitoring_loop(self, interval: float):
        """Background monitoring loop for continuous race detection."""
        while self._monitoring_active:
            try:
                await asyncio.sleep(interval)

                # Detect races in recent activity
                races = await self._detect_races(detection_window=interval * 2)

                if races["race_count"] > 0:
                    self.logger.warning(
                        f"Monitoring detected {races['race_count']} race conditions"
                    )

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")

    def _serialize_race(self, race: RaceConditionDetection) -> Dict[str, Any]:
        """Serialize a race condition detection to dictionary."""
        return {
            "detection_id": race.detection_id,
            "race_type": race.race_type.value,
            "involved_operations": race.involved_operations,
            "involved_resources": race.involved_resources,
            "conflicting_accesses": [
                {
                    "access_id": a.access_id,
                    "resource_id": a.resource_id,
                    "operation_id": a.operation_id,
                    "thread_id": a.thread_id,
                    "process_id": a.process_id,
                    "access_type": a.access_type.value,
                    "start_time": a.start_time,
                    "end_time": a.end_time,
                    "duration": a.duration,
                    "success": a.success,
                    "error": a.error,
                }
                for a in race.conflicting_accesses
            ],
            "detection_time": race.detection_time,
            "confidence_score": race.confidence_score,
            "severity": race.severity,
            "potential_impact": race.potential_impact,
            "recommended_prevention": [p.value for p in race.recommended_prevention],
            "timing_analysis": race.timing_analysis,
            "metadata": race.metadata,
        }

    async def _report_operation(self, **kwargs) -> Dict[str, Any]:
        """Report an operation with resource access for race detection."""
        operation_id = kwargs.get("operation_id", str(uuid.uuid4()))
        resource_id = kwargs.get("resource_id")
        access_type = kwargs.get("access_type", "read")
        thread_id = kwargs.get("thread_id", str(threading.get_ident()))
        process_id = kwargs.get("process_id", str(os.getpid()))
        metadata = kwargs.get("metadata", {})

        # Register the operation
        register_result = await self._register_operation(
            operation_id=operation_id,
            operation_type="reported_operation",
            metadata=metadata,
        )

        # Register resource access if specified
        if resource_id:
            access_result = await self._register_access(
                resource_id=resource_id,
                operation_id=operation_id,
                thread_id=thread_id,
                process_id=process_id,
                access_type=access_type,
                metadata=metadata,
            )

        return {
            "operation_id": operation_id,
            "resource_id": resource_id,
            "access_type": access_type,
            "thread_id": thread_id,
            "process_id": process_id,
            "detection_status": "reported",
            "races_detected": [
                self._serialize_race(race) for race in self._detected_races
            ],
            "race_count": len(self._detected_races),
            "active_accesses": len(
                self._active_accesses
            ),  # Fixed to use correct data structure
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "active",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    async def _complete_operation(self, **kwargs) -> Dict[str, Any]:
        """Complete an operation and perform final race detection analysis."""
        operation_id = kwargs.get("operation_id")
        resource_id = kwargs.get("resource_id")
        success = kwargs.get("success", True)

        # If operation_id is provided, complete that specific operation
        if operation_id:
            if operation_id in self._active_operations:
                operation = self._active_operations.pop(operation_id)
                # You could add completion logic here

        # Return the current state with race detection results
        return {
            "operation_id": operation_id,
            "resource_id": resource_id,
            "operation_success": success,
            "races_detected": [
                self._serialize_race(race) for race in self._detected_races
            ],
            "race_count": len(self._detected_races),
            "active_accesses": len(self._active_accesses),
            "active_operations": len(self._active_operations),
            "prevention_suggestions": [],
            "resource_conflicts": {},
            "timing_analysis": {},
            "monitoring_status": "operation_completed",
            "timestamp": datetime.now(UTC).isoformat(),
            "status": "success",
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        import asyncio

        return asyncio.run(self.async_run(**kwargs))

    async def cleanup(self):
        """Cleanup resources when node is destroyed."""
        await self._stop_monitoring()
        await super().cleanup() if hasattr(super(), "cleanup") else None
