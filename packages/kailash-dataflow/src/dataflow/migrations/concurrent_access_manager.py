"""
Concurrent Access Protection System

Provides migration locking, queue management, deadlock detection, and atomic operations
to handle multiple processes accessing the same schema safely.

Features:
- Migration locking with timeout and cleanup
- Concurrent migration queue with priority processing
- Deadlock detection and resolution
- Atomic migration execution with rollback capability
"""

import asyncio
import heapq
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# Data classes and enums for the concurrent access system


@dataclass
class LockInfo:
    """Information about a migration lock."""

    schema_name: str
    holder_process_id: str
    acquired_at: datetime
    dependencies: List[str] = field(default_factory=list)


@dataclass
class LockStatus:
    """Status of a migration lock."""

    schema_name: str
    is_locked: bool
    holder_process_id: Optional[str] = None
    acquired_at: Optional[datetime] = None


@dataclass
class MigrationOperation:
    """A single migration operation."""

    type: str
    table_name: str
    sql: str = ""
    rollback_sql: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationRequest:
    """Request for migration execution."""

    schema_name: str
    operations: List[MigrationOperation]
    priority: int = 1  # Lower number = higher priority
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class MigrationResult:
    """Result of migration execution."""

    success: bool
    queue_id: str
    operations_completed: int = 0
    rollback_executed: bool = False
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None


@dataclass
class QueueStatus:
    """Status of a queued migration."""

    queue_id: str
    status: str  # PENDING, PROCESSING, COMPLETED, FAILED, NOT_FOUND
    position: int = -1
    estimated_wait_time: Optional[int] = None


@dataclass
class DeadlockScenario:
    """Description of a detected deadlock scenario."""

    involved_schemas: List[str]
    involved_processes: List[str]
    cycle_description: str


@dataclass
class ResolutionStrategy:
    """Strategy for resolving a deadlock."""

    strategy_type: str  # ABORT_YOUNGEST, TIMEOUT_BASED, PRIORITY_BASED
    target_process: Optional[str] = None
    timeout_seconds: Optional[int] = None
    description: str = ""


@dataclass
class DependencyGraph:
    """Graph of lock dependencies."""

    nodes: List[str] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class AtomicityAssessment:
    """Assessment of migration atomicity."""

    is_atomic: bool
    risk_level: str  # LOW, MEDIUM, HIGH
    warnings: List[str] = field(default_factory=list)
    estimated_duration_ms: int = 0


@dataclass
class RollbackStep:
    """A single step in rollback plan."""

    operation_type: str
    sql: str
    estimated_duration_ms: int
    risk_level: str


@dataclass
class RollbackPlan:
    """Plan for rolling back migrations."""

    steps: List[RollbackStep] = field(default_factory=list)
    fully_reversible: bool = True
    data_loss_warning: Optional[str] = None
    irreversible_operations: List[str] = field(default_factory=list)
    estimated_total_duration_ms: int = 0


class MigrationLockManager:
    """
    Distributed locking system for migration operations.

    Provides exclusive locks for schema migrations with timeout,
    cleanup, and context manager support.
    """

    def __init__(self, connection_manager, lock_timeout: int = 30):
        """
        Initialize migration lock manager.

        Args:
            connection_manager: Database connection manager
            lock_timeout: Default lock timeout in seconds
        """
        self.connection_manager = connection_manager
        self.lock_timeout = lock_timeout
        self.process_id = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self._table_ensured = False
        # Detect database type from connection manager for database-specific SQL
        self._db_type = getattr(connection_manager, "_parameter_style", "postgresql")

    async def _ensure_lock_table(self):
        """Ensure migration lock table exists."""
        # Use database-specific CREATE TABLE syntax
        if self._db_type == "mysql":
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS dataflow_migration_locks (
                schema_name VARCHAR(255) PRIMARY KEY,
                holder_process_id VARCHAR(255) NOT NULL,
                acquired_at DATETIME NOT NULL,
                expires_at DATETIME NOT NULL,
                lock_data TEXT
            )
            """
        else:
            # PostgreSQL and SQLite use TIMESTAMP
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS dataflow_migration_locks (
                schema_name VARCHAR(255) PRIMARY KEY,
                holder_process_id VARCHAR(255) NOT NULL,
                acquired_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                lock_data TEXT
            )
            """

        try:
            await self.connection_manager.execute_query(create_table_sql)
        except Exception as e:
            logger.warning(f"Failed to create lock table: {e}")

    async def acquire_migration_lock(
        self, schema_name: str, timeout: int = None
    ) -> bool:
        """
        Acquire exclusive lock for schema migrations.

        Args:
            schema_name: Name of schema to lock
            timeout: Lock acquisition timeout in seconds

        Returns:
            True if lock acquired, False otherwise
        """
        if timeout is None:
            timeout = self.lock_timeout

        # Ensure lock table exists on first use
        if not self._table_ensured:
            await self._ensure_lock_table()
            self._table_ensured = True

        expires_at = datetime.now() + timedelta(seconds=timeout)

        # First, cleanup any expired locks
        await self._cleanup_expired_locks()

        # Use database-specific INSERT syntax to handle conflicts
        # PostgreSQL: ON CONFLICT DO NOTHING
        # MySQL: INSERT IGNORE
        # SQLite: INSERT OR IGNORE
        if self._db_type == "mysql":
            insert_lock_sql = """
            INSERT IGNORE INTO dataflow_migration_locks
            (schema_name, holder_process_id, acquired_at, expires_at, lock_data)
            VALUES (%s, %s, %s, %s, %s)
            """
        elif self._db_type == "sqlite":
            insert_lock_sql = """
            INSERT OR IGNORE INTO dataflow_migration_locks
            (schema_name, holder_process_id, acquired_at, expires_at, lock_data)
            VALUES (?, ?, ?, ?, ?)
            """
        else:
            # PostgreSQL
            insert_lock_sql = """
            INSERT INTO dataflow_migration_locks
            (schema_name, holder_process_id, acquired_at, expires_at, lock_data)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (schema_name) DO NOTHING
            """

        try:
            result = await self.connection_manager.execute_query(
                insert_lock_sql,
                (
                    schema_name,
                    self.process_id,
                    datetime.now(),
                    expires_at,
                    json.dumps({"timeout": timeout}),
                ),
            )

            # Check if we successfully acquired the lock
            # For asyncpg, INSERT result is "INSERT 0 1" if successful, "INSERT 0 0" if conflict
            if result and (
                "INSERT 0 1" in str(result) if isinstance(result, str) else result
            ):
                # Verify we are the lock holder - use database-specific placeholders
                if self._db_type == "mysql":
                    check_sql = """
                    SELECT holder_process_id FROM dataflow_migration_locks
                    WHERE schema_name = %s AND holder_process_id = %s
                    """
                elif self._db_type == "sqlite":
                    check_sql = """
                    SELECT holder_process_id FROM dataflow_migration_locks
                    WHERE schema_name = ? AND holder_process_id = ?
                    """
                else:
                    check_sql = """
                    SELECT holder_process_id FROM dataflow_migration_locks
                    WHERE schema_name = $1 AND holder_process_id = $2
                    """

                check_result = await self.connection_manager.execute_query(
                    check_sql, (schema_name, self.process_id)
                )

                if check_result:
                    logger.info(f"Acquired migration lock for schema: {schema_name}")
                    return True

            logger.warning(f"Failed to acquire lock for schema: {schema_name}")
            return False

        except asyncio.TimeoutError:
            logger.warning(f"Lock acquisition timeout for schema: {schema_name}")
            return False
        except Exception as e:
            logger.error(f"Error acquiring lock for schema {schema_name}: {e}")
            return False

    async def release_migration_lock(self, schema_name: str) -> None:
        """
        Release migration lock with cleanup.

        Args:
            schema_name: Name of schema to unlock
        """
        # Use database-specific placeholders
        if self._db_type == "mysql":
            delete_lock_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE schema_name = %s AND holder_process_id = %s
            """
        elif self._db_type == "sqlite":
            delete_lock_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE schema_name = ? AND holder_process_id = ?
            """
        else:
            delete_lock_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE schema_name = $1 AND holder_process_id = $2
            """

        try:
            await self.connection_manager.execute_query(
                delete_lock_sql, (schema_name, self.process_id)
            )
            logger.info(f"Released migration lock for schema: {schema_name}")

        except Exception as e:
            logger.error(f"Error releasing lock for schema {schema_name}: {e}")
            # Still attempt cleanup of expired locks
            try:
                await self._cleanup_expired_locks()
            except Exception as cleanup_error:
                logger.error(
                    f"Cleanup failed after lock release error: {cleanup_error}"
                )

    async def check_lock_status(self, schema_name: str) -> LockStatus:
        """
        Check if schema is currently locked for migration.

        Args:
            schema_name: Name of schema to check

        Returns:
            LockStatus with current lock information
        """
        # Clean up expired locks first
        await self._cleanup_expired_locks()

        # Use database-specific placeholders
        if self._db_type == "mysql":
            check_sql = """
            SELECT holder_process_id, acquired_at
            FROM dataflow_migration_locks
            WHERE schema_name = %s AND expires_at > %s
            """
        elif self._db_type == "sqlite":
            check_sql = """
            SELECT holder_process_id, acquired_at
            FROM dataflow_migration_locks
            WHERE schema_name = ? AND expires_at > ?
            """
        else:
            check_sql = """
            SELECT holder_process_id, acquired_at
            FROM dataflow_migration_locks
            WHERE schema_name = $1 AND expires_at > $2
            """

        try:
            result = await self.connection_manager.execute_query(
                check_sql, (schema_name, datetime.now())
            )

            if result:
                logger.debug(f"Lock status result: {result}")
                logger.debug(f"First item: {result[0]}")
                logger.debug(f"Type of first item: {type(result[0])}")
                holder_process_id, acquired_at = result[0]
                return LockStatus(
                    schema_name=schema_name,
                    is_locked=True,
                    holder_process_id=holder_process_id,
                    acquired_at=acquired_at,
                )
            else:
                return LockStatus(schema_name=schema_name, is_locked=False)

        except Exception as e:
            logger.error(f"Error checking lock status for schema {schema_name}: {e}")
            return LockStatus(schema_name=schema_name, is_locked=False)

    @asynccontextmanager
    async def migration_lock(self, schema_name: str, timeout: int = None):
        """
        Context manager for safe lock acquisition/release.

        Args:
            schema_name: Name of schema to lock
            timeout: Lock timeout in seconds

        Raises:
            RuntimeError: If lock acquisition fails
        """
        acquired = await self.acquire_migration_lock(schema_name, timeout)

        if not acquired:
            raise RuntimeError(
                f"Failed to acquire migration lock for schema: {schema_name}"
            )

        try:
            yield
        finally:
            await self.release_migration_lock(schema_name)

    async def _cleanup_expired_locks(self):
        """Clean up expired locks from the database."""
        # Use database-specific placeholders
        if self._db_type == "mysql":
            cleanup_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE expires_at <= %s
            """
        elif self._db_type == "sqlite":
            cleanup_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE expires_at <= ?
            """
        else:
            cleanup_sql = """
            DELETE FROM dataflow_migration_locks
            WHERE expires_at <= $1
            """

        try:
            await self.connection_manager.execute_query(cleanup_sql, (datetime.now(),))
        except Exception as e:
            logger.warning(f"Failed to cleanup expired locks: {e}")


class ConcurrentMigrationQueue:
    """
    Migration queue management for high-concurrency scenarios.

    Provides priority-based queue processing with safe order execution
    and status tracking.
    """

    def __init__(self, connection_manager):
        """
        Initialize concurrent migration queue.

        Args:
            connection_manager: Database connection manager
        """
        self.connection_manager = connection_manager
        self._queue = []  # Priority queue
        self._queue_map = {}  # Queue ID to request mapping
        self._queue_lock = threading.RLock()
        self._next_position = 0
        self._table_ensured = False
        # Detect database type from connection manager for database-specific SQL
        self._db_type = getattr(connection_manager, "_parameter_style", "postgresql")

    async def _ensure_queue_table(self):
        """Ensure migration queue table exists."""
        # Use database-specific CREATE TABLE syntax
        if self._db_type == "mysql":
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS dataflow_migration_queue (
                queue_id VARCHAR(255) PRIMARY KEY,
                schema_name VARCHAR(255) NOT NULL,
                priority INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                operations TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME,
                error_message TEXT
            )
            """
        else:
            # PostgreSQL and SQLite use TIMESTAMP
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS dataflow_migration_queue (
                queue_id VARCHAR(255) PRIMARY KEY,
                schema_name VARCHAR(255) NOT NULL,
                priority INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                operations TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT
            )
            """

        try:
            await self.connection_manager.execute_query(create_table_sql)
        except Exception as e:
            logger.warning(f"Failed to create queue table: {e}")

    def enqueue_migration(self, request: MigrationRequest) -> str:
        """
        Add migration to queue, return queue ID.

        Args:
            request: Migration request to enqueue

        Returns:
            Queue ID for tracking
        """
        queue_id = request.request_id

        with self._queue_lock:
            # Add to priority queue (priority, position, request)
            heapq.heappush(
                self._queue, (request.priority, self._next_position, request)
            )
            self._queue_map[queue_id] = request
            self._next_position += 1

        logger.info(
            f"Enqueued migration {queue_id} for schema {request.schema_name} with priority {request.priority}"
        )
        return queue_id

    async def process_migration_queue(self) -> List[MigrationResult]:
        """
        Process queued migrations in safe order.

        Returns:
            List of migration results
        """
        # Ensure queue table exists on first use
        if not self._table_ensured:
            await self._ensure_queue_table()
            self._table_ensured = True

        results = []

        while True:
            # Get next migration from queue
            request = self._dequeue_next_migration()
            if request is None:
                break  # Queue is empty

            # Process the migration
            result = await self._execute_migration(request)
            results.append(result)

        return results

    def get_queue_status(self, queue_id: str) -> QueueStatus:
        """
        Check migration queue position and status.

        Args:
            queue_id: Queue ID to check

        Returns:
            Current queue status
        """
        with self._queue_lock:
            if queue_id not in self._queue_map:
                return QueueStatus(queue_id=queue_id, status="NOT_FOUND")

            # Find position in queue
            position = 0
            for priority, pos, req in self._queue:
                if req.request_id == queue_id:
                    return QueueStatus(
                        queue_id=queue_id, status="PENDING", position=position
                    )
                position += 1

            # If not in queue, might be processing or completed
            return QueueStatus(
                queue_id=queue_id, status="PROCESSING"
            )  # Simplified status

    def cancel_queued_migration(self, queue_id: str) -> bool:
        """
        Cancel pending migration from queue.

        Args:
            queue_id: Queue ID to cancel

        Returns:
            True if cancelled, False if not found
        """
        with self._queue_lock:
            if queue_id not in self._queue_map:
                return False

            # Remove from queue
            request = self._queue_map[queue_id]
            del self._queue_map[queue_id]

            # Rebuild queue without the cancelled request
            new_queue = []
            for priority, pos, req in self._queue:
                if req.request_id != queue_id:
                    new_queue.append((priority, pos, req))

            self._queue = new_queue
            heapq.heapify(self._queue)

            logger.info(f"Cancelled migration {queue_id}")
            return True

    def _dequeue_next_migration(self) -> Optional[MigrationRequest]:
        """Get next migration from priority queue."""
        with self._queue_lock:
            if not self._queue:
                return None

            priority, pos, request = heapq.heappop(self._queue)
            del self._queue_map[request.request_id]
            return request

    async def _execute_migration(self, request: MigrationRequest) -> MigrationResult:
        """
        Execute a migration request.

        Args:
            request: Migration request to execute

        Returns:
            Migration result
        """
        start_time = time.perf_counter()

        try:
            # Use atomic executor for migration
            executor = AtomicMigrationExecutor(self.connection_manager)
            result = await executor.execute_atomic_migration(request.operations)

            end_time = time.perf_counter()
            execution_time_ms = int((end_time - start_time) * 1000)

            return MigrationResult(
                success=result.success,
                queue_id=request.request_id,
                operations_completed=result.operations_completed,
                rollback_executed=result.rollback_executed,
                error_message=result.error_message,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            end_time = time.perf_counter()
            execution_time_ms = int((end_time - start_time) * 1000)

            logger.error(f"Migration execution failed for {request.request_id}: {e}")
            return MigrationResult(
                success=False,
                queue_id=request.request_id,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )


class DeadlockDetector:
    """
    Deadlock detection and resolution for migration locks.

    Monitors lock dependencies and provides resolution strategies
    for detected deadlock scenarios.
    """

    def __init__(self):
        """Initialize deadlock detector."""
        self._current_locks = {}

    def detect_potential_deadlock(
        self, current_locks: Dict[str, LockInfo]
    ) -> List[DeadlockScenario]:
        """
        Identify potential deadlock situations.

        Args:
            current_locks: Current lock information

        Returns:
            List of detected deadlock scenarios
        """
        deadlocks = []

        # Build dependency graph
        dependency_graph = self._build_dependency_graph(current_locks)

        # Detect cycles in dependency graph
        cycles = self._detect_cycles(dependency_graph)

        for cycle in cycles:
            # Create deadlock scenario for each cycle
            involved_processes = []
            for schema in cycle:
                if schema in current_locks:
                    involved_processes.append(current_locks[schema].holder_process_id)

            deadlock = DeadlockScenario(
                involved_schemas=cycle,
                involved_processes=list(set(involved_processes)),
                cycle_description=" -> ".join(cycle + [cycle[0]]),
            )
            deadlocks.append(deadlock)

        return deadlocks

    def resolve_deadlock(self, deadlock: DeadlockScenario) -> ResolutionStrategy:
        """
        Provide strategy to resolve detected deadlock.

        Args:
            deadlock: Deadlock scenario to resolve

        Returns:
            Resolution strategy
        """
        # For simplicity, use abort youngest strategy
        if len(deadlock.involved_processes) <= 2:
            # Simple case - abort youngest process
            return ResolutionStrategy(
                strategy_type="ABORT_YOUNGEST",
                target_process=deadlock.involved_processes[
                    -1
                ],  # Assume last is youngest
                description="Abort youngest process to break deadlock cycle",
            )
        else:
            # Complex case - use timeout based resolution
            return ResolutionStrategy(
                strategy_type="TIMEOUT_BASED",
                timeout_seconds=30,
                description="Use timeout-based resolution for complex deadlock",
            )

    def monitor_lock_dependencies(self) -> DependencyGraph:
        """
        Track lock dependencies for deadlock prevention.

        Returns:
            Current dependency graph
        """
        # Get current locks (would be implemented to query actual locks)
        current_locks = self._get_current_locks()

        # Build and return dependency graph
        return self._build_dependency_graph(current_locks)

    def _build_dependency_graph(self, locks: Dict[str, LockInfo]) -> DependencyGraph:
        """Build dependency graph from lock information."""
        nodes = list(locks.keys())
        edges = []

        for schema, lock_info in locks.items():
            for dependency in lock_info.dependencies:
                if dependency in locks:
                    edges.append((schema, dependency))

        return DependencyGraph(nodes=nodes, edges=edges)

    def _detect_cycles(self, graph: DependencyGraph) -> List[List[str]]:
        """Detect cycles in dependency graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node, path):
            if node in rec_stack:
                # Found cycle - don't include the duplicate node at the end
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)

            # Find outgoing edges
            for edge in graph.edges:
                if edge[0] == node:
                    dfs(edge[1], path + [node])

            rec_stack.remove(node)

        for node in graph.nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    def _get_current_locks(self) -> Dict[str, LockInfo]:
        """Get current locks (placeholder implementation)."""
        return self._current_locks


class AtomicMigrationExecutor:
    """
    Atomic migration execution with rollback capabilities.

    Executes migration operations atomically with complete rollback
    support and validation.
    """

    def __init__(self, connection_manager):
        """
        Initialize atomic migration executor.

        Args:
            connection_manager: Database connection manager
        """
        self.connection_manager = connection_manager

    async def execute_atomic_migration(
        self, operations: List[MigrationOperation]
    ) -> MigrationResult:
        """
        Execute migration operations atomically with rollback.

        Args:
            operations: List of migration operations

        Returns:
            Migration result with success status and details
        """
        start_time = time.perf_counter()
        operations_completed = 0
        rollback_executed = False

        try:
            # Begin transaction
            await self.connection_manager.begin_transaction()

            # Execute each operation
            for i, operation in enumerate(operations):
                try:
                    await self.connection_manager.execute_query(operation.sql)
                    operations_completed += 1
                    logger.debug(
                        f"Completed operation {i+1}/{len(operations)}: {operation.type}"
                    )

                except Exception as op_error:
                    logger.error(f"Operation {i+1} failed: {op_error}")
                    # Rollback transaction
                    await self.connection_manager.rollback_transaction()
                    rollback_executed = True

                    end_time = time.perf_counter()
                    execution_time_ms = int((end_time - start_time) * 1000)

                    return MigrationResult(
                        success=False,
                        queue_id="",  # Will be set by caller
                        operations_completed=operations_completed,
                        rollback_executed=rollback_executed,
                        error_message=str(op_error),
                        execution_time_ms=execution_time_ms,
                    )

            # Commit transaction if all operations succeeded
            await self.connection_manager.commit_transaction()

            end_time = time.perf_counter()
            execution_time_ms = int((end_time - start_time) * 1000)

            return MigrationResult(
                success=True,
                queue_id="",  # Will be set by caller
                operations_completed=operations_completed,
                rollback_executed=rollback_executed,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            # Attempt rollback on any error
            try:
                await self.connection_manager.rollback_transaction()
                rollback_executed = True
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")

            end_time = time.perf_counter()
            execution_time_ms = int((end_time - start_time) * 1000)

            return MigrationResult(
                success=False,
                queue_id="",
                operations_completed=operations_completed,
                rollback_executed=rollback_executed,
                error_message=str(e),
                execution_time_ms=execution_time_ms,
            )

    def validate_migration_atomicity(
        self, operations: List[MigrationOperation]
    ) -> AtomicityAssessment:
        """
        Assess if operations can be executed atomically.

        Args:
            operations: List of operations to assess

        Returns:
            Atomicity assessment with risk level and warnings
        """
        warnings = []
        risk_level = "LOW"
        is_atomic = True
        estimated_duration_ms = 0

        # Analyze each operation
        for operation in operations:
            op_type = operation.type
            estimated_duration_ms += self._estimate_operation_duration(op_type)

            if op_type == "DROP_TABLE":
                warnings.append("DROP_TABLE operation has high data loss risk")
                risk_level = "HIGH"

            elif op_type == "DROP_COLUMN":
                warnings.append("DROP_COLUMN operation causes irreversible data loss")
                risk_level = "HIGH"

            elif op_type == "MODIFY_COLUMN":
                warnings.append("MODIFY_COLUMN operation may cause data loss")
                if risk_level == "LOW":
                    risk_level = "MEDIUM"

        # Check for operations that break atomicity
        dangerous_operations = ["DROP_TABLE", "TRUNCATE_TABLE"]
        if any(op.type in dangerous_operations for op in operations):
            is_atomic = False

        return AtomicityAssessment(
            is_atomic=is_atomic,
            risk_level=risk_level,
            warnings=warnings,
            estimated_duration_ms=estimated_duration_ms,
        )

    def prepare_rollback_plan(
        self, operations: List[MigrationOperation]
    ) -> RollbackPlan:
        """
        Generate comprehensive rollback plan before execution.

        Args:
            operations: List of operations to prepare rollback for

        Returns:
            Complete rollback plan with steps and risk assessment
        """
        steps = []
        fully_reversible = True
        data_loss_warning = None
        irreversible_operations = []
        estimated_total_duration_ms = 0

        # Process operations in reverse order for rollback
        for operation in reversed(operations):
            rollback_sql = operation.rollback_sql

            if not rollback_sql or rollback_sql.startswith("-- Cannot"):
                # Operation is not reversible - still add to steps but mark as irreversible
                fully_reversible = False
                irreversible_operations.append(
                    f"{operation.type} on {operation.table_name}"
                )

                # Add a placeholder step for tracking
                step = RollbackStep(
                    operation_type=operation.type,
                    sql=rollback_sql or "-- No rollback available",
                    estimated_duration_ms=0,
                    risk_level="HIGH",
                )
                steps.append(step)

                # Set data loss warning for irreversible operations
                if not data_loss_warning:
                    data_loss_warning = "Rollback may result in data loss"

                continue

            # Estimate rollback duration and risk
            duration = self._estimate_operation_duration(operation.type)
            risk = self._assess_rollback_risk(operation.type)

            estimated_total_duration_ms += duration

            step = RollbackStep(
                operation_type=operation.type,
                sql=rollback_sql,
                estimated_duration_ms=duration,
                risk_level=risk,
            )
            steps.append(step)

            # Check for data loss warnings - only for HIGH risk operations
            if risk == "HIGH" and not data_loss_warning:
                data_loss_warning = "Rollback may result in data loss"

        return RollbackPlan(
            steps=steps,
            fully_reversible=fully_reversible,
            data_loss_warning=data_loss_warning,
            irreversible_operations=irreversible_operations,
            estimated_total_duration_ms=estimated_total_duration_ms,
        )

    async def execute_rollback_plan(self, rollback_plan: RollbackPlan) -> bool:
        """
        Execute a prepared rollback plan.

        Args:
            rollback_plan: Rollback plan to execute

        Returns:
            True if rollback successful, False otherwise
        """
        try:
            await self.connection_manager.begin_transaction()

            for step in rollback_plan.steps:
                await self.connection_manager.execute_query(step.sql)
                logger.debug(f"Executed rollback step: {step.operation_type}")

            await self.connection_manager.commit_transaction()
            logger.info("Rollback plan executed successfully")
            return True

        except Exception as e:
            logger.error(f"Rollback plan execution failed: {e}")
            try:
                await self.connection_manager.rollback_transaction()
            except Exception as rollback_error:
                logger.error(
                    f"Failed to rollback rollback transaction: {rollback_error}"
                )
            return False

    def _estimate_operation_duration(self, operation_type: str) -> int:
        """Estimate operation duration in milliseconds."""
        duration_estimates = {
            "CREATE_TABLE": 100,
            "DROP_TABLE": 500,
            "ADD_COLUMN": 200,
            "DROP_COLUMN": 300,
            "MODIFY_COLUMN": 400,
            "CREATE_INDEX": 1000,
            "DROP_INDEX": 200,
        }
        return duration_estimates.get(operation_type, 250)

    def _assess_rollback_risk(self, operation_type: str) -> str:
        """Assess risk level of rollback operation."""
        risk_levels = {
            "CREATE_INDEX": "LOW",
            "DROP_INDEX": "LOW",
            "CREATE_TABLE": "LOW",
            "ADD_COLUMN": "MEDIUM",  # Rollback drops column, losing data
            "MODIFY_COLUMN": "MEDIUM",
            "DROP_COLUMN": "HIGH",  # Cannot recover dropped data
            "DROP_TABLE": "HIGH",  # Cannot recover dropped table
        }
        return risk_levels.get(operation_type, "MEDIUM")
