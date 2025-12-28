"""
Lean API wrapper for Kailash workflows using FastAPI.

This module provides a general-purpose API wrapper that can expose any Kailash
workflow as a REST API with minimal configuration.
"""

import asyncio
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow
from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Execution modes for workflow API."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class WorkflowRequest(BaseModel):
    """Base request model for workflow execution."""

    inputs: dict[str, Any] | None = Field(
        None, description="Input data for workflow nodes"
    )
    parameters: dict[str, Any] | None = Field(
        None, description="Legacy: parameters for workflow execution"
    )
    config: dict[str, Any] | None = Field(
        None, description="Node configuration overrides"
    )
    mode: ExecutionMode = Field(ExecutionMode.SYNC, description="Execution mode")

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
        if isinstance(workflow, WorkflowBuilder):
            self.workflow = workflow
            self.workflow_graph = workflow.build()
            self.workflow_id = getattr(workflow, "workflow_id", "unnamed")
            self.version = getattr(workflow, "version", "1.0.0")
        else:  # Workflow instance
            self.workflow = workflow
            self.workflow_graph = workflow
            self.workflow_id = workflow.workflow_id
            self.version = workflow.version

        # Use AsyncLocalRuntime by default for FastAPI/Docker deployment
        # Users can explicitly pass LocalRuntime() for backward compatibility
        if runtime is None:
            from kailash.runtime.async_local import AsyncLocalRuntime

            self.runtime = AsyncLocalRuntime()
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
            self.runtime = runtime
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

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """Manage app lifecycle."""
        # Startup
        yield
        # Shutdown - cleanup cache
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
            except:
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

    async def _execute_sync(self, request: WorkflowRequest) -> WorkflowResponse:
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
                results = await self.runtime.execute_workflow_async(
                    self.workflow_graph,
                    inputs=request.get_inputs(),
                )
                # AsyncLocalRuntime returns dict with 'results' key
                if isinstance(results, dict) and "results" in results:
                    results = results["results"]
            else:
                # Fallback to sync runtime with threading (backward compatibility)
                results = await asyncio.to_thread(
                    self.runtime.execute,
                    self.workflow_graph,
                    parameters=request.get_inputs(),
                )

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
            raise HTTPException(status_code=500, detail=str(e))

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

            self._execution_cache[execution_id].update(
                {"status": "completed", "result": result.dict()}
            )

        except Exception as e:
            self._execution_cache[execution_id].update(
                {"status": "failed", "error": str(e)}
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
            # EXECUTE WORKFLOW
            # ========================================
            # For now, execute synchronously
            # Future enhancement: Stream intermediate results
            result = await self._execute_sync(request)

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
            yield f"id: {event_id}\n"
            yield "event: error\n"
            error_data = {
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": time.time(),
            }
            yield f"data: {json.dumps(error_data)}\n\n"

    def run(self, host: str = "0.0.0.0", port: int = 8000, **kwargs):
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
