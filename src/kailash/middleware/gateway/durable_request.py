"""Durable request implementation with state machine and checkpointing.

This module provides request durability through:
- State machine for request lifecycle
- Automatic checkpointing at key points
- Execution journal for audit trail
- Resumable execution after failures
"""

import asyncio
import datetime as dt
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Import will be added when checkpoint_manager is implemented
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from kailash.runtime import LocalRuntime

if TYPE_CHECKING:
    from .checkpoint_manager import CheckpointManager

from kailash.sdk_exceptions import NodeExecutionError
from kailash.workflow import Workflow, WorkflowBuilder

logger = logging.getLogger(__name__)


class RequestState(Enum):
    """Request lifecycle states."""

    INITIALIZED = "initialized"
    VALIDATED = "validated"
    WORKFLOW_CREATED = "workflow_created"
    EXECUTING = "executing"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RESUMING = "resuming"


@dataclass
class RequestMetadata:
    """Metadata for durable request."""

    request_id: str
    method: str
    path: str
    headers: Dict[str, str]
    query_params: Dict[str, str]
    body: Optional[Dict[str, Any]]
    client_ip: str
    user_id: Optional[str]
    tenant_id: Optional[str]
    idempotency_key: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass
class Checkpoint:
    """Checkpoint data structure."""

    checkpoint_id: str
    request_id: str
    sequence: int
    name: str
    state: RequestState
    data: Dict[str, Any]
    workflow_state: Optional[Dict[str, Any]]
    created_at: datetime
    size_bytes: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "request_id": self.request_id,
            "sequence": self.sequence,
            "name": self.name,
            "state": self.state.value,
            "data": self.data,
            "workflow_state": self.workflow_state,
            "created_at": self.created_at.isoformat(),
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Checkpoint":
        """Create from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            request_id=data["request_id"],
            sequence=data["sequence"],
            name=data["name"],
            state=RequestState(data["state"]),
            data=data["data"],
            workflow_state=data.get("workflow_state"),
            created_at=datetime.fromisoformat(data["created_at"]),
            size_bytes=data["size_bytes"],
        )


@dataclass
class ExecutionJournal:
    """Journal of all execution events."""

    request_id: str
    events: List[Dict[str, Any]] = field(default_factory=list)

    async def record(self, event_type: str, data: Dict[str, Any]):
        """Record an execution event."""
        event = {
            "timestamp": datetime.now(dt.UTC).isoformat(),
            "type": event_type,
            "data": data,
            "sequence": len(self.events),
        }
        self.events.append(event)
        logger.debug(f"Recorded event {event_type} for request {self.request_id}")

    def get_events(self, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get events, optionally filtered by type."""
        if event_type:
            return [e for e in self.events if e["type"] == event_type]
        return self.events


class DurableRequest:
    """Durable request with automatic checkpointing and resumability."""

    def __init__(
        self,
        request_id: Optional[str] = None,
        metadata: Optional[RequestMetadata] = None,
        checkpoint_manager: Optional["CheckpointManager"] = None,
    ):
        """Initialize durable request."""
        self.id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        self.metadata = metadata or self._create_default_metadata()
        self.state = RequestState.INITIALIZED
        self.checkpoints: List[Checkpoint] = []
        self.journal = ExecutionJournal(self.id)
        self.checkpoint_manager = checkpoint_manager

        # Execution state
        self.workflow: Optional[Workflow] = None
        self.workflow_id: Optional[str] = None
        self.runtime: Optional[LocalRuntime] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[Exception] = None

        # Timing
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.checkpoint_count = 0

        # Cancellation support
        self._cancel_event = asyncio.Event()

    def _create_default_metadata(self) -> RequestMetadata:
        """Create default metadata."""
        now = datetime.now(dt.UTC)
        return RequestMetadata(
            request_id=self.id,
            method="POST",
            path="/api/workflow",
            headers={},
            query_params={},
            body=None,
            client_ip="0.0.0.0",
            user_id=None,
            tenant_id=None,
            idempotency_key=None,
            created_at=now,
            updated_at=now,
        )

    async def execute(self) -> Dict[str, Any]:
        """Execute request with automatic checkpointing."""
        try:
            self.start_time = time.time()
            await self.journal.record(
                "request_started",
                {
                    "request_id": self.id,
                    "state": self.state.value,
                },
            )

            # Validate request
            await self._validate_request()

            # Create workflow
            await self._create_workflow()

            # Execute with checkpoints
            result = await self._execute_workflow()

            # Mark complete
            self.state = RequestState.COMPLETED
            self.end_time = time.time()
            self.result = result

            await self.journal.record(
                "request_completed",
                {
                    "request_id": self.id,
                    "duration_ms": (self.end_time - self.start_time) * 1000,
                    "checkpoint_count": self.checkpoint_count,
                },
            )

            return {
                "request_id": self.id,
                "status": "completed",
                "result": result,
                "duration_ms": (self.end_time - self.start_time) * 1000,
                "checkpoints": self.checkpoint_count,
            }

        except asyncio.CancelledError:
            await self._handle_cancellation()
            raise

        except Exception as e:
            await self._handle_error(e)
            raise

    async def resume(self, checkpoint_id: Optional[str] = None) -> Dict[str, Any]:
        """Resume execution from checkpoint."""
        self.state = RequestState.RESUMING
        await self.journal.record(
            "request_resuming",
            {
                "request_id": self.id,
                "checkpoint_id": checkpoint_id,
            },
        )

        try:
            # Restore from checkpoint
            if checkpoint_id:
                checkpoint = await self._restore_checkpoint(checkpoint_id)
            else:
                # Use latest checkpoint
                checkpoint = await self._restore_latest_checkpoint()

            if not checkpoint:
                raise ValueError("No checkpoint found to resume from")

            # Restore state
            self.state = checkpoint.state
            if checkpoint.workflow_state:
                await self._restore_workflow_state(checkpoint.workflow_state)

            # Continue execution
            return await self.execute()

        except Exception as e:
            await self._handle_error(e)
            raise

    async def cancel(self):
        """Cancel the request execution."""
        self._cancel_event.set()
        self.state = RequestState.CANCELLED
        await self.journal.record(
            "request_cancelled",
            {
                "request_id": self.id,
            },
        )

        if self.workflow and self.runtime:
            # TODO: Implement workflow cancellation
            pass

    async def checkpoint(self, name: str, data: Dict[str, Any] = None) -> str:
        """Create a checkpoint."""
        if self._cancel_event.is_set():
            raise asyncio.CancelledError("Request was cancelled")

        checkpoint = Checkpoint(
            checkpoint_id=f"ckpt_{uuid.uuid4().hex[:12]}",
            request_id=self.id,
            sequence=self.checkpoint_count,
            name=name,
            state=self.state,
            data=data or {},
            workflow_state=(
                await self._capture_workflow_state() if self.workflow else None
            ),
            created_at=datetime.now(dt.UTC),
            size_bytes=len(json.dumps(data or {})),
        )

        self.checkpoints.append(checkpoint)
        self.checkpoint_count += 1

        # Save to checkpoint manager if available
        if self.checkpoint_manager:
            await self.checkpoint_manager.save_checkpoint(checkpoint)

        await self.journal.record(
            "checkpoint_created",
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "name": name,
                "sequence": checkpoint.sequence,
            },
        )

        logger.info(f"Created checkpoint {name} for request {self.id}")
        return checkpoint.checkpoint_id

    async def _validate_request(self):
        """Validate the request."""
        self.state = RequestState.VALIDATED
        await self.checkpoint(
            "request_validated",
            {
                "metadata": {
                    "method": self.metadata.method,
                    "path": self.metadata.path,
                    "idempotency_key": self.metadata.idempotency_key,
                }
            },
        )

    async def _create_workflow(self):
        """Create workflow from request."""
        # This is a simplified example - in practice, this would
        # parse the request and create appropriate workflow
        if not self.metadata.body:
            raise ValueError("Request body required for workflow creation")

        workflow_config = self.metadata.body.get("workflow", {})

        # Create workflow based on configuration
        self.workflow = Workflow(
            workflow_id=f"wf_{self.id}",
            name=workflow_config.get("name", "DurableWorkflow"),
        )

        # TODO: Add nodes based on workflow config
        # This would parse the request and build the workflow

        self.workflow_id = self.workflow.workflow_id
        self.state = RequestState.WORKFLOW_CREATED

        await self.checkpoint(
            "workflow_created",
            {
                "workflow_id": self.workflow_id,
                "node_count": len(self.workflow.nodes),
            },
        )

    async def _execute_workflow(self) -> Dict[str, Any]:
        """Execute workflow with checkpointing."""
        self.state = RequestState.EXECUTING
        self.runtime = LocalRuntime()

        # Execute workflow
        # TODO: Implement checkpoint-aware execution
        # For now, standard execution
        result, run_id = await self.runtime.execute(self.workflow)

        # Checkpoint final result
        await self.checkpoint(
            "workflow_completed",
            {
                "run_id": run_id,
                "result": result,
            },
        )

        return result

    async def _capture_workflow_state(self) -> Dict[str, Any]:
        """Capture current workflow state."""
        if not self.workflow:
            return {}

        # TODO: Implement workflow state capture
        # This would include:
        # - Completed nodes
        # - Node outputs
        # - Workflow variables
        # - Execution context

        return {
            "workflow_id": self.workflow_id,
            "completed_nodes": [],
            "node_outputs": {},
        }

    async def _restore_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Restore from specific checkpoint."""
        if self.checkpoint_manager:
            return await self.checkpoint_manager.load_checkpoint(checkpoint_id)

        # Search in memory
        for ckpt in self.checkpoints:
            if ckpt.checkpoint_id == checkpoint_id:
                return ckpt

        return None

    async def _restore_latest_checkpoint(self) -> Optional[Checkpoint]:
        """Restore from latest checkpoint."""
        if self.checkpoint_manager:
            return await self.checkpoint_manager.load_latest_checkpoint(self.id)

        # Use in-memory checkpoint
        return self.checkpoints[-1] if self.checkpoints else None

    async def _restore_workflow_state(self, workflow_state: Dict[str, Any]):
        """Restore workflow state from checkpoint."""
        # TODO: Implement workflow state restoration
        # This would restore:
        # - Node execution state
        # - Intermediate results
        # - Workflow variables
        pass

    async def _handle_cancellation(self):
        """Handle request cancellation."""
        self.state = RequestState.CANCELLED
        self.end_time = time.time()

        await self.checkpoint(
            "request_cancelled",
            {
                "duration_ms": (
                    (self.end_time - self.start_time) * 1000 if self.start_time else 0
                ),
            },
        )

        await self.journal.record(
            "request_cancelled",
            {
                "request_id": self.id,
                "checkpoints_created": self.checkpoint_count,
            },
        )

    async def _handle_error(self, error: Exception):
        """Handle execution error."""
        self.state = RequestState.FAILED
        self.end_time = time.time()
        self.error = error

        await self.checkpoint(
            "request_failed",
            {
                "error": str(error),
                "error_type": type(error).__name__,
            },
        )

        await self.journal.record(
            "request_failed",
            {
                "request_id": self.id,
                "error": str(error),
                "error_type": type(error).__name__,
                "duration_ms": (
                    (self.end_time - self.start_time) * 1000 if self.start_time else 0
                ),
            },
        )

        logger.error(f"Request {self.id} failed: {error}")

    def get_status(self) -> Dict[str, Any]:
        """Get current request status."""
        return {
            "request_id": self.id,
            "state": self.state.value,
            "checkpoints": self.checkpoint_count,
            "events": len(self.journal.events),
            "duration_ms": (
                (self.end_time - self.start_time) * 1000
                if self.start_time and self.end_time
                else None
            ),
            "result": self.result,
            "error": str(self.error) if self.error else None,
        }
