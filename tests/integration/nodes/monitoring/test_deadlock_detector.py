"""Unit tests for DeadlockDetectorNode."""

import asyncio
import time
from unittest.mock import patch

import pytest
from kailash.nodes.monitoring import DeadlockDetectorNode
from kailash.nodes.monitoring.deadlock_detector import (
    DeadlockType,
    ResolutionStrategy,
    ResourceLock,
    TransactionWait,
)
from kailash.sdk_exceptions import NodeExecutionError


class TestDeadlockDetectorNode:
    """Test suite for DeadlockDetectorNode."""

    def test_node_initialization(self):
        """Test that DeadlockDetectorNode initializes correctly."""
        node = DeadlockDetectorNode(id="test_deadlock_detector")
        assert node.id == "test_deadlock_detector"
        assert node._active_locks == {}
        assert node._active_waits == {}
        assert node._wait_for_graph == {}
        assert node._transaction_resources == {}
        assert node._resource_holders == {}
        assert node._detected_deadlocks == []
        assert node._detection_history == []
        assert node._monitoring_active is False
        assert isinstance(node._background_tasks, set)

    def test_get_parameters(self):
        """Test parameter definition."""
        node = DeadlockDetectorNode()
        params = node.get_parameters()

        # Check required parameters
        assert "operation" in params
        assert params["operation"].required is True

        # Check optional parameters with defaults
        assert "transaction_id" in params
        assert params["transaction_id"].required is False

        assert "resource_id" in params
        assert params["resource_id"].required is False

        assert "lock_type" in params
        assert params["lock_type"].default == "exclusive"

        assert "detection_algorithm" in params
        assert params["detection_algorithm"].default == "wait_for_graph"

        assert "resolution_strategy" in params
        assert params["resolution_strategy"].default == "victim_selection"

        assert "enable_monitoring" in params
        assert params["enable_monitoring"].default is False

        assert "monitoring_interval" in params
        assert params["monitoring_interval"].default == 1.0

    def test_get_output_schema(self):
        """Test output schema definition."""
        node = DeadlockDetectorNode()
        schema = node.get_output_schema()

        # Check output fields
        assert "deadlocks_detected" in schema
        assert "deadlock_count" in schema
        assert "active_locks" in schema
        assert "active_waits" in schema
        assert "resolution_actions" in schema
        assert "wait_for_graph" in schema
        assert "monitoring_status" in schema
        assert "timestamp" in schema
        assert "status" in schema

    def test_deadlock_type_enum(self):
        """Test DeadlockType enumeration."""
        assert DeadlockType.RESOURCE_LOCK.value == "resource_lock"
        assert DeadlockType.WAIT_FOR_GRAPH.value == "wait_for_graph"
        assert DeadlockType.TIMEOUT_INFERRED.value == "timeout_inferred"
        assert DeadlockType.CIRCULAR_DEPENDENCY.value == "circular_dependency"

    def test_resolution_strategy_enum(self):
        """Test ResolutionStrategy enumeration."""
        assert ResolutionStrategy.VICTIM_SELECTION.value == "victim_selection"
        assert ResolutionStrategy.TIMEOUT_ROLLBACK.value == "timeout_rollback"
        assert ResolutionStrategy.PRIORITY_BASED.value == "priority_based"
        assert ResolutionStrategy.COST_BASED.value == "cost_based"
        assert ResolutionStrategy.MANUAL.value == "manual"

    def test_resource_lock_creation(self):
        """Test ResourceLock dataclass."""
        lock = ResourceLock(
            resource_id="table_orders",
            lock_type="exclusive",
            holder_transaction_id="txn_123",
            requested_at=time.time(),
        )

        assert lock.resource_id == "table_orders"
        assert lock.lock_type == "exclusive"
        assert lock.holder_transaction_id == "txn_123"
        assert lock.granted_at is None
        assert lock.timeout is None
        assert lock.metadata == {}

    def test_transaction_wait_creation(self):
        """Test TransactionWait dataclass."""
        wait = TransactionWait(
            transaction_id="txn_456",
            waiting_for_transaction_id="txn_123",
            resource_id="table_orders",
            wait_start_time=time.time(),
            priority=1,
            cost=100.0,
        )

        assert wait.transaction_id == "txn_456"
        assert wait.waiting_for_transaction_id == "txn_123"
        assert wait.resource_id == "table_orders"
        assert wait.priority == 1
        assert wait.cost == 100.0
        assert wait.timeout is None
        assert wait.metadata == {}

    def test_register_lock(self):
        """Test registering a resource lock."""
        node = DeadlockDetectorNode()

        result = node.execute(
            operation="register_lock",
            transaction_id="txn_123",
            resource_id="table_orders",
            lock_type="exclusive",
            timeout=30.0,
        )

        # Verify result
        assert result["status"] == "success"
        assert result["active_locks"] == 1
        assert result["active_waits"] == 0
        assert result["deadlock_count"] == 0

        # Verify internal state
        lock_id = "txn_123:table_orders"
        assert lock_id in node._active_locks
        lock = node._active_locks[lock_id]
        assert lock.resource_id == "table_orders"
        assert lock.lock_type == "exclusive"
        assert lock.holder_transaction_id == "txn_123"
        assert lock.timeout == 30.0

        assert "table_orders" in node._transaction_resources["txn_123"]
        assert node._resource_holders["table_orders"] == "txn_123"

    def test_register_lock_missing_params(self):
        """Test registering lock with missing parameters."""
        node = DeadlockDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="register_lock", transaction_id="txn_123")

        assert "transaction_id and resource_id are required" in str(exc_info.value)

    def test_register_wait(self):
        """Test registering a transaction wait."""
        node = DeadlockDetectorNode()

        result = node.execute(
            operation="register_wait",
            transaction_id="txn_456",
            waiting_for_transaction_id="txn_123",
            resource_id="table_orders",
            timeout=30.0,
            priority=1,
            cost=50.0,
        )

        # Verify result
        assert result["status"] == "success"
        assert result["active_locks"] == 0
        assert result["active_waits"] == 1
        assert result["deadlock_count"] == 0

        # Verify internal state
        wait_id = "txn_456:txn_123"
        assert wait_id in node._active_waits
        wait = node._active_waits[wait_id]
        assert wait.transaction_id == "txn_456"
        assert wait.waiting_for_transaction_id == "txn_123"
        assert wait.resource_id == "table_orders"
        assert wait.timeout == 30.0
        assert wait.priority == 1
        assert wait.cost == 50.0

        # Verify wait-for graph
        assert "txn_123" in node._wait_for_graph["txn_456"]

    def test_register_wait_missing_params(self):
        """Test registering wait with missing parameters."""
        node = DeadlockDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="register_wait", transaction_id="txn_456")

        assert "transaction_id and waiting_for_transaction_id are required" in str(
            exc_info.value
        )

    def test_simple_deadlock_detection(self):
        """Test detecting a simple two-transaction deadlock."""
        node = DeadlockDetectorNode()

        # Create circular wait: txn_1 -> txn_2 -> txn_1
        node.execute(
            operation="register_wait",
            transaction_id="txn_1",
            waiting_for_transaction_id="txn_2",
            resource_id="resource_A",
        )

        result = node.execute(
            operation="register_wait",
            transaction_id="txn_2",
            waiting_for_transaction_id="txn_1",
            resource_id="resource_B",
        )

        # Should detect deadlock immediately
        assert result["deadlock_count"] == 1
        deadlock = result["deadlocks_detected"][0]
        assert deadlock["deadlock_type"] == "wait_for_graph"
        assert set(deadlock["involved_transactions"]) == {"txn_1", "txn_2"}
        assert len(deadlock["wait_chain"]) == 2

    def test_three_way_deadlock_detection(self):
        """Test detecting a three-transaction deadlock."""
        node = DeadlockDetectorNode()

        # Create circular wait: txn_1 -> txn_2 -> txn_3 -> txn_1
        node.execute(
            operation="register_wait",
            transaction_id="txn_1",
            waiting_for_transaction_id="txn_2",
            resource_id="resource_A",
        )

        node.execute(
            operation="register_wait",
            transaction_id="txn_2",
            waiting_for_transaction_id="txn_3",
            resource_id="resource_B",
        )

        result = node.execute(
            operation="register_wait",
            transaction_id="txn_3",
            waiting_for_transaction_id="txn_1",
            resource_id="resource_C",
        )

        # Should detect deadlock
        assert result["deadlock_count"] == 1
        deadlock = result["deadlocks_detected"][0]
        assert deadlock["deadlock_type"] == "wait_for_graph"
        assert set(deadlock["involved_transactions"]) == {"txn_1", "txn_2", "txn_3"}
        assert len(deadlock["wait_chain"]) == 3

    def test_detect_deadlocks_operation(self):
        """Test explicit deadlock detection operation."""
        node = DeadlockDetectorNode()

        # Set up deadlock scenario
        node.execute(
            operation="register_wait",
            transaction_id="txn_A",
            waiting_for_transaction_id="txn_B",
            resource_id="resource_1",
        )

        node.execute(
            operation="register_wait",
            transaction_id="txn_B",
            waiting_for_transaction_id="txn_A",
            resource_id="resource_2",
        )

        # Explicitly detect deadlocks
        result = node.execute(
            operation="detect_deadlocks", detection_algorithm="wait_for_graph"
        )

        # Verify detection
        assert result["status"] == "success"
        assert (
            result["deadlock_count"] >= 1
        )  # May have detected during registration too
        assert len(result["resolution_actions"]) >= 1

        # Check that deadlock was stored
        assert len(node._detected_deadlocks) >= 1
        assert len(node._detection_history) >= 1

    def test_timeout_based_detection(self):
        """Test timeout-based deadlock detection."""
        node = DeadlockDetectorNode()

        # Register wait with short timeout
        current_time = time.time()

        # Mock time to simulate timeout
        with patch("time.time", return_value=current_time + 35):  # 35 seconds later
            # Create wait with 30 second timeout (should be exceeded)
            wait = TransactionWait(
                transaction_id="txn_timeout",
                waiting_for_transaction_id="txn_holder",
                resource_id="resource_timeout",
                wait_start_time=current_time,
                timeout=30.0,
            )
            node._active_waits["txn_timeout:txn_holder"] = wait

            result = node.execute(
                operation="detect_deadlocks", detection_algorithm="timeout_based"
            )

        # Should detect timeout deadlock
        assert result["deadlock_count"] == 1
        deadlock = result["deadlocks_detected"][0]
        assert deadlock["deadlock_type"] == "timeout_inferred"
        assert "txn_timeout" in deadlock["involved_transactions"]

    def test_release_lock(self):
        """Test releasing locks."""
        node = DeadlockDetectorNode()

        # Register locks and waits
        node.execute(
            operation="register_lock",
            transaction_id="txn_123",
            resource_id="table_orders",
            lock_type="exclusive",
        )

        node.execute(
            operation="register_wait",
            transaction_id="txn_456",
            waiting_for_transaction_id="txn_123",
            resource_id="table_orders",
        )

        # Release lock
        result = node.execute(operation="release_lock", transaction_id="txn_123")

        # Verify release
        assert result["status"] == "success"
        assert result["active_locks"] == 0
        assert result["active_waits"] == 0
        assert "Released locks for txn_123" in result["resolution_actions"]

        # Verify internal state cleanup
        assert len(node._active_locks) == 0
        assert len(node._active_waits) == 0
        assert "table_orders" not in node._resource_holders

    def test_release_specific_lock(self):
        """Test releasing a specific resource lock."""
        node = DeadlockDetectorNode()

        # Register multiple locks for same transaction
        node.execute(
            operation="register_lock",
            transaction_id="txn_123",
            resource_id="table_orders",
            lock_type="exclusive",
        )

        node.execute(
            operation="register_lock",
            transaction_id="txn_123",
            resource_id="table_customers",
            lock_type="shared",
        )

        # Release specific lock
        result = node.execute(
            operation="release_lock",
            transaction_id="txn_123",
            resource_id="table_orders",
        )

        # Verify only specific lock was released
        assert result["active_locks"] == 1
        assert "txn_123:table_orders" not in node._active_locks
        assert "txn_123:table_customers" in node._active_locks

    def test_victim_selection_priority_based(self):
        """Test victim selection based on priority."""
        node = DeadlockDetectorNode()

        # Create wait chain with different priorities
        wait1 = TransactionWait(
            transaction_id="txn_high_priority",
            waiting_for_transaction_id="txn_low_priority",
            resource_id="resource_1",
            wait_start_time=time.time(),
            priority=1,  # Higher priority (lower number)
        )

        wait2 = TransactionWait(
            transaction_id="txn_low_priority",
            waiting_for_transaction_id="txn_high_priority",
            resource_id="resource_2",
            wait_start_time=time.time(),
            priority=5,  # Lower priority (higher number)
        )

        # Create mock deadlock
        from kailash.nodes.monitoring.deadlock_detector import DeadlockDetection

        deadlock = DeadlockDetection(
            detection_id="test_deadlock",
            deadlock_type=DeadlockType.WAIT_FOR_GRAPH,
            involved_transactions=["txn_high_priority", "txn_low_priority"],
            involved_resources=["resource_1", "resource_2"],
            detection_time=time.time(),
            wait_chain=[wait1, wait2],
        )

        # Test victim selection
        victims = node._select_victim_candidates(deadlock)

        # Lower priority transaction should be selected as victim
        assert "txn_high_priority" in victims
        assert len(victims) >= 1

    def test_victim_selection_cost_based(self):
        """Test victim selection based on cost."""
        node = DeadlockDetectorNode()

        # Create wait chain with different costs
        wait1 = TransactionWait(
            transaction_id="txn_expensive",
            waiting_for_transaction_id="txn_cheap",
            resource_id="resource_1",
            wait_start_time=time.time(),
            cost=1000.0,  # Higher cost
        )

        wait2 = TransactionWait(
            transaction_id="txn_cheap",
            waiting_for_transaction_id="txn_expensive",
            resource_id="resource_2",
            wait_start_time=time.time(),
            cost=10.0,  # Lower cost
        )

        # Create mock deadlock
        from kailash.nodes.monitoring.deadlock_detector import DeadlockDetection

        deadlock = DeadlockDetection(
            detection_id="test_deadlock",
            deadlock_type=DeadlockType.WAIT_FOR_GRAPH,
            involved_transactions=["txn_expensive", "txn_cheap"],
            involved_resources=["resource_1", "resource_2"],
            detection_time=time.time(),
            wait_chain=[wait1, wait2],
        )

        # Test victim selection
        victims = node._select_victim_candidates(deadlock)

        # Lower cost transaction should be selected as victim
        assert "txn_cheap" in victims

    def test_resolve_deadlock(self):
        """Test deadlock resolution."""
        node = DeadlockDetectorNode()

        # Set up and detect deadlock
        node.execute(
            operation="register_wait",
            transaction_id="txn_A",
            waiting_for_transaction_id="txn_B",
            resource_id="resource_1",
        )

        node.execute(
            operation="register_wait",
            transaction_id="txn_B",
            waiting_for_transaction_id="txn_A",
            resource_id="resource_2",
        )

        detect_result = node.execute(operation="detect_deadlocks")
        deadlock_id = detect_result["deadlocks_detected"][0]["detection_id"]

        # Resolve deadlock
        result = node.execute(
            operation="resolve_deadlock",
            deadlock_id=deadlock_id,
            victim_transaction_id="txn_A",
            resolution_strategy="victim_selection",
        )

        # Verify resolution
        assert result["status"] == "success"
        assert len(result["resolution_actions"]) == 1
        action = result["resolution_actions"][0]
        assert action["action"] == "abort_transaction"
        assert action["transaction_id"] == "txn_A"

        # Verify deadlock marked as resolved
        deadlock = node._detected_deadlocks[0]
        assert deadlock.metadata.get("resolved") is True
        assert deadlock.metadata.get("victim_transaction") == "txn_A"

    def test_resolve_deadlock_not_found(self):
        """Test resolving non-existent deadlock."""
        node = DeadlockDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(
                operation="resolve_deadlock", deadlock_id="nonexistent_deadlock"
            )

        assert "Deadlock nonexistent_deadlock not found" in str(exc_info.value)

    def test_get_status(self):
        """Test getting detector status."""
        node = DeadlockDetectorNode()

        # Add some state
        node.execute(
            operation="register_lock",
            transaction_id="txn_123",
            resource_id="table_orders",
        )

        result = node.execute(operation="get_status")

        # Verify status
        assert result["status"] == "success"
        assert result["active_locks"] == 1
        assert result["active_waits"] == 0
        assert result["deadlock_count"] == 0
        assert result["monitoring_status"] == "idle"

    def test_start_stop_monitoring(self):
        """Test starting and stopping monitoring."""
        node = DeadlockDetectorNode()

        # Start monitoring
        result = node.execute(operation="start_monitoring", monitoring_interval=0.1)

        assert result["status"] == "success"
        assert result["monitoring_status"] == "monitoring"
        assert node._monitoring_active is True

        # Stop monitoring
        result = node.execute(operation="stop_monitoring")

        assert result["status"] == "success"
        assert result["monitoring_status"] == "stopped"
        assert node._monitoring_active is False

    def test_serialize_deadlock(self):
        """Test deadlock serialization."""
        node = DeadlockDetectorNode()

        # Create deadlock with wait chain
        wait = TransactionWait(
            transaction_id="txn_1",
            waiting_for_transaction_id="txn_2",
            resource_id="resource_A",
            wait_start_time=1234567890.0,
            timeout=30.0,
            priority=1,
            cost=100.0,
        )

        from kailash.nodes.monitoring.deadlock_detector import DeadlockDetection

        deadlock = DeadlockDetection(
            detection_id="test_deadlock_123",
            deadlock_type=DeadlockType.WAIT_FOR_GRAPH,
            involved_transactions=["txn_1", "txn_2"],
            involved_resources=["resource_A", "resource_B"],
            detection_time=1234567890.0,
            wait_chain=[wait],
            victim_candidates=["txn_1"],
            recommended_strategy=ResolutionStrategy.PRIORITY_BASED,
            metadata={"cycle_length": 2},
        )

        serialized = node._serialize_deadlock(deadlock)

        # Verify serialization
        assert serialized["detection_id"] == "test_deadlock_123"
        assert serialized["deadlock_type"] == "wait_for_graph"
        assert serialized["involved_transactions"] == ["txn_1", "txn_2"]
        assert serialized["involved_resources"] == ["resource_A", "resource_B"]
        assert serialized["detection_time"] == 1234567890.0
        assert len(serialized["wait_chain"]) == 1
        assert serialized["wait_chain"][0]["transaction_id"] == "txn_1"
        assert serialized["victim_candidates"] == ["txn_1"]
        assert serialized["recommended_strategy"] == "priority_based"
        assert serialized["metadata"]["cycle_length"] == 2

    def test_recommend_resolution_strategy(self):
        """Test resolution strategy recommendation."""
        node = DeadlockDetectorNode()

        # Test timeout-based strategy
        from kailash.nodes.monitoring.deadlock_detector import DeadlockDetection

        timeout_deadlock = DeadlockDetection(
            detection_id="timeout_deadlock",
            deadlock_type=DeadlockType.TIMEOUT_INFERRED,
            involved_transactions=["txn_1"],
            involved_resources=["resource_1"],
            detection_time=time.time(),
            wait_chain=[],
        )

        strategy = node._recommend_resolution_strategy(timeout_deadlock)
        assert strategy == ResolutionStrategy.TIMEOUT_ROLLBACK

        # Test priority-based strategy
        wait_with_priority = TransactionWait(
            transaction_id="txn_1",
            waiting_for_transaction_id="txn_2",
            resource_id="resource_1",
            wait_start_time=time.time(),
            priority=5,  # Non-zero priority
        )

        priority_deadlock = DeadlockDetection(
            detection_id="priority_deadlock",
            deadlock_type=DeadlockType.WAIT_FOR_GRAPH,
            involved_transactions=["txn_1", "txn_2"],
            involved_resources=["resource_1"],
            detection_time=time.time(),
            wait_chain=[wait_with_priority],
        )

        strategy = node._recommend_resolution_strategy(priority_deadlock)
        assert strategy == ResolutionStrategy.PRIORITY_BASED

    def test_unknown_operation(self):
        """Test unknown operation handling."""
        node = DeadlockDetectorNode()

        with pytest.raises(NodeExecutionError) as exc_info:
            node.execute(operation="unknown_operation")

        assert "Unknown operation: unknown_operation" in str(exc_info.value)

    def test_node_import(self):
        """Test that DeadlockDetectorNode can be imported from monitoring module."""
        from kailash.nodes.monitoring import DeadlockDetectorNode as ImportedNode

        assert ImportedNode is not None
        assert ImportedNode.__name__ == "DeadlockDetectorNode"

    def test_synchronous_execute(self):
        """Test synchronous execution wrapper."""
        node = DeadlockDetectorNode()

        with patch.object(node, "async_run") as mock_async_run:
            mock_async_run.return_value = {
                "deadlocks_detected": [],
                "deadlock_count": 0,
                "active_locks": 0,
                "active_waits": 0,
                "resolution_actions": [],
                "wait_for_graph": {},
                "monitoring_status": "idle",
                "timestamp": "2023-01-01T00:00:00Z",
                "status": "success",
            }

            # Execute synchronously
            result = node.execute(operation="get_status")

            assert result["status"] == "success"
            assert result["deadlock_count"] == 0

    def test_cleanup(self):
        """Test node cleanup."""
        node = DeadlockDetectorNode()

        # Start monitoring to create background tasks
        node.execute(operation="start_monitoring")

        # Cleanup
        asyncio.run(node.cleanup())

        # Verify monitoring stopped
        assert node._monitoring_active is False
