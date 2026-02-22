"""Basic workflow server implementation.

This module provides WorkflowServer - a renamed and improved version of
WorkflowAPIGateway with clearer naming and better organization.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..api.workflow_api import WorkflowAPI
from ..workflow import Workflow

logger = logging.getLogger(__name__)


class WorkflowRegistration(BaseModel):
    """Registration details for a workflow."""

    model_config = {"arbitrary_types_allowed": True}

    name: str
    type: str = Field(description="embedded or proxied")
    workflow: Workflow | None = None
    proxy_url: str | None = None
    health_check: str | None = None
    description: str | None = None
    version: str = "1.0.0"
    tags: list[str] = Field(default_factory=list)


class WorkflowServer:
    """Basic workflow server for hosting multiple Kailash workflows.

    This server provides:
    - Multi-workflow hosting with dynamic registration
    - REST API endpoints for workflow execution
    - WebSocket support for real-time updates
    - MCP server integration
    - Health monitoring
    - CORS support

    This is the base server class. For production deployments, consider
    using EnterpriseWorkflowServer which includes durability, security,
    and monitoring features.

    Attributes:
        app: FastAPI application instance
        workflows: Registry of all registered workflows
        executor: Thread pool for synchronous execution
        mcp_servers: Registry of MCP servers
    """

    def __init__(
        self,
        title: str = "Kailash Workflow Server",
        description: str = "Multi-workflow hosting server",
        version: str = "1.0.0",
        max_workers: int = 10,
        cors_origins: list[str] = None,
        **kwargs,
    ):
        """Initialize the workflow server.

        Args:
            title: Server title for documentation
            description: Server description
            version: Server version
            max_workers: Maximum thread pool workers
            cors_origins: Allowed CORS origins
        """
        self.workflows: dict[str, WorkflowRegistration] = {}
        self.mcp_servers: dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Create FastAPI app with lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            yield
            # Shutdown
            logger.info("Shutting down workflow server")
            self.executor.shutdown(wait=True)

        self.app = FastAPI(
            title=title, description=description, version=version, lifespan=lifespan
        )

        # Add CORS middleware
        if cors_origins:
            # Only allow credentials when origins are explicitly specified (not wildcard)
            allow_creds = "*" not in cors_origins
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=cors_origins,
                allow_credentials=allow_creds,
                allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
                allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            )

        # Register root endpoints
        self._register_root_endpoints()

    def _register_root_endpoints(self):
        """Register server-level endpoints."""

        @self.app.get("/")
        async def root():
            """Server information."""
            return {
                "name": self.app.title,
                "version": self.app.version,
                "workflows": list(self.workflows.keys()),
                "mcp_servers": list(self.mcp_servers.keys()),
                "type": "workflow_server",
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
            """Server health check."""
            health_status = {
                "status": "healthy",
                "server_type": "workflow_server",
                "workflows": {},
                "mcp_servers": {},
            }

            # Check workflow health
            for name, reg in self.workflows.items():
                if reg.type == "embedded":
                    health_status["workflows"][name] = "healthy"
                elif reg.type == "proxied" and reg.proxy_url:
                    # Check proxy health by hitting the remote health endpoint
                    try:
                        import aiohttp

                        url = f"{reg.proxy_url.rstrip('/')}{reg.health_check}"
                        timeout = aiohttp.ClientTimeout(total=5)
                        async with aiohttp.ClientSession(timeout=timeout) as session:
                            async with session.get(url) as resp:
                                if resp.status == 200:
                                    health_status["workflows"][name] = "healthy"
                                else:
                                    health_status["workflows"][name] = "degraded"
                    except Exception as e:
                        logger.warning(f"Proxy health check failed for {name}: {e}")
                        health_status["workflows"][name] = "unhealthy"
                else:
                    health_status["workflows"][name] = "unknown"

            # Check MCP server health
            for name, server in self.mcp_servers.items():
                try:
                    if hasattr(server, "health_check"):
                        mcp_health = await server.health_check()
                        health_status["mcp_servers"][name] = (
                            "healthy" if mcp_health else "unhealthy"
                        )
                    elif hasattr(server, "is_running"):
                        health_status["mcp_servers"][name] = (
                            "healthy" if server.is_running else "stopped"
                        )
                    else:
                        health_status["mcp_servers"][name] = "healthy"
                except Exception as e:
                    logger.warning(f"MCP health check failed for {name}: {e}")
                    health_status["mcp_servers"][name] = "unhealthy"

            return health_status

        # Note: Metrics and authentication endpoints are provided by EnterpriseWorkflowServer
        # Basic WorkflowServer focuses on core workflow functionality

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates."""
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

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: str = None,
        tags: list[str] = None,
    ):
        """Register a workflow with the server.

        Args:
            name: Unique workflow identifier
            workflow: Workflow instance to register
            description: Optional workflow description
            tags: Optional tags for categorization
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create workflow registration
        registration = WorkflowRegistration(
            name=name,
            type="embedded",
            workflow=workflow,
            description=description or f"Workflow: {name}",
            tags=tags or [],
        )

        self.workflows[name] = registration

        # Create workflow API wrapper
        workflow_api = WorkflowAPI(workflow)

        # Register workflow endpoints with prefix
        prefix = f"/workflows/{name}"
        self.app.mount(prefix, workflow_api.app)

        logger.info(f"Registered workflow '{name}' at {prefix}")

    def register_mcp_server(self, name: str, mcp_server: Any):
        """Register an MCP server with the workflow server.

        Args:
            name: Unique MCP server identifier
            mcp_server: MCP server instance
        """
        if name in self.mcp_servers:
            raise ValueError(f"MCP server '{name}' already registered")

        self.mcp_servers[name] = mcp_server

        # Mount MCP server endpoints
        mcp_prefix = f"/mcp/{name}"
        if hasattr(mcp_server, "app"):
            self.app.mount(mcp_prefix, mcp_server.app)
        elif hasattr(mcp_server, "get_app"):
            self.app.mount(mcp_prefix, mcp_server.get_app())

        logger.info(f"Registered MCP server '{name}' at {mcp_prefix}")

    def proxy_workflow(
        self,
        name: str,
        proxy_url: str,
        health_check: str = "/health",
        description: str = None,
        tags: list[str] = None,
    ):
        """Register a proxied workflow running on another server.

        Args:
            name: Unique workflow identifier
            proxy_url: Base URL of the proxied workflow
            health_check: Health check endpoint path
            description: Optional workflow description
            tags: Optional tags for categorization
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Create proxied workflow registration
        registration = WorkflowRegistration(
            name=name,
            type="proxied",
            proxy_url=proxy_url,
            health_check=health_check,
            description=description or f"Proxied workflow: {name}",
            tags=tags or [],
        )

        self.workflows[name] = registration

        # Create proxy endpoints that forward requests to the remote server
        @self.app.api_route(
            f"/workflows/{name}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        )
        async def proxy_handler(request: Request, path: str, _url=proxy_url):
            """Forward requests to proxied workflow server."""
            import aiohttp

            target_url = f"{_url.rstrip('/')}/{path}"
            timeout = aiohttp.ClientTimeout(total=30)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Forward headers (excluding host)
                headers = {
                    k: v
                    for k, v in request.headers.items()
                    if k.lower() not in ("host", "content-length")
                }

                body = (
                    await request.body()
                    if request.method in ("POST", "PUT", "PATCH")
                    else None
                )

                async with session.request(
                    request.method,
                    target_url,
                    headers=headers,
                    data=body,
                    params=dict(request.query_params),
                ) as resp:
                    content = await resp.read()
                    from starlette.responses import Response as StarletteResponse

                    return StarletteResponse(
                        content=content,
                        status_code=resp.status,
                        headers=dict(resp.headers),
                    )

        logger.info(f"Registered proxied workflow '{name}' -> {proxy_url}")

    def _get_workflow_endpoints(self, name: str) -> list[str]:
        """Get available endpoints for a workflow."""
        base = f"/workflows/{name}"
        return [
            f"{base}/execute",
            f"{base}/status",
            f"{base}/schema",
            f"{base}/docs",
        ]

    def run(self, host: str = "0.0.0.0", port: int = 8000, **kwargs):
        """Run the workflow server.

        Args:
            host: Host address to bind to
            port: Port to listen on
            **kwargs: Additional arguments passed to uvicorn
        """
        import uvicorn

        uvicorn.run(self.app, host=host, port=port, **kwargs)

    def execute(self, **kwargs):
        """Execute the server (alias for run)."""
        self.run(**kwargs)
