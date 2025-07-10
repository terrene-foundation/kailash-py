"""API Channel implementation using EnterpriseWorkflowServer."""

import asyncio
import logging
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from ..servers import EnterpriseWorkflowServer
from ..workflow import Workflow
from .base import (
    Channel,
    ChannelConfig,
    ChannelEvent,
    ChannelResponse,
    ChannelStatus,
    ChannelType,
)

logger = logging.getLogger(__name__)


class APIChannel(Channel):
    """HTTP API channel implementation using EnterpriseWorkflowServer.

    This channel provides RESTful API access to workflows and session management
    through the existing EnterpriseWorkflowServer infrastructure.
    """

    def __init__(
        self,
        config: ChannelConfig,
        workflow_server: Optional[EnterpriseWorkflowServer] = None,
    ):
        """Initialize API channel.

        Args:
            config: Channel configuration
            workflow_server: Optional existing workflow server, will create one if not provided
        """
        super().__init__(config)

        # Create or use provided workflow server
        if workflow_server:
            self.workflow_server = workflow_server
        else:
            self.workflow_server = self._create_workflow_server()

        self.app: FastAPI = self.workflow_server.app
        self._server: Optional[uvicorn.Server] = None
        self._server_task: Optional[asyncio.Task] = None

        # Add channel-specific endpoints
        self._setup_channel_endpoints()

        logger.info(
            f"Initialized API channel {self.name} on {config.host}:{config.port}"
        )

    def _create_workflow_server(self) -> EnterpriseWorkflowServer:
        """Create a new workflow server with channel configuration."""
        # Extract server config from channel config
        server_title = self.config.extra_config.get("title", f"{self.name} API Server")
        server_description = self.config.extra_config.get(
            "description", f"API server for {self.name} channel"
        )

        # CORS configuration
        cors_origins = self.config.extra_config.get("cors_origins", ["*"])

        return EnterpriseWorkflowServer(
            title=server_title,
            description=server_description,
            cors_origins=cors_origins,
            enable_durability=self.config.extra_config.get("enable_durability", True),
            enable_resource_management=self.config.extra_config.get(
                "enable_resource_management", True
            ),
            enable_async_execution=self.config.extra_config.get(
                "enable_async_execution", True
            ),
            enable_health_checks=self.config.extra_config.get(
                "enable_health_checks", True
            ),
        )

    def _setup_channel_endpoints(self) -> None:
        """Add channel-specific endpoints to the FastAPI app."""

        @self.app.get("/channel/info")
        async def get_channel_info():
            """Get information about this API channel."""
            return {
                "channel_name": self.name,
                "channel_type": self.channel_type.value,
                "status": self.status.value,
                "config": {
                    "host": self.config.host,
                    "port": self.config.port,
                    "enable_sessions": self.config.enable_sessions,
                    "enable_auth": self.config.enable_auth,
                    "enable_event_routing": self.config.enable_event_routing,
                },
            }

        @self.app.post("/channel/events")
        async def emit_channel_event(request: Request):
            """Emit an event through this channel."""
            try:
                data = await request.json()

                event = ChannelEvent(
                    event_id=data.get(
                        "event_id", f"api_{asyncio.get_event_loop().time()}"
                    ),
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type=data.get("event_type", "api_event"),
                    payload=data.get("payload", {}),
                    session_id=data.get("session_id"),
                    metadata=data.get("metadata", {}),
                )

                await self.emit_event(event)

                return {"status": "success", "event_id": event.event_id}

            except Exception as e:
                logger.error(f"Error emitting channel event: {e}")
                raise HTTPException(status_code=400, detail=str(e))

        @self.app.get("/channel/status")
        async def get_channel_status():
            """Get detailed channel status."""
            return await self.get_status()

        @self.app.get("/channel/health")
        async def get_channel_health():
            """Get channel health check."""
            health = await self.health_check()
            status_code = 200 if health["healthy"] else 503
            return Response(
                content=str(health),
                status_code=status_code,
                media_type="application/json",
            )

    async def start(self) -> None:
        """Start the API channel server."""
        if self.status == ChannelStatus.RUNNING:
            logger.warning(f"API channel {self.name} is already running")
            return

        try:
            self.status = ChannelStatus.STARTING
            self._setup_event_queue()

            # Configure uvicorn server
            config = uvicorn.Config(
                app=self.app,
                host=self.config.host,
                port=self.config.port or 8000,
                log_level="info" if logger.isEnabledFor(logging.INFO) else "warning",
                access_log=False,  # We'll handle our own logging
            )

            self._server = uvicorn.Server(config)

            # Start server in background task
            self._server_task = asyncio.create_task(self._server.serve())

            # Wait a moment for server to start
            await asyncio.sleep(0.1)

            self.status = ChannelStatus.RUNNING

            # Emit startup event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"api_startup_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_started",
                    payload={"host": self.config.host, "port": self.config.port},
                )
            )

            logger.info(
                f"API channel {self.name} started on {self.config.host}:{self.config.port}"
            )

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Failed to start API channel {self.name}: {e}")
            raise

    async def stop(self) -> None:
        """Stop the API channel server."""
        if self.status == ChannelStatus.STOPPED:
            return

        try:
            self.status = ChannelStatus.STOPPING

            # Emit shutdown event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"api_shutdown_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="channel_stopping",
                    payload={},
                )
            )

            # Stop the uvicorn server
            if self._server:
                self._server.should_exit = True

            # Cancel the server task
            if self._server_task and not self._server_task.done():
                self._server_task.cancel()
                try:
                    await self._server_task
                except asyncio.CancelledError:
                    pass

            await self._cleanup()
            self.status = ChannelStatus.STOPPED

            logger.info(f"API channel {self.name} stopped")

        except Exception as e:
            self.status = ChannelStatus.ERROR
            logger.error(f"Error stopping API channel {self.name}: {e}")
            raise

    async def handle_request(self, request: Dict[str, Any]) -> ChannelResponse:
        """Handle a request through the API channel.

        Args:
            request: Request data with workflow execution parameters

        Returns:
            ChannelResponse with execution results
        """
        try:
            workflow_name = request.get("workflow_name")
            if not workflow_name:
                return ChannelResponse(success=False, error="workflow_name is required")

            # Check if workflow exists
            if workflow_name not in self.workflow_server.workflows:
                return ChannelResponse(
                    success=False, error=f"Workflow '{workflow_name}' not found"
                )

            # Execute workflow through server's runtime
            workflow_registration = self.workflow_server.workflows[workflow_name]
            inputs = request.get("inputs", {})

            # Emit request event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"api_request_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="workflow_request",
                    payload={"workflow_name": workflow_name, "inputs": inputs},
                    session_id=request.get("session_id"),
                )
            )

            # Execute workflow
            if workflow_registration.type == "embedded":
                workflow = workflow_registration.workflow
                results, run_id = self.workflow_server.runtime.execute(
                    workflow, parameters=inputs
                )
            else:
                # Handle proxied workflows
                return ChannelResponse(
                    success=False,
                    error="Proxied workflows not yet supported in APIChannel",
                )

            # Emit completion event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"api_completion_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="workflow_completed",
                    payload={
                        "workflow_name": workflow_name,
                        "run_id": run_id,
                        "success": True,
                    },
                    session_id=request.get("session_id"),
                )
            )

            return ChannelResponse(
                success=True,
                data={
                    "results": results,
                    "run_id": run_id,
                    "workflow_name": workflow_name,
                },
                metadata={"channel": self.name, "type": "api"},
            )

        except Exception as e:
            logger.error(f"Error handling API request: {e}")

            # Emit error event
            await self.emit_event(
                ChannelEvent(
                    event_id=f"api_error_{asyncio.get_event_loop().time()}",
                    channel_name=self.name,
                    channel_type=self.channel_type,
                    event_type="workflow_error",
                    payload={"error": str(e), "request": request},
                    session_id=request.get("session_id"),
                )
            )

            return ChannelResponse(
                success=False,
                error=str(e),
                metadata={"channel": self.name, "type": "api"},
            )

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> None:
        """Register a workflow with this API channel.

        Args:
            name: Workflow name
            workflow: Workflow instance
            description: Optional description
            tags: Optional tags
        """
        self.workflow_server.register_workflow(
            name=name, workflow=workflow, description=description, tags=tags
        )
        logger.info(f"Registered workflow '{name}' with API channel {self.name}")

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        health_check: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> None:
        """Register a proxied workflow with this API channel.

        Args:
            name: Workflow name
            proxy_url: URL to proxy requests to
            health_check: Optional health check endpoint
            description: Optional description
            tags: Optional tags
        """
        self.workflow_server.proxy_workflow(
            name=name,
            proxy_url=proxy_url,
            health_check=health_check,
            description=description,
            tags=tags,
        )
        logger.info(
            f"Registered proxied workflow '{name}' with API channel {self.name}"
        )

    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        base_health = await super().health_check()

        # Add API-specific health checks
        api_checks = {
            "server_running": self._server is not None
            and not (self._server_task and self._server_task.done()),
            "workflows_registered": len(self.workflow_server.workflows) > 0,
            "enterprise_features": {
                "durability": self.workflow_server.enable_durability,
                "resource_management": self.workflow_server.enable_resource_management,
                "async_execution": self.workflow_server.enable_async_execution,
                "health_checks": self.workflow_server.enable_health_checks,
            },
        }

        all_healthy = base_health["healthy"] and all(api_checks.values())

        return {
            **base_health,
            "healthy": all_healthy,
            "checks": {**base_health["checks"], **api_checks},
            "workflows": list(self.workflow_server.workflows.keys()),
            "enterprise_info": api_checks["enterprise_features"],
        }
