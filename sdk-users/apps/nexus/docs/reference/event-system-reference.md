# Event System Reference

Complete reference for Nexus's enterprise-grade event system, covering event-driven architecture, real-time notifications, workflow triggers, and cross-channel event propagation.

## ⚠️ Version Notice: v1.0 vs v1.1 Capabilities

**IMPORTANT**: The event system documentation describes the complete architecture and API. However, some features differ between versions:

### v1.0 (Current - Production Ready)
- ✅ **Event Creation & Logging**: Full support via `broadcast_event()`
- ✅ **Event Retrieval**: Use `get_events()` to retrieve logged events
- ✅ **Event Handlers**: Full support for synchronous and asynchronous handlers
- ✅ **Event Bus**: Complete pub/sub architecture implemented
- ❌ **Real-Time Broadcasting**: Events are LOGGED, not broadcast in real-time
- ❌ **WebSocket Streaming**: Planned for v1.1
- ❌ **SSE (Server-Sent Events)**: Planned for v1.1

### v1.1 (Planned - See ROADMAP.md)
- ✅ All v1.0 features (backward compatible)
- ✅ **WebSocket Event Broadcasting**: Real-time push to connected clients
- ✅ **SSE Streaming**: Browser-compatible event streaming
- ✅ **MCP Event Notifications**: AI agent event subscriptions

**For v1.0 Users**:
- Use `app.broadcast_event(type, data)` to log events
- Use `app.get_events(session_id=None, event_type=None, limit=100)` to retrieve events
- Events are stored in `_event_log` and can be queried
- All code examples work as shown, but "broadcasting" means logging in v1.0

**Upgrade Path to v1.1**:
- No code changes required
- `broadcast_event()` will automatically gain real-time capabilities
- Existing event logging continues to work
- New WebSocket/SSE endpoints will be additive

## Overview

Nexus provides a comprehensive event system that enables real-time communication, workflow orchestration, and cross-channel session synchronization. This reference covers all event types, handlers, publishers, subscribers, and integration patterns.

## Core Event Architecture

### Event System Foundation

```python
from nexus import Nexus
from typing import Dict, Any, List, Optional, Callable, Union
import asyncio
import json
import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from concurrent.futures import ThreadPoolExecutor

class EventType(Enum):
    """Core event types in Nexus system"""

    # Workflow Events
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    WORKFLOW_PAUSED = "workflow.paused"
    WORKFLOW_RESUMED = "workflow.resumed"
    WORKFLOW_CANCELLED = "workflow.cancelled"

    # Node Events
    NODE_STARTED = "node.started"
    NODE_COMPLETED = "node.completed"
    NODE_FAILED = "node.failed"
    NODE_RETRYING = "node.retrying"

    # System Events
    SYSTEM_STARTED = "system.started"
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_ERROR = "system.error"
    HEALTH_CHECK = "system.health_check"

    # User Events
    USER_AUTHENTICATED = "user.authenticated"
    USER_SESSION_STARTED = "user.session_started"
    USER_SESSION_ENDED = "user.session_ended"
    USER_ACTION = "user.action"

    # Channel Events
    CHANNEL_CONNECTED = "channel.connected"
    CHANNEL_DISCONNECTED = "channel.disconnected"
    CHANNEL_MESSAGE = "channel.message"

    # Custom Events
    CUSTOM_EVENT = "custom.event"

class EventPriority(Enum):
    """Event priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Event:
    """Core event object"""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType = EventType.CUSTOM_EVENT
    source: str = ""
    target: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    channel: Optional[str] = None
    retryable: bool = True
    max_retries: int = 3
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source": self.source,
            "target": self.target,
            "payload": self.payload,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "channel": self.channel,
            "retryable": self.retryable,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create event from dictionary"""

        event = cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=EventType(data.get("event_type", EventType.CUSTOM_EVENT.value)),
            source=data.get("source", ""),
            target=data.get("target"),
            payload=data.get("payload", {}),
            metadata=data.get("metadata", {}),
            priority=EventPriority(data.get("priority", EventPriority.NORMAL.value)),
            correlation_id=data.get("correlation_id"),
            session_id=data.get("session_id"),
            user_id=data.get("user_id"),
            channel=data.get("channel"),
            retryable=data.get("retryable", True),
            max_retries=data.get("max_retries", 3),
            retry_count=data.get("retry_count", 0)
        )

        # Parse timestamp
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            event.timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        return event

class EventHandler:
    """Base class for event handlers"""

    def __init__(self, handler_id: str, event_types: List[EventType],
                 async_handler: bool = False):
        self.handler_id = handler_id
        self.event_types = event_types
        self.async_handler = async_handler
        self.execution_count = 0
        self.last_execution = None
        self.error_count = 0

    def can_handle(self, event: Event) -> bool:
        """Check if handler can process this event"""
        return event.event_type in self.event_types

    def handle(self, event: Event) -> Dict[str, Any]:
        """Handle event (synchronous)"""
        self.execution_count += 1
        self.last_execution = datetime.now(timezone.utc)

        try:
            result = self._process_event(event)
            return {
                "handler_id": self.handler_id,
                "event_id": event.event_id,
                "status": "success",
                "result": result,
                "timestamp": self.last_execution.isoformat()
            }
        except Exception as e:
            self.error_count += 1
            return {
                "handler_id": self.handler_id,
                "event_id": event.event_id,
                "status": "error",
                "error": str(e),
                "timestamp": self.last_execution.isoformat()
            }

    async def handle_async(self, event: Event) -> Dict[str, Any]:
        """Handle event (asynchronous)"""
        self.execution_count += 1
        self.last_execution = datetime.now(timezone.utc)

        try:
            result = await self._process_event_async(event)
            return {
                "handler_id": self.handler_id,
                "event_id": event.event_id,
                "status": "success",
                "result": result,
                "timestamp": self.last_execution.isoformat()
            }
        except Exception as e:
            self.error_count += 1
            return {
                "handler_id": self.handler_id,
                "event_id": event.event_id,
                "status": "error",
                "error": str(e),
                "timestamp": self.last_execution.isoformat()
            }

    def _process_event(self, event: Event) -> Any:
        """Process event synchronously - override in subclasses"""
        return {"message": f"Processed event {event.event_id}"}

    async def _process_event_async(self, event: Event) -> Any:
        """Process event asynchronously - override in subclasses"""
        return {"message": f"Async processed event {event.event_id}"}

    def get_stats(self) -> Dict[str, Any]:
        """Get handler statistics"""
        return {
            "handler_id": self.handler_id,
            "event_types": [et.value for et in self.event_types],
            "execution_count": self.execution_count,
            "error_count": self.error_count,
            "last_execution": self.last_execution.isoformat() if self.last_execution else None,
            "success_rate": ((self.execution_count - self.error_count) / self.execution_count) if self.execution_count > 0 else 0
        }

class EventBus:
    """Central event bus for Nexus platform"""

    def __init__(self, max_workers: int = 10):
        self.handlers: Dict[str, EventHandler] = {}
        self.subscribers: Dict[EventType, List[str]] = {}
        self.event_history: List[Event] = []
        self.max_history_size = 10000
        self.max_workers = max_workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self.event_stats = {
            "total_events": 0,
            "processed_events": 0,
            "failed_events": 0,
            "handlers_registered": 0
        }
        self._lock = threading.Lock()

    def register_handler(self, handler: EventHandler) -> None:
        """Register an event handler"""

        with self._lock:
            self.handlers[handler.handler_id] = handler

            # Subscribe handler to its event types
            for event_type in handler.event_types:
                if event_type not in self.subscribers:
                    self.subscribers[event_type] = []
                if handler.handler_id not in self.subscribers[event_type]:
                    self.subscribers[event_type].append(handler.handler_id)

            self.event_stats["handlers_registered"] = len(self.handlers)

    def unregister_handler(self, handler_id: str) -> None:
        """Unregister an event handler"""

        with self._lock:
            if handler_id in self.handlers:
                handler = self.handlers[handler_id]

                # Remove from subscribers
                for event_type in handler.event_types:
                    if event_type in self.subscribers:
                        if handler_id in self.subscribers[event_type]:
                            self.subscribers[event_type].remove(handler_id)
                        if not self.subscribers[event_type]:
                            del self.subscribers[event_type]

                del self.handlers[handler_id]
                self.event_stats["handlers_registered"] = len(self.handlers)

    def publish(self, event: Event) -> Dict[str, Any]:
        """Publish event to all registered handlers"""

        with self._lock:
            self.event_stats["total_events"] += 1

            # Add to history
            self._add_to_history(event)

            # Get handlers for this event type
            handler_ids = self.subscribers.get(event.event_type, [])

            if not handler_ids:
                return {
                    "event_id": event.event_id,
                    "handlers_notified": 0,
                    "results": []
                }

            results = []

            # Process handlers
            for handler_id in handler_ids:
                if handler_id in self.handlers:
                    handler = self.handlers[handler_id]

                    if handler.can_handle(event):
                        try:
                            if handler.async_handler:
                                # Schedule async handler
                                future = asyncio.create_task(handler.handle_async(event))
                                result = {"handler_id": handler_id, "status": "scheduled", "future": future}
                            else:
                                # Execute sync handler
                                result = handler.handle(event)

                            results.append(result)
                            self.event_stats["processed_events"] += 1

                        except Exception as e:
                            error_result = {
                                "handler_id": handler_id,
                                "event_id": event.event_id,
                                "status": "error",
                                "error": str(e)
                            }
                            results.append(error_result)
                            self.event_stats["failed_events"] += 1

            return {
                "event_id": event.event_id,
                "handlers_notified": len(results),
                "results": results
            }

    async def publish_async(self, event: Event) -> Dict[str, Any]:
        """Publish event asynchronously"""

        self.event_stats["total_events"] += 1
        self._add_to_history(event)

        # Get handlers for this event type
        handler_ids = self.subscribers.get(event.event_type, [])

        if not handler_ids:
            return {
                "event_id": event.event_id,
                "handlers_notified": 0,
                "results": []
            }

        # Collect async tasks
        tasks = []
        sync_results = []

        for handler_id in handler_ids:
            if handler_id in self.handlers:
                handler = self.handlers[handler_id]

                if handler.can_handle(event):
                    if handler.async_handler:
                        task = handler.handle_async(event)
                        tasks.append(task)
                    else:
                        # Execute sync handler in thread pool
                        sync_result = handler.handle(event)
                        sync_results.append(sync_result)

        # Wait for async tasks
        async_results = []
        if tasks:
            async_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        all_results = sync_results + [
            result if not isinstance(result, Exception) else {"status": "error", "error": str(result)}
            for result in async_results
        ]

        success_count = sum(1 for r in all_results if r.get("status") != "error")
        self.event_stats["processed_events"] += success_count
        self.event_stats["failed_events"] += len(all_results) - success_count

        return {
            "event_id": event.event_id,
            "handlers_notified": len(all_results),
            "results": all_results
        }

    def _add_to_history(self, event: Event) -> None:
        """Add event to history with size limit"""

        self.event_history.append(event)

        # Maintain history size limit
        if len(self.event_history) > self.max_history_size:
            self.event_history = self.event_history[-self.max_history_size:]

    def get_event_history(self, limit: int = 100, event_type: Optional[EventType] = None) -> List[Dict[str, Any]]:
        """Get recent event history"""

        events = self.event_history

        # Filter by event type if specified
        if event_type:
            events = [e for e in events if e.event_type == event_type]

        # Apply limit
        events = events[-limit:]

        return [event.to_dict() for event in events]

    def get_stats(self) -> Dict[str, Any]:
        """Get event bus statistics"""

        handler_stats = {handler_id: handler.get_stats() for handler_id, handler in self.handlers.items()}

        return {
            "event_stats": self.event_stats.copy(),
            "handlers": handler_stats,
            "subscribers": {et.value: handler_ids for et, handler_ids in self.subscribers.items()},
            "history_size": len(self.event_history)
        }

# Example usage
app = Nexus()

# Create event bus
event_bus = EventBus(max_workers=5)

# Create sample event
workflow_event = Event(
    event_type=EventType.WORKFLOW_STARTED,
    source="workflow_engine",
    payload={
        "workflow_id": "wf_12345",
        "workflow_name": "data-processor",
        "user_id": "user_789"
    },
    metadata={
        "execution_mode": "production",
        "priority": "high"
    },
    session_id="session_456",
    correlation_id="corr_123"
)

print(f"Created event: {workflow_event.event_id}")
print(f"Event type: {workflow_event.event_type.value}")
print(f"Event payload: {workflow_event.payload}")
```

### Event Handlers and Processors

```python
from typing import Dict, Any, List, Optional
import logging
import json

class WorkflowEventHandler(EventHandler):
    """Handler for workflow-related events"""

    def __init__(self, handler_id: str = "workflow_handler"):
        super().__init__(
            handler_id=handler_id,
            event_types=[
                EventType.WORKFLOW_STARTED,
                EventType.WORKFLOW_COMPLETED,
                EventType.WORKFLOW_FAILED,
                EventType.WORKFLOW_PAUSED,
                EventType.WORKFLOW_RESUMED,
                EventType.WORKFLOW_CANCELLED
            ],
            async_handler=False
        )
        self.workflow_stats = {
            "started": 0,
            "completed": 0,
            "failed": 0,
            "paused": 0,
            "resumed": 0,
            "cancelled": 0
        }

    def _process_event(self, event: Event) -> Any:
        """Process workflow events"""

        workflow_id = event.payload.get("workflow_id", "unknown")
        workflow_name = event.payload.get("workflow_name", "unknown")

        if event.event_type == EventType.WORKFLOW_STARTED:
            self.workflow_stats["started"] += 1
            return self._handle_workflow_started(event, workflow_id, workflow_name)

        elif event.event_type == EventType.WORKFLOW_COMPLETED:
            self.workflow_stats["completed"] += 1
            return self._handle_workflow_completed(event, workflow_id, workflow_name)

        elif event.event_type == EventType.WORKFLOW_FAILED:
            self.workflow_stats["failed"] += 1
            return self._handle_workflow_failed(event, workflow_id, workflow_name)

        elif event.event_type == EventType.WORKFLOW_PAUSED:
            self.workflow_stats["paused"] += 1
            return self._handle_workflow_paused(event, workflow_id, workflow_name)

        elif event.event_type == EventType.WORKFLOW_RESUMED:
            self.workflow_stats["resumed"] += 1
            return self._handle_workflow_resumed(event, workflow_id, workflow_name)

        elif event.event_type == EventType.WORKFLOW_CANCELLED:
            self.workflow_stats["cancelled"] += 1
            return self._handle_workflow_cancelled(event, workflow_id, workflow_name)

        return {"message": f"Unhandled workflow event: {event.event_type.value}"}

    def _handle_workflow_started(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow started event"""

        logging.info(f"Workflow started: {workflow_id} ({workflow_name})")

        # Perform workflow start actions
        actions_taken = [
            "logged_workflow_start",
            "updated_metrics",
            "notified_monitoring"
        ]

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_started",
            "actions_taken": actions_taken,
            "timestamp": event.timestamp.isoformat()
        }

    def _handle_workflow_completed(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow completed event"""

        execution_time = event.payload.get("execution_time_ms", 0)

        logging.info(f"Workflow completed: {workflow_id} in {execution_time}ms")

        actions_taken = [
            "logged_workflow_completion",
            "updated_success_metrics",
            "cleaned_temp_resources",
            "sent_completion_notification"
        ]

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_completed",
            "execution_time_ms": execution_time,
            "actions_taken": actions_taken,
            "timestamp": event.timestamp.isoformat()
        }

    def _handle_workflow_failed(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow failed event"""

        error_message = event.payload.get("error", "Unknown error")

        logging.error(f"Workflow failed: {workflow_id} - {error_message}")

        actions_taken = [
            "logged_workflow_failure",
            "updated_error_metrics",
            "triggered_failure_alerts",
            "initiated_cleanup_procedures"
        ]

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_failed",
            "error": error_message,
            "actions_taken": actions_taken,
            "timestamp": event.timestamp.isoformat()
        }

    def _handle_workflow_paused(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow paused event"""

        reason = event.payload.get("pause_reason", "User requested")

        logging.info(f"Workflow paused: {workflow_id} - {reason}")

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_paused",
            "pause_reason": reason,
            "timestamp": event.timestamp.isoformat()
        }

    def _handle_workflow_resumed(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow resumed event"""

        logging.info(f"Workflow resumed: {workflow_id}")

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_resumed",
            "timestamp": event.timestamp.isoformat()
        }

    def _handle_workflow_cancelled(self, event: Event, workflow_id: str, workflow_name: str) -> Dict[str, Any]:
        """Handle workflow cancelled event"""

        reason = event.payload.get("cancel_reason", "User cancelled")

        logging.warning(f"Workflow cancelled: {workflow_id} - {reason}")

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "action": "workflow_cancelled",
            "cancel_reason": reason,
            "timestamp": event.timestamp.isoformat()
        }

    def get_workflow_stats(self) -> Dict[str, Any]:
        """Get workflow processing statistics"""
        return self.workflow_stats.copy()

class NotificationHandler(EventHandler):
    """Handler for sending notifications based on events"""

    def __init__(self, handler_id: str = "notification_handler"):
        super().__init__(
            handler_id=handler_id,
            event_types=[
                EventType.WORKFLOW_COMPLETED,
                EventType.WORKFLOW_FAILED,
                EventType.SYSTEM_ERROR,
                EventType.USER_AUTHENTICATED
            ],
            async_handler=True
        )
        self.notification_channels = ["email", "slack", "webhook"]
        self.notifications_sent = 0

    async def _process_event_async(self, event: Event) -> Any:
        """Process events for notifications"""

        notification_type = self._determine_notification_type(event)
        recipients = self._determine_recipients(event)
        message = self._create_message(event)

        # Simulate sending notifications
        sent_notifications = []

        for channel in self.notification_channels:
            if self._should_send_to_channel(event, channel):
                notification_result = await self._send_notification(
                    channel, recipients, message, notification_type
                )
                sent_notifications.append(notification_result)
                self.notifications_sent += 1

        return {
            "event_id": event.event_id,
            "notification_type": notification_type,
            "recipients": recipients,
            "channels": len(sent_notifications),
            "notifications_sent": sent_notifications
        }

    def _determine_notification_type(self, event: Event) -> str:
        """Determine notification type based on event"""

        if event.event_type == EventType.WORKFLOW_COMPLETED:
            return "success"
        elif event.event_type == EventType.WORKFLOW_FAILED:
            return "error"
        elif event.event_type == EventType.SYSTEM_ERROR:
            return "critical"
        elif event.event_type == EventType.USER_AUTHENTICATED:
            return "info"
        else:
            return "general"

    def _determine_recipients(self, event: Event) -> List[str]:
        """Determine notification recipients"""

        recipients = []

        # Add user if specified
        if event.user_id:
            recipients.append(event.user_id)

        # Add system administrators for critical events
        if event.priority == EventPriority.CRITICAL:
            recipients.extend(["admin@example.com", "ops-team"])

        # Add workflow owner for workflow events
        if event.event_type.value.startswith("workflow."):
            workflow_owner = event.payload.get("workflow_owner")
            if workflow_owner:
                recipients.append(workflow_owner)

        return list(set(recipients))  # Remove duplicates

    def _create_message(self, event: Event) -> str:
        """Create notification message"""

        if event.event_type == EventType.WORKFLOW_COMPLETED:
            workflow_name = event.payload.get("workflow_name", "Unknown")
            return f"Workflow '{workflow_name}' completed successfully"

        elif event.event_type == EventType.WORKFLOW_FAILED:
            workflow_name = event.payload.get("workflow_name", "Unknown")
            error = event.payload.get("error", "Unknown error")
            return f"Workflow '{workflow_name}' failed: {error}"

        elif event.event_type == EventType.SYSTEM_ERROR:
            error = event.payload.get("error", "System error occurred")
            return f"System Error: {error}"

        elif event.event_type == EventType.USER_AUTHENTICATED:
            user_id = event.user_id or "Unknown user"
            return f"User {user_id} authenticated successfully"

        else:
            return f"Event {event.event_type.value} occurred"

    def _should_send_to_channel(self, event: Event, channel: str) -> bool:
        """Determine if notification should be sent to channel"""

        # Send critical events to all channels
        if event.priority == EventPriority.CRITICAL:
            return True

        # Send workflow failures to email and slack
        if event.event_type == EventType.WORKFLOW_FAILED and channel in ["email", "slack"]:
            return True

        # Send completions to webhook only
        if event.event_type == EventType.WORKFLOW_COMPLETED and channel == "webhook":
            return True

        # Send auth events to email only
        if event.event_type == EventType.USER_AUTHENTICATED and channel == "email":
            return True

        return False

    async def _send_notification(self, channel: str, recipients: List[str],
                               message: str, notification_type: str) -> Dict[str, Any]:
        """Simulate sending notification to channel"""

        # Simulate async notification sending
        await asyncio.sleep(0.1)

        return {
            "channel": channel,
            "recipients": recipients,
            "message": message,
            "type": notification_type,
            "status": "sent",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Register handlers with event bus
workflow_handler = WorkflowEventHandler()
notification_handler = NotificationHandler()

event_bus.register_handler(workflow_handler)
event_bus.register_handler(notification_handler)

# Publish workflow events
workflow_started_event = Event(
    event_type=EventType.WORKFLOW_STARTED,
    source="workflow_engine",
    payload={
        "workflow_id": "wf_12345",
        "workflow_name": "data-processor",
        "workflow_owner": "user@example.com"
    },
    user_id="user_789",
    priority=EventPriority.NORMAL
)

workflow_completed_event = Event(
    event_type=EventType.WORKFLOW_COMPLETED,
    source="workflow_engine",
    payload={
        "workflow_id": "wf_12345",
        "workflow_name": "data-processor",
        "execution_time_ms": 2500,
        "workflow_owner": "user@example.com"
    },
    user_id="user_789",
    priority=EventPriority.NORMAL
)

# Publish events
start_result = event_bus.publish(workflow_started_event)
completion_result = event_bus.publish(workflow_completed_event)

print(f"Workflow started - handlers notified: {start_result['handlers_notified']}")
print(f"Workflow completed - handlers notified: {completion_result['handlers_notified']}")

# Get event bus statistics
bus_stats = event_bus.get_stats()
print(f"Event bus stats: {bus_stats['event_stats']}")

# Get workflow handler statistics
workflow_stats = workflow_handler.get_workflow_stats()
print(f"Workflow handler stats: {workflow_stats}")
```

## Real-time Event Streaming

### WebSocket Event Streaming

```python
import asyncio
import websockets
import json
from typing import Dict, Any, Set, List, Optional
from dataclasses import dataclass

@dataclass
class EventSubscription:
    """Event subscription configuration"""

    subscription_id: str
    event_types: List[EventType]
    filters: Dict[str, Any]
    client_id: str
    session_id: Optional[str] = None
    active: bool = True

class EventStreamManager:
    """Manage real-time event streaming to clients"""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.websocket_clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.subscriptions: Dict[str, EventSubscription] = {}
        self.client_subscriptions: Dict[str, List[str]] = {}  # client_id -> subscription_ids
        self.active_streams = 0

        # Register as event handler for all events
        stream_handler = StreamingEventHandler(self)
        self.event_bus.register_handler(stream_handler)

    async def add_client(self, client_id: str, websocket: websockets.WebSocketServerProtocol) -> None:
        """Add new WebSocket client"""

        self.websocket_clients[client_id] = websocket
        self.client_subscriptions[client_id] = []
        self.active_streams += 1

        # Send welcome message
        welcome_message = {
            "type": "connection_established",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "capabilities": ["event_streaming", "real_time_updates", "filtered_subscriptions"]
        }

        await self._send_to_client(client_id, welcome_message)

    async def remove_client(self, client_id: str) -> None:
        """Remove WebSocket client"""

        if client_id in self.websocket_clients:
            # Remove all subscriptions for this client
            subscription_ids = self.client_subscriptions.get(client_id, [])
            for subscription_id in subscription_ids:
                self.unsubscribe(subscription_id)

            del self.websocket_clients[client_id]
            del self.client_subscriptions[client_id]
            self.active_streams -= 1

    def subscribe(self, client_id: str, event_types: List[EventType],
                 filters: Dict[str, Any] = None, session_id: str = None) -> str:
        """Subscribe client to specific events"""

        subscription_id = f"sub_{uuid.uuid4()}"

        subscription = EventSubscription(
            subscription_id=subscription_id,
            event_types=event_types,
            filters=filters or {},
            client_id=client_id,
            session_id=session_id
        )

        self.subscriptions[subscription_id] = subscription
        self.client_subscriptions[client_id].append(subscription_id)

        return subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove event subscription"""

        if subscription_id in self.subscriptions:
            subscription = self.subscriptions[subscription_id]
            client_id = subscription.client_id

            # Remove from client subscriptions
            if client_id in self.client_subscriptions:
                if subscription_id in self.client_subscriptions[client_id]:
                    self.client_subscriptions[client_id].remove(subscription_id)

            del self.subscriptions[subscription_id]
            return True

        return False

    async def stream_event(self, event: Event) -> None:
        """Stream event to subscribed clients"""

        # Find matching subscriptions
        matching_subscriptions = []

        for subscription in self.subscriptions.values():
            if subscription.active and self._event_matches_subscription(event, subscription):
                matching_subscriptions.append(subscription)

        # Send to matching clients
        for subscription in matching_subscriptions:
            client_id = subscription.client_id

            if client_id in self.websocket_clients:
                event_message = {
                    "type": "event",
                    "subscription_id": subscription.subscription_id,
                    "event": event.to_dict()
                }

                await self._send_to_client(client_id, event_message)

    def _event_matches_subscription(self, event: Event, subscription: EventSubscription) -> bool:
        """Check if event matches subscription criteria"""

        # Check event type
        if event.event_type not in subscription.event_types:
            return False

        # Apply filters
        for filter_key, filter_value in subscription.filters.items():
            if filter_key == "session_id":
                if event.session_id != filter_value:
                    return False
            elif filter_key == "user_id":
                if event.user_id != filter_value:
                    return False
            elif filter_key == "source":
                if event.source != filter_value:
                    return False
            elif filter_key == "priority":
                if event.priority.value != filter_value:
                    return False

        return True

    async def _send_to_client(self, client_id: str, message: Dict[str, Any]) -> None:
        """Send message to specific client"""

        if client_id in self.websocket_clients:
            websocket = self.websocket_clients[client_id]

            try:
                await websocket.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                # Client disconnected, remove them
                await self.remove_client(client_id)
            except Exception as e:
                print(f"Error sending to client {client_id}: {e}")

    async def broadcast_to_all(self, message: Dict[str, Any]) -> None:
        """Broadcast message to all connected clients"""

        for client_id in list(self.websocket_clients.keys()):
            await self._send_to_client(client_id, message)

    def get_streaming_stats(self) -> Dict[str, Any]:
        """Get streaming statistics"""

        return {
            "active_streams": self.active_streams,
            "total_subscriptions": len(self.subscriptions),
            "connected_clients": len(self.websocket_clients),
            "subscriptions_by_type": self._get_subscriptions_by_type()
        }

    def _get_subscriptions_by_type(self) -> Dict[str, int]:
        """Get subscription counts by event type"""

        type_counts = {}

        for subscription in self.subscriptions.values():
            for event_type in subscription.event_types:
                type_name = event_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1

        return type_counts

class StreamingEventHandler(EventHandler):
    """Handler that streams events to WebSocket clients"""

    def __init__(self, stream_manager: EventStreamManager):
        super().__init__(
            handler_id="streaming_handler",
            event_types=list(EventType),  # Subscribe to all events
            async_handler=True
        )
        self.stream_manager = stream_manager

    async def _process_event_async(self, event: Event) -> Any:
        """Stream event to connected clients"""

        await self.stream_manager.stream_event(event)

        return {
            "streamed_to_clients": self.stream_manager.active_streams,
            "event_id": event.event_id,
            "event_type": event.event_type.value
        }

# Example WebSocket server setup
async def websocket_handler(websocket, path):
    """Handle WebSocket connections"""

    client_id = f"client_{uuid.uuid4()}"

    try:
        # Add client to stream manager
        await stream_manager.add_client(client_id, websocket)

        # Handle client messages
        async for message in websocket:
            try:
                data = json.loads(message)
                await handle_client_message(client_id, data)
            except json.JSONDecodeError:
                error_message = {
                    "type": "error",
                    "message": "Invalid JSON message"
                }
                await stream_manager._send_to_client(client_id, error_message)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Remove client
        await stream_manager.remove_client(client_id)

async def handle_client_message(client_id: str, message: Dict[str, Any]) -> None:
    """Handle messages from WebSocket clients"""

    message_type = message.get("type")

    if message_type == "subscribe":
        # Subscribe to events
        event_type_names = message.get("event_types", [])
        event_types = [EventType(name) for name in event_type_names if name in [et.value for et in EventType]]
        filters = message.get("filters", {})
        session_id = message.get("session_id")

        subscription_id = stream_manager.subscribe(client_id, event_types, filters, session_id)

        response = {
            "type": "subscription_created",
            "subscription_id": subscription_id,
            "event_types": event_type_names,
            "filters": filters
        }

        await stream_manager._send_to_client(client_id, response)

    elif message_type == "unsubscribe":
        # Unsubscribe from events
        subscription_id = message.get("subscription_id")
        success = stream_manager.unsubscribe(subscription_id)

        response = {
            "type": "unsubscribed",
            "subscription_id": subscription_id,
            "success": success
        }

        await stream_manager._send_to_client(client_id, response)

    elif message_type == "get_stats":
        # Get streaming stats
        stats = stream_manager.get_streaming_stats()

        response = {
            "type": "stats",
            "stats": stats
        }

        await stream_manager._send_to_client(client_id, response)

# Create stream manager
stream_manager = EventStreamManager(event_bus)

# Example: Start WebSocket server
# start_server = websockets.serve(websocket_handler, "localhost", 8765)
# asyncio.get_event_loop().run_until_complete(start_server)

print("Event system initialized with streaming capabilities")
print(f"Stream manager active: {stream_manager.active_streams} streams")
```

## Event-Driven Workflow Triggers

### Workflow Trigger System

```python
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

class TriggerCondition(Enum):
    """Trigger condition types"""
    EVENT_OCCURRED = "event_occurred"
    EVENT_SEQUENCE = "event_sequence"
    TIME_BASED = "time_based"
    THRESHOLD_REACHED = "threshold_reached"
    PATTERN_MATCHED = "pattern_matched"

@dataclass
class WorkflowTrigger:
    """Workflow trigger configuration"""

    trigger_id: str
    workflow_name: str
    condition: TriggerCondition
    event_types: List[EventType]
    filters: Dict[str, Any]
    parameters: Dict[str, Any]
    active: bool = True
    max_executions: Optional[int] = None
    execution_count: int = 0

class WorkflowTriggerManager:
    """Manage event-driven workflow triggers"""

    def __init__(self, event_bus: EventBus, nexus_app):
        self.event_bus = event_bus
        self.nexus_app = nexus_app
        self.triggers: Dict[str, WorkflowTrigger] = {}
        self.trigger_history: List[Dict[str, Any]] = []

        # Register as event handler
        trigger_handler = TriggerEventHandler(self)
        self.event_bus.register_handler(trigger_handler)

    def register_trigger(self, trigger: WorkflowTrigger) -> None:
        """Register a workflow trigger"""

        self.triggers[trigger.trigger_id] = trigger

        print(f"Registered trigger {trigger.trigger_id} for workflow {trigger.workflow_name}")

    def unregister_trigger(self, trigger_id: str) -> bool:
        """Unregister a workflow trigger"""

        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            return True

        return False

    async def process_event_for_triggers(self, event: Event) -> List[Dict[str, Any]]:
        """Process event against all triggers"""

        triggered_workflows = []

        for trigger in self.triggers.values():
            if trigger.active and self._should_trigger_workflow(event, trigger):
                result = await self._execute_triggered_workflow(event, trigger)
                triggered_workflows.append(result)

        return triggered_workflows

    def _should_trigger_workflow(self, event: Event, trigger: WorkflowTrigger) -> bool:
        """Check if event should trigger workflow"""

        # Check if trigger has exceeded max executions
        if trigger.max_executions and trigger.execution_count >= trigger.max_executions:
            return False

        # Check event type
        if event.event_type not in trigger.event_types:
            return False

        # Apply filters
        for filter_key, filter_value in trigger.filters.items():
            if filter_key == "source" and event.source != filter_value:
                return False
            elif filter_key == "user_id" and event.user_id != filter_value:
                return False
            elif filter_key == "priority" and event.priority.value != filter_value:
                return False

        # Check condition-specific logic
        if trigger.condition == TriggerCondition.EVENT_OCCURRED:
            return True
        elif trigger.condition == TriggerCondition.THRESHOLD_REACHED:
            return self._check_threshold_condition(event, trigger)
        elif trigger.condition == TriggerCondition.PATTERN_MATCHED:
            return self._check_pattern_condition(event, trigger)

        return False

    def _check_threshold_condition(self, event: Event, trigger: WorkflowTrigger) -> bool:
        """Check threshold-based trigger condition"""

        threshold_field = trigger.parameters.get("threshold_field")
        threshold_value = trigger.parameters.get("threshold_value", 0)
        comparison = trigger.parameters.get("comparison", "greater_than")

        if not threshold_field:
            return False

        event_value = event.payload.get(threshold_field, 0)

        if comparison == "greater_than":
            return event_value > threshold_value
        elif comparison == "less_than":
            return event_value < threshold_value
        elif comparison == "equal":
            return event_value == threshold_value

        return False

    def _check_pattern_condition(self, event: Event, trigger: WorkflowTrigger) -> bool:
        """Check pattern-based trigger condition"""

        pattern_field = trigger.parameters.get("pattern_field")
        pattern_regex = trigger.parameters.get("pattern_regex")

        if not pattern_field or not pattern_regex:
            return False

        field_value = str(event.payload.get(pattern_field, ""))

        import re
        return bool(re.search(pattern_regex, field_value))

    async def _execute_triggered_workflow(self, event: Event, trigger: WorkflowTrigger) -> Dict[str, Any]:
        """Execute workflow triggered by event"""

        # Increment execution count
        trigger.execution_count += 1

        # Prepare workflow input data
        workflow_input = {
            "trigger_event": event.to_dict(),
            "trigger_id": trigger.trigger_id,
            "triggered_at": datetime.now(timezone.utc).isoformat()
        }

        # Add trigger parameters to input
        workflow_input.update(trigger.parameters.get("workflow_input", {}))

        try:
            # Execute workflow (simulated - in real implementation would use workflow engine)
            execution_result = await self._simulate_workflow_execution(
                trigger.workflow_name,
                workflow_input
            )

            # Record trigger execution
            trigger_record = {
                "trigger_id": trigger.trigger_id,
                "workflow_name": trigger.workflow_name,
                "event_id": event.event_id,
                "execution_result": execution_result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "success"
            }

            self.trigger_history.append(trigger_record)

            return trigger_record

        except Exception as e:
            # Record trigger failure
            error_record = {
                "trigger_id": trigger.trigger_id,
                "workflow_name": trigger.workflow_name,
                "event_id": event.event_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "error"
            }

            self.trigger_history.append(error_record)

            return error_record

    async def _simulate_workflow_execution(self, workflow_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate workflow execution (replace with actual workflow engine call)"""

        # Simulate async workflow execution
        await asyncio.sleep(0.2)

        return {
            "workflow_name": workflow_name,
            "execution_id": f"exec_{uuid.uuid4()}",
            "status": "completed",
            "execution_time_ms": 200,
            "result": {
                "message": f"Workflow {workflow_name} executed successfully",
                "input_data": input_data
            }
        }

    def get_trigger_stats(self) -> Dict[str, Any]:
        """Get trigger statistics"""

        active_triggers = sum(1 for t in self.triggers.values() if t.active)
        total_executions = sum(t.execution_count for t in self.triggers.values())

        success_count = sum(1 for record in self.trigger_history if record["status"] == "success")
        error_count = len(self.trigger_history) - success_count

        return {
            "total_triggers": len(self.triggers),
            "active_triggers": active_triggers,
            "total_executions": total_executions,
            "successful_executions": success_count,
            "failed_executions": error_count,
            "trigger_history_size": len(self.trigger_history)
        }

class TriggerEventHandler(EventHandler):
    """Event handler for processing workflow triggers"""

    def __init__(self, trigger_manager: WorkflowTriggerManager):
        super().__init__(
            handler_id="trigger_handler",
            event_types=list(EventType),  # Listen to all events
            async_handler=True
        )
        self.trigger_manager = trigger_manager

    async def _process_event_async(self, event: Event) -> Any:
        """Process event for workflow triggers"""

        triggered_workflows = await self.trigger_manager.process_event_for_triggers(event)

        return {
            "event_id": event.event_id,
            "triggered_workflows": len(triggered_workflows),
            "executions": triggered_workflows
        }

# Example trigger setup
trigger_manager = WorkflowTriggerManager(event_bus, app)

# Register some example triggers
workflow_failure_trigger = WorkflowTrigger(
    trigger_id="failure_response_trigger",
    workflow_name="failure-recovery-workflow",
    condition=TriggerCondition.EVENT_OCCURRED,
    event_types=[EventType.WORKFLOW_FAILED],
    filters={"priority": "high"},
    parameters={
        "workflow_input": {
            "recovery_mode": "automatic",
            "notify_admins": True
        }
    }
)

high_volume_trigger = WorkflowTrigger(
    trigger_id="high_volume_trigger",
    workflow_name="scale-up-workflow",
    condition=TriggerCondition.THRESHOLD_REACHED,
    event_types=[EventType.WORKFLOW_STARTED],
    filters={},
    parameters={
        "threshold_field": "concurrent_workflows",
        "threshold_value": 50,
        "comparison": "greater_than",
        "workflow_input": {
            "scale_factor": 2,
            "target_instances": 10
        }
    }
)

trigger_manager.register_trigger(workflow_failure_trigger)
trigger_manager.register_trigger(high_volume_trigger)

print(f"Registered {len(trigger_manager.triggers)} workflow triggers")

# Example: Trigger a workflow failure event
failure_event = Event(
    event_type=EventType.WORKFLOW_FAILED,
    source="workflow_engine",
    payload={
        "workflow_id": "wf_critical_123",
        "workflow_name": "payment-processor",
        "error": "Database connection failed",
        "concurrent_workflows": 75  # Above threshold
    },
    priority=EventPriority.HIGH,
    user_id="system"
)

# Publish the failure event (this will trigger the failure response workflow)
trigger_result = event_bus.publish(failure_event)
print(f"Failure event published - handlers notified: {trigger_result['handlers_notified']}")

# Get trigger statistics
trigger_stats = trigger_manager.get_trigger_stats()
print(f"Trigger stats: {trigger_stats}")
```

This event system reference provides comprehensive coverage of Nexus's event-driven architecture, including real-time streaming, workflow triggers, and cross-channel event propagation. All examples demonstrate production-ready patterns for event handling and processing.
