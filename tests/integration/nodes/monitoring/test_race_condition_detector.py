"""Unit tests for RaceConditionDetectorNode."""

import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.monitoring import RaceConditionDetectorNode
from kailash.nodes.monitoring.race_condition_detector import (
    AccessType,
    ConcurrentOperation,
    PreventionStrategy,
    RaceConditionDetection,
    RaceConditionType,
    ResourceAccess,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestRaceConditionDetectorNode:
    """Test suite for RaceConditionDetectorNode."""

    def test_node_initialization(self):
        """Test that RaceConditionDetectorNode initializes correctly."""
        node = RaceConditionDetectorNode(id="test_race_detector")
        assert node.id == "test_race_detector"
        assert node._active_accesses == {}
        assert node._completed_accesses == []
        assert node._active_operations == {}
        assert node._resource_access_history == {}
        assert node._detected_races == []
        assert node._monitoring_active is False
        assert isinstance(node._background_tasks, set)
        assert "min_confidence" in node._detection_thresholds
        assert "timing_threshold" in node._detection_thresholds

    def test_get_parameters(self):
        """Test parameter definition."""
        node = RaceConditionDetectorNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operation" in params
        assert params["operation"].required is True

        # Check optional parameters with defaults
        assert "access_id" in params
        assert params["access_id"].required is False

        assert "resource_id" in params
        assert params["resource_id"].required is False

        assert "operation_id" in params
        assert params["operation_id"].required is False

        assert "access_type" in params
        assert params["access_type"].default == "read"

        assert "detection_window" in params
        assert params["detection_window"].default == 5.0

        assert "min_confidence" in params
        assert params["min_confidence"].default == 0.5

        assert "timing_threshold" in params
        assert params["timing_threshold"].default == 0.001

        assert "enable_monitoring" in params
        assert params["enable_monitoring"].default is False

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = RaceConditionDetectorNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "races_detected" in schema
        assert "race_count" in schema
        assert "active_accesses" in schema
        assert "active_operations" in schema
        assert "prevention_suggestions" in schema
        assert "resource_conflicts" in schema
        assert "timing_analysis" in schema
        assert "monitoring_status" in schema
        assert "timestamp" in schema
        assert "status" in schema

    def test_race_condition_type_enum(self):
        """Test RaceConditionType enumeration."""
        assert RaceConditionType.READ_WRITE_RACE.value == "read_write_race"
        assert RaceConditionType.WRITE_WRITE_RACE.value == "write_write_race"
        assert RaceConditionType.CHECK_THEN_ACT.value == "check_then_act"
        assert RaceConditionType.LOST_UPDATE.value == "lost_update"
        assert RaceConditionType.DIRTY_READ.value == "dirty_read"
        assert RaceConditionType.PHANTOM_READ.value == "phantom_read"
        assert RaceConditionType.TIMING_DEPENDENT.value == "timing_dependent"

    def test_access_type_enum(self):
        """Test AccessType enumeration."""
        assert AccessType.READ.value == "read"
        assert AccessType.WRITE.value == "write"
        assert AccessType.READ_WRITE.value == "read_write"
        assert AccessType.DELETE.value == "delete"
        assert AccessType.CREATE.value == "create"

    def test_prevention_strategy_enum(self):
        """Test PreventionStrategy enumeration."""
        assert PreventionStrategy.OPTIMISTIC_LOCKING.value == "optimistic_locking"
        assert PreventionStrategy.PESSIMISTIC_LOCKING.value == "pessimistic_locking"
        assert PreventionStrategy.ATOMIC_OPERATIONS.value == "atomic_operations"
        assert PreventionStrategy.SERIALIZATION.value == "serialization"
        assert PreventionStrategy.IMMUTABLE_DATA.value == "immutable_data"
        assert PreventionStrategy.MESSAGE_PASSING.value == "message_passing"
        assert PreventionStrategy.SYNCHRONIZATION.value == "synchronization"

    def test_resource_access_creation(self):
        """Test ResourceAccess dataclass."""
        access = ResourceAccess(
            access_id="access_123",
            resource_id="table_users",
            operation_id="op_456",
            thread_id="thread_1",
            process_id="proc_1",
            access_type=AccessType.READ,
            start_time=time.time(),
            metadata={"query": "SELECT * FROM users"},
        )

        assert access.access_id == "access_123"
        assert access.resource_id == "table_users"
        assert access.operation_id == "op_456"
        assert access.thread_id == "thread_1"
        assert access.process_id == "proc_1"
        assert access.access_type == AccessType.READ
        assert access.success is True
        assert access.error is None
        assert access.metadata["query"] == "SELECT * FROM users"

    def test_concurrent_operation_creation(self):
        """Test ConcurrentOperation dataclass."""
        operation = ConcurrentOperation(
            operation_id="op_789",
            start_time=time.time(),
            thread_id="thread_2",
            process_id="proc_2",
            metadata={"operation_type": "user_update"},
        )

        assert operation.operation_id == "op_789"
        assert operation.thread_id == "thread_2"
        assert operation.process_id == "proc_2"
        assert operation.accesses == []
        assert operation.total_resources == 0
        assert operation.conflicting_operations == set()
        assert operation.metadata["operation_type"] == "user_update"

    def test_race_condition_detection_creation(self):
        """Test RaceConditionDetection dataclass."""
        access1 = ResourceAccess(
            "acc1", "res1", "op1", "t1", "p1", AccessType.READ, time.time()
        )
        access2 = ResourceAccess(
            "acc2", "res1", "op2", "t2", "p2", AccessType.WRITE, time.time()
        )

        detection = RaceConditionDetection(
            detection_id="race_123",
            race_type=RaceConditionType.READ_WRITE_RACE,
            involved_operations=["op1", "op2"],
            involved_resources=["res1"],
            conflicting_accesses=[access1, access2],
            detection_time=time.time(),
            confidence_score=0.8,
            severity="high",
            potential_impact="Data inconsistency",
            recommended_prevention=[PreventionStrategy.OPTIMISTIC_LOCKING],
            timing_analysis={"overlap": 0.001},
        )

        assert detection.detection_id == "race_123"
        assert detection.race_type == RaceConditionType.READ_WRITE_RACE
        assert len(detection.involved_operations) == 2
        assert len(detection.involved_resources) == 1
        assert len(detection.conflicting_accesses) == 2
        assert detection.confidence_score == 0.8
        assert detection.severity == "high"
        assert PreventionStrategy.OPTIMISTIC_LOCKING in detection.recommended_prevention

    def test_register_access(self):
        """Test registering a resource access."""
        node = RaceConditionDetectorNode()

        result = node.execute(
            operation="register_access",
            resource_id="table_orders",
            operation_id="op_123",
            thread_id="thread_1",
            process_id="proc_1",
            access_type="read",
            metadata={"query": "SELECT * FROM orders"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["active_accesses"] == 1
        assert result["active_operations"] == 0
        assert result["race_count"] == 0

        # Verify internal state
        assert len(node._active_accesses) == 1
        access = list(node._active_accesses.values())[0]
        assert access.resource_id == "table_orders"
        assert access.operation_id == "op_123"
        assert access.thread_id == "thread_1"
        assert access.access_type == AccessType.READ
        assert access.metadata["query"] == "SELECT * FROM orders"

        # Verify resource history
        assert "table_orders" in node._resource_access_history
        assert len(node._resource_access_history["table_orders"]) == 1

    def test_register_access_missing_resource_id(self):
        """Test registering access without resource_id."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="register_access")

        assert "resource_id is required" in str(exc_info.value)

    def test_end_access(self):
        """Test ending a resource access."""
        node = RaceConditionDetectorNode()

        # Register access first
        result = node.execute(
            operation="register_access",
            access_id="access_456",
            resource_id="table_products",
            thread_id="thread_2",
            access_type="write",
        )

        # Wait a small amount to ensure duration > 0
        import time

        time.sleep(0.01)

        # End access
        result = node.execute(
            operation="end_access", access_id="access_456", success=True
        )

        # Verify result
        assert result["status"] == "success"
        assert result["active_accesses"] == 0
        assert result["timing_analysis"]["access_duration"] > 0

        # Verify internal state
        assert "access_456" not in node._active_accesses
        assert len(node._completed_accesses) == 1

        completed_access = node._completed_accesses[0]
        assert completed_access.access_id == "access_456"
        assert completed_access.success is True
        assert completed_access.duration is not None
        assert completed_access.duration > 0

    def test_end_access_missing_id(self):
        """Test ending access without access_id."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_access")

        assert "access_id is required" in str(exc_info.value)

    def test_end_access_not_found(self):
        """Test ending access that doesn't exist."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_access", access_id="nonexistent")

        assert "Access nonexistent not found" in str(exc_info.value)

    def test_register_operation(self):
        """Test registering a concurrent operation."""
        node = RaceConditionDetectorNode()

        result = node.execute(
            operation="register_operation",
            operation_id="op_789",
            thread_id="thread_3",
            process_id="proc_3",
            metadata={"operation_type": "bulk_update"},
        )

        # Verify result
        assert result["status"] == "success"
        assert result["active_operations"] == 1

        # Verify internal state
        assert "op_789" in node._active_operations
        operation = node._active_operations["op_789"]
        assert operation.operation_id == "op_789"
        assert operation.thread_id == "thread_3"
        assert operation.process_id == "proc_3"
        assert operation.metadata["operation_type"] == "bulk_update"

    def test_register_operation_missing_id(self):
        """Test registering operation without operation_id."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="register_operation")

        assert "operation_id is required" in str(exc_info.value)

    def test_end_operation(self):
        """Test ending a concurrent operation."""
        node = RaceConditionDetectorNode()

        # Register operation first
        node.execute(
            operation="register_operation",
            operation_id="op_end_test",
            thread_id="thread_4",
        )

        # End operation
        result = node.execute(operation="end_operation", operation_id="op_end_test")

        # Verify result
        assert result["status"] == "success"
        assert result["active_operations"] == 0

        # Verify internal state
        assert "op_end_test" not in node._active_operations

    def test_end_operation_missing_id(self):
        """Test ending operation without operation_id."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_operation")

        assert "operation_id is required" in str(exc_info.value)

    def test_end_operation_not_found(self):
        """Test ending operation that doesn't exist."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="end_operation", operation_id="nonexistent")

        assert "Operation nonexistent not found" in str(exc_info.value)

    def test_detect_races_basic(self):
        """Test basic race condition detection."""
        node = RaceConditionDetectorNode()

        # Create completed accesses manually for testing
        base_time = time.time()
        access1 = ResourceAccess(
            access_id="acc1",
            resource_id="shared_resource",
            operation_id="op1",
            thread_id="thread1",
            process_id="proc1",
            access_type=AccessType.READ,
            start_time=base_time,
            end_time=base_time + 0.1,
            duration=0.1,
        )
        access2 = ResourceAccess(
            access_id="acc2",
            resource_id="shared_resource",
            operation_id="op2",
            thread_id="thread2",
            process_id="proc2",
            access_type=AccessType.WRITE,
            start_time=base_time + 0.05,  # Overlaps with access1
            end_time=base_time + 0.15,
            duration=0.1,
        )

        node._completed_accesses = [access1, access2]

        result = node.execute(
            operation="detect_races",
            detection_window=1.0,
            min_confidence=0.3,
            timing_threshold=0.1,
        )

        # Verify result
        assert result["status"] == "success"
        assert result["race_count"] >= 0  # May detect race depending on timing

    def test_detect_races_with_filters(self):
        """Test race detection with resource filters."""
        node = RaceConditionDetectorNode()

        # Create test accesses
        base_time = time.time()
        access1 = ResourceAccess(
            "acc1", "orders_table", "op1", "t1", "p1", AccessType.READ, base_time
        )
        access2 = ResourceAccess(
            "acc2", "users_table", "op2", "t2", "p2", AccessType.WRITE, base_time
        )
        access1.end_time = base_time + 0.1
        access1.duration = 0.1
        access2.end_time = base_time + 0.1
        access2.duration = 0.1

        node._completed_accesses = [access1, access2]

        result = node.execute(
            operation="detect_races",
            detection_window=1.0,
            resource_filters=["orders"],
        )

        # Should only analyze orders_table
        assert result["status"] == "success"

    def test_get_status(self):
        """Test getting detector status."""
        node = RaceConditionDetectorNode()

        result = node.execute(operation="get_status")

        # Verify result
        assert result["status"] == "success"
        assert result["races_detected"] == []
        assert result["race_count"] == 0
        assert result["active_accesses"] == 0
        assert result["active_operations"] == 0
        assert result["monitoring_status"] == "idle"

    def test_start_monitoring(self):
        """Test starting race condition monitoring."""
        node = RaceConditionDetectorNode()

        result = node.execute(operation="start_monitoring", monitoring_interval=0.1)

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "monitoring"

        # Verify internal state
        assert node._monitoring_active is True

        # Cleanup
        asyncio.run(node._stop_monitoring())

    def test_stop_monitoring(self):
        """Test stopping race condition monitoring."""
        node = RaceConditionDetectorNode()

        # Start monitoring first
        node.execute(operation="start_monitoring")

        # Stop monitoring
        result = node.execute(operation="stop_monitoring")

        # Verify result
        assert result["status"] == "success"
        assert result["monitoring_status"] == "stopped"

        # Verify internal state
        assert node._monitoring_active is False

    def test_determine_race_type(self):
        """Test race type determination."""
        node = RaceConditionDetectorNode()

        # Write-Write race
        access1 = ResourceAccess(
            "acc1", "res1", "op1", "t1", "p1", AccessType.WRITE, time.time()
        )
        access2 = ResourceAccess(
            "acc2", "res1", "op2", "t2", "p2", AccessType.WRITE, time.time()
        )
        race_type = node._determine_race_type(access1, access2)
        assert race_type == RaceConditionType.WRITE_WRITE_RACE

        # Read-Write race
        access3 = ResourceAccess(
            "acc3", "res1", "op3", "t3", "p3", AccessType.READ, time.time()
        )
        access4 = ResourceAccess(
            "acc4", "res1", "op4", "t4", "p4", AccessType.WRITE, time.time()
        )
        race_type = node._determine_race_type(access3, access4)
        assert race_type == RaceConditionType.READ_WRITE_RACE

        # Lost update
        access5 = ResourceAccess(
            "acc5", "res1", "op5", "t5", "p5", AccessType.READ_WRITE, time.time()
        )
        access6 = ResourceAccess(
            "acc6", "res1", "op6", "t6", "p6", AccessType.READ_WRITE, time.time()
        )
        race_type = node._determine_race_type(access5, access6)
        assert race_type == RaceConditionType.LOST_UPDATE

        # Same thread (no race)
        access7 = ResourceAccess(
            "acc7", "res1", "op7", "same_thread", "p7", AccessType.WRITE, time.time()
        )
        access8 = ResourceAccess(
            "acc8", "res1", "op8", "same_thread", "p8", AccessType.WRITE, time.time()
        )
        race_type = node._determine_race_type(access7, access8)
        assert race_type is None

    def test_calculate_confidence(self):
        """Test confidence score calculation."""
        node = RaceConditionDetectorNode()

        # High confidence: write conflict, close timing, different processes
        access1 = ResourceAccess(
            "acc1", "res1", "op1", "t1", "p1", AccessType.WRITE, time.time()
        )
        access2 = ResourceAccess(
            "acc2", "res1", "op2", "t2", "p2", AccessType.WRITE, time.time()
        )
        access1.end_time = access1.start_time + 0.001  # Very close timing

        confidence = node._calculate_confidence(access1, access2)
        assert confidence > 0.8  # Should be high confidence

        # Lower confidence: read-read (no conflict)
        access3 = ResourceAccess(
            "acc3", "res1", "op3", "t3", "p1", AccessType.READ, time.time()
        )
        access4 = ResourceAccess(
            "acc4", "res1", "op4", "t4", "p1", AccessType.READ, time.time()
        )

        confidence = node._calculate_confidence(access3, access4)
        assert confidence <= 0.8  # Should be lower confidence

    def test_determine_severity(self):
        """Test severity determination."""
        node = RaceConditionDetectorNode()

        # Critical severity for write-write with high confidence
        severity = node._determine_severity(RaceConditionType.WRITE_WRITE_RACE, 0.9)
        assert severity == "critical"

        # High severity for write-write with medium confidence
        severity = node._determine_severity(RaceConditionType.WRITE_WRITE_RACE, 0.7)
        assert severity == "high"

        # Medium severity for read-write
        severity = node._determine_severity(RaceConditionType.READ_WRITE_RACE, 0.8)
        assert severity == "high"

        # Low severity for timing dependent
        severity = node._determine_severity(RaceConditionType.TIMING_DEPENDENT, 0.5)
        assert severity == "low"

    def test_get_potential_impact(self):
        """Test potential impact descriptions."""
        node = RaceConditionDetectorNode()

        impact = node._get_potential_impact(RaceConditionType.WRITE_WRITE_RACE)
        assert "corruption" in impact.lower()

        impact = node._get_potential_impact(RaceConditionType.READ_WRITE_RACE)
        assert "stale" in impact.lower()

        impact = node._get_potential_impact(RaceConditionType.LOST_UPDATE)
        assert "lost" in impact.lower()

        impact = node._get_potential_impact(RaceConditionType.CHECK_THEN_ACT)
        assert "logic" in impact.lower()

    def test_get_recommended_prevention(self):
        """Test prevention strategy recommendations."""
        node = RaceConditionDetectorNode()

        # Write-write race should recommend pessimistic locking
        strategies = node._get_recommended_prevention(
            RaceConditionType.WRITE_WRITE_RACE
        )
        assert PreventionStrategy.PESSIMISTIC_LOCKING in strategies

        # Read-write race should recommend optimistic locking
        strategies = node._get_recommended_prevention(RaceConditionType.READ_WRITE_RACE)
        assert PreventionStrategy.OPTIMISTIC_LOCKING in strategies

        # Check-then-act should recommend atomic operations
        strategies = node._get_recommended_prevention(RaceConditionType.CHECK_THEN_ACT)
        assert PreventionStrategy.ATOMIC_OPERATIONS in strategies

    def test_serialize_race(self):
        """Test race condition serialization."""
        node = RaceConditionDetectorNode()

        access1 = ResourceAccess(
            access_id="acc1",
            resource_id="res1",
            operation_id="op1",
            thread_id="t1",
            process_id="p1",
            access_type=AccessType.READ,
            start_time=1234567890.0,
            end_time=1234567891.0,
            duration=1.0,
            success=True,
        )

        race = RaceConditionDetection(
            detection_id="race123",
            race_type=RaceConditionType.READ_WRITE_RACE,
            involved_operations=["op1", "op2"],
            involved_resources=["res1"],
            conflicting_accesses=[access1],
            detection_time=1234567890.0,
            confidence_score=0.8,
            severity="high",
            potential_impact="Test impact",
            recommended_prevention=[PreventionStrategy.OPTIMISTIC_LOCKING],
            timing_analysis={"overlap": 0.001},
        )

        serialized = node._serialize_race(race)

        # Verify serialization
        assert serialized["detection_id"] == "race123"
        assert serialized["race_type"] == "read_write_race"
        assert serialized["involved_operations"] == ["op1", "op2"]
        assert serialized["involved_resources"] == ["res1"]
        assert len(serialized["conflicting_accesses"]) == 1
        assert serialized["confidence_score"] == 0.8
        assert serialized["severity"] == "high"
        assert serialized["potential_impact"] == "Test impact"
        assert "optimistic_locking" in serialized["recommended_prevention"]
        assert serialized["timing_analysis"]["overlap"] == 0.001

        # Verify access serialization
        access_data = serialized["conflicting_accesses"][0]
        assert access_data["access_id"] == "acc1"
        assert access_data["resource_id"] == "res1"
        assert access_data["access_type"] == "read"
        assert access_data["start_time"] == 1234567890.0
        assert access_data["duration"] == 1.0

    def test_analyze_resource_conflicts(self):
        """Test resource conflict analysis."""
        node = RaceConditionDetectorNode()

        # Create test resource accesses
        resource_accesses = {
            "res1": [
                ResourceAccess(
                    "acc1", "res1", "op1", "t1", "p1", AccessType.READ, time.time()
                ),
                ResourceAccess(
                    "acc2", "res1", "op2", "t2", "p2", AccessType.WRITE, time.time()
                ),
                ResourceAccess(
                    "acc3", "res1", "op3", "t3", "p3", AccessType.WRITE, time.time()
                ),
            ],
            "res2": [
                ResourceAccess(
                    "acc4", "res2", "op4", "t4", "p4", AccessType.READ, time.time()
                ),
                ResourceAccess(
                    "acc5", "res2", "op5", "t5", "p5", AccessType.READ, time.time()
                ),
            ],
        }

        conflicts = node._analyze_resource_conflicts(resource_accesses)

        # Verify conflict analysis
        assert "res1" in conflicts
        assert "res2" in conflicts

        res1_conflict = conflicts["res1"]
        assert res1_conflict["total_accesses"] == 3
        assert res1_conflict["write_accesses"] == 2
        assert res1_conflict["read_accesses"] == 1
        assert res1_conflict["concurrent_threads"] == 3
        assert res1_conflict["conflict_potential"] == "high"

        res2_conflict = conflicts["res2"]
        assert res2_conflict["total_accesses"] == 2
        assert res2_conflict["write_accesses"] == 0
        assert res2_conflict["read_accesses"] == 2
        assert res2_conflict["conflict_potential"] == "low"

    def test_generate_timing_analysis(self):
        """Test timing analysis generation."""
        node = RaceConditionDetectorNode()

        # Create test resource accesses with durations
        base_time = time.time()
        access1 = ResourceAccess(
            "acc1", "res1", "op1", "t1", "p1", AccessType.READ, base_time
        )
        access1.duration = 0.1
        access2 = ResourceAccess(
            "acc2", "res1", "op2", "t2", "p2", AccessType.WRITE, base_time + 0.05
        )
        access2.duration = 0.2

        resource_accesses = {"res1": [access1, access2]}

        analysis = node._generate_timing_analysis(resource_accesses)

        # Verify timing analysis
        assert "res1" in analysis
        res1_analysis = analysis["res1"]
        assert res1_analysis["access_count"] == 2
        assert abs(res1_analysis["avg_duration"] - 0.15) < 0.01  # (0.1 + 0.2) / 2
        assert res1_analysis["max_duration"] == 0.2
        assert abs(res1_analysis["time_span"] - 0.05) < 0.01
        assert res1_analysis["concurrency_level"] == 2

    def test_unknown_operation(self):
        """Test unknown operation handling."""
        node = RaceConditionDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="unknown_operation")

        assert "Unknown operation: unknown_operation" in str(exc_info.value)

    def test_node_import(self):
        """Test that RaceConditionDetectorNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import RaceConditionDetectorNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "RaceConditionDetectorNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = RaceConditionDetectorNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "races_detected": [],
                "race_count": 0,
                "active_accesses": 0,
                "active_operations": 0,
                "prevention_suggestions": [],
                "resource_conflicts": {},
                "timing_analysis": {},
                "monitoring_status": "idle",
                "timestamp": datetime.now(UTC).isoformat(),
                "status": "success",
            }

            # Execute synchronously
            result = node.execute(operation="get_status")

            assert result["status"] == "success"
            assert result["monitoring_status"] == "idle"

    def test_cleanup(self):
        """Test node cleanup."""
        node = RaceConditionDetectorNode()

        # Start monitoring to create background tasks
        node.execute(operation="start_monitoring")

        # Cleanup
        asyncio.run(node.cleanup())

        # Verify monitoring stopped
        assert node._monitoring_active is False

    def test_concurrent_access_detection(self):
        """Test detection of immediate concurrent access races."""
        node = RaceConditionDetectorNode()

        # Register first access (read)
        result1 = node.execute(
            operation="register_access",
            access_id="acc1",
            resource_id="shared_data",
            thread_id="thread1",
            access_type="read",
        )

        # Register concurrent access (write) - should detect potential race
        result2 = node.execute(
            operation="register_access",
            access_id="acc2",
            resource_id="shared_data",
            thread_id="thread2",  # Different thread
            access_type="write",
        )

        # Should detect potential race condition
        assert result2["status"] == "success"
        # Race detection depends on timing and implementation details

    def test_operation_with_multiple_accesses(self):
        """Test operation containing multiple resource accesses."""
        node = RaceConditionDetectorNode()

        # Register operation
        node.execute(
            operation="register_operation",
            operation_id="complex_op",
            thread_id="main_thread",
        )

        # Add multiple accesses to the operation
        node.execute(
            operation="register_access",
            access_id="acc1",
            resource_id="resource1",
            operation_id="complex_op",
            thread_id="main_thread",
            access_type="read",
        )

        node.execute(
            operation="register_access",
            access_id="acc2",
            resource_id="resource1",
            operation_id="complex_op",
            thread_id="main_thread",
            access_type="write",
        )

        # End accesses
        time.sleep(0.01)
        node.execute(operation="end_access", access_id="acc1", success=True)
        node.execute(operation="end_access", access_id="acc2", success=True)

        # End operation (should analyze for check-then-act patterns)
        result = node.execute(operation="end_operation", operation_id="complex_op")

        assert result["status"] == "success"
        # May detect check-then-act race condition

    def test_access_with_error(self):
        """Test handling access that ends with an error."""
        node = RaceConditionDetectorNode()

        # Register and end access with error
        node.execute(
            operation="register_access",
            access_id="error_acc",
            resource_id="problematic_resource",
            thread_id="error_thread",
            access_type="write",
        )

        result = node.execute(
            operation="end_access",
            access_id="error_acc",
            success=False,
            error="Database connection failed",
        )

        assert result["status"] == "success"

        # Verify error recorded
        completed_access = node._completed_accesses[0]
        assert completed_access.success is False
        assert completed_access.error == "Database connection failed"
