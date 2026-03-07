"""Integration of durable request handling with API Gateway.

This module provides:
- Durable API Gateway with checkpointing
- Automatic request deduplication
- Event sourcing integration
- Backward compatibility with existing gateway
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from kailash.api.gateway import WorkflowAPIGateway

from .checkpoint_manager import CheckpointManager
from .deduplicator import RequestDeduplicator
from .durable_request import DurableRequest, RequestMetadata, RequestState
from .event_store import (
    EventStore,
    EventType,
    performance_metrics_projection,
    request_state_projection,
)

logger = logging.getLogger(__name__)


class DurableAPIGateway(WorkflowAPIGateway):
    """API Gateway with durable request handling.

    Extends the standard gateway with:
    - Request durability and checkpointing
    - Automatic deduplication
    - Event sourcing for audit trail
    - Long-running request support
    """

    def __init__(
        self,
        title: str = "Kailash Durable Workflow Gateway",
        description: str = "Durable API for Kailash workflows",
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
        """Initialize durable API gateway."""
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
        self.deduplicator = deduplicator or RequestDeduplicator()
        self.event_store = event_store or EventStore()

        # Track active requests
        self.active_requests: Dict[str, DurableRequest] = {}

        # Register event projections
        self.event_store.register_projection(
            "request_states",
            request_state_projection,
        )
        self.event_store.register_projection(
            "performance_metrics",
            performance_metrics_projection,
        )

        # Add durability middleware if enabled
        if self.enable_durability:
            self._add_durability_middleware()

        # Register durability endpoints
        self._register_durability_endpoints()

        # Track background tasks
        self._background_tasks: List[asyncio.Task] = []

    def _add_durability_middleware(self):
        """Add middleware for durable request handling."""

        @self.app.middleware("http")
        async def durability_middleware(request: Request, call_next):
            """Process requests with durability support."""
            # Check if durability is enabled for this endpoint
            if not self._should_use_durability(request):
                return await call_next(request)

            # Extract request metadata
            metadata = await self._extract_metadata(request)

            # Check for duplicate request
            duplicate_response = await self._check_duplicate(request, metadata)
            if duplicate_response:
                return duplicate_response

            # Create durable request
            durable_request = DurableRequest(
                metadata=metadata,
                checkpoint_manager=self.checkpoint_manager,
            )

            # Track active request
            self.active_requests[durable_request.id] = durable_request

            try:
                # Record request creation
                await self.event_store.append(
                    EventType.REQUEST_CREATED,
                    durable_request.id,
                    {
                        "method": metadata.method,
                        "path": metadata.path,
                        "idempotency_key": metadata.idempotency_key,
                    },
                )

                # Execute with durability
                response = await self._execute_durable_request(
                    durable_request,
                    request,
                    call_next,
                )

                # Cache response for deduplication
                await self._cache_response(request, metadata, response)

                return response

            finally:
                # Clean up active request
                del self.active_requests[durable_request.id]

    def _should_use_durability(self, request: Request) -> bool:
        """Check if durability should be used for this request."""
        if not self.enable_durability:
            return False

        if self.durability_opt_in:
            # Check for durability header or query param
            use_durability = (
                request.headers.get("X-Durable-Request", "").lower() == "true"
                or request.query_params.get("durable", "").lower() == "true"
            )
            return use_durability

        # Durability enabled for all requests
        return True

    async def _extract_metadata(self, request: Request) -> RequestMetadata:
        """Extract metadata from HTTP request."""
        # Get body if present
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.json()
            except Exception:
                pass

        # Extract user/tenant from headers or auth
        user_id = request.headers.get("X-User-ID")
        tenant_id = request.headers.get("X-Tenant-ID")

        # Get idempotency key
        idempotency_key = request.headers.get("Idempotency-Key") or request.headers.get(
            "X-Idempotency-Key"
        )

        return RequestMetadata(
            request_id=f"req_{request.headers.get('X-Request-ID', '')}",
            method=request.method,
            path=str(request.url.path),
            headers={
                k: v
                for k, v in request.headers.items()
                if k.lower()
                not in (
                    "authorization",
                    "cookie",
                    "x-api-key",
                    "x-auth-token",
                    "proxy-authorization",
                    "set-cookie",
                )
            },
            query_params=dict(request.query_params),
            body=body,
            client_ip=request.client.host if request.client else "0.0.0.0",
            user_id=user_id,
            tenant_id=tenant_id,
            idempotency_key=idempotency_key,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def _check_duplicate(
        self,
        request: Request,
        metadata: RequestMetadata,
    ) -> Optional[Response]:
        """Check for duplicate request."""
        duplicate = await self.deduplicator.check_duplicate(
            method=metadata.method,
            path=metadata.path,
            query_params=metadata.query_params,
            body=metadata.body,
            headers=metadata.headers,
            idempotency_key=metadata.idempotency_key,
        )

        if duplicate:
            # Record deduplication hit
            await self.event_store.append(
                EventType.DEDUPLICATION_HIT,
                metadata.request_id,
                {
                    "cached_response": True,
                    "cache_age_seconds": duplicate["cache_age_seconds"],
                },
            )

            return JSONResponse(
                content=duplicate["data"],
                status_code=duplicate["status_code"],
                headers={
                    **duplicate["headers"],
                    "X-Cached-Response": "true",
                    "X-Cache-Age": str(duplicate["cache_age_seconds"]),
                },
            )

        return None

    async def _execute_durable_request(
        self,
        durable_request: DurableRequest,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """Execute request with durability."""
        import time

        start_time = time.monotonic()
        try:
            response = await call_next(request)

            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

            # Record completion with actual duration
            await self.event_store.append(
                EventType.REQUEST_COMPLETED,
                durable_request.id,
                {
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            )

            return response

        except Exception as e:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            # Record failure
            await self.event_store.append(
                EventType.REQUEST_FAILED,
                durable_request.id,
                {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms,
                },
            )
            raise

    async def _cache_response(
        self,
        request: Request,
        metadata: RequestMetadata,
        response: Response,
    ):
        """Cache response for deduplication."""
        # Only cache successful responses
        if response.status_code >= 400:
            return

        # Extract response data
        response_data = {}
        if hasattr(response, "body"):
            try:
                # Decode response body
                import json

                response_data = json.loads(response.body)
            except (json.JSONDecodeError, Exception):
                pass

        await self.deduplicator.cache_response(
            method=metadata.method,
            path=metadata.path,
            query_params=metadata.query_params,
            body=metadata.body,
            headers=metadata.headers,
            idempotency_key=metadata.idempotency_key,
            response_data=response_data,
            status_code=response.status_code,
            response_headers=(
                dict(response.headers) if hasattr(response, "headers") else {}
            ),
        )

    def _register_durability_endpoints(self):
        """Register durability-specific endpoints."""

        @self.app.get("/durability/status")
        async def durability_status():
            """Get durability system status."""
            return {
                "enabled": self.enable_durability,
                "opt_in": self.durability_opt_in,
                "active_requests": len(self.active_requests),
                "checkpoint_stats": self.checkpoint_manager.get_stats(),
                "deduplication_stats": self.deduplicator.get_stats(),
                "event_store_stats": self.event_store.get_stats(),
            }

        @self.app.get("/durability/requests/{request_id}")
        async def get_request_status(request_id: str):
            """Get status of a durable request."""
            # Check active requests
            if request_id in self.active_requests:
                return self.active_requests[request_id].get_status()

            # Check event store for historical data
            events = await self.event_store.get_events(request_id)
            if not events:
                raise HTTPException(status_code=404, detail="Request not found")

            # Build status from events
            status = {
                "request_id": request_id,
                "events": len(events),
                "first_event": events[0].timestamp.isoformat(),
                "last_event": events[-1].timestamp.isoformat(),
                "state": "unknown",
            }

            # Determine final state
            for event in reversed(events):
                if event.event_type == EventType.REQUEST_COMPLETED:
                    status["state"] = "completed"
                    break
                elif event.event_type == EventType.REQUEST_FAILED:
                    status["state"] = "failed"
                    break
                elif event.event_type == EventType.REQUEST_CANCELLED:
                    status["state"] = "cancelled"
                    break

            return status

        @self.app.get("/durability/requests/{request_id}/events")
        async def get_request_events(request_id: str):
            """Get all events for a request."""
            events = await self.event_store.get_events(request_id)
            return {
                "request_id": request_id,
                "event_count": len(events),
                "events": [e.to_dict() for e in events],
            }

        @self.app.post("/durability/requests/{request_id}/resume")
        async def resume_request(request_id: str, checkpoint_id: Optional[str] = None):
            """Resume a failed or incomplete request from its last checkpoint."""
            # Load request events to reconstruct state
            events = await self.event_store.get_events(request_id)
            if not events:
                raise HTTPException(
                    status_code=404, detail=f"No events found for request {request_id}"
                )

            # Find the latest checkpoint or creation event
            last_checkpoint = None
            request_metadata = None
            for event in events:
                event_data = event.to_dict()
                if event_data.get("event_type") == EventType.REQUEST_CREATED:
                    request_metadata = event_data.get("data", {})
                if event_data.get("event_type") == EventType.CHECKPOINT_CREATED:
                    if (
                        checkpoint_id is None
                        or event_data.get("data", {}).get("checkpoint_id")
                        == checkpoint_id
                    ):
                        last_checkpoint = event_data

            if request_metadata is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No creation event found for request {request_id}",
                )

            # Check if request already completed
            for event in events:
                event_data = event.to_dict()
                if event_data.get("event_type") == EventType.REQUEST_COMPLETED:
                    return {
                        "status": "already_completed",
                        "request_id": request_id,
                        "message": "Request has already completed successfully",
                    }

            # Record resumption event
            await self.event_store.append(
                EventType.REQUEST_RESUMED,
                request_id,
                {
                    "resumed_from": (
                        last_checkpoint.get("data", {}).get("checkpoint_id")
                        if last_checkpoint
                        else "start"
                    ),
                    "resumed_at": datetime.now(UTC).isoformat(),
                },
            )

            return {
                "status": "resumed",
                "request_id": request_id,
                "resumed_from_checkpoint": (
                    last_checkpoint.get("data", {}).get("checkpoint_id")
                    if last_checkpoint
                    else None
                ),
                "original_metadata": request_metadata,
            }

        @self.app.delete("/durability/requests/{request_id}")
        async def cancel_request(request_id: str):
            """Cancel an active request."""
            if request_id not in self.active_requests:
                raise HTTPException(status_code=404, detail="Active request not found")

            durable_request = self.active_requests[request_id]
            await durable_request.cancel()

            return {"status": "cancelled", "request_id": request_id}

        @self.app.get("/durability/projections/{name}")
        async def get_projection(name: str):
            """Get current state of a projection."""
            projection = self.event_store.get_projection(name)
            if projection is None:
                raise HTTPException(status_code=404, detail="Projection not found")

            return {
                "name": name,
                "state": projection,
            }

    async def close(self, shutdown_timeout: float = 30.0):
        """Close the durable gateway and cleanup resources.

        Args:
            shutdown_timeout: Maximum seconds to wait for active requests
                to complete before force-closing.
        """
        import time

        # Wait for active requests to complete with timeout
        if self.active_requests:
            logger.info(
                f"Graceful shutdown: waiting for {len(self.active_requests)} "
                f"active requests (timeout={shutdown_timeout}s)"
            )
            start = time.monotonic()
            while (
                self.active_requests and (time.monotonic() - start) < shutdown_timeout
            ):
                await asyncio.sleep(0.5)

            if self.active_requests:
                remaining = list(self.active_requests.keys())
                logger.warning(
                    f"Shutdown timeout reached with {len(remaining)} requests "
                    f"still active: {remaining[:5]}"
                )
                # Cancel remaining requests
                for req_id, durable_request in list(self.active_requests.items()):
                    try:
                        await durable_request.cancel()
                    except Exception as e:
                        logger.error(f"Failed to cancel request {req_id}: {e}")

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close components
        await self.checkpoint_manager.close()
        await self.deduplicator.close()
        await self.event_store.close()
        logger.info("Durable gateway closed")
