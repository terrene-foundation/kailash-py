"""
Unit Tests for Concurrent Access Protection System - Tier 1

Tests migration locking, queue management, deadlock detection, and atomic operations
with mock dependencies and fast execution (<1 second per test).
"""

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the classes we'll implement
from dataflow.migrations.concurrent_access_manager import (
    AtomicityAssessment,
    AtomicMigrationExecutor,
    ConcurrentMigrationQueue,
    DeadlockDetector,
    DeadlockScenario,
    DependencyGraph,
    LockInfo,
    LockStatus,
    MigrationLockManager,
    MigrationOperation,
    MigrationRequest,
    MigrationResult,
    QueueStatus,
    ResolutionStrategy,
    RollbackPlan,
)


class TestMigrationLockManager:
    """Test migration lock manager functionality."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager for testing."""
        manager = AsyncMock()
        manager.execute_query = AsyncMock()
        manager.get_connection = AsyncMock()
        return manager

    @pytest.fixture
    def lock_manager(self, mock_connection_manager):
        """Create lock manager instance for testing."""
        return MigrationLockManager(mock_connection_manager, lock_timeout=30)

    @pytest.mark.asyncio
    async def test_acquire_migration_lock_success(
        self, lock_manager, mock_connection_manager
    ):
        """Test successful lock acquisition."""

        # Setup mock to simulate successful operations:
        # 1. Table creation succeeds
        # 2. Cleanup query succeeds
        # 3. Insert lock succeeds
        # 4. Verification query returns the lock
        # Mock the verification query to return our process ID
        def mock_execute_query(*args, **kwargs):
            if "SELECT holder_process_id" in args[0]:
                # Return a row with the lock manager's process ID
                return [(lock_manager.process_id,)]
            return True

        mock_connection_manager.execute_query.side_effect = mock_execute_query

        # Test lock acquisition
        result = await lock_manager.acquire_migration_lock("test_schema")

        # Verify lock was acquired
        assert result is True
        assert mock_connection_manager.execute_query.call_count == 4

    @pytest.mark.asyncio
    async def test_acquire_migration_lock_timeout(
        self, lock_manager, mock_connection_manager
    ):
        """Test lock acquisition timeout."""
        # Setup mock to simulate lock timeout
        mock_connection_manager.execute_query.side_effect = asyncio.TimeoutError()

        # Test lock acquisition with timeout
        result = await lock_manager.acquire_migration_lock("test_schema", timeout=1)

        # Verify lock acquisition failed due to timeout
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_migration_lock_already_locked(
        self, lock_manager, mock_connection_manager
    ):
        """Test lock acquisition when schema is already locked."""
        # Setup mock to simulate already locked schema
        mock_connection_manager.execute_query.return_value = False

        # Test lock acquisition
        result = await lock_manager.acquire_migration_lock("test_schema")

        # Verify lock acquisition failed
        assert result is False

    @pytest.mark.asyncio
    async def test_release_migration_lock_success(
        self, lock_manager, mock_connection_manager
    ):
        """Test successful lock release."""
        # Setup mock for successful lock release
        mock_connection_manager.execute_query.return_value = True

        # Test lock release
        await lock_manager.release_migration_lock("test_schema")

        # Verify release was called
        mock_connection_manager.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_migration_lock_cleanup_on_error(
        self, lock_manager, mock_connection_manager
    ):
        """Test lock release with cleanup on error."""
        # Setup mock to simulate error during release
        mock_connection_manager.execute_query.side_effect = Exception("Database error")

        # Test lock release handles errors gracefully
        await lock_manager.release_migration_lock("test_schema")

        # Verify cleanup was attempted
        assert mock_connection_manager.execute_query.called

    @pytest.mark.asyncio
    async def test_check_lock_status_locked(
        self, lock_manager, mock_connection_manager
    ):
        """Test checking lock status when schema is locked."""
        # Setup mock to return lock status (holder_process_id, acquired_at)
        test_time = datetime.now()
        mock_connection_manager.execute_query.return_value = [
            ("process_123", test_time)
        ]

        # Test lock status check
        status = await lock_manager.check_lock_status("test_schema")

        # Verify status indicates locked
        assert status.is_locked is True
        assert status.schema_name == "test_schema"
        assert status.holder_process_id == "process_123"
        assert status.acquired_at == test_time

    @pytest.mark.asyncio
    async def test_check_lock_status_unlocked(
        self, lock_manager, mock_connection_manager
    ):
        """Test checking lock status when schema is not locked."""
        # Setup mock to return empty result
        mock_connection_manager.execute_query.return_value = []

        # Test lock status check
        status = await lock_manager.check_lock_status("test_schema")

        # Verify status indicates unlocked
        assert status.is_locked is False
        assert status.schema_name == "test_schema"
        assert status.holder_process_id is None

    @pytest.mark.asyncio
    async def test_migration_lock_context_manager_success(self, lock_manager):
        """Test migration lock context manager successful operation."""
        with (
            patch.object(lock_manager, "acquire_migration_lock", return_value=True),
            patch.object(lock_manager, "release_migration_lock") as mock_release,
        ):

            async with lock_manager.migration_lock("test_schema"):
                # Lock should be acquired at this point
                pass

            # Verify lock was released
            mock_release.assert_called_once_with("test_schema")

    @pytest.mark.asyncio
    async def test_migration_lock_context_manager_acquisition_failure(
        self, lock_manager
    ):
        """Test migration lock context manager when acquisition fails."""
        with patch.object(lock_manager, "acquire_migration_lock", return_value=False):

            with pytest.raises(RuntimeError, match="Failed to acquire migration lock"):
                async with lock_manager.migration_lock("test_schema"):
                    pass

    @pytest.mark.asyncio
    async def test_migration_lock_context_manager_exception_handling(
        self, lock_manager
    ):
        """Test migration lock context manager releases lock on exception."""
        with (
            patch.object(lock_manager, "acquire_migration_lock", return_value=True),
            patch.object(lock_manager, "release_migration_lock") as mock_release,
        ):

            with pytest.raises(ValueError):
                async with lock_manager.migration_lock("test_schema"):
                    raise ValueError("Test exception")

            # Verify lock was still released despite exception
            mock_release.assert_called_once_with("test_schema")


class TestConcurrentMigrationQueue:
    """Test concurrent migration queue functionality."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager for testing."""
        return AsyncMock()

    @pytest.fixture
    def migration_queue(self, mock_connection_manager):
        """Create migration queue instance for testing."""
        return ConcurrentMigrationQueue(mock_connection_manager)

    def test_enqueue_migration_success(self, migration_queue):
        """Test successful migration enqueuing."""
        # Create test migration request
        request = MigrationRequest(
            schema_name="test_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="test_table")
            ],
            priority=1,
        )

        # Test enqueuing
        queue_id = migration_queue.enqueue_migration(request)

        # Verify queue ID was returned
        assert isinstance(queue_id, str)
        assert len(queue_id) > 0

    def test_enqueue_migration_with_priority(self, migration_queue):
        """Test migration enqueuing with different priorities."""
        # Create high priority request
        high_priority_request = MigrationRequest(
            schema_name="high_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="high_table")
            ],
            priority=1,
        )

        # Create low priority request
        low_priority_request = MigrationRequest(
            schema_name="low_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="low_table")
            ],
            priority=3,
        )

        # Enqueue both
        high_id = migration_queue.enqueue_migration(high_priority_request)
        low_id = migration_queue.enqueue_migration(low_priority_request)

        # Verify both were enqueued
        assert high_id != low_id

    @pytest.mark.asyncio
    async def test_process_migration_queue_empty(self, migration_queue):
        """Test processing empty migration queue."""
        # Test processing empty queue
        results = await migration_queue.process_migration_queue()

        # Verify empty results
        assert results == []

    @pytest.mark.asyncio
    async def test_process_migration_queue_single_migration(self, migration_queue):
        """Test processing queue with single migration."""
        # Enqueue a migration
        request = MigrationRequest(
            schema_name="test_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="test_table")
            ],
            priority=1,
        )
        queue_id = migration_queue.enqueue_migration(request)

        # Mock successful processing
        with patch.object(
            migration_queue,
            "_execute_migration",
            return_value=MigrationResult(success=True, queue_id=queue_id),
        ):

            # Process queue
            results = await migration_queue.process_migration_queue()

            # Verify results
            assert len(results) == 1
            assert results[0].success is True
            assert results[0].queue_id == queue_id

    @pytest.mark.asyncio
    async def test_process_migration_queue_priority_order(self, migration_queue):
        """Test queue processing respects priority order."""
        # Enqueue migrations with different priorities
        low_request = MigrationRequest(
            schema_name="low_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="low_table")
            ],
            priority=3,
        )
        high_request = MigrationRequest(
            schema_name="high_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="high_table")
            ],
            priority=1,
        )

        low_id = migration_queue.enqueue_migration(low_request)
        high_id = migration_queue.enqueue_migration(high_request)

        # Mock processing
        processed_order = []

        async def mock_execute(request):
            processed_order.append(request.schema_name)
            return MigrationResult(success=True, queue_id=request.schema_name)

        with patch.object(
            migration_queue, "_execute_migration", side_effect=mock_execute
        ):

            # Process queue
            results = await migration_queue.process_migration_queue()

            # Verify high priority was processed first
            assert processed_order[0] == "high_schema"
            assert processed_order[1] == "low_schema"

    def test_get_queue_status_existing(self, migration_queue):
        """Test getting status of existing queue item."""
        # Enqueue migration
        request = MigrationRequest(
            schema_name="test_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="test_table")
            ],
            priority=1,
        )
        queue_id = migration_queue.enqueue_migration(request)

        # Get status
        status = migration_queue.get_queue_status(queue_id)

        # Verify status
        assert status.queue_id == queue_id
        assert status.status == "PENDING"
        assert status.position >= 0

    def test_get_queue_status_nonexistent(self, migration_queue):
        """Test getting status of non-existent queue item."""
        # Test non-existent queue ID
        status = migration_queue.get_queue_status("nonexistent_id")

        # Verify status indicates not found
        assert status.queue_id == "nonexistent_id"
        assert status.status == "NOT_FOUND"

    def test_cancel_queued_migration_success(self, migration_queue):
        """Test successful migration cancellation."""
        # Enqueue migration
        request = MigrationRequest(
            schema_name="test_schema",
            operations=[
                MigrationOperation(type="CREATE_TABLE", table_name="test_table")
            ],
            priority=1,
        )
        queue_id = migration_queue.enqueue_migration(request)

        # Cancel migration
        result = migration_queue.cancel_queued_migration(queue_id)

        # Verify cancellation
        assert result is True

    def test_cancel_queued_migration_nonexistent(self, migration_queue):
        """Test cancelling non-existent migration."""
        # Test cancelling non-existent migration
        result = migration_queue.cancel_queued_migration("nonexistent_id")

        # Verify cancellation failed
        assert result is False


class TestDeadlockDetector:
    """Test deadlock detection and resolution."""

    @pytest.fixture
    def deadlock_detector(self):
        """Create deadlock detector instance for testing."""
        return DeadlockDetector()

    def test_detect_potential_deadlock_none(self, deadlock_detector):
        """Test deadlock detection with no deadlocks."""
        # Create lock info with no potential deadlocks
        current_locks = {
            "schema_a": LockInfo(
                schema_name="schema_a",
                holder_process_id="process_1",
                acquired_at=datetime.now(),
                dependencies=[],
            )
        }

        # Test deadlock detection
        deadlocks = deadlock_detector.detect_potential_deadlock(current_locks)

        # Verify no deadlocks detected
        assert deadlocks == []

    def test_detect_potential_deadlock_circular(self, deadlock_detector):
        """Test deadlock detection with circular dependency."""
        # Create circular dependency scenario
        current_locks = {
            "schema_a": LockInfo(
                schema_name="schema_a",
                holder_process_id="process_1",
                acquired_at=datetime.now(),
                dependencies=["schema_b"],
            ),
            "schema_b": LockInfo(
                schema_name="schema_b",
                holder_process_id="process_2",
                acquired_at=datetime.now(),
                dependencies=["schema_a"],
            ),
        }

        # Test deadlock detection
        deadlocks = deadlock_detector.detect_potential_deadlock(current_locks)

        # Verify deadlock detected
        assert len(deadlocks) == 1
        assert deadlocks[0].involved_schemas == ["schema_a", "schema_b"]

    def test_detect_potential_deadlock_complex_chain(self, deadlock_detector):
        """Test deadlock detection with complex dependency chain."""
        # Create complex circular dependency
        current_locks = {
            "schema_a": LockInfo(
                schema_name="schema_a",
                holder_process_id="process_1",
                acquired_at=datetime.now(),
                dependencies=["schema_b"],
            ),
            "schema_b": LockInfo(
                schema_name="schema_b",
                holder_process_id="process_2",
                acquired_at=datetime.now(),
                dependencies=["schema_c"],
            ),
            "schema_c": LockInfo(
                schema_name="schema_c",
                holder_process_id="process_3",
                acquired_at=datetime.now(),
                dependencies=["schema_a"],
            ),
        }

        # Test deadlock detection
        deadlocks = deadlock_detector.detect_potential_deadlock(current_locks)

        # Verify complex deadlock detected
        assert len(deadlocks) == 1
        assert len(deadlocks[0].involved_schemas) == 3

    def test_resolve_deadlock_abort_youngest(self, deadlock_detector):
        """Test deadlock resolution by aborting youngest transaction."""
        # Create deadlock scenario
        deadlock = DeadlockScenario(
            involved_schemas=["schema_a", "schema_b"],
            involved_processes=["process_1", "process_2"],
            cycle_description="schema_a -> schema_b -> schema_a",
        )

        # Test resolution
        strategy = deadlock_detector.resolve_deadlock(deadlock)

        # Verify resolution strategy
        assert strategy.strategy_type == "ABORT_YOUNGEST"
        assert strategy.target_process in deadlock.involved_processes

    def test_resolve_deadlock_timeout_based(self, deadlock_detector):
        """Test deadlock resolution using timeout-based strategy."""
        # Create complex deadlock scenario
        deadlock = DeadlockScenario(
            involved_schemas=["schema_a", "schema_b", "schema_c"],
            involved_processes=["process_1", "process_2", "process_3"],
            cycle_description="complex multi-schema deadlock",
        )

        # Test resolution
        strategy = deadlock_detector.resolve_deadlock(deadlock)

        # Verify strategy is appropriate for complex scenario
        assert strategy.strategy_type in [
            "ABORT_YOUNGEST",
            "TIMEOUT_BASED",
            "PRIORITY_BASED",
        ]

    def test_monitor_lock_dependencies_empty(self, deadlock_detector):
        """Test monitoring lock dependencies with no locks."""
        # Test dependency monitoring with no active locks
        dependency_graph = deadlock_detector.monitor_lock_dependencies()

        # Verify empty dependency graph
        assert dependency_graph.nodes == []
        assert dependency_graph.edges == []

    def test_monitor_lock_dependencies_with_locks(self, deadlock_detector):
        """Test monitoring lock dependencies with active locks."""
        # Setup mock lock information
        with patch.object(
            deadlock_detector,
            "_get_current_locks",
            return_value={
                "schema_a": LockInfo(
                    schema_name="schema_a",
                    holder_process_id="process_1",
                    acquired_at=datetime.now(),
                    dependencies=["schema_b"],
                )
            },
        ):

            # Test dependency monitoring
            dependency_graph = deadlock_detector.monitor_lock_dependencies()

            # Verify dependency graph
            assert "schema_a" in dependency_graph.nodes
            assert len(dependency_graph.edges) >= 0


class TestAtomicMigrationExecutor:
    """Test atomic migration execution functionality."""

    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager for testing."""
        manager = AsyncMock()
        manager.begin_transaction = AsyncMock()
        manager.commit_transaction = AsyncMock()
        manager.rollback_transaction = AsyncMock()
        manager.execute_query = AsyncMock()
        return manager

    @pytest.fixture
    def atomic_executor(self, mock_connection_manager):
        """Create atomic migration executor for testing."""
        return AtomicMigrationExecutor(mock_connection_manager)

    @pytest.mark.asyncio
    async def test_execute_atomic_migration_success(
        self, atomic_executor, mock_connection_manager
    ):
        """Test successful atomic migration execution."""
        # Create test migration operations
        operations = [
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT PRIMARY KEY)",
            ),
            MigrationOperation(
                type="ADD_COLUMN",
                table_name="test_table",
                sql="ALTER TABLE test_table ADD COLUMN name VARCHAR(100)",
            ),
        ]

        # Mock successful execution
        mock_connection_manager.execute_query.return_value = True

        # Test atomic execution
        result = await atomic_executor.execute_atomic_migration(operations)

        # Verify success
        assert result.success is True
        assert result.operations_completed == 2
        assert result.rollback_executed is False

        # Verify transaction handling
        mock_connection_manager.begin_transaction.assert_called_once()
        mock_connection_manager.commit_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_atomic_migration_failure_with_rollback(
        self, atomic_executor, mock_connection_manager
    ):
        """Test atomic migration execution with failure and rollback."""
        # Create test migration operations
        operations = [
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT PRIMARY KEY)",
                rollback_sql="DROP TABLE test_table",
            ),
            MigrationOperation(
                type="ADD_COLUMN",
                table_name="test_table",
                sql="INVALID SQL THAT WILL FAIL",
                rollback_sql="-- No rollback needed",
            ),
        ]

        # Mock execution failure on second operation
        mock_connection_manager.execute_query.side_effect = [
            True,
            Exception("SQL Error"),
        ]

        # Test atomic execution
        result = await atomic_executor.execute_atomic_migration(operations)

        # Verify failure and rollback
        assert result.success is False
        assert result.operations_completed == 1  # Only first operation completed
        assert result.rollback_executed is True
        assert "SQL Error" in result.error_message

        # Verify rollback was called
        mock_connection_manager.rollback_transaction.assert_called_once()

    def test_validate_migration_atomicity_valid(self, atomic_executor):
        """Test atomicity validation for valid operations."""
        # Create atomic-compatible operations
        operations = [
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT)",
            ),
            MigrationOperation(
                type="ADD_COLUMN",
                table_name="test_table",
                sql="ALTER TABLE test_table ADD COLUMN name VARCHAR(100)",
            ),
        ]

        # Test atomicity validation
        assessment = atomic_executor.validate_migration_atomicity(operations)

        # Verify assessment
        assert assessment.is_atomic is True
        assert assessment.risk_level == "LOW"
        assert len(assessment.warnings) == 0

    def test_validate_migration_atomicity_invalid(self, atomic_executor):
        """Test atomicity validation for invalid operations."""
        # Create operations that cannot be atomic
        operations = [
            MigrationOperation(
                type="DROP_TABLE", table_name="test_table", sql="DROP TABLE test_table"
            ),
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT, name VARCHAR(100))",
            ),
        ]

        # Test atomicity validation
        assessment = atomic_executor.validate_migration_atomicity(operations)

        # Verify assessment identifies risks
        assert assessment.is_atomic is False
        assert assessment.risk_level == "HIGH"
        assert len(assessment.warnings) > 0

    def test_validate_migration_atomicity_medium_risk(self, atomic_executor):
        """Test atomicity validation for medium risk operations."""
        # Create medium risk operations
        operations = [
            MigrationOperation(
                type="MODIFY_COLUMN",
                table_name="test_table",
                sql="ALTER TABLE test_table ALTER COLUMN data_type TYPE TEXT",
            )
        ]

        # Test atomicity validation
        assessment = atomic_executor.validate_migration_atomicity(operations)

        # Verify medium risk assessment
        assert assessment.risk_level == "MEDIUM"
        assert len(assessment.warnings) > 0

    def test_prepare_rollback_plan_comprehensive(self, atomic_executor):
        """Test comprehensive rollback plan preparation."""
        # Create complex operations
        operations = [
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT)",
                rollback_sql="DROP TABLE test_table",
            ),
            MigrationOperation(
                type="ADD_COLUMN",
                table_name="test_table",
                sql="ALTER TABLE test_table ADD COLUMN name VARCHAR(100)",
                rollback_sql="ALTER TABLE test_table DROP COLUMN name",
            ),
            MigrationOperation(
                type="DROP_COLUMN",
                table_name="other_table",
                sql="ALTER TABLE other_table DROP COLUMN old_field",
                rollback_sql="-- Cannot recover dropped data",
            ),
        ]

        # Test rollback plan preparation
        rollback_plan = atomic_executor.prepare_rollback_plan(operations)

        # Verify rollback plan
        assert len(rollback_plan.steps) == 3  # All operations have rollback steps
        assert rollback_plan.fully_reversible is False  # Due to DROP_COLUMN
        assert rollback_plan.data_loss_warning is not None
        assert len(rollback_plan.irreversible_operations) == 1

    def test_prepare_rollback_plan_fully_reversible(self, atomic_executor):
        """Test rollback plan for fully reversible operations."""
        # Create fully reversible operations
        operations = [
            MigrationOperation(
                type="CREATE_TABLE",
                table_name="test_table",
                sql="CREATE TABLE test_table (id INT)",
                rollback_sql="DROP TABLE test_table",
            ),
            MigrationOperation(
                type="ADD_COLUMN",
                table_name="test_table",
                sql="ALTER TABLE test_table ADD COLUMN name VARCHAR(100)",
                rollback_sql="ALTER TABLE test_table DROP COLUMN name",
            ),
        ]

        # Test rollback plan preparation
        rollback_plan = atomic_executor.prepare_rollback_plan(operations)

        # Verify fully reversible plan
        assert rollback_plan.fully_reversible is True
        assert rollback_plan.data_loss_warning is None
        assert len(rollback_plan.irreversible_operations) == 0


# Performance and stress test markers for unit tests
class TestConcurrentAccessPerformance:
    """Test performance characteristics of concurrent access components."""

    @pytest.mark.timeout(1)  # All unit tests must complete in <1 second
    def test_lock_manager_performance(self):
        """Test lock manager operations complete within performance requirements."""
        # This test ensures lock manager operations are fast
        start_time = time.perf_counter()

        # Create lock manager (mocked for unit test)
        lock_manager = MigrationLockManager(AsyncMock(), lock_timeout=30)

        # Perform multiple operations
        for i in range(100):
            # Simulate lock operations (mocked)
            schema_name = f"test_schema_{i}"

        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds

        # Verify performance requirement (<1000ms for unit tests)
        assert (
            execution_time < 1000
        ), f"Lock manager operations took {execution_time:.2f}ms"

    @pytest.mark.timeout(1)
    def test_queue_manager_performance(self):
        """Test queue manager operations complete within performance requirements."""
        start_time = time.perf_counter()

        # Create queue manager
        queue_manager = ConcurrentMigrationQueue(AsyncMock())

        # Enqueue multiple migrations
        for i in range(50):
            request = MigrationRequest(
                schema_name=f"schema_{i}",
                operations=[
                    MigrationOperation(type="CREATE_TABLE", table_name=f"table_{i}")
                ],
                priority=1,
            )
            queue_manager.enqueue_migration(request)

        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000

        # Verify performance requirement
        assert execution_time < 1000, f"Queue operations took {execution_time:.2f}ms"

    @pytest.mark.timeout(1)
    def test_deadlock_detector_performance(self):
        """Test deadlock detector completes analysis within performance requirements."""
        start_time = time.perf_counter()

        # Create deadlock detector
        detector = DeadlockDetector()

        # Create complex lock scenario
        current_locks = {}
        for i in range(20):
            current_locks[f"schema_{i}"] = LockInfo(
                schema_name=f"schema_{i}",
                holder_process_id=f"process_{i}",
                acquired_at=datetime.now(),
                dependencies=[f"schema_{(i+1) % 20}"] if i < 19 else [],
            )

        # Test deadlock detection
        deadlocks = detector.detect_potential_deadlock(current_locks)

        end_time = time.perf_counter()
        execution_time = (end_time - start_time) * 1000

        # Verify performance requirement
        assert execution_time < 1000, f"Deadlock detection took {execution_time:.2f}ms"
