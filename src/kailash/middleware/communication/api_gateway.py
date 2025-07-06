"""
Enhanced API Gateway for Kailash Middleware

Provides a comprehensive API gateway that integrates agent-UI middleware,
real-time communication, and dynamic workflow management with full
frontend support capabilities.
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ...nodes.base import NodeRegistry
from ...nodes.security import CredentialManagerNode
from ...nodes.transform import DataTransformer
from ...workflow import Workflow
from ...workflow.builder import WorkflowBuilder
from ..core.agent_ui import AgentUIMiddleware
from ..core.schema import DynamicSchemaRegistry
from .events import EventFilter, EventType
from .realtime import RealtimeMiddleware

logger = logging.getLogger(__name__)

# Auth manager will be injected via dependency injection
# This avoids circular imports and allows for flexible auth implementations


# Pydantic Models
class SessionCreateRequest(BaseModel):
    """Request model for creating a new session."""

    user_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """Response model for session operations."""

    session_id: str
    user_id: Optional[str] = None
    created_at: datetime
    active: bool = True


class WorkflowCreateRequest(BaseModel):
    """Request model for creating a workflow."""

    name: str
    description: Optional[str] = None
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WorkflowExecuteRequest(BaseModel):
    """Request model for executing a workflow."""

    workflow_id: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    config_overrides: Dict[str, Any] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    """Response model for workflow execution."""

    execution_id: str
    workflow_id: str
    status: str
    created_at: datetime
    progress: float = 0.0


class NodeSchemaRequest(BaseModel):
    """Request model for getting node schemas."""

    node_types: Optional[List[str]] = None
    include_examples: bool = False


class WebhookRegisterRequest(BaseModel):
    """Request model for registering webhooks."""

    url: str
    secret: Optional[str] = None
    event_types: List[str] = Field(default_factory=list)
    headers: Dict[str, str] = Field(default_factory=dict)


class APIGateway:
    """
    Enhanced API Gateway for Kailash Middleware.

    Now uses SDK components for:
    - Authentication and authorization with SDKAuthManager
    - Data transformation with DataTransformer nodes
    - Audit logging with AuditLogNode
    - Security event tracking with SecurityEventNode

    Provides:
    - Session management for frontend clients
    - Real-time workflow execution and monitoring
    - Dynamic workflow creation and modification
    - Node discovery and schema generation
    - Multi-transport real-time communication (WebSocket, SSE, Webhooks)
    - AI chat integration for workflow assistance
    - Comprehensive monitoring and statistics
    """

    def __init__(
        self,
        title: str = "Kailash Middleware Gateway",
        description: str = "Enhanced API gateway for agent-frontend communication",
        version: str = "1.0.0",
        cors_origins: List[str] = None,
        enable_docs: bool = True,
        max_sessions: int = 1000,
        enable_auth: bool = True,
        auth_manager=None,  # Dependency injection for auth
        database_url: str = None,
    ):
        """
        Initialize API Gateway with dependency injection support.

        Args:
            title: API title
            description: API description
            version: API version
            cors_origins: Allowed CORS origins
            enable_docs: Enable OpenAPI documentation
            max_sessions: Maximum concurrent sessions
            enable_auth: Enable authentication
            auth_manager: Optional auth manager instance (creates default if None and auth enabled)
            database_url: Optional database URL for persistence
        """
        self.title = title
        self.version = version
        self.enable_docs = enable_docs
        self.enable_auth = enable_auth

        # Initialize SDK nodes for gateway operations
        self._init_sdk_nodes(database_url)

        # Initialize core middleware components
        self.agent_ui = AgentUIMiddleware(max_sessions=max_sessions)
        self.realtime = RealtimeMiddleware(self.agent_ui)
        self.schema_registry = DynamicSchemaRegistry()
        self.node_registry = NodeRegistry()

        # Initialize auth manager if enabled
        if enable_auth:
            if auth_manager is None:
                # Create default auth manager if none provided
                # Import here to avoid circular dependency
                from ..auth import JWTAuthManager

                self.auth_manager = JWTAuthManager(
                    secret_key="api-gateway-secret",
                    algorithm="HS256",
                    issuer="kailash-gateway",
                    audience="kailash-api",
                )
            else:
                self.auth_manager = auth_manager
        else:
            self.auth_manager = None

        # Create FastAPI app with lifespan management
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting {title} v{version}")
            await self._log_startup()
            yield
            # Shutdown
            logger.info("Shutting down gateway")
            await self._cleanup()

        self.app = FastAPI(
            title=title,
            description=description,
            version=version,
            docs_url="/docs" if enable_docs else None,
            redoc_url="/redoc" if enable_docs else None,
            lifespan=lifespan,
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins or ["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup routes
        self._setup_routes()

        # Performance tracking
        self.start_time = time.time()
        self.requests_processed = 0

    def _init_sdk_nodes(self, database_url: str = None):
        """Initialize SDK nodes for gateway operations."""

        # Data transformer for request/response formatting
        self.data_transformer = DataTransformer(
            name="gateway_transformer",
            # Transformations will be provided at runtime
            transformations=[],
        )

        # Credential manager for gateway security
        self.credential_manager = CredentialManagerNode(
            name="gateway_credentials",
            credential_name="gateway_secrets",
            credential_type="custom",
        )

    async def _log_startup(self):
        """Log gateway startup."""
        logger.info(
            f"API Gateway started: {self.title} v{self.version}, Auth: {self.enable_auth}"
        )

    async def _cleanup(self):
        """Cleanup resources on shutdown."""
        try:
            # Close all sessions
            for session_id in list(self.agent_ui.sessions.keys()):
                await self.agent_ui.close_session(session_id)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def _setup_routes(self):
        """Setup all API routes."""
        self._setup_core_routes()
        self._setup_session_routes()
        self._setup_workflow_routes()
        self._setup_execution_routes()
        self._setup_schema_routes()
        self._setup_realtime_routes()
        self._setup_monitoring_routes()

    def _setup_core_routes(self):
        """Setup core gateway routes."""

        @self.app.get("/")
        async def root():
            """Gateway information and status."""
            return {
                "name": self.title,
                "version": self.version,
                "status": "healthy",
                "uptime_seconds": time.time() - self.start_time,
                "features": {
                    "sessions": True,
                    "real_time": True,
                    "dynamic_workflows": True,
                    "ai_chat": True,
                    "webhooks": True,
                },
                "endpoints": {
                    "sessions": "/api/sessions",
                    "workflows": "/api/workflows",
                    "schemas": "/api/schemas",
                    "websocket": "/ws",
                    "sse": "/events",
                    "docs": "/docs" if self.enable_docs else None,
                },
            }

        @self.app.get("/health")
        async def health_check():
            """Detailed health check."""
            try:
                agent_ui_stats = self.agent_ui.get_stats()
                realtime_stats = self.realtime.get_stats()
                schema_stats = self.schema_registry.get_stats()

                return {
                    "status": "healthy",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "uptime_seconds": time.time() - self.start_time,
                    "requests_processed": self.requests_processed,
                    "components": {
                        "agent_ui": {
                            "status": "healthy",
                            "active_sessions": agent_ui_stats["active_sessions"],
                            "workflows_executed": agent_ui_stats["workflows_executed"],
                        },
                        "realtime": {
                            "status": "healthy",
                            "events_processed": realtime_stats["events_processed"],
                            "websocket_connections": realtime_stats.get(
                                "websocket_stats", {}
                            ).get("total_connections", 0),
                        },
                        "schema_registry": {
                            "status": "healthy",
                            "schemas_generated": schema_stats["schemas_generated"],
                            "cache_hit_rate": schema_stats["cache_hit_rate"],
                        },
                    },
                }
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return JSONResponse(
                    status_code=503, content={"status": "unhealthy", "error": str(e)}
                )

    def _setup_session_routes(self):
        """Setup session management routes."""

        @self.app.post("/api/sessions", response_model=SessionResponse)
        async def create_session(
            request: SessionCreateRequest, current_user: Dict[str, Any] = None
        ):
            """Create a new session for a frontend client."""
            try:
                # Use authenticated user ID if available
                user_id = request.user_id
                if self.enable_auth and current_user:
                    user_id = current_user.get("user_id", user_id)

                session_id = await self.agent_ui.create_session(
                    user_id=user_id, metadata=request.metadata
                )

                session = await self.agent_ui.get_session(session_id)
                self.requests_processed += 1

                # Log session creation
                logger.info(f"Session created: {session_id} for user {user_id}")

                # Transform response using SDK node
                response_data = {
                    "session_id": session_id,
                    "user_id": session.user_id,
                    "created_at": session.created_at.isoformat(),
                    "active": session.active,
                }

                transformed = self.data_transformer.execute(
                    data=response_data,
                    transformations=[f"{{**data, 'api_version': '{self.version}'}}"],
                )

                return SessionResponse(**transformed["result"])
            except Exception as e:
                logger.error(f"Error creating session: {e}")

                # Log security event for failed session creation
                logger.warning(
                    f"Session creation failed for user {request.user_id}: {str(e)}"
                )

                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get session information."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            return {
                "session_id": session_id,
                "user_id": session.user_id,
                "created_at": session.created_at.isoformat(),
                "active": session.active,
                "workflows": list(session.workflows.keys()),
                "active_executions": len(
                    [
                        exec_id
                        for exec_id, exec_data in session.executions.items()
                        if exec_data["status"] in ["started", "running"]
                    ]
                ),
            }

        @self.app.delete("/api/sessions/{session_id}")
        async def close_session(session_id: str):
            """Close a session."""
            await self.agent_ui.close_session(session_id)
            return {"message": "Session closed"}

        @self.app.get("/api/sessions")
        async def list_sessions():
            """List all active sessions."""
            sessions = []
            for session_id, session in self.agent_ui.sessions.items():
                if session.active:
                    sessions.append(
                        {
                            "session_id": session_id,
                            "user_id": session.user_id,
                            "created_at": session.created_at.isoformat(),
                            "workflow_count": len(session.workflows),
                            "execution_count": len(session.executions),
                        }
                    )
            return {"sessions": sessions, "total": len(sessions)}

    def _setup_workflow_routes(self):
        """Setup workflow management routes."""

        @self.app.post("/api/workflows")
        async def create_workflow(request: WorkflowCreateRequest, session_id: str):
            """Create a new workflow dynamically."""
            try:
                workflow_config = {
                    "name": request.name,
                    "description": request.description,
                    "nodes": request.nodes,
                    "connections": request.connections,
                    "metadata": request.metadata,
                }

                workflow_id = await self.agent_ui.create_dynamic_workflow(
                    session_id=session_id, workflow_config=workflow_config
                )

                return {
                    "workflow_id": workflow_id,
                    "name": request.name,
                    "session_id": session_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            except Exception as e:
                logger.error(f"Error creating workflow: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/workflows/{workflow_id}")
        async def get_workflow(workflow_id: str, session_id: str):
            """Get workflow information and schema."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            workflow = None
            if workflow_id in session.workflows:
                workflow = session.workflows[workflow_id]
            elif workflow_id in self.agent_ui.shared_workflows:
                workflow = self.agent_ui.shared_workflows[workflow_id]
            else:
                raise HTTPException(status_code=404, detail="Workflow not found")

            # Generate schema
            schema = self.schema_registry.get_workflow_schema(workflow)

            return {
                "workflow_id": workflow_id,
                "schema": schema,
                "is_shared": workflow_id in self.agent_ui.shared_workflows,
            }

        @self.app.get("/api/workflows")
        async def list_workflows(session_id: Optional[str] = None):
            """List available workflows."""
            workflows = []

            # Add shared workflows
            for workflow_id, workflow in self.agent_ui.shared_workflows.items():
                workflows.append(
                    {
                        "workflow_id": workflow_id,
                        "name": workflow.name,
                        "description": workflow.description,
                        "is_shared": True,
                        "node_count": len(workflow.nodes),
                    }
                )

            # Add session workflows if session_id provided
            if session_id:
                session = await self.agent_ui.get_session(session_id)
                if session:
                    for workflow_id, workflow in session.workflows.items():
                        workflows.append(
                            {
                                "workflow_id": workflow_id,
                                "name": workflow.name,
                                "description": workflow.description,
                                "is_shared": False,
                                "node_count": len(workflow.nodes),
                            }
                        )

            return {"workflows": workflows, "total": len(workflows)}

    def _setup_execution_routes(self):
        """Setup workflow execution routes."""

        @self.app.post("/api/executions", response_model=ExecutionResponse)
        async def execute_workflow(request: WorkflowExecuteRequest, session_id: str):
            """Execute a workflow."""
            try:
                execution_id = await self.agent_ui.execute_workflow(
                    session_id=session_id,
                    workflow_id=request.workflow_id,
                    inputs=request.inputs,
                    config_overrides=request.config_overrides,
                )

                return ExecutionResponse(
                    execution_id=execution_id,
                    workflow_id=request.workflow_id,
                    status="started",
                    created_at=datetime.now(timezone.utc),
                )
            except Exception as e:
                logger.error(f"Error executing workflow: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/executions/{execution_id}")
        async def get_execution_status(execution_id: str, session_id: str):
            """Get execution status."""
            status = await self.agent_ui.get_execution_status(execution_id, session_id)
            if not status:
                raise HTTPException(status_code=404, detail="Execution not found")

            return {
                "execution_id": execution_id,
                "status": status["status"],
                "progress": status.get("progress", 0.0),
                "created_at": status["created_at"].isoformat(),
                "outputs": status.get("outputs", {}),
                "error": status.get("error"),
            }

        @self.app.delete("/api/executions/{execution_id}")
        async def cancel_execution(execution_id: str, session_id: str):
            """Cancel a running execution."""
            await self.agent_ui.cancel_execution(execution_id, session_id)
            return {"message": "Execution cancelled"}

        @self.app.get("/api/executions")
        async def list_executions(session_id: str):
            """List executions for a session."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            executions = []
            for execution_id, execution in session.executions.items():
                executions.append(
                    {
                        "execution_id": execution_id,
                        "workflow_id": execution["workflow_id"],
                        "status": execution["status"],
                        "progress": execution.get("progress", 0.0),
                        "created_at": execution["created_at"].isoformat(),
                    }
                )

            return {"executions": executions, "total": len(executions)}

    def _setup_schema_routes(self):
        """Setup schema and node discovery routes."""

        @self.app.get("/api/schemas/nodes")
        async def get_node_schemas(request: NodeSchemaRequest = Depends()):
            """Get schemas for available node types."""
            try:
                # Get all registered nodes
                available_nodes = self.node_registry.get_all_nodes()

                # Filter by requested types if specified
                if request.node_types:
                    available_nodes = {
                        name: node_class
                        for name, node_class in available_nodes.items()
                        if name in request.node_types
                    }

                # Generate schemas
                schemas = {}
                for node_name, node_class in available_nodes.items():
                    schema = self.schema_registry.get_node_schema(node_class)
                    schemas[node_name] = schema

                return {
                    "schemas": schemas,
                    "total": len(schemas),
                    "categories": self._get_node_categories(schemas),
                }
            except Exception as e:
                logger.error(f"Error getting node schemas: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/schemas/nodes/{node_type}")
        async def get_node_schema(node_type: str):
            """Get schema for a specific node type."""
            node_class = self.node_registry.get_node(node_type)
            if not node_class:
                raise HTTPException(status_code=404, detail="Node type not found")

            schema = self.schema_registry.get_node_schema(node_class)
            return {"node_type": node_type, "schema": schema}

        @self.app.get("/api/schemas/workflows/{workflow_id}")
        async def get_workflow_schema(workflow_id: str, session_id: str):
            """Get schema for a specific workflow."""
            session = await self.agent_ui.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            workflow = None
            if workflow_id in session.workflows:
                workflow = session.workflows[workflow_id]
            elif workflow_id in self.agent_ui.shared_workflows:
                workflow = self.agent_ui.shared_workflows[workflow_id]
            else:
                raise HTTPException(status_code=404, detail="Workflow not found")

            schema = self.schema_registry.get_workflow_schema(workflow)
            return {"workflow_id": workflow_id, "schema": schema}

    def _get_node_categories(self, schemas: Dict[str, Any]) -> Dict[str, List[str]]:
        """Group nodes by category."""
        categories = {}
        for node_name, schema in schemas.items():
            category = schema.get("category", "general")
            if category not in categories:
                categories[category] = []
            categories[category].append(node_name)
        return categories

    def _setup_realtime_routes(self):
        """Setup real-time communication routes."""

        @self.app.websocket("/ws")
        async def websocket_endpoint(
            websocket: WebSocket,
            session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            event_types: Optional[str] = None,
        ):
            """WebSocket endpoint for real-time communication."""
            # Parse event types from query parameter
            event_type_list = event_types.split(",") if event_types else None

            await self.realtime.handle_websocket(
                websocket, session_id, user_id, event_type_list
            )

        @self.app.get("/events")
        async def sse_endpoint(
            request: Request,
            session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            event_types: Optional[str] = None,
        ):
            """Server-Sent Events endpoint."""
            event_type_list = event_types.split(",") if event_types else None

            return self.realtime.create_sse_stream(
                request, session_id, user_id, event_type_list
            )

        @self.app.post("/api/webhooks")
        async def register_webhook(request: WebhookRegisterRequest):
            """Register a webhook endpoint."""
            webhook_id = str(uuid.uuid4())

            self.realtime.register_webhook(
                webhook_id=webhook_id,
                url=request.url,
                secret=request.secret,
                event_types=request.event_types,
                headers=request.headers,
            )

            return {
                "webhook_id": webhook_id,
                "url": request.url,
                "event_types": request.event_types,
            }

        @self.app.delete("/api/webhooks/{webhook_id}")
        async def unregister_webhook(webhook_id: str):
            """Unregister a webhook endpoint."""
            self.realtime.unregister_webhook(webhook_id)
            return {"message": "Webhook unregistered"}

    def _setup_monitoring_routes(self):
        """Setup monitoring and statistics routes."""

        @self.app.get("/api/stats")
        async def get_stats():
            """Get comprehensive system statistics."""
            try:
                return {
                    "gateway": {
                        "uptime_seconds": time.time() - self.start_time,
                        "requests_processed": self.requests_processed,
                        "title": self.title,
                        "version": self.version,
                    },
                    "agent_ui": self.agent_ui.get_stats(),
                    "realtime": self.realtime.get_stats(),
                    "schema_registry": self.schema_registry.get_stats(),
                }
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/events/recent")
        async def get_recent_events(
            count: int = 100,
            event_types: Optional[str] = None,
            session_id: Optional[str] = None,
        ):
            """Get recent events with filtering."""
            try:
                # Parse event types
                event_type_list = None
                if event_types:
                    event_type_list = [
                        EventType(t.strip()) for t in event_types.split(",")
                    ]

                # Create filter
                event_filter = EventFilter(
                    event_types=event_type_list, session_id=session_id
                )

                # Get events
                events = await self.agent_ui.event_stream.get_recent_events(
                    count=count, event_filter=event_filter
                )

                return {
                    "events": [event.to_dict() for event in events],
                    "total": len(events),
                    "filters": {
                        "event_types": event_types,
                        "session_id": session_id,
                        "count": count,
                    },
                }
            except Exception as e:
                logger.error(f"Error getting recent events: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    # Public API methods
    def run(
        self, host: str = "0.0.0.0", port: int = 8000, reload: bool = False, **kwargs
    ):
        """Run the API gateway server."""
        import uvicorn

        logger.info(f"Starting {self.title} on {host}:{port}")
        uvicorn.run(self.app, host=host, port=port, reload=reload, **kwargs)

    def mount_existing_app(self, path: str, app: FastAPI):
        """Mount an existing FastAPI app at a specific path."""
        self.app.mount(path, app)
        logger.info(f"Mounted existing app at {path}")

    def register_shared_workflow(
        self, workflow_id: str, workflow: Union[Workflow, WorkflowBuilder]
    ):
        """Register a workflow as shared across all sessions."""
        asyncio.create_task(
            self.agent_ui.register_workflow(
                workflow_id=workflow_id, workflow=workflow, make_shared=True
            )
        )
        logger.info(f"Registered shared workflow: {workflow_id}")


# Convenience function for quick setup
def create_gateway(
    agent_ui_middleware: AgentUIMiddleware = None, auth_manager=None, **kwargs
) -> APIGateway:
    """
    Create a configured API gateway instance with dependency injection.

    Args:
        agent_ui_middleware: Optional existing AgentUIMiddleware instance
        auth_manager: Optional auth manager instance (e.g., JWTAuthManager)
        **kwargs: Additional arguments for APIGateway initialization

    Returns:
        Configured APIGateway instance

    Example:
        >>> from kailash.middleware.auth import JWTAuthManager
        >>>
        >>> # Create with custom auth
        >>> auth = JWTAuthManager(use_rsa=True)
        >>> gateway = create_gateway(
        ...     title="My App Gateway",
        ...     cors_origins=["http://localhost:3000"],
        ...     auth_manager=auth
        ... )
        >>>
        >>> # Or use default auth
        >>> gateway = create_gateway(title="My App")
        >>>
        >>> gateway.execute(port=8000)
    """
    # Pass auth_manager to APIGateway
    if auth_manager is not None:
        kwargs["auth_manager"] = auth_manager

    gateway = APIGateway(**kwargs)

    if agent_ui_middleware:
        gateway.agent_ui = agent_ui_middleware
        gateway.realtime = RealtimeMiddleware(agent_ui_middleware)

    return gateway
