#!/usr/bin/env python3
"""
Rename Transaction Manager - TODO-139 Phase 2 Component

Transaction coordination and rollback management for complex rename operations.
Provides atomic operation execution with comprehensive rollback capabilities.

CRITICAL REQUIREMENTS:
- Multi-step transaction coordination with savepoints
- Comprehensive rollback capabilities for partial failures
- Atomic execution of complex rename workflows
- Transaction state tracking and management
- Savepoint management for granular rollback control

Core transaction capabilities:
- Transaction Coordination (CRITICAL - ensure atomicity)
- Savepoint Management (HIGH - granular rollback control)
- Rollback Operations (CRITICAL - recovery from failures)
- State Tracking (MEDIUM - monitor transaction progress)
- Error Handling (HIGH - graceful failure management)
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import asyncpg

logger = logging.getLogger(__name__)


class TransactionState(Enum):
    """States of transaction execution."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class SavepointManager:
    """Manages savepoints within a transaction."""

    active_savepoints: List[str] = field(default_factory=list)
    savepoint_counter: int = 0

    def generate_savepoint_name(self, prefix: str = "sp") -> str:
        """Generate a unique savepoint name."""
        self.savepoint_counter += 1
        return f"{prefix}_{self.savepoint_counter}_{uuid.uuid4().hex[:6]}"

    def add_savepoint(self, name: str):
        """Add savepoint to active list."""
        if name not in self.active_savepoints:
            self.active_savepoints.append(name)

    def remove_savepoint(self, name: str):
        """Remove savepoint from active list."""
        if name in self.active_savepoints:
            self.active_savepoints.remove(name)

    def get_latest_savepoint(self) -> Optional[str]:
        """Get the most recently created savepoint."""
        return self.active_savepoints[-1] if self.active_savepoints else None


@dataclass
class RollbackResult:
    """Result of rollback operation."""

    success: bool
    rolled_back_operations: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    rollback_duration: float = 0.0


@dataclass
class TransactionStep:
    """Represents a single step in a transaction."""

    step_id: str
    sql_command: str
    rollback_command: Optional[str] = None
    savepoint_before: Optional[str] = None
    completed: bool = False
    execution_time: float = 0.0


class TransactionError(Exception):
    """Raised when transaction operations fail."""

    pass


class RenameTransactionManager:
    """
    Transaction Manager for rename operations with comprehensive rollback.

    Coordinates multi-step transactions with savepoint management and
    rollback capabilities for complex rename workflows.
    """

    def __init__(self, connection: asyncpg.Connection):
        """Initialize transaction manager with database connection."""
        if connection is None:
            raise ValueError("Database connection is required")

        self.connection = connection
        self.current_state = TransactionState.NOT_STARTED
        self.transaction_id: Optional[str] = None
        self.savepoint_manager = SavepointManager()
        self.executed_steps: List[TransactionStep] = []
        self.transaction_start_time: Optional[float] = None
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def active_savepoints(self) -> List[str]:
        """Get list of active savepoints."""
        return self.savepoint_manager.active_savepoints

    async def begin_transaction(self) -> str:
        """
        Begin a new database transaction.

        Returns:
            Transaction ID
        """
        if self.current_state != TransactionState.NOT_STARTED:
            raise TransactionError(
                f"Transaction already started with state: {self.current_state}"
            )

        try:
            self.transaction_start_time = time.time()
            self.transaction_id = f"rename_txn_{uuid.uuid4().hex[:8]}"

            await self.connection.execute("BEGIN")
            self.current_state = TransactionState.ACTIVE

            self.logger.info(f"Transaction started: {self.transaction_id}")
            return self.transaction_id

        except Exception as e:
            self.logger.error(f"Failed to begin transaction: {e}")
            self.current_state = TransactionState.FAILED
            raise TransactionError(f"Failed to begin transaction: {str(e)}")

    async def create_savepoint(self, name: Optional[str] = None) -> str:
        """
        Create a savepoint within the current transaction.

        Args:
            name: Optional savepoint name (auto-generated if None)

        Returns:
            Savepoint name
        """
        if self.current_state != TransactionState.ACTIVE:
            raise TransactionError(
                f"Cannot create savepoint - transaction state: {self.current_state}"
            )

        try:
            if name is None:
                name = self.savepoint_manager.generate_savepoint_name("rename_sp")

            await self.connection.execute(f"SAVEPOINT {name}")
            self.savepoint_manager.add_savepoint(name)

            self.logger.debug(f"Savepoint created: {name}")
            return name

        except Exception as e:
            self.logger.error(f"Failed to create savepoint {name}: {e}")
            raise TransactionError(f"Failed to create savepoint: {str(e)}")

    async def rollback_to_savepoint(self, savepoint_name: str) -> RollbackResult:
        """
        Rollback to a specific savepoint.

        Args:
            savepoint_name: Name of savepoint to rollback to

        Returns:
            RollbackResult with operation details
        """
        if self.current_state != TransactionState.ACTIVE:
            raise TransactionError(
                f"Cannot rollback - transaction state: {self.current_state}"
            )

        if savepoint_name not in self.active_savepoints:
            raise TransactionError(f"Savepoint {savepoint_name} not found")

        start_time = time.time()
        rolled_back_operations = []

        try:
            await self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            rolled_back_operations.append(f"ROLLBACK TO SAVEPOINT {savepoint_name}")

            # Remove savepoints created after this one
            savepoint_index = self.active_savepoints.index(savepoint_name)
            removed_savepoints = self.active_savepoints[savepoint_index + 1 :]

            for sp in removed_savepoints:
                self.savepoint_manager.remove_savepoint(sp)
                rolled_back_operations.append(f"Removed savepoint {sp}")

            # Mark steps as not completed if they were executed after this savepoint
            for step in reversed(self.executed_steps):
                if step.savepoint_before == savepoint_name:
                    break
                if step.completed:
                    step.completed = False
                    rolled_back_operations.append(f"Reverted step {step.step_id}")

            rollback_duration = time.time() - start_time

            self.logger.info(
                f"Rolled back to savepoint {savepoint_name} ({rollback_duration:.3f}s)"
            )

            return RollbackResult(
                success=True,
                rolled_back_operations=rolled_back_operations,
                rollback_duration=rollback_duration,
            )

        except Exception as e:
            self.logger.error(f"Failed to rollback to savepoint {savepoint_name}: {e}")
            return RollbackResult(
                success=False,
                error_message=str(e),
                rollback_duration=time.time() - start_time,
            )

    async def commit_transaction(self) -> RollbackResult:
        """
        Commit the current transaction.

        Returns:
            RollbackResult indicating success/failure
        """
        if self.current_state != TransactionState.ACTIVE:
            raise TransactionError(
                f"Cannot commit - transaction state: {self.current_state}"
            )

        try:
            await self.connection.execute("COMMIT")
            self.current_state = TransactionState.COMMITTED

            transaction_duration = time.time() - (self.transaction_start_time or 0)

            self.logger.info(
                f"Transaction committed: {self.transaction_id} "
                f"({transaction_duration:.3f}s, {len(self.executed_steps)} steps)"
            )

            return RollbackResult(
                success=True, rolled_back_operations=[], rollback_duration=0.0
            )

        except Exception as e:
            self.logger.error(f"Failed to commit transaction: {e}")
            self.current_state = TransactionState.FAILED
            raise TransactionError(f"Failed to commit transaction: {str(e)}")

    async def rollback_transaction(self) -> RollbackResult:
        """
        Rollback the entire transaction.

        Returns:
            RollbackResult with rollback details
        """
        if self.current_state not in [TransactionState.ACTIVE, TransactionState.FAILED]:
            self.logger.warning(f"Attempting rollback with state: {self.current_state}")

        start_time = time.time()
        rolled_back_operations = []

        try:
            await self.connection.execute("ROLLBACK")
            self.current_state = TransactionState.ROLLED_BACK

            # Track all operations that were rolled back
            for step in self.executed_steps:
                if step.completed:
                    rolled_back_operations.append(f"Reverted step {step.step_id}")
                    step.completed = False

            # Clear all savepoints
            for savepoint in self.active_savepoints:
                rolled_back_operations.append(f"Removed savepoint {savepoint}")
            self.savepoint_manager.active_savepoints.clear()

            rollback_duration = time.time() - start_time

            self.logger.info(
                f"Transaction rolled back: {self.transaction_id} "
                f"({rollback_duration:.3f}s, {len(rolled_back_operations)} operations)"
            )

            return RollbackResult(
                success=True,
                rolled_back_operations=rolled_back_operations,
                rollback_duration=rollback_duration,
            )

        except Exception as e:
            self.logger.error(f"Failed to rollback transaction: {e}")
            return RollbackResult(
                success=False,
                error_message=str(e),
                rollback_duration=time.time() - start_time,
            )

    async def execute_step(self, step: Any) -> RollbackResult:
        """
        Execute a workflow step with automatic savepoint management.

        Args:
            step: Workflow step to execute

        Returns:
            RollbackResult indicating success/failure
        """
        if self.current_state != TransactionState.ACTIVE:
            raise TransactionError(
                f"Cannot execute step - transaction state: {self.current_state}"
            )

        step_start_time = time.time()

        # Create savepoint before executing step
        savepoint_name = await self.create_savepoint(
            f"before_{getattr(step, 'step_id', 'unknown')}"
        )

        transaction_step = TransactionStep(
            step_id=getattr(step, "step_id", f"step_{len(self.executed_steps)}"),
            sql_command=getattr(step, "sql_command", ""),
            rollback_command=getattr(step, "rollback_command", None),
            savepoint_before=savepoint_name,
        )

        try:
            # Execute the SQL command
            if transaction_step.sql_command:
                await self.connection.execute(transaction_step.sql_command)

            transaction_step.completed = True
            transaction_step.execution_time = time.time() - step_start_time
            self.executed_steps.append(transaction_step)

            self.logger.debug(
                f"Step executed successfully: {transaction_step.step_id} "
                f"({transaction_step.execution_time:.3f}s)"
            )

            return RollbackResult(
                success=True, rolled_back_operations=[], rollback_duration=0.0
            )

        except Exception as e:
            self.logger.error(
                f"Step execution failed: {transaction_step.step_id} - {e}"
            )

            # Rollback to savepoint created before this step
            rollback_result = await self.rollback_to_savepoint(savepoint_name)

            # Add the failed step to executed steps for tracking
            transaction_step.completed = False
            transaction_step.execution_time = time.time() - step_start_time
            self.executed_steps.append(transaction_step)

            return RollbackResult(
                success=False,
                error_message=str(e),
                rolled_back_operations=rollback_result.rolled_back_operations,
                rollback_duration=rollback_result.rollback_duration,
            )

    def get_transaction_state(self) -> Dict[str, Any]:
        """
        Get current transaction state information.

        Returns:
            Dictionary with transaction state details
        """
        return {
            "transaction_id": self.transaction_id,
            "current_state": self.current_state,
            "active_savepoints": self.active_savepoints,
            "executed_steps_count": len(self.executed_steps),
            "completed_steps_count": sum(
                1 for step in self.executed_steps if step.completed
            ),
            "transaction_duration": (
                time.time() - self.transaction_start_time
                if self.transaction_start_time
                else 0.0
            ),
        }

    def cleanup(self):
        """Clean up transaction manager state."""
        self.executed_steps.clear()
        self.savepoint_manager.active_savepoints.clear()
        self.savepoint_manager.savepoint_counter = 0
        self.current_state = TransactionState.NOT_STARTED
        self.transaction_id = None
        self.transaction_start_time = None

        self.logger.debug("Transaction manager state cleaned up")
