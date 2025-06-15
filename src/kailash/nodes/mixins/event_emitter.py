"""
Event Emitter Mixin for Nodes

Provides event emission capabilities for nodes to integrate with the
middleware layer for real-time monitoring and communication.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from kailash.middleware.events import EventStream

logger = logging.getLogger(__name__)


class EventEmitterMixin:
    """
    Mixin that adds event emission capabilities to nodes.

    This mixin allows nodes to emit events that can be consumed by the
    middleware layer for real-time monitoring, logging, and frontend updates.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_stream: Optional["EventStream"] = None
        self._session_id: Optional[str] = None
        self._workflow_id: Optional[str] = None
        self._execution_id: Optional[str] = None

    def set_event_context(
        self,
        event_stream: "EventStream",
        session_id: str = None,
        workflow_id: str = None,
        execution_id: str = None,
    ):
        """Set the event context for this node."""
        self._event_stream = event_stream
        self._session_id = session_id
        self._workflow_id = workflow_id
        self._execution_id = execution_id

    async def emit_node_started(self, inputs: Dict[str, Any] = None):
        """Emit node started event."""
        if self._event_stream:
            try:
                from kailash.middleware.events import EventType, NodeEvent

                event = NodeEvent(
                    type=EventType.NODE_STARTED,
                    workflow_id=self._workflow_id,
                    node_id=getattr(self, "name", "unknown"),
                    node_type=self.__class__.__name__,
                    node_name=getattr(self, "name", "unknown"),
                    inputs=inputs or {},
                    session_id=self._session_id,
                )

                await self._event_stream.emit(event)
            except Exception as e:
                logger.warning(f"Failed to emit node started event: {e}")

    async def emit_node_completed(
        self, outputs: Dict[str, Any] = None, execution_time_ms: float = None
    ):
        """Emit node completed event."""
        if self._event_stream:
            try:
                from kailash.middleware.events import EventType, NodeEvent

                event = NodeEvent(
                    type=EventType.NODE_COMPLETED,
                    workflow_id=self._workflow_id,
                    node_id=getattr(self, "name", "unknown"),
                    node_type=self.__class__.__name__,
                    node_name=getattr(self, "name", "unknown"),
                    outputs=outputs or {},
                    execution_time_ms=execution_time_ms,
                    session_id=self._session_id,
                )

                await self._event_stream.emit(event)
            except Exception as e:
                logger.warning(f"Failed to emit node completed event: {e}")

    async def emit_node_failed(self, error: str):
        """Emit node failed event."""
        if self._event_stream:
            try:
                from kailash.middleware.events import EventType, NodeEvent

                event = NodeEvent(
                    type=EventType.NODE_FAILED,
                    workflow_id=self._workflow_id,
                    node_id=getattr(self, "name", "unknown"),
                    node_type=self.__class__.__name__,
                    node_name=getattr(self, "name", "unknown"),
                    error=error,
                    session_id=self._session_id,
                )

                await self._event_stream.emit(event)
            except Exception as e:
                logger.warning(f"Failed to emit node failed event: {e}")

    async def emit_node_progress(self, progress_percent: float, message: str = None):
        """Emit node progress event."""
        if self._event_stream:
            try:
                from kailash.middleware.events import EventType, NodeEvent

                event = NodeEvent(
                    type=EventType.NODE_PROGRESS,
                    workflow_id=self._workflow_id,
                    node_id=getattr(self, "name", "unknown"),
                    node_type=self.__class__.__name__,
                    node_name=getattr(self, "name", "unknown"),
                    metadata={"progress_percent": progress_percent, "message": message},
                    session_id=self._session_id,
                )

                await self._event_stream.emit(event)
            except Exception as e:
                logger.warning(f"Failed to emit node progress event: {e}")

    def has_event_stream(self) -> bool:
        """Check if event stream is available."""
        return self._event_stream is not None


class EventAwareNode:
    """
    Enhanced node base class with built-in event emission.

    This class can be used as a base class for nodes that want
    automatic event emission during execution.
    """

    def __init__(self, *args, **kwargs):
        # Initialize the mixin first
        if hasattr(super(), "__init__"):
            super().__init__(*args, **kwargs)

        # Add event emission capabilities
        self._event_mixin = EventEmitterMixin()

    def set_event_context(self, *args, **kwargs):
        """Delegate to mixin."""
        self._event_mixin.set_event_context(*args, **kwargs)

    async def emit_node_started(self, *args, **kwargs):
        """Delegate to mixin."""
        await self._event_mixin.emit_node_started(*args, **kwargs)

    async def emit_node_completed(self, *args, **kwargs):
        """Delegate to mixin."""
        await self._event_mixin.emit_node_completed(*args, **kwargs)

    async def emit_node_failed(self, *args, **kwargs):
        """Delegate to mixin."""
        await self._event_mixin.emit_node_failed(*args, **kwargs)

    async def emit_node_progress(self, *args, **kwargs):
        """Delegate to mixin."""
        await self._event_mixin.emit_node_progress(*args, **kwargs)

    def has_event_stream(self) -> bool:
        """Delegate to mixin."""
        return self._event_mixin.has_event_stream()


def enable_events_for_node(node_instance, event_stream, **context):
    """
    Enable events for a node instance.

    This function can be used to add event capabilities to existing
    node instances without requiring them to inherit from EventAwareNode.

    Args:
        node_instance: The node instance to enhance
        event_stream: The event stream to use
        **context: Additional context (session_id, workflow_id, etc.)
    """
    # Add mixin to the instance
    if not hasattr(node_instance, "_event_mixin"):
        node_instance._event_mixin = EventEmitterMixin()

        # Add methods to the instance
        node_instance.set_event_context = node_instance._event_mixin.set_event_context
        node_instance.emit_node_started = node_instance._event_mixin.emit_node_started
        node_instance.emit_node_completed = (
            node_instance._event_mixin.emit_node_completed
        )
        node_instance.emit_node_failed = node_instance._event_mixin.emit_node_failed
        node_instance.emit_node_progress = node_instance._event_mixin.emit_node_progress
        node_instance.has_event_stream = node_instance._event_mixin.has_event_stream

    # Set the event context
    node_instance.set_event_context(event_stream, **context)
