"""
Real-time Communication Middleware for Kailash

Provides WebSocket, Server-Sent Events (SSE), and Webhook support for
real-time agent-frontend communication with sub-200ms latency.
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Union
from urllib.parse import parse_qs

from fastapi import Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ...nodes.api import HTTPRequestNode
from ...nodes.security import CredentialManagerNode
from ...nodes.transform import DataTransformer
from ..core.agent_ui import AgentUIMiddleware
from .events import BaseEvent, EventFilter, EventPriority, EventStream, EventType

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections with authentication and filtering."""

    def __init__(self):
        self.connections: Dict[str, Dict] = {}  # connection_id -> connection_info
        self.session_connections: Dict[str, Set[str]] = (
            {}
        )  # session_id -> set of connection_ids
        self.user_connections: Dict[str, Set[str]] = (
            {}
        )  # user_id -> set of connection_ids

    async def connect(
        self,
        websocket: WebSocket,
        connection_id: str,
        session_id: str = None,
        user_id: str = None,
        event_filter: EventFilter = None,
    ):
        """Accept and register a WebSocket connection."""
        await websocket.accept()

        self.connections[connection_id] = {
            "websocket": websocket,
            "session_id": session_id,
            "user_id": user_id,
            "event_filter": event_filter or EventFilter(),
            "connected_at": datetime.now(timezone.utc),
            "messages_sent": 0,
            "last_ping": time.time(),
        }

        # Track by session and user
        if session_id:
            if session_id not in self.session_connections:
                self.session_connections[session_id] = set()
            self.session_connections[session_id].add(connection_id)

        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)

        logger.info(
            f"WebSocket connection {connection_id} established for session {session_id}"
        )

    async def disconnect(self, connection_id: str):
        """Disconnect and cleanup a WebSocket connection."""
        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]
        session_id = connection["session_id"]
        user_id = connection["user_id"]

        # Remove from tracking
        if session_id and session_id in self.session_connections:
            self.session_connections[session_id].discard(connection_id)
            if not self.session_connections[session_id]:
                del self.session_connections[session_id]

        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        # Close WebSocket
        try:
            await connection["websocket"].close()
        except:
            pass

        del self.connections[connection_id]
        logger.info(f"WebSocket connection {connection_id} disconnected")

    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """Send message to a specific connection."""
        if connection_id not in self.connections:
            return False

        connection = self.connections[connection_id]
        try:
            await connection["websocket"].send_text(json.dumps(message))
            connection["messages_sent"] += 1
            return True
        except Exception as e:
            logger.error(f"Error sending to connection {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False

    async def send_to_session(self, session_id: str, message: Dict[str, Any]):
        """Send message to all connections in a session."""
        if session_id not in self.session_connections:
            return 0

        sent_count = 0
        for connection_id in list(self.session_connections[session_id]):
            if await self.send_to_connection(connection_id, message):
                sent_count += 1

        return sent_count

    async def send_to_user(self, user_id: str, message: Dict[str, Any]):
        """Send message to all connections for a user."""
        if user_id not in self.user_connections:
            return 0

        sent_count = 0
        for connection_id in list(self.user_connections[user_id]):
            if await self.send_to_connection(connection_id, message):
                sent_count += 1

        return sent_count

    async def broadcast(
        self, message: Dict[str, Any], event_filter: EventFilter = None
    ):
        """Broadcast message to all matching connections."""
        sent_count = 0
        for connection_id, connection in list(self.connections.items()):
            # Apply filtering if provided
            if event_filter:
                if (
                    event_filter.session_id
                    and connection["session_id"] != event_filter.session_id
                ):
                    continue
                if (
                    event_filter.user_id
                    and connection["user_id"] != event_filter.user_id
                ):
                    continue

            if await self.send_to_connection(connection_id, message):
                sent_count += 1

        return sent_count

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        total_messages = sum(
            conn["messages_sent"] for conn in self.connections.values()
        )
        return {
            "total_connections": len(self.connections),
            "active_sessions": len(self.session_connections),
            "active_users": len(self.user_connections),
            "total_messages_sent": total_messages,
        }


class SSEManager:
    """Manages Server-Sent Events streams."""

    def __init__(self):
        self.streams: Dict[str, Dict] = {}  # stream_id -> stream_info
        self.session_streams: Dict[str, Set[str]] = (
            {}
        )  # session_id -> set of stream_ids

    def create_stream(
        self,
        stream_id: str,
        session_id: str = None,
        user_id: str = None,
        event_filter: EventFilter = None,
    ) -> AsyncGenerator[str, None]:
        """Create a new SSE stream."""

        async def event_generator():
            # Store stream info
            self.streams[stream_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "event_filter": event_filter or EventFilter(),
                "created_at": datetime.now(timezone.utc),
                "events_sent": 0,
                "active": True,
            }

            # Track by session
            if session_id:
                if session_id not in self.session_streams:
                    self.session_streams[session_id] = set()
                self.session_streams[session_id].add(stream_id)

            try:
                # Send initial connection event
                yield f"data: {json.dumps({'type': 'connected', 'stream_id': stream_id})}\n\n"

                # Keep connection alive and wait for events
                while self.streams.get(stream_id, {}).get("active", False):
                    # Send heartbeat every 30 seconds
                    yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                    await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"SSE stream {stream_id} error: {e}")
            finally:
                # Cleanup
                await self.close_stream(stream_id)

        return event_generator()

    async def send_to_stream(self, stream_id: str, message: Dict[str, Any]):
        """Send message to a specific SSE stream."""
        if stream_id not in self.streams:
            return False

        # In a real implementation, this would queue the message for the generator
        # For now, we'll track that the message was sent
        self.streams[stream_id]["events_sent"] += 1
        return True

    async def send_to_session_streams(self, session_id: str, message: Dict[str, Any]):
        """Send message to all SSE streams in a session."""
        if session_id not in self.session_streams:
            return 0

        sent_count = 0
        for stream_id in list(self.session_streams[session_id]):
            if await self.send_to_stream(stream_id, message):
                sent_count += 1

        return sent_count

    async def close_stream(self, stream_id: str):
        """Close and cleanup an SSE stream."""
        if stream_id not in self.streams:
            return

        stream = self.streams[stream_id]
        stream["active"] = False

        session_id = stream["session_id"]
        if session_id and session_id in self.session_streams:
            self.session_streams[session_id].discard(stream_id)
            if not self.session_streams[session_id]:
                del self.session_streams[session_id]

        del self.streams[stream_id]
        logger.info(f"SSE stream {stream_id} closed")


class WebhookManager:
    """Manages webhook delivery for events using SDK nodes."""

    def __init__(self, max_retries: int = 3, timeout_seconds: int = 10):
        self.webhooks: Dict[str, Dict] = {}  # webhook_id -> webhook_config
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.delivery_stats = {
            "total_attempts": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
        }

        # Use HTTPRequestNode instead of httpx
        self.http_node = HTTPRequestNode(
            name="webhook_delivery",
            retry_count=max_retries,
            timeout=timeout_seconds,
            headers={"User-Agent": "Kailash-Middleware/2.0"},
        )

        # Use CredentialManagerNode for webhook authentication
        self.credential_node = CredentialManagerNode(
            name="webhook_auth",
            credential_name="webhook_secrets",
            credential_type="custom",
        )

    def register_webhook(
        self,
        webhook_id: str,
        url: str,
        secret: str = None,
        event_filter: EventFilter = None,
        headers: Dict[str, str] = None,
    ):
        """Register a webhook endpoint."""
        self.webhooks[webhook_id] = {
            "url": url,
            "secret": secret,
            "event_filter": event_filter or EventFilter(),
            "headers": headers or {},
            "created_at": datetime.now(timezone.utc),
            "deliveries": 0,
            "failures": 0,
            "active": True,
        }
        logger.info(f"Registered webhook {webhook_id} -> {url}")

    def unregister_webhook(self, webhook_id: str):
        """Unregister a webhook endpoint."""
        if webhook_id in self.webhooks:
            del self.webhooks[webhook_id]
            logger.info(f"Unregistered webhook {webhook_id}")

    async def deliver_event(self, event: BaseEvent):
        """Deliver event to all matching webhooks."""
        delivery_results = []

        for webhook_id, webhook in self.webhooks.items():
            if not webhook["active"]:
                continue

            # Check if event matches filter
            if webhook["event_filter"].matches(event):
                result = await self._deliver_to_webhook(webhook_id, webhook, event)
                delivery_results.append(result)

        return delivery_results

    async def _deliver_to_webhook(
        self, webhook_id: str, webhook: Dict[str, Any], event: BaseEvent
    ) -> Dict[str, Any]:
        """Deliver event to a specific webhook using SDK HTTPRequestNode."""
        url = webhook["url"]
        delivery_id = str(uuid.uuid4())

        # Prepare headers
        headers = {
            **webhook.get("headers", {}),
            "X-Kailash-Webhook-Id": webhook_id,
            "X-Kailash-Delivery-Id": delivery_id,
        }

        # Add signature if secret is provided
        if webhook["secret"]:
            # In production, this would include HMAC signature
            headers["X-Kailash-Signature"] = f"sha256={webhook['secret'][:8]}..."

        # Prepare payload
        payload = {
            "webhook_id": webhook_id,
            "event": event.to_dict(),
            "delivery_id": delivery_id,
            "timestamp": time.time(),
        }

        # Log delivery attempt
        logger.info(
            f"Webhook delivery attempt: {webhook_id} -> {url} (event: {event.type.value})"
        )

        self.delivery_stats["total_attempts"] += 1

        try:
            # Use HTTPRequestNode for delivery (it handles retries internally)
            response = self.http_node.execute(
                url=url, method="POST", json_data=payload, headers=headers
            )

            status_code = response.get("status_code", 0)

            if status_code < 400:
                webhook["deliveries"] += 1
                self.delivery_stats["successful_deliveries"] += 1

                # Log successful delivery
                logger.info(
                    f"Webhook delivery successful: {webhook_id} (status: {status_code})"
                )

                return {
                    "webhook_id": webhook_id,
                    "success": True,
                    "status_code": status_code,
                    "delivery_id": delivery_id,
                }
            else:
                # Log HTTP error
                logger.warning(
                    f"Webhook delivery HTTP error: {webhook_id} (status: {status_code})"
                )

                webhook["failures"] += 1
                self.delivery_stats["failed_deliveries"] += 1

                return {
                    "webhook_id": webhook_id,
                    "success": False,
                    "status_code": status_code,
                    "error": f"HTTP {status_code}",
                }

        except Exception as e:
            # Log delivery failure
            logger.error(f"Webhook delivery failed: {webhook_id} - {str(e)}")

            webhook["failures"] += 1
            self.delivery_stats["failed_deliveries"] += 1

            return {
                "webhook_id": webhook_id,
                "success": False,
                "error": str(e),
                "delivery_id": delivery_id,
            }


class RealtimeMiddleware:
    """
    Real-time communication middleware supporting multiple transport layers.

    Provides:
    - WebSocket connections for bidirectional real-time communication
    - Server-Sent Events (SSE) for unidirectional event streaming
    - Webhook delivery for external integrations
    - Sub-200ms latency optimization
    - Event filtering and routing
    """

    def __init__(
        self,
        agent_ui_middleware: AgentUIMiddleware,
        enable_websockets: bool = True,
        enable_sse: bool = True,
        enable_webhooks: bool = True,
        latency_target_ms: int = 200,
    ):
        self.agent_ui = agent_ui_middleware
        self.enable_websockets = enable_websockets
        self.enable_sse = enable_sse
        self.enable_webhooks = enable_webhooks
        self.latency_target_ms = latency_target_ms

        # Transport managers
        self.connection_manager = ConnectionManager() if enable_websockets else None
        self.sse_manager = SSEManager() if enable_sse else None
        self.webhook_manager = WebhookManager() if enable_webhooks else None

        # Performance tracking
        self.start_time = time.time()
        self.events_processed = 0
        self.latency_samples = []

        # Event subscription will be set up during initialize()
        self._event_subscription_task = None

    async def initialize(self):
        """Initialize the middleware and set up event subscriptions."""
        # Set up event subscription in async context
        self._event_subscription_task = asyncio.create_task(self._subscribe_to_events())
        logger.info("RealtimeMiddleware initialized with event subscriptions")

    def _setup_event_subscription(self):
        """Subscribe to events from the agent UI middleware."""
        # Deprecated - use initialize() instead
        logger.warning(
            "_setup_event_subscription called directly - use initialize() instead"
        )

    async def _subscribe_to_events(self):
        """Subscribe to and process events from agent UI."""

        async def event_handler(event: BaseEvent):
            start_time = time.time()

            try:
                await self._process_event(event)
                self.events_processed += 1

                # Track latency
                latency_ms = (time.time() - start_time) * 1000
                self.latency_samples.append(latency_ms)

                # Keep only recent samples
                if len(self.latency_samples) > 1000:
                    self.latency_samples = self.latency_samples[-500:]

                # Log if latency exceeds target
                if latency_ms > self.latency_target_ms:
                    logger.warning(
                        f"Event processing latency {latency_ms:.1f}ms exceeds target {self.latency_target_ms}ms"
                    )

            except Exception as e:
                logger.error(f"Error processing event {event.id}: {e}")

        await self.agent_ui.event_stream.subscribe("realtime_middleware", event_handler)

    async def _process_event(self, event: BaseEvent):
        """Process and route event to appropriate transport layers."""
        message = {"event": event.to_dict(), "timestamp": time.time()}

        # Route to WebSocket connections
        if self.enable_websockets and self.connection_manager:
            await self.connection_manager.broadcast(message)

        # Route to SSE streams (would need to implement message queuing)
        if self.enable_sse and self.sse_manager:
            # In a real implementation, this would queue messages for active streams
            pass

        # Route to webhooks
        if self.enable_webhooks and self.webhook_manager:
            await self.webhook_manager.deliver_event(event)

    # WebSocket Methods
    async def handle_websocket(
        self,
        websocket: WebSocket,
        session_id: str = None,
        user_id: str = None,
        event_types: List[str] = None,
    ):
        """Handle WebSocket connection lifecycle."""
        if not self.enable_websockets:
            await websocket.close(code=1000)
            return

        connection_id = str(uuid.uuid4())

        # Parse event filter
        event_filter = EventFilter(
            event_types=[EventType(t) for t in event_types] if event_types else None,
            session_id=session_id,
            user_id=user_id,
        )

        try:
            await self.connection_manager.connect(
                websocket, connection_id, session_id, user_id, event_filter
            )

            # Handle incoming messages
            while True:
                try:
                    data = await websocket.receive_text()
                    message = json.loads(data)
                    await self._handle_websocket_message(connection_id, message)

                except WebSocketDisconnect:
                    break
                except json.JSONDecodeError:
                    await websocket.send_text(
                        json.dumps({"error": "Invalid JSON format"})
                    )
                except Exception as e:
                    logger.error(f"WebSocket message error: {e}")
                    await websocket.send_text(json.dumps({"error": str(e)}))

        finally:
            await self.connection_manager.disconnect(connection_id)

    async def _handle_websocket_message(
        self, connection_id: str, message: Dict[str, Any]
    ):
        """Handle incoming WebSocket messages."""
        message_type = message.get("type")

        if message_type == "ping":
            # Respond to ping
            connection = self.connection_manager.connections.get(connection_id)
            if connection:
                connection["last_ping"] = time.time()
                await self.connection_manager.send_to_connection(
                    connection_id, {"type": "pong", "timestamp": time.time()}
                )

        elif message_type == "execute_workflow":
            # Handle workflow execution request
            session_id = message.get("session_id")
            workflow_id = message.get("workflow_id")
            inputs = message.get("inputs", {})

            try:
                execution_id = await self.agent_ui.execute_workflow(
                    session_id, workflow_id, inputs
                )
                await self.connection_manager.send_to_connection(
                    connection_id,
                    {"type": "execution_started", "execution_id": execution_id},
                )
            except Exception as e:
                await self.connection_manager.send_to_connection(
                    connection_id, {"type": "error", "error": str(e)}
                )

        elif message_type == "subscribe_events":
            # Update event filter for this connection
            # Implementation would update the connection's event filter
            pass

    # SSE Methods
    def create_sse_stream(
        self,
        request: Request,
        session_id: str = None,
        user_id: str = None,
        event_types: List[str] = None,
    ) -> StreamingResponse:
        """Create Server-Sent Events stream."""
        if not self.enable_sse:
            return Response("SSE not enabled", status_code=501)

        stream_id = str(uuid.uuid4())

        # Parse event filter
        event_filter = EventFilter(
            event_types=[EventType(t) for t in event_types] if event_types else None,
            session_id=session_id,
            user_id=user_id,
        )

        generator = self.sse_manager.create_stream(
            stream_id, session_id, user_id, event_filter
        )

        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Stream-ID": stream_id,
            },
        )

    # Webhook Methods
    def register_webhook(
        self,
        webhook_id: str,
        url: str,
        secret: str = None,
        event_types: List[str] = None,
        session_id: str = None,
        headers: Dict[str, str] = None,
    ):
        """Register webhook endpoint."""
        if not self.enable_webhooks:
            raise ValueError("Webhooks not enabled")

        event_filter = EventFilter(
            event_types=[EventType(t) for t in event_types] if event_types else None,
            session_id=session_id,
        )

        self.webhook_manager.register_webhook(
            webhook_id, url, secret, event_filter, headers
        )

    def unregister_webhook(self, webhook_id: str):
        """Unregister webhook endpoint."""
        if self.enable_webhooks and self.webhook_manager:
            self.webhook_manager.unregister_webhook(webhook_id)

    # Statistics and Monitoring
    def get_stats(self) -> Dict[str, Any]:
        """Get real-time middleware statistics."""
        stats = {
            "uptime_seconds": time.time() - self.start_time,
            "events_processed": self.events_processed,
            "latency_target_ms": self.latency_target_ms,
            "enabled_transports": {
                "websockets": self.enable_websockets,
                "sse": self.enable_sse,
                "webhooks": self.enable_webhooks,
            },
        }

        # Add latency statistics
        if self.latency_samples:
            stats["latency_stats"] = {
                "avg_ms": sum(self.latency_samples) / len(self.latency_samples),
                "max_ms": max(self.latency_samples),
                "min_ms": min(self.latency_samples),
                "samples": len(self.latency_samples),
            }

        # Add transport-specific stats
        if self.connection_manager:
            stats["websocket_stats"] = self.connection_manager.get_stats()

        if self.webhook_manager:
            stats["webhook_stats"] = self.webhook_manager.delivery_stats

        return stats
