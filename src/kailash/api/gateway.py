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
    >>> gateway.execute(port=8000)  # doctest: +SKIP

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

import asyncio
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..runtime.local import LocalRuntime
from ..workflow import Workflow
from .workflow_api import WorkflowAPI

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
        cors_origins: list[str] = None,
    ):
        """Initialize the API gateway.

        Args:
            title: API title for documentation
            description: API description
            version: API version
            max_workers: Maximum thread pool workers
            cors_origins: Allowed CORS origins
        """
        self.workflows: dict[str, WorkflowRegistration] = {}
        self.mcp_servers: dict[str, Any] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

        # Proxy HTTP client (created lazily on first proxied request)
        self._proxy_client: httpx.AsyncClient | None = None

        # WebSocket subscription queues: workflow_name -> set of asyncio.Queue
        self._ws_subscriptions: dict[str, set[asyncio.Queue]] = defaultdict(set)

        # Round-robin counters for proxy backends
        self._proxy_round_robin: dict[str, int] = {}

        # Create FastAPI app with lifespan
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            yield
            # Shutdown
            logger.info("Shutting down gateway")
            if self._proxy_client:
                await self._proxy_client.aclose()
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

    async def _get_proxy_client(self) -> httpx.AsyncClient:
        """Get or create the shared async HTTP client for proxying."""
        if self._proxy_client is None or self._proxy_client.is_closed:
            self._proxy_client = httpx.AsyncClient(timeout=30.0)
        return self._proxy_client

    async def _check_proxy_health(self, reg: WorkflowRegistration) -> str:
        """Check health of a proxied workflow backend via HTTP GET.

        Args:
            reg: Workflow registration with proxy_url and health_check path

        Returns:
            "healthy", "unhealthy", or "unreachable"
        """
        if not reg.proxy_url:
            return "unknown"

        health_path = reg.health_check or "/health"
        url = reg.proxy_url.rstrip("/") + health_path

        try:
            client = await self._get_proxy_client()
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return "healthy"
            return "unhealthy"
        except Exception as exc:
            logger.warning(f"Proxy health check failed for {reg.name}: {exc}")
            return "unreachable"

    async def _check_mcp_health(self, name: str, server: Any) -> str:
        """Check health of an MCP server.

        If the server object exposes a ping() or health() coroutine, call it.
        Otherwise return 'unknown'.
        """
        try:
            if hasattr(server, "ping"):
                result = server.ping()
                if asyncio.iscoroutine(result):
                    result = await result
                return "healthy" if result else "unhealthy"
            if hasattr(server, "health"):
                result = server.health()
                if asyncio.iscoroutine(result):
                    result = await result
                return "healthy" if result else "unhealthy"
        except Exception as exc:
            logger.warning(f"MCP health check failed for {name}: {exc}")
            return "unhealthy"
        return "unknown"

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
            """Gateway health check with real backend probing."""
            health_status = {"status": "healthy", "workflows": {}, "mcp_servers": {}}

            # Check workflow health
            for name, reg in self.workflows.items():
                if reg.type == "embedded":
                    health_status["workflows"][name] = "healthy"
                else:
                    health_status["workflows"][name] = await self._check_proxy_health(
                        reg
                    )

            # Check MCP server health
            for name, server in self.mcp_servers.items():
                health_status["mcp_servers"][name] = await self._check_mcp_health(
                    name, server
                )

            # Overall status degrades if any component is unhealthy
            all_wf = list(health_status["workflows"].values())
            all_mcp = list(health_status["mcp_servers"].values())
            if "unhealthy" in all_wf or "unreachable" in all_wf:
                health_status["status"] = "degraded"
            if "unhealthy" in all_mcp:
                health_status["status"] = "degraded"

            return health_status

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time workflow event updates via SSE-like push."""
            await websocket.accept()
            queue: asyncio.Queue = asyncio.Queue()
            subscribed_workflows: set[str] = set()

            async def _sender():
                """Push events from queue to websocket."""
                try:
                    while True:
                        event = await queue.get()
                        await websocket.send_json(event)
                except asyncio.CancelledError:
                    pass

            sender_task = asyncio.create_task(_sender())

            try:
                while True:
                    data = await websocket.receive_json()
                    msg_type = data.get("type")

                    if msg_type == "subscribe":
                        wf_name = data.get("workflow")
                        if wf_name and wf_name in self.workflows:
                            self._ws_subscriptions[wf_name].add(queue)
                            subscribed_workflows.add(wf_name)
                            await websocket.send_json(
                                {
                                    "type": "subscribed",
                                    "workflow": wf_name,
                                    "message": f"Subscribed to {wf_name}",
                                }
                            )
                        else:
                            await websocket.send_json(
                                {
                                    "type": "error",
                                    "message": f"Workflow '{wf_name}' not found",
                                }
                            )

                    elif msg_type == "unsubscribe":
                        wf_name = data.get("workflow")
                        if wf_name in subscribed_workflows:
                            self._ws_subscriptions[wf_name].discard(queue)
                            subscribed_workflows.discard(wf_name)
                            await websocket.send_json(
                                {
                                    "type": "unsubscribed",
                                    "workflow": wf_name,
                                }
                            )
                    else:
                        await websocket.send_json(
                            {"type": "ack", "message": "Message received"}
                        )

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                sender_task.cancel()
                for wf_name in subscribed_workflows:
                    self._ws_subscriptions[wf_name].discard(queue)
                try:
                    await websocket.close()
                except Exception:
                    pass

        # ---------- MCP tool REST endpoints ----------
        @self.app.get("/mcp/tools")
        async def list_mcp_tools():
            """List all tools from all registered MCP servers."""
            all_tools = {}
            for name, server in self.mcp_servers.items():
                if hasattr(server, "list_tools"):
                    try:
                        tools = server.list_tools()
                        if asyncio.iscoroutine(tools):
                            tools = await tools
                        all_tools[name] = tools
                    except Exception as exc:
                        all_tools[name] = {"error": str(exc)}
                else:
                    all_tools[name] = {"error": "Server does not support list_tools"}
            return all_tools

        @self.app.post("/mcp/{server_name}/tools/{tool_name}")
        async def call_mcp_tool(server_name: str, tool_name: str, request: Request):
            """Execute an MCP tool via REST.

            Body should contain the tool arguments as JSON.
            """
            if server_name not in self.mcp_servers:
                return Response(
                    content=f'{{"error": "MCP server \'{server_name}\' not found"}}',
                    status_code=404,
                    media_type="application/json",
                )

            server = self.mcp_servers[server_name]
            body = await request.json()

            if hasattr(server, "call_tool"):
                try:
                    result = server.call_tool(tool_name, body)
                    if asyncio.iscoroutine(result):
                        result = await result
                    return {"success": True, "result": result}
                except Exception as exc:
                    return Response(
                        content=f'{{"error": "{exc}"}}',
                        status_code=500,
                        media_type="application/json",
                    )
            return Response(
                content='{"error": "Server does not support call_tool"}',
                status_code=501,
                media_type="application/json",
            )

    def register_workflow(
        self,
        name: str,
        workflow: Workflow,
        description: str | None = None,
        version: str = "1.0.0",
        tags: list[str] = None,
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
        description: str | None = None,
        version: str = "1.0.0",
        tags: list[str] = None,
    ):
        """Register a proxied workflow with real request forwarding.

        Incoming requests to /{name}/{path} will be forwarded to
        proxy_url/{path} using round-robin if multiple backends are
        configured (comma-separated in proxy_url).

        Args:
            name: Unique workflow identifier
            proxy_url: URL(s) of the workflow service (comma-separated for multi-backend)
            health_check: Health check endpoint path
            description: Workflow description
            version: Workflow version
            tags: Workflow tags
        """
        if name in self.workflows:
            raise ValueError(f"Workflow '{name}' already registered")

        # Support multiple backends via comma-separated URLs
        backends = [u.strip() for u in proxy_url.split(",") if u.strip()]
        primary_url = backends[0]

        self.workflows[name] = WorkflowRegistration(
            name=name,
            type="proxied",
            proxy_url=primary_url,
            health_check=health_check,
            description=description,
            version=version,
            tags=tags or [],
        )

        # Store all backends for round-robin
        self._proxy_round_robin[name] = 0

        # Register a catch-all route that forwards requests
        @self.app.api_route(
            f"/{name}/{{path:path}}",
            methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
        )
        async def _proxy_handler(
            path: str, request: Request, _name=name, _backends=backends
        ):
            """Forward request to backend using round-robin."""
            idx = self._proxy_round_robin.get(_name, 0)
            backend = _backends[idx % len(_backends)]
            self._proxy_round_robin[_name] = idx + 1

            target_url = f"{backend.rstrip('/')}/{path}"

            # Forward headers (exclude host)
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in ("host", "content-length")
            }

            body = await request.body()

            try:
                client = await self._get_proxy_client()
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=dict(request.query_params),
                )
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    media_type=resp.headers.get("content-type"),
                )
            except httpx.RequestError as exc:
                logger.error(f"Proxy request to {target_url} failed: {exc}")
                return Response(
                    content=f'{{"error": "Backend unreachable: {exc}"}}',
                    status_code=502,
                    media_type="application/json",
                )

        logger.info(f"Registered proxied workflow: {name} -> {proxy_url}")

    def register_mcp_server(self, name: str, mcp_server: Any):
        """Register an MCP server and expose its tools as REST endpoints.

        Args:
            name: Unique MCP server identifier
            mcp_server: MCP server instance (must support list_tools/call_tool)
        """
        if name in self.mcp_servers:
            raise ValueError(f"MCP server '{name}' already registered")

        self.mcp_servers[name] = mcp_server

        logger.info(f"Registered MCP server: {name}")

    async def publish_workflow_event(self, workflow_name: str, event: dict[str, Any]):
        """Publish an event to all WebSocket subscribers of a workflow.

        Args:
            workflow_name: Name of the workflow that produced the event
            event: Event data dict to send
        """
        subscribers = self._ws_subscriptions.get(workflow_name, set())
        dead_queues = set()
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.add(queue)
        for dq in dead_queues:
            subscribers.discard(dq)

    def _get_workflow_endpoints(self, name: str) -> list[str]:
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
        self.chains: dict[str, list[str]] = {}
        self.dependencies: dict[str, list[str]] = {}

    def create_chain(self, name: str, workflow_sequence: list[str]):
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
        self, chain_name: str, initial_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a workflow chain.

        Each workflow in the chain receives the output of the previous one
        as its input parameters. Proxied workflows are called via HTTP POST,
        while embedded workflows are executed in-process via LocalRuntime.

        Args:
            chain_name: Chain to execute
            initial_input: Input for first workflow

        Returns:
            Final output from the chain
        """
        if chain_name not in self.chains:
            raise ValueError(f"Chain '{chain_name}' not found")

        result = initial_input
        runtime = LocalRuntime()

        for workflow_name in self.chains[chain_name]:
            reg = self.gateway.workflows[workflow_name]

            if reg.type == "embedded" and reg.workflow is not None:
                # Execute embedded workflow in-process
                wf_results, _run_id = runtime.execute(reg.workflow, parameters=result)
                # Flatten results: use all node outputs as next input
                result = {}
                for _node_id, node_output in wf_results.items():
                    if isinstance(node_output, dict):
                        result.update(node_output)
                    else:
                        result[_node_id] = node_output

            elif reg.type == "proxied" and reg.proxy_url:
                # Forward to proxied backend via HTTP POST
                client = await self.gateway._get_proxy_client()
                url = f"{reg.proxy_url.rstrip('/')}/execute"
                resp = await client.post(url, json=result, timeout=60.0)
                resp.raise_for_status()
                result = resp.json()

            else:
                raise ValueError(
                    f"Workflow '{workflow_name}' is not executable "
                    f"(type={reg.type}, workflow={reg.workflow is not None})"
                )

        return result
