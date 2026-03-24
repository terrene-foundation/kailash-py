"""Durable request with state machine, checkpointing, and resumable execution.

This module provides :class:`DurableRequest` -- a request wrapper that
persists execution progress via :class:`Checkpoint` objects and can be
resumed from the last checkpoint after a failure or cancellation.

Key capabilities:
- State machine governing the request lifecycle (INITIALIZED through
  COMPLETED / FAILED / CANCELLED)
- Automatic checkpointing at validation, workflow creation, and
  workflow completion boundaries
- :class:`ExecutionJournal` for a full audit trail of events
- Resumable execution: on resume the :class:`ExecutionTracker` replays
  cached node outputs so already-completed nodes are skipped
- Workflow construction from a JSON request body via
  :class:`~kailash.workflow.builder.WorkflowBuilder`
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
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.execution_tracker import ExecutionTracker

if TYPE_CHECKING:
    from .checkpoint_manager import CheckpointManager

from kailash.sdk_exceptions import NodeExecutionError, WorkflowCancelledError
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
        runtime: Optional[LocalRuntime] = None,
    ):
        """Initialize durable request.

        Args:
            request_id: Optional request identifier.
            metadata: Optional request metadata.
            checkpoint_manager: Optional checkpoint manager.
            runtime: Optional shared runtime. If provided, its ref count is
                incremented via acquire(). If None a new LocalRuntime is
                created lazily in _execute_workflow().
        """
        self.id = request_id or f"req_{uuid.uuid4().hex[:12]}"
        self.metadata = metadata or self._create_default_metadata()
        self.state = RequestState.INITIALIZED
        self.checkpoints: List[Checkpoint] = []
        self.journal = ExecutionJournal(self.id)
        self.checkpoint_manager = checkpoint_manager

        # Execution state
        self.workflow: Optional[Workflow] = None
        self.workflow_id: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[Exception] = None

        # Runtime injection
        if runtime is not None:
            self._injected_runtime = runtime.acquire()
            self._owns_runtime = False
        else:
            self._injected_runtime = None
            self._owns_runtime = True
        self.runtime: Optional[LocalRuntime] = None

        # Timing
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.checkpoint_count = 0

        # Cancellation support
        self._cancel_event = asyncio.Event()
        self._cancellation_token = CancellationToken()
        self._execution_task: Optional[asyncio.Task] = None

        # Checkpoint/restore execution tracker
        self._execution_tracker: ExecutionTracker = ExecutionTracker()

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
        # Store current task so cancel() can await/force-cancel it
        try:
            self._execution_task = asyncio.current_task()
        except RuntimeError:
            self._execution_task = None

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

        except WorkflowCancelledError:
            await self._handle_cancellation()
            raise

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

    async def cancel(
        self, reason: str = "User requested cancellation", timeout: float = 30.0
    ):
        """Cancel the request execution.

        Signals the cancellation token so the runtime stops between nodes,
        then optionally force-cancels the execution task if it does not
        stop within the grace period.

        Args:
            reason: Human-readable reason for cancellation.
            timeout: Seconds to wait for graceful stop before force-cancelling
                the asyncio task. Defaults to 30 seconds.
        """
        self._cancel_event.set()
        self._cancellation_token.cancel(reason=reason)
        self.state = RequestState.CANCELLED
        await self.journal.record(
            "request_cancelled",
            {
                "request_id": self.id,
                "reason": reason,
            },
        )

        if self.workflow and self.runtime and self._execution_task is not None:
            # Wait for the current node to finish (grace period)
            if not self._execution_task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(self._execution_task),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    # Grace period expired -- force-cancel the task
                    self._execution_task.cancel()
                    try:
                        await self._execution_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    await self.journal.record(
                        "request_force_cancelled",
                        {
                            "request_id": self.id,
                            "reason": f"Force-cancelled after {timeout}s timeout",
                        },
                    )
                except (asyncio.CancelledError, WorkflowCancelledError):
                    # Expected -- workflow stopped cooperatively
                    pass
                except Exception:
                    # Unexpected error during wait; already cancelled
                    pass

            await self.journal.record(
                "cancellation_complete",
                {
                    "request_id": self.id,
                    "completed_nodes": getattr(self, "_completed_nodes", []),
                },
            )

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
        """Create workflow from request body configuration.

        Parses the ``workflow`` key from the request body and constructs a
        :class:`~kailash.workflow.graph.Workflow` via :class:`WorkflowBuilder`.

        Expected schema::

            {
                "workflow": {
                    "name": "MyWorkflow",
                    "nodes": [
                        {"type": "NodeType", "id": "node_id", "params": {...}}
                    ],
                    "connections": [
                        {"from": "src_node.output", "to": "tgt_node.input"}
                    ]
                }
            }

        Connection strings use dot notation: ``"node_id.port_name"``.

        Raises:
            ValueError: If the request body is missing, the ``workflow`` key
                is absent, no nodes are defined, a node type is unrecognised,
                or a connection string is malformed.
        """
        if not self.metadata.body:
            raise ValueError("Request body required for workflow creation")

        workflow_config = self.metadata.body.get("workflow")
        if not workflow_config or not isinstance(workflow_config, dict):
            raise ValueError(
                "Request body must contain a 'workflow' key with "
                "name, nodes, and connections"
            )

        nodes = workflow_config.get("nodes")
        if not nodes or not isinstance(nodes, list):
            raise ValueError("Workflow config must contain a non-empty 'nodes' list")

        builder = WorkflowBuilder()

        # ------------------------------------------------------------------
        # Add nodes
        # ------------------------------------------------------------------
        for idx, node_spec in enumerate(nodes):
            if not isinstance(node_spec, dict):
                raise ValueError(
                    f"Node at index {idx} must be a dict with "
                    "'type', 'id', and optional 'params'"
                )

            node_type = node_spec.get("type")
            node_id = node_spec.get("id")

            if not node_type:
                raise ValueError(f"Node at index {idx} is missing 'type'")
            if not node_id:
                raise ValueError(f"Node at index {idx} is missing 'id'")

            params = node_spec.get("params") or {}
            if not isinstance(params, dict):
                raise ValueError(
                    f"Node '{node_id}' params must be a dict, "
                    f"got {type(params).__name__}"
                )

            try:
                builder.add_node(node_type, node_id, params)
            except Exception as e:
                raise ValueError(
                    f"Failed to add node '{node_id}' of type '{node_type}': {e}"
                ) from e

        # ------------------------------------------------------------------
        # Add connections
        # ------------------------------------------------------------------
        connections = workflow_config.get("connections") or []
        if not isinstance(connections, list):
            raise ValueError("Workflow 'connections' must be a list")

        for idx, conn in enumerate(connections):
            if not isinstance(conn, dict):
                raise ValueError(
                    f"Connection at index {idx} must be a dict "
                    "with 'from' and 'to' keys"
                )

            from_str = conn.get("from", "")
            to_str = conn.get("to", "")

            if "." not in from_str:
                raise ValueError(
                    f"Connection at index {idx}: 'from' must use "
                    f"dot notation 'node_id.output', got '{from_str}'"
                )
            if "." not in to_str:
                raise ValueError(
                    f"Connection at index {idx}: 'to' must use "
                    f"dot notation 'node_id.input', got '{to_str}'"
                )

            src_node, src_output = from_str.split(".", 1)
            tgt_node, tgt_input = to_str.split(".", 1)

            try:
                builder.add_connection(src_node, src_output, tgt_node, tgt_input)
            except Exception as e:
                raise ValueError(
                    f"Failed to add connection {from_str} -> {to_str}: {e}"
                ) from e

        # ------------------------------------------------------------------
        # Build the Workflow and store it
        # ------------------------------------------------------------------
        workflow_name = workflow_config.get("name", "DurableWorkflow")
        self.workflow = builder.build(
            workflow_id=f"wf_{self.id}",
            name=workflow_name,
        )

        self.workflow_id = self.workflow.workflow_id
        self.state = RequestState.WORKFLOW_CREATED

        await self.checkpoint(
            "workflow_created",
            {
                "workflow_id": self.workflow_id,
                "node_count": len(self.workflow.nodes),
            },
        )

    def close(self) -> None:
        """Release runtime reference acquired during construction."""
        if hasattr(self, "_injected_runtime") and self._injected_runtime is not None:
            self._injected_runtime.release()
            self._injected_runtime = None
        if hasattr(self, "runtime") and self.runtime is not None:
            # Only close runtime we created ourselves
            if self._owns_runtime:
                self.runtime.close()
            self.runtime = None

    async def _execute_workflow(self) -> Dict[str, Any]:
        """Execute workflow with checkpointing, cancellation, and resume support."""
        self.state = RequestState.EXECUTING
        if self._injected_runtime is not None:
            self.runtime = self._injected_runtime
        else:
            self.runtime = LocalRuntime()

        # Execute workflow with cancellation token and execution tracker.
        # The tracker enables checkpoint capture and resume-from-checkpoint:
        # already-completed nodes (from a prior checkpoint) are skipped,
        # and newly completed nodes are recorded for subsequent checkpoints.
        result, run_id = await self.runtime.execute_async(
            self.workflow,
            cancellation_token=self._cancellation_token,
            execution_tracker=self._execution_tracker,
        )

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
        """Capture current workflow state from the execution tracker.

        The tracker records per-node completion and outputs as the workflow
        executes.  This method serialises the tracker state so that it can
        be stored inside a ``Checkpoint.workflow_state`` dict and later
        restored via ``_restore_workflow_state``.
        """
        if not self.workflow:
            return {}

        tracker = self._execution_tracker
        if tracker is None:
            return {
                "workflow_id": self.workflow_id,
                "completed_nodes": [],
                "node_outputs": {},
            }

        return {
            "workflow_id": self.workflow_id,
            **tracker.to_dict(),
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
        """Restore workflow state from a checkpoint.

        Rebuilds the ``ExecutionTracker`` from the serialised dict so that
        when ``_execute_workflow`` runs, the runtime skips already-completed
        nodes and replays their cached outputs.
        """
        self._execution_tracker = ExecutionTracker.from_dict(workflow_state)

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
