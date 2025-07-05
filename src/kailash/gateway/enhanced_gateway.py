"""Enhanced Gateway with resource management and async workflow support.

This module provides an enhanced version of the DurableAPIGateway that adds:
- Resource reference resolution for non-serializable objects
- Integration with ResourceRegistry for shared resources
- Secret management for credentials
- Async workflow execution support
- Health checks for resources
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Set, Union

from ..middleware.gateway.durable_gateway import DurableAPIGateway
from ..resources.registry import ResourceRegistry
from ..runtime.async_local import AsyncLocalRuntime, ExecutionContext
from ..workflow import Workflow
from .resource_resolver import ResourceReference, ResourceResolver
from .security import SecretManager

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


class EnhancedDurableAPIGateway(DurableAPIGateway):
    """Gateway with resource management and async workflow support."""

    def __init__(
        self,
        resource_registry: ResourceRegistry = None,
        secret_manager: SecretManager = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.resource_registry = resource_registry or ResourceRegistry()
        self.secret_manager = secret_manager or SecretManager()
        self._workflow_resources: Dict[str, Set[str]] = {}
        self._resource_resolver = ResourceResolver(
            self.resource_registry, self.secret_manager
        )
        self._runtime = AsyncLocalRuntime(resource_registry=self.resource_registry)
        self._active_requests: Dict[str, WorkflowResponse] = {}
        self._cleanup_tasks: List[asyncio.Task] = []

    def register_workflow(
        self,
        workflow_id: str,
        workflow: Workflow,
        required_resources: List[str] = None,
        description: str = None,
    ):
        """Register workflow with resource requirements."""
        # Use parent's register_workflow method
        super().register_workflow(workflow_id, workflow)

        # Track resource requirements
        if required_resources:
            self._workflow_resources[workflow_id] = set(required_resources)

        # Extract requirements from workflow metadata
        if hasattr(workflow, "metadata"):
            declared_resources = workflow.metadata.get("required_resources", [])
            if workflow_id not in self._workflow_resources:
                self._workflow_resources[workflow_id] = set()
            self._workflow_resources[workflow_id].update(declared_resources)

        # Store workflow description
        if description and hasattr(workflow, "metadata"):
            workflow.metadata["description"] = description

    async def execute_workflow(
        self, workflow_id: str, request: WorkflowRequest
    ) -> WorkflowResponse:
        """Execute workflow with resource injection."""
        # Create response object
        response = WorkflowResponse(
            request_id=request.request_id,
            workflow_id=workflow_id,
            status="pending",
            started_at=datetime.now(UTC),
        )

        # Store active request
        self._active_requests[request.request_id] = response

        try:
            # Validate workflow exists
            if workflow_id not in self.workflows:
                raise WorkflowNotFoundError(f"Workflow {workflow_id} not found")

            workflow_reg = self.workflows[workflow_id]
            workflow = workflow_reg.workflow

            # Update status
            response.status = "running"

            # Prepare execution context
            context = await self._prepare_execution_context(workflow_id, request)

            # Execute with resource injection
            result = await self._execute_with_resources(
                workflow, request.inputs, context
            )

            # Update response
            response.status = "completed"
            response.result = (
                result.get("results", result) if isinstance(result, dict) else result
            )
            response.completed_at = datetime.now(UTC)
            response.execution_time = (
                response.completed_at - response.started_at
            ).total_seconds()

        except Exception as e:
            # Handle error
            response.status = "failed"
            response.error = str(e)
            response.completed_at = datetime.now(UTC)
            response.execution_time = (
                response.completed_at - response.started_at
            ).total_seconds()

            # Log error
            logger.error(f"Workflow {workflow_id} failed: {e}", exc_info=True)

        finally:
            # Clean up active request after a delay
            cleanup_task = asyncio.create_task(
                self._cleanup_request(request.request_id)
            )
            self._cleanup_tasks.append(cleanup_task)

        return response

    async def _prepare_execution_context(
        self, workflow_id: str, request: WorkflowRequest
    ) -> ExecutionContext:
        """Prepare execution context with resources."""
        context = ExecutionContext()
        context.resource_registry = self.resource_registry

        # Add request context variables
        for key, value in request.context.items():
            context.set_variable(key, value)

        # Handle resource references in request
        if request.resources:
            for name, ref in request.resources.items():
                if isinstance(ref, ResourceReference):
                    # Resolve resource reference
                    resource = await self._resource_resolver.resolve(ref)

                    # Register the resource under the expected name
                    # Create a wrapper factory that returns the already-created resource
                    class ExistingResourceFactory:
                        def __init__(self, resource):
                            self._resource = resource

                        async def create(self):
                            return self._resource

                    self.resource_registry.register_factory(
                        name, ExistingResourceFactory(resource)
                    )

                elif isinstance(ref, str) and ref.startswith("@"):
                    # Reference to registered resource
                    resource_name = ref[1:]  # Remove @ prefix
                    # Ensure resource exists
                    if not self.resource_registry.has_factory(resource_name):
                        raise ValueError(f"Resource '{resource_name}' not registered")
                    # Resource will be fetched on demand

                elif isinstance(ref, dict) and "type" in ref:
                    # Inline resource reference
                    resource_ref = ResourceReference(**ref)
                    resource = await self._resource_resolver.resolve(resource_ref)

        # Add required resources to context
        required = self._workflow_resources.get(workflow_id, set())
        for resource_name in required:
            if not self.resource_registry.has_factory(resource_name):
                raise ValueError(f"Required resource '{resource_name}' not available")

        return context

    async def _execute_with_resources(
        self, workflow: Workflow, inputs: Dict[str, Any], context: ExecutionContext
    ) -> Any:
        """Execute workflow with resources."""
        # Use async runtime for execution
        result = await self._runtime.execute_workflow_async(workflow, inputs, context)
        return result

    async def _cleanup_request(self, request_id: str, delay: int = 3600):
        """Clean up request after delay."""
        try:
            await asyncio.sleep(delay)
            if request_id in self._active_requests:
                del self._active_requests[request_id]
        except asyncio.CancelledError:
            # Task was cancelled during shutdown
            pass

    async def get_workflow_status(self, request_id: str) -> WorkflowResponse:
        """Get status of workflow execution."""
        if request_id in self._active_requests:
            return self._active_requests[request_id]

        # Could check persistent storage here
        raise ValueError(f"Request {request_id} not found")

    def list_workflows(self) -> Dict[str, Dict[str, Any]]:
        """List all registered workflows with metadata."""
        workflows = {}

        for workflow_id, workflow_reg in self.workflows.items():
            workflow = workflow_reg.workflow
            metadata = getattr(workflow, "metadata", {})
            workflows[workflow_id] = {
                "name": workflow.name,
                "description": metadata.get(
                    "description", workflow_reg.description or ""
                ),
                "required_resources": list(
                    self._workflow_resources.get(workflow_id, [])
                ),
                "async_workflow": metadata.get("async_workflow", False),
                "node_count": len(workflow.nodes),
                "type": workflow_reg.type,
                "version": workflow_reg.version,
                "tags": workflow_reg.tags,
            }

        return workflows

    async def shutdown(self):
        """Shutdown the gateway and cleanup resources."""
        # Cancel all cleanup tasks
        for task in self._cleanup_tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to complete
        if self._cleanup_tasks:
            await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)

        # Clear the task list
        self._cleanup_tasks.clear()

        # Clear active requests
        self._active_requests.clear()

        # Cleanup runtime if it has a cleanup method
        if hasattr(self._runtime, "cleanup"):
            await self._runtime.cleanup()

        # Call parent's close method to cleanup middleware components
        if hasattr(super(), "close"):
            await super().close()

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on gateway and resources."""
        health = {
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "workflows": len(self.workflows),
            "active_requests": len(self._active_requests),
            "resources": {},
        }

        # Check resource health
        for resource_name in self.resource_registry.list_resources():
            try:
                resource = await self.resource_registry.get_resource(resource_name)
                # Try to get health check
                factory = self.resource_registry._factories.get(resource_name)
                if (
                    factory
                    and hasattr(factory, "health_check")
                    and factory.health_check
                ):
                    is_healthy = await factory.health_check(resource)
                    health["resources"][resource_name] = (
                        "healthy" if is_healthy else "unhealthy"
                    )
                else:
                    health["resources"][resource_name] = "healthy"
            except Exception as e:
                health["resources"][resource_name] = f"unhealthy: {str(e)}"
                health["status"] = "degraded"

        return health
