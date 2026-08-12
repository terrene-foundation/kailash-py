"""FastAPI integration for Enhanced Gateway.

This module provides REST API endpoints for the enhanced gateway
with resource management and async workflow support.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# `fastapi` is an OPTIONAL dependency under the `server` extra. Per
# `rules/dependencies.md` § "Declared = Imported": optional-extra imports
# MUST raise loudly with an actionable error naming the extra.
try:
    from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
    from fastapi.responses import JSONResponse
except ImportError as exc:  # pragma: no cover — covered by structural invariant test
    raise ImportError(
        "kailash.gateway.api requires server dependencies (fastapi). "
        "Install with: pip install 'kailash[server]'"
    ) from exc

from pydantic import BaseModel, ConfigDict, Field

from ..resources.registry import ResourceRegistry
from ..utils.http_errors import safe_http_detail
from ..utils.server_auth import install_server_auth_middleware
from .enhanced_gateway import (
    EnhancedDurableAPIGateway,
    ResourceReference,
    WorkflowRequest,
    WorkflowResponse,
)
from .security import SecretManager

logger = logging.getLogger(__name__)


# Pydantic models for API
class ResourceReferenceModel(BaseModel):
    """Model for resource reference in API."""

    type: str = Field(
        ..., description="Resource type (database, http_client, cache, etc.)"
    )
    config: Dict[str, Any] = Field(..., description="Resource configuration")
    credentials_ref: Optional[str] = Field(
        None, description="Reference to credentials secret"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "type": "database",
                "config": {"host": "localhost", "port": 5432, "database": "myapp"},
                "credentials_ref": "db_credentials",
            }
        }
    )


class WorkflowRequestModel(BaseModel):
    """API model for workflow requests."""

    inputs: Dict[str, Any] = Field(..., description="Workflow input parameters")
    resources: Optional[Dict[str, Union[str, ResourceReferenceModel]]] = Field(
        None,
        description="Resource references (@name for registered, or inline definition)",
    )
    context: Optional[Dict[str, Any]] = Field(
        None, description="Additional context variables"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "inputs": {"user_id": 123, "action": "process"},
                "resources": {
                    "db": "@main_database",
                    "api": {
                        "type": "http_client",
                        "config": {"base_url": "https://api.example.com"},
                        "credentials_ref": "api_key_secret",
                    },
                },
                "context": {"environment": "production", "trace_id": "abc123"},
            }
        }
    )


class WorkflowResponseModel(BaseModel):
    """API model for workflow responses."""

    request_id: str
    workflow_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time: Optional[float] = None


class WorkflowRegistrationModel(BaseModel):
    """Model for workflow registration."""

    workflow_definition: Dict[str, Any] = Field(..., description="Workflow definition")
    required_resources: Optional[List[str]] = Field(
        None, description="Required resource names"
    )
    description: Optional[str] = Field(None, description="Workflow description")


# Create router
router = APIRouter(prefix="/api/v1", tags=["workflows"])

# Dependency to get gateway instance
_gateway_instance: Optional[EnhancedDurableAPIGateway] = None


async def get_gateway() -> EnhancedDurableAPIGateway:
    """Get or create gateway instance."""
    global _gateway_instance
    if not _gateway_instance:
        _gateway_instance = EnhancedDurableAPIGateway()
    return _gateway_instance


# API Endpoints
@router.post("/workflows/{workflow_id}/execute", response_model=WorkflowResponseModel)
async def execute_workflow(
    workflow_id: str,
    request: WorkflowRequestModel,
    background_tasks: BackgroundTasks,
    gateway: EnhancedDurableAPIGateway = Depends(get_gateway),
):
    """Execute a workflow with resource support."""
    # Convert API model to internal request
    resources = {}
    if request.resources:
        for name, ref in request.resources.items():
            if isinstance(ref, str):
                resources[name] = ref
            elif isinstance(ref, ResourceReferenceModel):
                resources[name] = ResourceReference(
                    type=ref.type,
                    config=ref.config,
                    credentials_ref=ref.credentials_ref,
                )
            elif isinstance(ref, dict):
                resources[name] = ResourceReference(**ref)

    workflow_request = WorkflowRequest(
        inputs=request.inputs, resources=resources, context=request.context or {}
    )

    # Execute workflow
    try:
        response = await gateway.execute_workflow(workflow_id, workflow_request)
        return WorkflowResponseModel(**response.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=safe_http_detail(e, logger=logger, context="execute workflow"),
        ) from e


@router.get(
    "/workflows/{workflow_id}/status/{request_id}", response_model=WorkflowResponseModel
)
async def get_workflow_status(
    workflow_id: str,
    request_id: str,
    gateway: EnhancedDurableAPIGateway = Depends(get_gateway),
):
    """Get status of a workflow execution."""
    # Scoped to the lookup ALONE. `safe_types=(ValueError,)` under an
    # `except ValueError` was a no-op allowlist: every exception that could
    # reach it was inside it by construction, so the fail-closed default was
    # unreachable at this site. Worse, the old `try:` also spanned the
    # `WorkflowResponseModel(...)` construction below, and
    # `pydantic.ValidationError` subclasses `ValueError` -- a validation
    # failure returned the offending INPUT VALUES to the caller as a 404.
    try:
        response = await gateway.get_workflow_status(request_id)
    except ValueError as e:
        # The gateway's own not-found signal (enhanced_gateway.py raises
        # `ValueError(f"Request {request_id} not found")`). Nothing in that
        # message is unknown to the caller, so nothing is allowlisted and
        # the generic fail-closed 404 body is used instead.
        raise HTTPException(
            status_code=404,
            detail=safe_http_detail(
                e,
                logger=logger,
                context="get workflow status",
                status_code=404,
            ),
        ) from e

    if response.workflow_id != workflow_id:
        raise HTTPException(
            status_code=400,
            detail=f"Request {request_id} is for workflow {response.workflow_id}, not {workflow_id}",
        )

    try:
        return WorkflowResponseModel(**response.to_dict())
    except Exception as e:
        # Serialization failure is a server fault, not a missing resource.
        raise HTTPException(
            status_code=500,
            detail=safe_http_detail(
                e, logger=logger, context="serialize workflow status"
            ),
        ) from e


@router.get("/workflows")
async def list_workflows(gateway: EnhancedDurableAPIGateway = Depends(get_gateway)):
    """List all registered workflows."""
    return gateway.list_workflows()


@router.get("/workflows/{workflow_id}")
async def get_workflow_details(
    workflow_id: str, gateway: EnhancedDurableAPIGateway = Depends(get_gateway)
):
    """Get details of a specific workflow."""
    workflows = gateway.list_workflows()
    if workflow_id not in workflows:
        raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")
    return workflows[workflow_id]


@router.post("/workflows/{workflow_id}/register")
async def register_workflow(
    workflow_id: str,
    registration: WorkflowRegistrationModel,
    gateway: EnhancedDurableAPIGateway = Depends(get_gateway),
):
    """Register a new workflow."""
    try:
        # Build workflow from definition
        from ..workflow import WorkflowBuilder

        builder = WorkflowBuilder()

        # Parse workflow definition
        for node in registration.workflow_definition.get("nodes", []):
            builder.add_node(node["type"], node["id"], node.get("config", {}))

        for conn in registration.workflow_definition.get("connections", []):
            builder.add_connection(
                conn["from_node"],
                conn.get("from_output"),
                conn["to_node"],
                conn.get("to_input"),
            )

        workflow = builder.build()
        workflow.name = workflow_id

        # Register with gateway
        gateway.register_workflow(
            workflow_id,
            workflow,
            required_resources=registration.required_resources,
            description=registration.description,
        )

        return {
            "status": "registered",
            "workflow_id": workflow_id,
            "message": f"Workflow {workflow_id} registered successfully",
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=safe_http_detail(
                e, logger=logger, context="register workflow", status_code=400
            ),
        ) from e


@router.get("/health")
async def health_check(gateway: EnhancedDurableAPIGateway = Depends(get_gateway)):
    """Check gateway and resource health."""
    return await gateway.health_check()


@router.get("/resources")
async def list_resources(gateway: EnhancedDurableAPIGateway = Depends(get_gateway)):
    """List available resources."""
    return gateway.resource_registry.list_resources()


# Create FastAPI app
def create_gateway_app(
    resource_registry: Optional[ResourceRegistry] = None,
    secret_manager: Optional[SecretManager] = None,
    title: str = "Kailash Enhanced Gateway",
    description: str = "API Gateway for async workflows with resource management",
    version: str = "1.0.0",
    # Server-wide authentication (#2072) -- NAMED, never **kwargs.
    require_auth: bool = True,
    auth_config: Any = None,
    external_auth_reason: Optional[str] = None,
    auth_exempt_paths: Optional[list[str]] = None,
) -> FastAPI:
    """Create FastAPI app for gateway.

    Args:
        resource_registry: Registry supplying workflow resources.
        secret_manager: Secret manager for resource credentials.
        title: OpenAPI title.
        description: OpenAPI description.
        version: OpenAPI version.
        require_auth: Whether every request must be authenticated.
            **Defaults to ``True`` (fail-closed); BREAKING.** See
            :mod:`kailash.utils.server_auth` and issue #2072.
        auth_config: Explicit ``JWTConfig`` (or field ``dict``).
        external_auth_reason: Non-empty string declaring that an ASGI
            middleware outside this app authenticates every request.
        auth_exempt_paths: Extra paths exempt from authentication.

    Returns:
        The FastAPI application that actually serves the routes.
    """

    # `@app.on_event(...)` is deprecated in FastAPI and emits a
    # DeprecationWarning on every construction; a lifespan context manager is
    # the supported form and runs the same startup/shutdown work. The body
    # reads `_gateway_instance` at REQUEST time, not definition time, so
    # defining it before the instance is assigned below is safe.
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        logger.info("Enhanced Gateway starting up...")
        try:
            yield
        finally:
            # `finally`, so the resource registry is still cleaned up when
            # startup or serving raises -- otherwise a failed boot leaks every
            # resource the registry opened.
            logger.info("Enhanced Gateway shutting down...")
            if _gateway_instance and _gateway_instance.resource_registry:
                await _gateway_instance.resource_registry.cleanup()

    app = FastAPI(
        title=title, description=description, version=version, lifespan=lifespan
    )

    # Set up gateway instance
    global _gateway_instance
    _gateway_instance = EnhancedDurableAPIGateway(
        resource_registry=resource_registry,
        secret_manager=secret_manager,
        title=title,
        description=description,
        version=version,
        require_auth=require_auth,
        auth_config=auth_config,
        external_auth_reason=external_auth_reason,
        auth_exempt_paths=auth_exempt_paths,
    )

    # Include router
    app.include_router(router)

    # Authenticate THIS app, not the gateway's own (#2072).
    #
    # `EnhancedDurableAPIGateway` builds its own FastAPI instance and installs
    # the auth middleware there -- but that app is NOT the one returned here,
    # and it is not the one serving these routes. The router above is mounted
    # on the LOCAL `app`, and its handlers reach the gateway through
    # `Depends(get_gateway)`, which is an INSTANCE INJECTOR and authenticates
    # nothing.
    #
    # Measured before this line existed, with KAILASH_JWT_SECRET set and the
    # gateway therefore reporting auth as installed:
    #
    #     middleware on RETURNED app: []
    #     middleware on GATEWAY  app: ['BaseHTTPMiddleware', 'JWTAuthMiddleware']
    #     GET /api/v1/workflows (NO creds) -> 200
    #
    # So the constructor's fail-closed raise protected an app nobody serves
    # while the served app stayed fully open -- a gate installed one object to
    # the left of the door. Installing here binds it to the surface that
    # actually receives requests.
    if _gateway_instance._auth_config is not None:
        install_server_auth_middleware(app, _gateway_instance._auth_config)

    return app
