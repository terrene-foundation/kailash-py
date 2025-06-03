"""
Lean API wrapper for Kailash workflows using FastAPI.

This module provides a general-purpose API wrapper that can expose any Kailash
workflow as a REST API with minimal configuration.
"""

import asyncio
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow


class ExecutionMode(str, Enum):
    """Execution modes for workflow API."""

    SYNC = "sync"
    ASYNC = "async"
    STREAM = "stream"


class WorkflowRequest(BaseModel):
    """Base request model for workflow execution."""

    inputs: Dict[str, Any] = Field(..., description="Input data for workflow nodes")
    config: Optional[Dict[str, Any]] = Field(
        None, description="Node configuration overrides"
    )
    mode: ExecutionMode = Field(ExecutionMode.SYNC, description="Execution mode")


class WorkflowResponse(BaseModel):
    """Base response model for workflow execution."""

    outputs: Dict[str, Any] = Field(..., description="Output data from workflow nodes")
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
        >>> api.run(port=8000)
    """

    def __init__(
        self,
        workflow: Union[WorkflowBuilder, Workflow],
        app_name: str = "Kailash Workflow API",
        version: str = "1.0.0",
        description: str = "API wrapper for Kailash workflow execution",
    ):
        """
        Initialize the API wrapper.

        Args:
            workflow: The WorkflowBuilder or Workflow instance to expose
            app_name: Name of the API application
            version: API version
            description: API description
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

        self.runtime = LocalRuntime()

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
        self._execution_cache: Dict[str, Dict[str, Any]] = {}

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """Manage app lifecycle."""
        # Startup
        yield
        # Shutdown - cleanup cache
        self._execution_cache.clear()

    def _setup_routes(self):
        """Setup API routes dynamically based on workflow."""

        # Main execution endpoint
        @self.app.post("/execute", response_model=WorkflowResponse)
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
                    self._execute_stream(request), media_type="application/json"
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
            graph_data = self.workflow_graph
            return {
                "id": self.workflow_id,
                "version": self.version,
                "nodes": list(graph_data.nodes()),
                "edges": list(graph_data.edges()),
                "input_nodes": [
                    n for n in graph_data.nodes() if graph_data.in_degree(n) == 0
                ],
                "output_nodes": [
                    n for n in graph_data.nodes() if graph_data.out_degree(n) == 0
                ],
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

            # Execute workflow with inputs
            results = await asyncio.to_thread(
                self.runtime.execute, self.workflow_graph, request.inputs
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
        """Execute workflow with streaming response."""
        import json
        import time

        try:
            # For streaming, we'd need workflow runner enhancement
            # to support progress callbacks. For now, simulate with
            # start/end events

            yield json.dumps(
                {
                    "event": "start",
                    "workflow_id": self.workflow_id,
                    "timestamp": time.time(),
                }
            ) + "\n"

            result = await self._execute_sync(request)

            yield json.dumps(
                {"event": "complete", "result": result.dict(), "timestamp": time.time()}
            ) + "\n"

        except Exception as e:
            yield json.dumps(
                {"event": "error", "error": str(e), "timestamp": time.time()}
            ) + "\n"

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
            sources: List[Dict[str, Any]]
            query: str
            execution_time: float

        @self.app.post("/documents")
        async def add_documents(documents: List[Document]):
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
        >>> api.run(port=8000)
    """
    api_classes = {
        "generic": WorkflowAPI,
        "rag": HierarchicalRAGAPI,
    }

    api_class = api_classes.get(api_type, WorkflowAPI)
    return api_class(workflow, **kwargs)
