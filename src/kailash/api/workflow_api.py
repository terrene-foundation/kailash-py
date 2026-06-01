"""
Lean API wrapper for Kailash workflows using FastAPI.

This module provides a general-purpose API wrapper that can expose any Kailash
workflow as a REST API with minimal configuration.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any

# `fastapi`, `starlette`, and `uvicorn` are OPTIONAL dependencies under the
# `server` extra (pyproject.toml). Per `rules/dependencies.md` § "Declared =
# Imported": optional-extra imports MUST raise loudly with an actionable
# error naming the extra — bare `ModuleNotFoundError` leaves a clean-install
# user with no signal that `kailash[server]` is the correct install.
try:
    import uvicorn
    from fastapi import BackgroundTasks, FastAPI
    from starlette.exceptions import HTTPException
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.api.workflow_api requires server dependencies (fastapi, "
        "starlette, uvicorn). Install with: pip install 'kailash[server]'"
    ) from exc

from pydantic import BaseModel, Field

from kailash.runtime.local import LocalRuntime
from kailash.utils.lifespan import (
    drive_router_lifespan_shutdown,
    drive_router_lifespan_startup,
)
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Execution modes for workflow API."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class WorkflowRequest(BaseModel):
    """Base request model for workflow execution."""

    inputs: dict[str, Any] | None = Field(
        default=None, description="Input data for workflow nodes"
    )
    parameters: dict[str, Any] | None = Field(
        default=None, description="Legacy: parameters for workflow execution"
    )
    config: dict[str, Any] | None = Field(
        default=None, description="Node configuration overrides"
    )
    mode: ExecutionMode = Field(
        default=ExecutionMode.SYNC, description="Execution mode"
    )

    def get_inputs(self) -> dict[str, Any]:
        """Get inputs, supporting both 'inputs' and 'parameters' format."""
        if self.inputs is not None:
            return self.inputs
        elif self.parameters is not None:
            return self.parameters
        else:
            return {}


class WorkflowResponse(BaseModel):
    """Base response model for workflow execution."""

    outputs: dict[str, Any] = Field(..., description="Output data from workflow nodes")
    execution_time: float = Field(..., description="Execution time in seconds")
    workflow_id: str = Field(..., description="Workflow identifier")
    version: str = Field(..., description="Workflow version")


class WorkflowAPI:
    """
    Lean API wrapper for Kailash workflows.

    This class provides a minimal, efficient way to expose any Kailash workflow
    as a REST API with support for synchronous, asynchronous, and streaming execution.

    Example:
        >>> # For any workflow
        >>> from my_workflows import rag_workflow
        >>> api = WorkflowAPI(rag_workflow)
        >>> api.execute(port=8000)
    """

    def __init__(
        self,
        workflow: WorkflowBuilder | Workflow,
        app_name: str = "Kailash Workflow API",
        version: str = "1.0.0",
        description: str = "API wrapper for Kailash workflow execution",
        runtime=None,
    ):
        """
        Initialize the API wrapper.

        Args:
            workflow: The WorkflowBuilder or Workflow instance to expose
            app_name: Name of the API application
            version: API version
            description: API description
            runtime: Optional runtime instance. If None, defaults to AsyncLocalRuntime
                    for optimal Docker/FastAPI performance. Pass LocalRuntime() for
                    backward compatibility or CLI contexts.
        """
        if isinstance(workflow, WorkflowBuilder) or hasattr(workflow, "build"):
            self.workflow = workflow
            self.workflow_graph = workflow.build()
            self.workflow_id = getattr(workflow, "workflow_id", "unnamed")
            self.version = getattr(workflow, "version", "1.0.0")
        else:  # Workflow instance
            self.workflow = workflow
            self.workflow_graph = workflow
            self.workflow_id = getattr(workflow, "workflow_id", "unnamed")
            self.version = getattr(workflow, "version", "1.0.0")

        # Use AsyncLocalRuntime by default for FastAPI/Docker deployment
        # Users can explicitly pass LocalRuntime() for backward compatibility
        if runtime is None:
            from kailash.runtime.async_local import AsyncLocalRuntime

            self.runtime = AsyncLocalRuntime()
            self._owns_runtime = True
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                "WorkflowAPI using AsyncLocalRuntime (Docker-optimized, no thread creation)"
            )
        else:
            # Validate that custom runtime has required interface
            if not hasattr(runtime, "execute"):
                raise TypeError(
                    f"Runtime must have 'execute' method. "
                    f"Got {type(runtime).__name__} which doesn't implement the runtime interface. "
                    f"Use LocalRuntime or AsyncLocalRuntime."
                )
            self.runtime = runtime.acquire() if hasattr(runtime, "acquire") else runtime
            self._owns_runtime = False
            import logging

            logger = logging.getLogger(__name__)
            logger.info(f"WorkflowAPI using {type(runtime).__name__}")

        # Create FastAPI app with lifespan management
        self.app = FastAPI(
            title=app_name,
            version=version,
            description=description,
            lifespan=self._lifespan,
        )

        # Setup routes
        self._setup_routes()

        # Cache for async executions
        self._execution_cache: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        """Release runtime reference."""
        if hasattr(self, "runtime") and self.runtime is not None:
            if self._owns_runtime:
                self.runtime.close()
            else:
                self.runtime.release()
            self.runtime = None

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """Manage app lifecycle."""
        # Startup
        # S2 (#712): drive router.on_startup hooks (e.g. consumer
        # @app.on_event("startup")). Without this iteration, the custom
        # _lifespan above replaces Starlette's _DefaultLifespan and
        # silently drops every router-registered hook (the #500 bug class).
        await drive_router_lifespan_startup(app)
        yield
        # Shutdown - cleanup cache
        await drive_router_lifespan_shutdown(app)
        self._execution_cache.clear()

    def _setup_routes(self):
        """Setup API routes dynamically based on workflow."""

        # Custom 404 handler for helpful error messages
        @self.app.exception_handler(404)
        async def custom_404_handler(request: Request, exc):
            """Provide helpful 404 error with available endpoints."""
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Endpoint not found",
                    "path": request.url.path,
                    "message": "The requested endpoint does not exist for this workflow.",
                    "available_endpoints": [
                        {
                            "method": "POST",
                            "path": "/execute",
                            "description": "Execute the workflow with input parameters",
                        },
                        {
                            "method": "GET",
                            "path": "/workflow/info",
                            "description": "Get workflow metadata and structure",
                        },
                        {
                            "method": "GET",
                            "path": "/health",
                            "description": "Check workflow API health status",
                        },
                    ],
                    "hint": "Most common: POST to /execute endpoint with JSON body containing 'inputs' field",
                    "documentation": "/docs",
                },
            )

        # Root execution endpoint (convenience for direct workflow execution)
        @self.app.post("/")
        async def execute_workflow_root(
            request: Request, background_tasks: BackgroundTasks
        ):
            """Execute the workflow with provided inputs (root endpoint)."""
            try:
                # Try to parse JSON body
                json_data = await request.json()
                workflow_request = WorkflowRequest(**json_data)
            except Exception:
                # If no JSON or invalid JSON, create empty request
                workflow_request = WorkflowRequest()
            return await execute_workflow(workflow_request, background_tasks)

        # Main execution endpoint
        @self.app.post("/execute")
        async def execute_workflow(
            request: WorkflowRequest, background_tasks: BackgroundTasks
        ):
            """Execute the workflow with provided inputs."""

            if request.mode == ExecutionMode.SYNC:
                return await self._execute_sync(request)
            elif request.mode == ExecutionMode.ASYNC:
                return await self._execute_async(request, background_tasks)
            else:  # STREAM
                return StreamingResponse(
                    self._execute_stream(request),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",  # Disable nginx buffering
                    },
                )

        # Status endpoint for async executions
        @self.app.get("/status/{execution_id}")
        async def get_execution_status(execution_id: str):
            """Get status of async execution."""
            if execution_id not in self._execution_cache:
                raise HTTPException(status_code=404, detail="Execution not found")
            return self._execution_cache[execution_id]

        # Workflow metadata endpoint
        @self.app.get("/workflow/info")
        async def get_workflow_info():
            """Get workflow metadata and structure."""
            workflow = self.workflow_graph

            # Get node information
            nodes = []
            for node_id, node_instance in workflow.nodes.items():
                nodes.append({"id": node_id, "type": node_instance.node_type})

            # Get edge information
            edges = []
            for conn in workflow.connections:
                edges.append(
                    {
                        "source": conn.source_node,
                        "target": conn.target_node,
                        "source_output": conn.source_output,
                        "target_input": conn.target_input,
                    }
                )

            return {
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "version": workflow.version,
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }

        # Health check
        @self.app.get("/health")
        async def health_check():
            """Check API health."""
            return {"status": "healthy", "workflow": self.workflow_id}

    async def _execute_sync(
        self, request: WorkflowRequest
    ) -> "WorkflowResponse | JSONResponse":
        """Execute workflow synchronously."""
        import time

        start_time = time.time()

        try:
            # Apply configuration overrides if provided
            if request.config:
                for node_id, config in request.config.items():
                    # This would need workflow builder enhancement to support
                    # dynamic config updates
                    pass

            # Use appropriate execution method based on runtime type
            from kailash.runtime.async_local import AsyncLocalRuntime

            if isinstance(self.runtime, AsyncLocalRuntime):
                # Use native async execution - no thread creation, no deadlock
                async_result = await self.runtime.execute_workflow_async(
                    self.workflow_graph,
                    inputs=request.get_inputs(),
                )
                # execute_workflow_async returns Tuple[Dict, str]
                results = (
                    async_result[0] if isinstance(async_result, tuple) else async_result
                )
            elif self.runtime is not None:
                # Fallback to sync runtime with threading (backward compatibility)
                results = await asyncio.to_thread(
                    self.runtime.execute,
                    self.workflow_graph,
                    parameters=request.get_inputs(),
                )
            else:
                raise RuntimeError("No runtime configured for workflow execution")

            # Handle tuple return from runtime
            if isinstance(results, tuple):
                results = results[0] if results else {}

            execution_time = time.time() - start_time

            return WorkflowResponse(
                outputs=results,
                execution_time=execution_time,
                workflow_id=self.workflow_id,
                version=self.version,
            )

        except Exception as e:
            # Honor a typed HTTP status carried by the exception BEFORE the
            # generic 500 collapse. Nexus' extractor dispatch path raises
            # `nexus.extractors.NexusHandlerError(status_code=int, body=dict|str)`
            # to return a typed 4xx/5xx from a handler; that same convention
            # MUST hold when a workflow raises it through this gateway-execute
            # path (issue #1218). Core SDK cannot import nexus (the dependency
            # runs the other way), so the typed-status contract is detected
            # structurally: any exception carrying an int `status_code` plus a
            # `body` (dict or str) is mapped to that status + body.
            #
            # The runtime wraps a node-raised exception in WorkflowExecutionError
            # (async_local.py raises `... from e`), so the typed error is usually
            # reachable only via the `__cause__`/`__context__` chain — walk it.
            # The mirror pattern lives at packages/kailash-nexus/src/nexus/sse.py
            # and nexus/websocket_handlers.py. A genuine internal error (no typed
            # status anywhere in the chain) still collapses to the canonical 500
            # below — unchanged.
            typed_exc = self._find_typed_status_exc(e)
            if typed_exc is not None:
                # `_find_typed_status_exc` already validated this is an int in
                # 100-599; `getattr` keeps the access off `BaseException` (which
                # has no `status_code`) so the duck-typed contract type-checks.
                typed_status: int = getattr(typed_exc, "status_code")
                raw_body = getattr(typed_exc, "body", None)
                if isinstance(raw_body, dict):
                    typed_body: Any = raw_body
                elif isinstance(raw_body, str):
                    typed_body = {"error": raw_body}
                else:
                    typed_body = {"error": str(typed_exc)}
                # Intent is logged server-side; the typed body is operator-facing
                # by the handler's own design, so it is returned verbatim.
                logger.warning(
                    "Workflow execution returned typed status %s: %s",
                    typed_status,
                    typed_exc,
                )
                return JSONResponse(status_code=typed_status, content=typed_body)
            # Generic internal error: raw error logged server-side, never echoed
            # to the client (HTTP status convention Rule 2 — canonical 500 body).
            logger.error(f"Workflow execution failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @staticmethod
    def _find_typed_status_exc(exc: BaseException) -> BaseException | None:
        """Walk the exception cause/context chain for a typed-HTTP-status error.

        Returns the first exception in the chain that carries an int
        ``status_code`` in the valid HTTP range (100-599) — the structural
        contract of ``nexus.extractors.NexusHandlerError`` (issue #1218). The
        runtime wraps node exceptions in ``WorkflowExecutionError(...) from e``,
        so the typed error is typically the ``__cause__`` (or a deeper link)
        rather than the top-level exception. Returns ``None`` when no link in
        the chain carries a valid typed status (genuine internal error).

        A bounded visited-set guards against a cyclic ``__cause__`` chain.
        """
        seen: set[int] = set()
        current: BaseException | None = exc
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            status = getattr(current, "status_code", None)
            # Require BOTH halves of the NexusHandlerError contract: an int
            # `status_code` in 100-599 AND a `body` attribute. Gating on
            # `status_code` alone would also match a stray `HTTPException`
            # (which carries `status_code` + `detail`, NOT `body`) raised
            # inside a workflow node, surfacing `str(exc)` to the client — a
            # low-grade info-disclosure. Requiring `body` collapses any such
            # non-NexusHandlerError to the canonical 500 instead.
            if (
                isinstance(status, int)
                and 100 <= status <= 599
                and hasattr(current, "body")
            ):
                return current
            # Prefer the explicit cause (``raise ... from e``); fall back to the
            # implicit context (``raise`` inside an ``except``).
            current = current.__cause__ or current.__context__

    async def _execute_async(
        self, request: WorkflowRequest, background_tasks: BackgroundTasks
    ):
        """Execute workflow asynchronously."""
        import uuid

        execution_id = str(uuid.uuid4())

        # Initialize cache entry
        self._execution_cache[execution_id] = {
            "status": "pending",
            "workflow_id": self.workflow_id,
            "version": self.version,
        }

        # Schedule background execution
        background_tasks.add_task(self._run_async_execution, execution_id, request)

        return {
            "execution_id": execution_id,
            "status": "pending",
            "message": f"Execution started. Check status at /status/{execution_id}",
        }

    async def _run_async_execution(self, execution_id: str, request: WorkflowRequest):
        """Run async execution in background."""
        try:
            self._execution_cache[execution_id]["status"] = "running"

            result = await self._execute_sync(request)

            if isinstance(result, JSONResponse):
                # A workflow raised a typed-status error (#1218); the async
                # background path records it as a failure carrying the typed
                # HTTP status rather than calling `.model_dump()` on a Response.
                self._execution_cache[execution_id].update(
                    {
                        "status": "failed",
                        "error": "Execution returned typed status",
                        "status_code": result.status_code,
                    }
                )
            else:
                self._execution_cache[execution_id].update(
                    {"status": "completed", "result": result.model_dump()}
                )

        except Exception as e:
            logger.error(f"Async workflow execution failed for {execution_id}: {e}")
            self._execution_cache[execution_id].update(
                {"status": "failed", "error": "Execution failed"}
            )

    async def _execute_stream(self, request: WorkflowRequest):
        """Execute workflow with Server-Sent Events streaming.

        SSE Format Specification:
            id: <event-id>\n
            event: <event-type>\n
            data: <json-data>\n
            \n

        Returns:
            Async generator yielding SSE-formatted strings
        """
        import asyncio
        import json
        import time

        event_id = 1  # Event ID counter for reconnection support

        try:
            # ========================================
            # START EVENT
            # ========================================
            yield f"id: {event_id}\n"
            yield "event: start\n"
            start_data = {
                "workflow_id": self.workflow_id,
                "version": self.version,
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(start_data)}\n\n"
            event_id += 1

            # Small delay to ensure client receives start event
            await asyncio.sleep(0.001)

            # ========================================
            # EXECUTE WORKFLOW (directly, not via _execute_sync)
            # ========================================
            # Execute the workflow directly so errors propagate with
            # their original message instead of being wrapped in HTTPException.
            start_time = time.time()

            from kailash.runtime.async_local import AsyncLocalRuntime

            if isinstance(self.runtime, AsyncLocalRuntime):
                async_result = await self.runtime.execute_workflow_async(
                    self.workflow_graph,
                    inputs=request.get_inputs(),
                )
                results = (
                    async_result[0] if isinstance(async_result, tuple) else async_result
                )
            elif self.runtime is not None:
                results = await asyncio.to_thread(
                    self.runtime.execute,
                    self.workflow_graph,
                    parameters=request.get_inputs(),
                )
            else:
                raise RuntimeError("No runtime configured for workflow execution")

            if isinstance(results, tuple):
                results = results[0] if results else {}

            execution_time = time.time() - start_time

            result = WorkflowResponse(
                outputs=results,
                execution_time=execution_time,
                workflow_id=self.workflow_id,
                version=self.version,
            )

            # ========================================
            # COMPLETE EVENT
            # ========================================
            yield f"id: {event_id}\n"
            yield "event: complete\n"
            complete_data = {
                "result": result.model_dump(),
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(complete_data)}\n\n"
            event_id += 1

            # ========================================
            # KEEPALIVE COMMENT (optional)
            # ========================================
            await asyncio.sleep(0.001)
            yield ":keepalive\n\n"

        except Exception as e:
            # ========================================
            # ERROR EVENT
            # ========================================
            logger.error(f"Workflow stream execution failed: {e}")
            yield f"id: {event_id}\n"
            yield "event: error\n"
            error_data = {
                "error": str(e),
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    def run(self, host: str = "127.0.0.1", port: int = 8000, **kwargs):
        """Run the API server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


# Specialized API wrapper for Hierarchical RAG workflows
class HierarchicalRAGAPI(WorkflowAPI):
    """
    Specialized API wrapper for Hierarchical RAG workflows.

    Provides RAG-specific endpoints and models for better developer experience.
    """

    def __init__(self, workflow: WorkflowBuilder, **kwargs):
        super().__init__(workflow, **kwargs)
        self._setup_rag_routes()

    def _setup_rag_routes(self):
        """Setup RAG-specific routes."""

        class Document(BaseModel):
            id: str
            title: str
            content: str

        class RAGQuery(BaseModel):
            query: str
            top_k: int = 3
            similarity_method: str = "cosine"
            temperature: float = 0.7
            max_tokens: int = 500

        class RAGResponse(BaseModel):
            answer: str
            sources: list[dict[str, Any]]
            query: str
            execution_time: float

        @self.app.post("/documents")
        async def add_documents(documents: list[Document]):
            """Add documents to the knowledge base."""
            # This would integrate with document storage
            return {"message": f"Added {len(documents)} documents"}

        @self.app.post("/query", response_model=RAGResponse)
        async def query_rag(request: RAGQuery):
            """Query the RAG system."""
            import time

            start_time = time.time()

            # Transform to workflow format
            workflow_request = WorkflowRequest(
                inputs={
                    "query": request.query,
                    "config": {
                        "relevance_scorer": {
                            "top_k": request.top_k,
                            "similarity_method": request.similarity_method,
                        },
                        "llm_agent": {
                            "temperature": request.temperature,
                            "max_tokens": request.max_tokens,
                        },
                    },
                }
            )

            result = await self._execute_sync(workflow_request)

            if isinstance(result, JSONResponse):
                # A node raised a typed-status error (#1218) — surface it to the
                # /query client verbatim rather than reading `.outputs` off a
                # Response.
                return result

            # Extract RAG-specific outputs
            outputs = result.outputs
            answer = (
                outputs.get("llm_response", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            sources = outputs.get("relevant_chunks", [])

            return RAGResponse(
                answer=answer,
                sources=sources,
                query=request.query,
                execution_time=time.time() - start_time,
            )


# Factory function for creating API wrappers
def create_workflow_api(
    workflow: WorkflowBuilder, api_type: str = "generic", **kwargs
) -> WorkflowAPI:
    """
    Factory function to create appropriate API wrapper.

    Args:
        workflow: The workflow to wrap
        api_type: Type of API wrapper ("generic", "rag", etc.)
        **kwargs: Additional arguments for API initialization

    Returns:
        Configured WorkflowAPI instance

    Example:
        >>> api = create_workflow_api(my_workflow, api_type="rag")
        >>> api.execute(port=8000)
    """
    api_classes = {
        "generic": WorkflowAPI,
        "rag": HierarchicalRAGAPI,
    }

    api_class = api_classes.get(api_type, WorkflowAPI)
    return api_class(workflow, **kwargs)
