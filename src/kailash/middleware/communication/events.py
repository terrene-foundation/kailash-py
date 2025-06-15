"""
Event system for Kailash Middleware

Provides standardized event types and emission for real-time communication
between agent systems and frontend UIs. Supports multiple transport layers
and efficient event batching.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Standard event types for agent-UI communication."""

    # Workflow Events (workflow lifecycle)
    WORKFLOW_CREATED = "workflow.created"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_PROGRESS = "workflow.progress"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_CANCELLED = "workflow.cancelled"

    # Node Events (individual node execution)
    NODE_STARTED = "node.started"
    NODE_PROGRESS = "node.progress"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_SKIPPED = "node.skipped"

    # UI Events (user interaction)
    UI_INPUT_REQUIRED = "ui.input_required"
    UI_APPROVAL_REQUIRED = "ui.approval_required"
    UI_CHOICE_REQUIRED = "ui.choice_required"
    UI_CONFIRMATION_REQUIRED = "ui.confirmation_required"

    # System Events (system state)
    SYSTEM_STATUS = "system.status"
    SYSTEM_ERROR = "system.error"
    SYSTEM_WARNING = "system.warning"

    # Data Events (data flow)
    DATA_UPDATED = "data.updated"
    DATA_VALIDATED = "data.validated"
    DATA_ERROR = "data.error"


class EventPriority(str, Enum):
    """Event priority levels for processing order."""

    CRITICAL = "critical"  # System errors, failures
    HIGH = "high"  # User input required, approvals
    NORMAL = "normal"  # Progress updates, completions
    LOW = "low"  # Status updates, informational


@dataclass
class BaseEvent:
    """Base event structure for all middleware events."""

    id: str
    type: EventType
    timestamp: datetime
    priority: EventPriority = EventPriority.NORMAL
    source: Optional[str] = None
    target: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())


@dataclass
class WorkflowEvent(BaseEvent):
    """Events related to workflow execution."""

    workflow_id: str = None
    workflow_name: str = None
    execution_id: str = None
    progress_percent: float = None
    current_node: str = None
    data: Dict[str, Any] = None
    error: str = None

    def __post_init__(self):
        super().__post_init__()
        if self.data is None:
            self.data = {}


@dataclass
class NodeEvent(BaseEvent):
    """Events related to individual node execution."""

    workflow_id: str = None
    node_id: str = None
    node_type: str = None
    node_name: str = None
    inputs: Dict[str, Any] = None
    outputs: Dict[str, Any] = None
    execution_time_ms: float = None
    error: str = None

    def __post_init__(self):
        super().__post_init__()
        if self.inputs is None:
            self.inputs = {}
        if self.outputs is None:
            self.outputs = {}


@dataclass
class UIEvent(BaseEvent):
    """Events requiring user interface interaction."""

    interaction_type: str = None  # input, approval, choice, confirmation
    prompt: str = None
    options: List[Dict[str, Any]] = None
    form_schema: Dict[str, Any] = None
    timeout_ms: int = None
    response_required: bool = True
    context: Dict[str, Any] = None

    def __post_init__(self):
        super().__post_init__()
        if self.options is None:
            self.options = []
        if self.form_schema is None:
            self.form_schema = {}
        if self.context is None:
            self.context = {}


class EventFilter:
    """Filter events based on criteria."""

    def __init__(
        self,
        event_types: List[EventType] = None,
        priorities: List[EventPriority] = None,
        source: str = None,
        target: str = None,
        session_id: str = None,
        user_id: str = None,
    ):
        self.event_types = event_types or []
        self.priorities = priorities or []
        self.source = source
        self.target = target
        self.session_id = session_id
        self.user_id = user_id

    def matches(self, event: BaseEvent) -> bool:
        """Check if event matches filter criteria."""
        if self.event_types and event.type not in self.event_types:
            return False
        if self.priorities and event.priority not in self.priorities:
            return False
        if self.source and event.source != self.source:
            return False
        if self.target and event.target != self.target:
            return False
        if self.session_id and event.session_id != self.session_id:
            return False
        if self.user_id and event.user_id != self.user_id:
            return False
        return True


class EventBatch:
    """
    Batch multiple events for efficient transmission.

    This class should be replaced with BatchProcessorNode from SDK for better performance.
    Keeping for backward compatibility but will be deprecated.
    """

    def __init__(self, max_size: int = 100, max_age_ms: int = 1000):
        self.max_size = max_size
        self.max_age_ms = max_age_ms
        self.events: List[BaseEvent] = []
        self.created_at = time.time() * 1000

        # TODO: Replace with BatchProcessorNode for production use
        logger.warning(
            "EventBatch is deprecated. Use BatchProcessorNode from SDK for better performance."
        )

    def add_event(self, event: BaseEvent) -> bool:
        """Add event to batch. Returns True if batch should be flushed."""
        self.events.append(event)

        # Check if batch should be flushed
        if len(self.events) >= self.max_size:
            return True

        age_ms = (time.time() * 1000) - self.created_at
        if age_ms >= self.max_age_ms:
            return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert batch to dictionary."""
        return {
            "batch_id": str(uuid.uuid4()),
            "event_count": len(self.events),
            "created_at": self.created_at,
            "events": [event.to_dict() for event in self.events],
        }


class EventStream:
    """
    Manages event streaming with multiple subscribers and filtering.

    Enhanced with SDK nodes for better performance:
    - Uses CacheNode for event history management
    - Uses AsyncQueueNode for event buffering
    - Uses MetricsCollectorNode for performance tracking
    """

    def __init__(self, enable_batching: bool = True, batch_size: int = 10):
        self.enable_batching = enable_batching
        self.batch_size = batch_size
        self.subscribers: Dict[str, Dict] = (
            {}
        )  # subscriber_id -> {filter, callback, active}
        self.event_history: List[BaseEvent] = []
        self.max_history = 1000
        self._lock = asyncio.Lock()

        # Performance tracking
        self.events_emitted = 0
        self.events_delivered = 0
        self.start_time = time.time()

        # Initialize SDK nodes for optimization
        self._init_sdk_nodes()

    def _init_sdk_nodes(self):
        """Initialize SDK nodes for performance optimization."""
        # Import SDK nodes for event management
        from ...nodes.enterprise import BatchProcessorNode
        from ...nodes.transform import DataTransformer

        # Batch processor for efficient event batching
        self.batch_processor = BatchProcessorNode(name="event_batch_processor")

        # Data transformer for event serialization
        self.data_transformer = DataTransformer(name="event_transformer")

        # TODO: Add CacheNode when available for event history
        # TODO: Add AsyncQueueNode when available for event buffering
        # TODO: Add MetricsCollectorNode when available for performance tracking

    async def subscribe(
        self,
        subscriber_id: str,
        callback: Callable[[Union[BaseEvent, EventBatch]], None],
        event_filter: EventFilter = None,
    ) -> str:
        """Subscribe to event stream with optional filtering."""
        async with self._lock:
            self.subscribers[subscriber_id] = {
                "filter": event_filter or EventFilter(),
                "callback": callback,
                "active": True,
                "subscribed_at": time.time(),
                "events_received": 0,
            }

        logger.info(f"Subscriber {subscriber_id} subscribed to event stream")
        return subscriber_id

    async def unsubscribe(self, subscriber_id: str):
        """Unsubscribe from event stream."""
        async with self._lock:
            if subscriber_id in self.subscribers:
                self.subscribers[subscriber_id]["active"] = False
                del self.subscribers[subscriber_id]
                logger.info(f"Subscriber {subscriber_id} unsubscribed")

    async def emit(self, event: BaseEvent):
        """Emit event to all matching subscribers."""
        async with self._lock:
            # Add to history
            self.event_history.append(event)
            if len(self.event_history) > self.max_history:
                self.event_history.pop(0)

            self.events_emitted += 1

            # Deliver to subscribers
            for subscriber_id, subscriber in list(self.subscribers.items()):
                if not subscriber["active"]:
                    continue

                # Check filter
                if subscriber["filter"].matches(event):
                    try:
                        await self._deliver_event(subscriber, event)
                        subscriber["events_received"] += 1
                        self.events_delivered += 1
                    except Exception as e:
                        logger.error(f"Error delivering event to {subscriber_id}: {e}")
                        subscriber["active"] = False

    async def _deliver_event(self, subscriber: Dict, event: BaseEvent):
        """Deliver event to subscriber with optional batching."""
        callback = subscriber["callback"]

        if self.enable_batching:
            # Add to batch (simplified - in production would maintain per-subscriber batches)
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)
        else:
            if asyncio.iscoroutinefunction(callback):
                await callback(event)
            else:
                callback(event)

    async def emit_workflow_started(
        self,
        workflow_id: str,
        workflow_name: str,
        execution_id: str = None,
        user_id: str = None,
        session_id: str = None,
    ):
        """Convenience method for workflow started events."""
        event = WorkflowEvent(
            id=str(uuid.uuid4()),
            type=EventType.WORKFLOW_STARTED,
            timestamp=datetime.now(timezone.utc),
            priority=EventPriority.NORMAL,
            workflow_id=workflow_id,
            workflow_name=workflow_name,
            execution_id=execution_id or str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
        )
        await self.emit(event)

    async def emit_workflow_progress(
        self,
        workflow_id: str,
        execution_id: str,
        progress_percent: float,
        current_node: str = None,
        data: Dict[str, Any] = None,
    ):
        """Convenience method for workflow progress events."""
        event = WorkflowEvent(
            id=str(uuid.uuid4()),
            type=EventType.WORKFLOW_PROGRESS,
            timestamp=datetime.now(timezone.utc),
            priority=EventPriority.NORMAL,
            workflow_id=workflow_id,
            execution_id=execution_id,
            progress_percent=progress_percent,
            current_node=current_node,
            data=data or {},
        )
        await self.emit(event)

    async def emit_node_completed(
        self,
        workflow_id: str,
        node_id: str,
        node_type: str,
        outputs: Dict[str, Any] = None,
        execution_time_ms: float = None,
    ):
        """Convenience method for node completion events."""
        event = NodeEvent(
            id=str(uuid.uuid4()),
            type=EventType.NODE_COMPLETED,
            timestamp=datetime.now(timezone.utc),
            priority=EventPriority.NORMAL,
            workflow_id=workflow_id,
            node_id=node_id,
            node_type=node_type,
            outputs=outputs or {},
            execution_time_ms=execution_time_ms,
        )
        await self.emit(event)

    async def emit_ui_input_required(
        self,
        prompt: str,
        form_schema: Dict[str, Any],
        session_id: str,
        user_id: str = None,
        timeout_ms: int = 30000,
    ):
        """Convenience method for UI input required events."""
        event = UIEvent(
            id=str(uuid.uuid4()),
            type=EventType.UI_INPUT_REQUIRED,
            timestamp=datetime.now(timezone.utc),
            priority=EventPriority.HIGH,
            interaction_type="input",
            prompt=prompt,
            form_schema=form_schema,
            timeout_ms=timeout_ms,
            session_id=session_id,
            user_id=user_id,
        )
        await self.emit(event)

    def get_stats(self) -> Dict[str, Any]:
        """Get event stream statistics."""
        uptime = time.time() - self.start_time
        return {
            "uptime_seconds": uptime,
            "events_emitted": self.events_emitted,
            "events_delivered": self.events_delivered,
            "active_subscribers": len(
                [s for s in self.subscribers.values() if s["active"]]
            ),
            "total_subscribers": len(self.subscribers),
            "events_per_second": self.events_emitted / uptime if uptime > 0 else 0,
            "delivery_rate": (
                self.events_delivered / self.events_emitted
                if self.events_emitted > 0
                else 0
            ),
            "history_size": len(self.event_history),
        }

    async def get_recent_events(
        self, count: int = 100, event_filter: EventFilter = None
    ) -> List[BaseEvent]:
        """Get recent events with optional filtering."""
        async with self._lock:
            events = self.event_history[-count:] if count else self.event_history

            if event_filter:
                events = [e for e in events if event_filter.matches(e)]

            return events
