"""Enterprise workflow server implementation.

This module provides EnterpriseWorkflowServer - a renamed and improved version of
EnhancedDurableAPIGateway with full enterprise features enabled by default.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Union

from ..gateway.resource_resolver import ResourceReference, ResourceResolver
from ..gateway.security import SecretManager
from ..resources.registry import ResourceRegistry
from ..runtime.async_local import AsyncLocalRuntime, ExecutionContext
from ..workflow import Workflow
from .durable_workflow_server import DurableWorkflowServer

logger = logging.getLogger(__name__)


class WorkflowNotFoundError(Exception):
    """Raised when workflow is not found."""

    pass


@dataclass
class WorkflowRequest:
    """Enhanced workflow request with resource support."""

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    inputs: Dict[str, Any] = field(default_factory=dict)
    resources: Dict[str, Union[str, ResourceReference]] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "request_id": self.request_id,
            "inputs": self.inputs,
            "resources": {
                k: v if isinstance(v, str) else v.to_dict()
                for k, v in self.resources.items()
            },
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WorkflowResponse:
    """Response from workflow execution."""

    request_id: str
    workflow_id: str
    status: str  # pending, running, completed, failed
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "request_id": self.request_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "execution_time": self.execution_time,
        }


class EnterpriseWorkflowServer(DurableWorkflowServer):
    """Enterprise workflow server with full production features.

    This is the recommended server for production deployments, providing:

    **Core Features:**
    - Multi-workflow hosting with dynamic registration
    - REST API endpoints for workflow execution
    - WebSocket support for real-time updates
    - MCP server integration

    **Durability Features:**
    - Request durability and checkpointing
    - Automatic deduplication
    - Event sourcing for audit trail
    - Long-running request support
    - Recovery mechanisms

    **Enterprise Features:**
    - Resource reference resolution for non-serializable objects
    - Integration with ResourceRegistry for shared resources
    - Secret management for credentials
    - Async workflow execution support
    - Health checks for resources
    - Security integrations
    - Monitoring and metrics

    This server enables all features by default but can be configured
    to disable specific capabilities for development or testing.
    """

    def __init__(
        self,
        title: str = "Kailash Enterprise Workflow Server",
        description: str = "Enterprise workflow server with full production features",
        version: str = "1.0.0",
        max_workers: int = 20,
        cors_origins: Optional[list[str]] = None,
        # Durability configuration (enabled by default)
        enable_durability: bool = True,
        durability_opt_in: bool = False,  # Enterprise default: always on
        # Enterprise feature configuration
        resource_registry: Optional[ResourceRegistry] = None,
        secret_manager: Optional[SecretManager] = None,
        enable_async_execution: bool = True,
        enable_health_checks: bool = True,
        enable_resource_management: bool = True,
        **kwargs,
    ):
        """Initialize enterprise workflow server."""
        super().__init__(
            title=title,
            description=description,
            version=version,
            max_workers=max_workers,
            cors_origins=cors_origins,
            enable_durability=enable_durability,
            durability_opt_in=durability_opt_in,
            **kwargs,
        )

        # Enterprise components
        self.resource_registry = resource_registry or ResourceRegistry()
        self.secret_manager = secret_manager or SecretManager()
        self.enable_async_execution = enable_async_execution
        self.enable_health_checks = enable_health_checks
        self.enable_resource_management = enable_resource_management

        # Resource tracking
        self._workflow_resources: Dict[str, Set[str]] = {}
        self._async_runtime: Optional[AsyncLocalRuntime] = None
        self._resource_resolver: Optional[ResourceResolver] = None

        # Initialize enterprise components
        self._initialize_enterprise_features()

        # Register enterprise endpoints
        self._register_enterprise_endpoints()

    def _initialize_enterprise_features(self):
        """Initialize enterprise feature components."""
        if self.enable_async_execution:
            self._async_runtime = AsyncLocalRuntime()

        if self.enable_resource_management:
            self._resource_resolver = ResourceResolver(
                resource_registry=self.resource_registry,
                secret_manager=self.secret_manager,
            )

        logger.info("Enterprise features initialized")

    def _register_enterprise_endpoints(self):
        """Register enterprise-specific endpoints."""

        @self.app.get("/enterprise/features")
        async def get_enterprise_features():
            """Get enabled enterprise features."""
            return {
                "durability": self.enable_durability,
                "async_execution": self.enable_async_execution,
                "resource_management": self.enable_resource_management,
                "health_checks": self.enable_health_checks,
                "secret_management": True,
                "features": [
                    "request_durability",
                    "resource_registry",
                    "secret_management",
                    "async_workflows",
                    "health_monitoring",
                    "resource_resolution",
                    "enterprise_security",
                ],
            }

        @self.app.get("/enterprise/resources")
        async def list_resources():
            """List all registered resources."""
            if not self.enable_resource_management:
                return {"error": "Resource management disabled"}

            return {
                "resources": list(self.resource_registry.list_resources()),
                "total": len(self.resource_registry.list_resources()),
            }

        @self.app.get("/enterprise/resources/{resource_name}")
        async def get_resource_info(resource_name: str):
            """Get information about a specific resource."""
            if not self.enable_resource_management:
                return {"error": "Resource management disabled"}

            try:
                resource = await self.resource_registry.get_resource(resource_name)
                health = await self.resource_registry.check_health(resource_name)

                return {
                    "name": resource_name,
                    "type": type(resource).__name__,
                    "health": health,
                    "workflows": list(
                        self._workflow_resources.get(resource_name, set())
                    ),
                }
            except (KeyError, Exception) as e:
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Resource not found")

        @self.app.get("/enterprise/health")
        async def enterprise_health_check():
            """Comprehensive enterprise health check."""
            health_status = {
                "status": "healthy",
                "server_type": "enterprise_workflow_server",
                "timestamp": datetime.now(UTC).isoformat(),
                "components": {},
            }

            # Check base server health
            base_health = await self._get_base_health()
            health_status["components"]["base_server"] = base_health

            # Check resource health
            if self.enable_resource_management and self.enable_health_checks:
                resource_health = await self._check_resource_health()
                health_status["components"]["resources"] = resource_health

            # Check async runtime health
            if self.enable_async_execution and self._async_runtime:
                runtime_health = await self._check_runtime_health()
                health_status["components"]["async_runtime"] = runtime_health

            # Check secret manager health
            secret_health = await self._check_secret_manager_health()
            health_status["components"]["secret_manager"] = secret_health

            # Determine overall status
            component_statuses = [
                comp.get("status", "unhealthy")
                for comp in health_status["components"].values()
            ]

            if all(status == "healthy" for status in component_statuses):
                health_status["status"] = "healthy"
            elif any(status == "healthy" for status in component_statuses):
                health_status["status"] = "degraded"
            else:
                health_status["status"] = "unhealthy"

            return health_status

        @self.app.post("/enterprise/workflows/{workflow_id}/execute_async")
        async def execute_workflow_async(workflow_id: str, request: dict):
            """Execute workflow asynchronously with resource resolution."""
            if not self.enable_async_execution:
                from fastapi import HTTPException

                raise HTTPException(status_code=503, detail="Async execution disabled")

            if workflow_id not in self.workflows:
                from fastapi import HTTPException

                raise HTTPException(
                    status_code=404, detail=f"Workflow '{workflow_id}' not found"
                )

            try:
                # Create enhanced request
                workflow_request = WorkflowRequest(
                    inputs=request.get("inputs", {}),
                    resources=request.get("resources", {}),
                    context=request.get("context", {}),
                )

                # Resolve resources if enabled
                resolved_inputs = workflow_request.inputs.copy()
                if self.enable_resource_management and workflow_request.resources:
                    resolved_resources = (
                        await self._resource_resolver.resolve_resources(
                            workflow_request.resources
                        )
                    )
                    resolved_inputs.update(resolved_resources)

                # Execute workflow asynchronously
                workflow_obj = self.workflows[workflow_id].workflow
                execution_context = ExecutionContext(
                    request_id=workflow_request.request_id,
                    workflow_id=workflow_id,
                    metadata=workflow_request.context,
                )

                result = await self._async_runtime.execute_async(
                    workflow_obj,
                    inputs=resolved_inputs,
                    context=execution_context,
                )

                # Create response
                response = WorkflowResponse(
                    request_id=workflow_request.request_id,
                    workflow_id=workflow_id,
                    status="completed",
                    result=result,
                    started_at=workflow_request.timestamp,
                    completed_at=datetime.now(UTC),
                )

                response.execution_time = (
                    response.completed_at - response.started_at
                ).total_seconds()

                return response.to_dict()

            except Exception as e:
                logger.error(f"Async workflow execution failed: {e}")

                error_response = WorkflowResponse(
                    request_id=workflow_request.request_id,
                    workflow_id=workflow_id,
                    status="failed",
                    error=str(e),
                    started_at=workflow_request.timestamp,
                    completed_at=datetime.now(UTC),
                )

                return error_response.to_dict()

    async def _get_base_health(self) -> Dict[str, Any]:
        """Get base server health status."""
        return {
            "status": "healthy",
            "workflows": len(self.workflows),
            "mcp_servers": len(self.mcp_servers),
            "active_requests": (
                len(self.active_requests) if hasattr(self, "active_requests") else 0
            ),
        }

    async def _check_resource_health(self) -> Dict[str, Any]:
        """Check health of all registered resources."""
        resource_health = {"status": "healthy", "resources": {}}

        try:
            for resource_name in self.resource_registry.list_resources():
                try:
                    health = await self.resource_registry.check_health(resource_name)
                    resource_health["resources"][resource_name] = health
                except Exception as e:
                    resource_health["resources"][resource_name] = {
                        "status": "unhealthy",
                        "error": str(e),
                    }
                    resource_health["status"] = "degraded"

        except Exception as e:
            resource_health["status"] = "unhealthy"
            resource_health["error"] = str(e)

        return resource_health

    async def _check_runtime_health(self) -> Dict[str, Any]:
        """Check async runtime health."""
        try:
            # Simple health check - try to access runtime
            if self._async_runtime:
                return {
                    "status": "healthy",
                    "type": type(self._async_runtime).__name__,
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": "Runtime not initialized",
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    async def _check_secret_manager_health(self) -> Dict[str, Any]:
        """Check secret manager health."""
        try:
            # Simple health check for secret manager
            return {
                "status": "healthy",
                "type": type(self.secret_manager).__name__,
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    def register_resource(self, name: str, resource: Any):
        """Register a resource for use in workflows."""
        if not self.enable_resource_management:
            raise RuntimeError("Resource management disabled")

        self.resource_registry.register_factory(name, lambda: resource)
        logger.info(f"Registered enterprise resource: {name}")

    def _register_root_endpoints(self):
        """Override to add enterprise info to root endpoint."""

        # Register the enterprise root endpoint first (before super() to take precedence)
        @self.app.get("/")
        async def root():
            """Server information with enterprise details."""
            base_info = {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
                "type": "enterprise_workflow_server",
            }

            # Add enterprise info
            base_info["enterprise"] = {
                "durability": self.enable_durability,
                "async_execution": self.enable_async_execution,
                "resource_management": self.enable_resource_management,
                "health_checks": self.enable_health_checks,
                "features": [
                    "request_durability",
                    "resource_registry",
                    "secret_management",
                    "async_workflows",
                    "health_monitoring",
                    "resource_resolution",
                    "enterprise_security",
                ],
                "resources": (
                    len(self.resource_registry.list_resources())
                    if self.enable_resource_management
                    else 0
                ),
            }

            return base_info

        # Now call super() to get other endpoints (health, workflows, etc.) but skip root
        # We'll register them manually to avoid route conflicts
        @self.app.get("/workflows")
        async def list_workflows():
            """List all registered workflows."""
            return {
                name: {
                    "type": reg.type,
                    "description": reg.description,
                    "version": reg.version,
                    "tags": reg.tags,
                    "endpoints": self._get_workflow_endpoints(name),
                }
                for name, reg in self.workflows.items()
            }

        @self.app.get("/health")
        async def health_check():
            """Server health check."""
            health_status = {
                "status": "healthy",
                "server_type": "enterprise_workflow_server",
                "workflows": {},
                "mcp_servers": {},
            }

            # Check workflow health
            for name, reg in self.workflows.items():
                if reg.type == "embedded":
                    health_status["workflows"][name] = "healthy"
                else:
                    # TODO: Implement proxy health check
                    health_status["workflows"][name] = "unknown"

            # Check MCP server health
            for name, server in self.mcp_servers.items():
                # TODO: Implement MCP health check
                health_status["mcp_servers"][name] = "unknown"

            return health_status

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket):
            """WebSocket for real-time updates."""
            from fastapi import WebSocket

            await websocket.accept()
            try:
                while True:
                    # Basic WebSocket echo - subclasses can override
                    data = await websocket.receive_text()
                    await websocket.send_text(f"Echo: {data}")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                await websocket.close()
