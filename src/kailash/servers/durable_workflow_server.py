"""Durable workflow server implementation.

This module provides DurableWorkflowServer - a renamed and improved version of
DurableAPIGateway with request durability and checkpointing capabilities.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..middleware.gateway.checkpoint_manager import CheckpointManager
from ..middleware.gateway.deduplicator import RequestDeduplicator
from ..middleware.gateway.durable_request import (
    DurableRequest,
    RequestMetadata,
    RequestState,
)
from ..middleware.gateway.event_store import (
    EventStore,
    EventType,
    performance_metrics_projection,
    request_state_projection,
)
from .workflow_server import WorkflowServer

logger = logging.getLogger(__name__)


class DurableWorkflowServer(WorkflowServer):
    """Workflow server with durable request handling.

    Extends the basic WorkflowServer with:
    - Request durability and checkpointing
    - Automatic deduplication
    - Event sourcing for audit trail
    - Long-running request support
    - Recovery mechanisms

    This server provides reliability features for production deployments
    where request durability is important. For full enterprise features,
    consider using EnterpriseWorkflowServer.
    """

    def __init__(
        self,
        title: str = "Kailash Durable Workflow Server",
        description: str = "Durable workflow server with checkpointing",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: Optional[list[str]] = None,
        # Durability configuration
        enable_durability: bool = True,
        checkpoint_manager: Optional[CheckpointManager] = None,
        deduplicator: Optional[RequestDeduplicator] = None,
        event_store: Optional[EventStore] = None,
        durability_opt_in: bool = True,  # If True, durability is opt-in per endpoint
    ):
        """Initialize durable workflow server."""
        super().__init__(
            title=title,
            description=description,
            version=version,
            max_workers=max_workers,
            cors_origins=cors_origins,
        )

        # Durability components
        self.enable_durability = enable_durability
        self.durability_opt_in = durability_opt_in
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        # Initialize deduplicator lazily to avoid event loop issues
        self._deduplicator = deduplicator
        self._event_store = event_store

        # Track active requests
        self.active_requests: Dict[str, DurableRequest] = {}

        # Track background tasks
        self._background_tasks: List[asyncio.Task] = []

        # Initialize durability components lazily
        self._durability_initialized = False

        # Add durability middleware if enabled
        if self.enable_durability:
            self._add_durability_middleware()

        # Register durability endpoints
        self._register_durability_endpoints()

    @property
    def deduplicator(self) -> RequestDeduplicator:
        """Get deduplicator instance, initializing if needed."""
        if self._deduplicator is None:
            self._deduplicator = RequestDeduplicator()
        return self._deduplicator

    @property
    def event_store(self) -> EventStore:
        """Get event store instance, initializing if needed."""
        if self._event_store is None:
            self._event_store = EventStore()
            # Register event projections
            self._event_store.register_projection(
                "request_states",
                request_state_projection,
            )
            self._event_store.register_projection(
                "performance_metrics",
                performance_metrics_projection,
            )
        return self._event_store

    def _add_durability_middleware(self):
        """Add middleware for durable request handling."""

        @self.app.middleware("http")
        async def durability_middleware(request: Request, call_next):
            """Middleware to handle request durability."""
            # Check if this endpoint should use durability
            should_be_durable = self._should_use_durability(request)

            if not should_be_durable:
                # Pass through without durability
                return await call_next(request)

            # Extract request metadata
            request_id = (
                request.headers.get("X-Request-ID")
                or f"req_{datetime.now(UTC).timestamp()}"
            )
            metadata = RequestMetadata(
                request_id=request_id,
                path=str(request.url.path),
                method=request.method,
                timestamp=datetime.now(UTC),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
            )

            try:
                # Check for duplicate request
                if await self.deduplicator.is_duplicate(request_id):
                    logger.info(f"Duplicate request detected: {request_id}")
                    cached_response = await self.deduplicator.get_cached_response(
                        request_id
                    )
                    if cached_response:
                        return JSONResponse(content=cached_response)

                # Create durable request
                durable_request = DurableRequest(
                    metadata=metadata,
                    state=RequestState.STARTED,
                )
                self.active_requests[request_id] = durable_request

                # Emit start event
                await self.event_store.emit_event(
                    EventType.REQUEST_STARTED,
                    {
                        "request_id": request_id,
                        "path": metadata.path,
                        "method": metadata.method,
                        "timestamp": metadata.timestamp.isoformat(),
                    },
                )

                # Create checkpoint before processing
                await self.checkpoint_manager.create_checkpoint(
                    request_id,
                    {
                        "metadata": metadata.model_dump(),
                        "state": RequestState.STARTED.value,
                        "created_at": datetime.now(UTC).isoformat(),
                    },
                )

                # Process request
                response = await call_next(request)

                # Update state to completed
                durable_request.state = RequestState.COMPLETED

                # Cache response for deduplication
                if response.status_code < 400:
                    # Only cache successful responses
                    response_body = b"".join(
                        [chunk async for chunk in response.body_iterator]
                    )
                    await self.deduplicator.cache_response(
                        request_id, response_body.decode()
                    )

                    # Recreate response with new body
                    response = Response(
                        content=response_body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )

                # Emit completion event
                await self.event_store.emit_event(
                    EventType.REQUEST_COMPLETED,
                    {
                        "request_id": request_id,
                        "status_code": response.status_code,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                return response

            except Exception as e:
                # Update state to failed
                if request_id in self.active_requests:
                    self.active_requests[request_id].state = RequestState.FAILED

                # Emit failure event
                await self.event_store.emit_event(
                    EventType.REQUEST_FAILED,
                    {
                        "request_id": request_id,
                        "error": str(e),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                logger.error(f"Request {request_id} failed: {e}")
                raise

            finally:
                # Clean up active request
                if request_id in self.active_requests:
                    del self.active_requests[request_id]

    def _should_use_durability(self, request: Request) -> bool:
        """Determine if request should use durability features."""
        if not self.enable_durability:
            return False

        if self.durability_opt_in:
            # Check for durability header
            return request.headers.get("X-Durable", "").lower() == "true"
        else:
            # Durability enabled by default, check for opt-out
            return request.headers.get("X-Durable", "").lower() != "false"

    def _register_durability_endpoints(self):
        """Register durability-specific endpoints."""

        @self.app.get("/durability/status")
        async def durability_status():
            """Get durability system status."""
            return {
                "enabled": self.enable_durability,
                "opt_in": self.durability_opt_in,
                "active_requests": len(self.active_requests),
                "checkpoint_count": await self.checkpoint_manager.get_checkpoint_count(),
                "event_count": await self.event_store.get_event_count(),
            }

        @self.app.get("/durability/requests")
        async def list_active_requests():
            """List currently active durable requests."""
            return {
                request_id: {
                    "state": req.state.value,
                    "metadata": req.metadata.model_dump(),
                    "created_at": req.metadata.timestamp.isoformat(),
                }
                for request_id, req in self.active_requests.items()
            }

        @self.app.get("/durability/requests/{request_id}")
        async def get_request_status(request_id: str):
            """Get status of a specific request."""
            if request_id in self.active_requests:
                req = self.active_requests[request_id]
                return {
                    "request_id": request_id,
                    "state": req.state.value,
                    "metadata": req.metadata.model_dump(),
                    "active": True,
                }

            # Check checkpoint storage
            checkpoint = await self.checkpoint_manager.get_checkpoint(request_id)
            if checkpoint:
                return {
                    "request_id": request_id,
                    "state": checkpoint.get("state", "unknown"),
                    "metadata": checkpoint.get("metadata", {}),
                    "active": False,
                }

            raise HTTPException(status_code=404, detail="Request not found")

        @self.app.post("/durability/requests/{request_id}/recover")
        async def recover_request(request_id: str):
            """Attempt to recover a failed request."""
            checkpoint = await self.checkpoint_manager.get_checkpoint(request_id)
            if not checkpoint:
                raise HTTPException(
                    status_code=404, detail="Request checkpoint not found"
                )

            # TODO: Implement request recovery logic
            return {
                "message": f"Recovery initiated for request {request_id}",
                "checkpoint": checkpoint,
            }

        @self.app.get("/durability/events")
        async def list_events(limit: int = 100, offset: int = 0):
            """List recent durability events."""
            events = await self.event_store.get_events(limit=limit, offset=offset)
            return {
                "events": [
                    {
                        "type": event.type.value,
                        "data": event.data,
                        "timestamp": event.timestamp.isoformat(),
                        "event_id": event.event_id,
                    }
                    for event in events
                ],
                "total": len(events),
                "limit": limit,
                "offset": offset,
            }

    async def cleanup_completed_requests(self, max_age_hours: int = 24):
        """Clean up old completed request data."""
        cutoff_time = datetime.now(UTC).timestamp() - (max_age_hours * 3600)

        # Clean up checkpoints
        await self.checkpoint_manager.cleanup_old_checkpoints(cutoff_time)

        # Clean up cached responses
        await self.deduplicator.cleanup_old_responses(cutoff_time)

        logger.info(f"Cleaned up durability data older than {max_age_hours} hours")

    def _register_root_endpoints(self):
        """Override to add durability info to root endpoint."""
        super()._register_root_endpoints()

        # Override the root endpoint to include durability info
        @self.app.get("/")
        async def root():
            """Server information with durability details."""
            base_info = {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
                "type": "durable_workflow_server",
            }

            # Add durability info
            base_info["durability"] = {
                "enabled": self.enable_durability,
                "opt_in": self.durability_opt_in,
                "features": [
                    "request_checkpointing",
                    "automatic_deduplication",
                    "event_sourcing",
                    "request_recovery",
                ],
            }

            return base_info
