"""Multi-workflow API gateway for managing multiple Kailash workflows.

This module provides a unified API server that can host multiple workflows
with dynamic routing, MCP integration, and centralized management.

Design Philosophy:
    The gateway acts as a single entry point for all workflow executions,
    providing unified authentication, monitoring, and resource management.
    It supports both embedded workflows (running in-process) and proxied
    workflows (running in separate processes).

Example:
    >>> # Basic usage with multiple workflows
    >>> from kailash.api import WorkflowAPIGateway
    >>> from kailash.workflow import Workflow

    >>> # Create workflows
    >>> sales_workflow = Workflow("sales_pipeline")
    >>> analytics_workflow = Workflow("analytics_pipeline")

    >>> # Create gateway
    >>> gateway = WorkflowAPIGateway(
    ...     title="Company API Gateway",
    ...     description="Unified API for all workflows"
    ... )

    >>> # Register workflows
    >>> gateway.register_workflow("sales", sales_workflow)
    >>> gateway.register_workflow("analytics", analytics_workflow)

    >>> # Start server
    >>> gateway.run(port=8000)  # doctest: +SKIP

    >>> # With MCP integration
    >>> from kailash.api.mcp_integration import MCPIntegration

    >>> # Add MCP server
    >>> mcp = MCPIntegration("tools_server")
    >>> gateway.register_mcp_server("tools", mcp)

    >>> # With proxied workflows
    >>> # Proxy to external workflow service
    >>> gateway.proxy_workflow(
    ...     "ml_pipeline",
    ...     "http://ml-service:8080",
    ...     health_check="/health"
    ... )
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..workflow import Workflow
from .workflow_api import WorkflowAPI

logger = logging.getLogger(__name__)


class WorkflowRegistration(BaseModel):
    """Registration details for a workflow."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    type: str = Field(description="embedded or proxied")
    workflow: Optional[Workflow] = None
    proxy_url: Optional[str] = None
    health_check: Optional[str] = None
    description: Optional[str] = None
    version: str = "1.0.0"
    tags: List[str] = Field(default_factory=list)


class WorkflowAPIGateway:
    """Unified API gateway for multiple Kailash workflows.

    This gateway provides:
    - Dynamic workflow registration
    - Unified routing with prefix-based paths
    - MCP server integration
    - Health monitoring
    - Resource management
    - WebSocket support for real-time updates

    Attributes:
        app: FastAPI application instance
        workflows: Registry of all registered workflows
        executor: Thread pool for synchronous execution
        mcp_servers: Registry of MCP servers
    """

    def __init__(
        self,
        title: str = "Kailash Workflow Gateway",
        description: str = "Unified API for Kailash workflows",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: List[str] = None,
    ):
        """Initialize the API gateway.

        Args:
            title: API title for documentation
            description: API description
            version: API version
            max_workers: Maximum thread pool workers
            cors_origins: Allowed CORS origins
        """
        self.workflows: Dict[str, WorkflowRegistration] = {}
        self.mcp_servers: Dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Create FastAPI app with lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            yield
            # Shutdown
            logger.info("Shutting down gateway")
            self.executor.shutdown(wait=True)

        self.app = FastAPI(
            title=title, description=description, version=version, lifespan=lifespan
        )

        # Add CORS middleware
        if cors_origins:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        # Register root endpoints
        self._register_root_endpoints()

    def _register_root_endpoints(self):
        """Register gateway-level endpoints."""

        @self.app.get("/")
        async def root():
            """Gateway information."""
            return {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
            }

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
            """Gateway health check."""
            health_status = {"status": "healthy", "workflows": {}, "mcp_servers": {}}

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
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates."""
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_json()
                    # Handle WebSocket messages
                    if data.get("type") == "subscribe":
                        # TODO: Implement subscription logic for workflow
                        data.get("workflow")
                    await websocket.send_json(
                        {"type": "ack", "message": "Message received"}
                    )
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                await websocket.close()

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: Optional[str] = None,
        version: str = "1.0.0",
        tags: List[str] = None,
        **kwargs,
    ):
        """Register an embedded workflow.

        Args:
            name: Unique workflow identifier
            workflow: Workflow instance
            description: Workflow description
            version: Workflow version
            tags: Workflow tags for organization
            **kwargs: Additional WorkflowAPI parameters
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create WorkflowAPI wrapper
        workflow_api = WorkflowAPI(
            workflow=workflow,
            app_name=f"{name} Workflow API",
            version=version,
            description=description,
        )

        # Mount the workflow app as a sub-application
        self.app.mount(f"/{name}", workflow_api.app)

        # Register workflow
        self.workflows[name] = WorkflowRegistration(
            name=name,
            type="embedded",
            workflow=workflow,
            description=description or workflow.name,
            version=version,
            tags=tags or [],
        )

        logger.info(f"Registered embedded workflow: {name}")

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        health_check: str = "/health",
        description: Optional[str] = None,
        version: str = "1.0.0",
        tags: List[str] = None,
    ):
        """Register a proxied workflow.

        Args:
            name: Unique workflow identifier
            proxy_url: URL of the workflow service
            health_check: Health check endpoint path
            description: Workflow description
            version: Workflow version
            tags: Workflow tags
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # TODO: Implement proxy routing
        # This would use httpx or similar to forward requests

        self.workflows[name] = WorkflowRegistration(
            name=name,
            type="proxied",
            proxy_url=proxy_url,
            health_check=health_check,
            description=description,
            version=version,
            tags=tags or [],
        )

        logger.info(f"Registered proxied workflow: {name} -> {proxy_url}")

    def register_mcp_server(self, name: str, mcp_server: Any):
        """Register an MCP server.

        Args:
            name: Unique MCP server identifier
            mcp_server: MCP server instance
        """
        if name in self.mcp_servers:
            raise ValueError(f"MCP server '{name}' already registered")

        self.mcp_servers[name] = mcp_server

        # TODO: Integrate MCP tools with workflows
        logger.info(f"Registered MCP server: {name}")

    def _get_workflow_endpoints(self, name: str) -> List[str]:
        """Get endpoints for a workflow."""
        reg = self.workflows.get(name)
        if not reg:
            return []

        base_endpoints = [
            f"/{name}/execute",
            f"/{name}/workflow/info",
            f"/{name}/health",
        ]

        if reg.type == "embedded":
            base_endpoints.append(f"/{name}/docs")

        return base_endpoints

    def run(
        self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False, **kwargs
    ):
        """Run the gateway server.

        Args:
            host: Host to bind to
            port: Port to bind to
            reload: Enable auto-reload
            **kwargs: Additional uvicorn parameters
        """
        import uvicorn

        uvicorn.run(self.app, host=host, port=port, reload=reload, **kwargs)


class WorkflowOrchestrator:
    """Advanced orchestrator for complex workflow scenarios.

    Provides:
    - Workflow chaining and dependencies
    - Conditional routing between workflows
    - Parallel workflow execution
    - Transaction management
    - Event-driven triggers
    """

    def __init__(self, gateway: WorkflowAPIGateway):
        """Initialize orchestrator with a gateway."""
        self.gateway = gateway
        self.chains: Dict[str, List[str]] = {}
        self.dependencies: Dict[str, List[str]] = {}

    def create_chain(self, name: str, workflow_sequence: List[str]):
        """Create a workflow chain.

        Args:
            name: Chain identifier
            workflow_sequence: Ordered list of workflow names
        """
        # Validate all workflows exist
        for workflow in workflow_sequence:
            if workflow not in self.gateway.workflows:
                raise ValueError(f"Workflow '{workflow}' not registered")

        self.chains[name] = workflow_sequence

    async def execute_chain(
        self, chain_name: str, initial_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a workflow chain.

        Args:
            chain_name: Chain to execute
            initial_input: Input for first workflow

        Returns:
            Final output from the chain
        """
        if chain_name not in self.chains:
            raise ValueError(f"Chain '{chain_name}' not found")

        result = initial_input
        for workflow_name in self.chains[chain_name]:
            # Execute workflow with previous result
            # TODO: Implement execution logic
            pass

        return result
