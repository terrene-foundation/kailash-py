"""
Kailash Workflow Studio API with JWT Authentication and Tenant Isolation

This module provides REST API endpoints for the Workflow Studio frontend,
with full JWT-based authentication and tenant isolation.

Key Features:
- JWT token-based authentication
- Complete tenant data isolation
- Role-based access control
- Secure workflow execution
- API key support for automation
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from kailash.nodes.base import NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.workflow import Workflow

from .auth import (
    APIKey,
    AuthService,
    Tenant,
    TenantContext,
    TokenResponse,
    User,
    UserCreate,
    UserLogin,
    get_current_tenant,
    get_current_user,
    require_permission,
)
from .custom_nodes import setup_custom_node_routes
from .database import (
    CustomNodeRepository,
    ExecutionRepository,
    WorkflowRepository,
    get_db_session,
    init_database,
)

logger = logging.getLogger(__name__)


# Pydantic models for API
class NodeDefinition(BaseModel):
    """Node definition for frontend consumption"""

    id: str
    category: str
    name: str
    description: str
    parameters: List[Dict[str, Any]]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]


class WorkflowCreate(BaseModel):
    """Workflow creation request"""

    name: str
    description: Optional[str] = None
    definition: Dict[str, Any]


class WorkflowUpdate(BaseModel):
    """Workflow update request"""

    name: Optional[str] = None
    description: Optional[str] = None
    definition: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    """Workflow response model"""

    id: str
    name: str
    description: Optional[str]
    definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]
    version: int


class ExecutionRequest(BaseModel):
    """Workflow execution request"""

    parameters: Optional[Dict[str, Any]] = None


class ExecutionResponse(BaseModel):
    """Workflow execution response"""

    id: str
    workflow_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    result: Optional[Dict[str, Any]]
    error: Optional[str]


class WorkflowImportRequest(BaseModel):
    """Workflow import request"""

    name: str
    description: Optional[str] = None
    format: str = Field(..., pattern="^(yaml|json|python)$")
    content: str


class WorkflowImportResponse(BaseModel):
    """Workflow import response"""

    id: str
    name: str
    description: Optional[str]
    definition: Dict[str, Any]
    created_at: datetime
    warnings: List[str] = []


class WorkflowStudioAPI:
    """Main API class for Workflow Studio with authentication"""

    def __init__(self, db_path: str = None):
        self.app = FastAPI(
            title="Kailash Workflow Studio API",
            version="2.0.0",
            description="Secure multi-tenant workflow studio API",
        )

        # Initialize database
        self.SessionLocal, self.engine = init_database(db_path)

        self.setup_middleware()
        self.setup_auth_routes()
        self.setup_routes()
        self.active_executions: Dict[str, asyncio.Task] = {}
        self.websocket_connections: Dict[str, List[WebSocket]] = {}

        # Register custom nodes on startup
        self.app.add_event_handler("startup", self._register_custom_nodes)

    async def _register_custom_nodes(self):
        """Register custom nodes from database into NodeRegistry"""
        try:
            with self.SessionLocal() as session:
                # Get all tenants
                tenants = session.query(Tenant).filter(Tenant.is_active).all()

                for tenant in tenants:
                    node_repo = CustomNodeRepository(session)
                    custom_nodes = node_repo.list(tenant.id)

                    for node in custom_nodes:
                        # Register node in NodeRegistry with tenant prefix
                        # This would require dynamic node creation based on stored definition
                        logger.info(
                            f"Registered custom node: {tenant.slug}/{node.name}"
                        )
        except Exception as e:
            logger.error(f"Error registering custom nodes: {e}")

    def setup_middleware(self):
        """Configure CORS and other middleware"""
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def setup_auth_routes(self):
        """Configure authentication routes"""

        @self.app.post("/api/auth/register", response_model=TokenResponse)
        async def register(
            user_data: UserCreate, session: Session = Depends(get_db_session)
        ):
            """Register a new user"""
            auth_service = AuthService(session)
            user, tokens = auth_service.register_user(user_data)
            return tokens

        @self.app.post("/api/auth/login", response_model=TokenResponse)
        async def login(
            credentials: UserLogin, session: Session = Depends(get_db_session)
        ):
            """Login and get JWT tokens"""
            auth_service = AuthService(session)
            user, tokens = auth_service.login_user(credentials)
            return tokens

        @self.app.post("/api/auth/refresh", response_model=TokenResponse)
        async def refresh_token(
            refresh_token: str = Body(..., embed=True),
            session: Session = Depends(get_db_session),
        ):
            """Refresh access token using refresh token"""
            auth_service = AuthService(session)
            return auth_service.refresh_token(refresh_token)

        @self.app.get("/api/auth/me")
        async def get_current_user_info(
            user: User = Depends(get_current_user),
            tenant: Tenant = Depends(get_current_tenant),
        ):
            """Get current user information"""
            return {
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "roles": user.roles,
                    "is_verified": user.is_verified,
                },
                "tenant": {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "subscription_tier": tenant.subscription_tier,
                    "features": tenant.features,
                },
            }

    def setup_routes(self):
        """Configure API routes with authentication"""

        # Setup custom node routes
        setup_custom_node_routes(self.app, self.SessionLocal)

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "version": "2.0.0"}

        # Node discovery endpoints
        @self.app.get("/api/nodes", response_model=Dict[str, List[NodeDefinition]])
        async def list_nodes(user: User = Depends(get_current_user)):
            """List all available nodes grouped by category"""
            # Filter nodes based on user permissions
            registry = NodeRegistry.list_nodes()
            nodes_by_category = {}

            for node_id, node_class in registry.items():
                # Skip nodes user doesn't have access to
                if not self._can_access_node(user, node_id):
                    continue

                # Extract category from module path
                module_parts = node_class.__module__.split(".")
                if "nodes" in module_parts:
                    idx = module_parts.index("nodes")
                    if idx + 1 < len(module_parts):
                        category = module_parts[idx + 1]
                    else:
                        category = "misc"
                else:
                    category = "misc"

                # Get node parameters
                try:
                    params = node_class.get_parameters()
                    param_list = [
                        {
                            "name": name,
                            "type": str(
                                param.type.__name__
                                if hasattr(param.type, "__name__")
                                else str(param.type)
                            ),
                            "required": param.required,
                            "description": param.description,
                            "default": param.default,
                        }
                        for name, param in params.items()
                    ]
                except Exception:
                    param_list = []

                # Extract input/output information
                inputs = []
                outputs = []

                # Check if node has explicit input schema
                if hasattr(node_class, "get_input_schema"):
                    try:
                        input_schema = node_class.get_input_schema()
                        if isinstance(input_schema, dict):
                            for key, schema in input_schema.items():
                                inputs.append(
                                    {
                                        "name": key,
                                        "type": schema.get("type", "any"),
                                        "required": schema.get("required", True),
                                    }
                                )
                    except Exception:
                        pass

                # If no explicit schema, infer from parameters
                if not inputs:
                    # Check if any parameters are marked as input sources
                    for param_name, param in params.items():
                        if hasattr(param, "source") and param.source == "input":
                            inputs.append(
                                {
                                    "name": param_name,
                                    "type": str(
                                        param.type.__name__
                                        if hasattr(param.type, "__name__")
                                        else "any"
                                    ),
                                    "required": param.required,
                                }
                            )

                    # If still no inputs and node typically processes data, add default
                    if not inputs and any(
                        keyword in node_class.__name__.lower()
                        for keyword in ["process", "transform", "filter", "merge"]
                    ):
                        inputs.append({"name": "data", "type": "any", "required": True})

                # Extract output information
                if hasattr(node_class, "get_output_schema"):
                    try:
                        output_schema = node_class.get_output_schema()
                        outputs.append(
                            {
                                "name": "output",
                                "type": (
                                    "object"
                                    if isinstance(output_schema, dict)
                                    else "any"
                                ),
                                "schema": (
                                    output_schema
                                    if isinstance(output_schema, dict)
                                    else None
                                ),
                            }
                        )
                    except Exception:
                        outputs.append({"name": "output", "type": "any"})
                else:
                    # Default output for all nodes
                    outputs.append({"name": "output", "type": "any"})

                # Create node definition
                node_def = NodeDefinition(
                    id=node_id,
                    category=category,
                    name=node_class.__name__,
                    description=node_class.__doc__ or "No description available",
                    parameters=param_list,
                    inputs=inputs,
                    outputs=outputs,
                )

                if category not in nodes_by_category:
                    nodes_by_category[category] = []
                nodes_by_category[category].append(node_def)

            return nodes_by_category

        # Workflow management endpoints with tenant isolation
        @self.app.get("/api/workflows", response_model=List[WorkflowResponse])
        async def list_workflows(
            limit: int = Query(100, ge=1, le=1000),
            offset: int = Query(0, ge=0),
            user: User = Depends(require_permission("read:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """List all workflows for the tenant"""
            repo = WorkflowRepository(session)
            workflows = repo.list(tenant.id, limit=limit, offset=offset)

            return [
                WorkflowResponse(
                    id=w.id,
                    name=w.name,
                    description=w.description,
                    definition=w.definition,
                    created_at=w.created_at,
                    updated_at=w.updated_at,
                    created_by=w.created_by,
                    version=w.version,
                )
                for w in workflows
            ]

        @self.app.post("/api/workflows", response_model=WorkflowResponse)
        async def create_workflow(
            workflow: WorkflowCreate,
            user: User = Depends(require_permission("write:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Create a new workflow"""
            # Check workflow limit
            if tenant.max_workflows["current"] >= tenant.max_workflows["limit"]:
                raise HTTPException(
                    status_code=403, detail="Workflow limit reached for tenant"
                )

            repo = WorkflowRepository(session)
            workflow_model = repo.create(
                tenant_id=tenant.id,
                name=workflow.name,
                description=workflow.description,
                definition=workflow.definition,
                created_by=user.email,
            )

            # Update tenant workflow count
            tenant.max_workflows["current"] += 1
            session.commit()

            return WorkflowResponse(
                id=workflow_model.id,
                name=workflow_model.name,
                description=workflow_model.description,
                definition=workflow_model.definition,
                created_at=workflow_model.created_at,
                updated_at=workflow_model.updated_at,
                created_by=workflow_model.created_by,
                version=workflow_model.version,
            )

        @self.app.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
        async def get_workflow(
            workflow_id: str,
            user: User = Depends(require_permission("read:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Get a specific workflow"""
            repo = WorkflowRepository(session)
            workflow = repo.get(workflow_id)

            if not workflow or workflow.tenant_id != tenant.id:
                raise HTTPException(status_code=404, detail="Workflow not found")

            return WorkflowResponse(
                id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                definition=workflow.definition,
                created_at=workflow.created_at,
                updated_at=workflow.updated_at,
                created_by=workflow.created_by,
                version=workflow.version,
            )

        @self.app.put("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
        async def update_workflow(
            workflow_id: str,
            update: WorkflowUpdate,
            user: User = Depends(require_permission("write:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Update an existing workflow"""
            repo = WorkflowRepository(session)
            workflow = repo.get(workflow_id)

            if not workflow or workflow.tenant_id != tenant.id:
                raise HTTPException(status_code=404, detail="Workflow not found")

            # Prepare updates
            updates = {}
            if update.name is not None:
                updates["name"] = update.name
            if update.description is not None:
                updates["description"] = update.description
            if update.definition is not None:
                updates["definition"] = update.definition

            workflow = repo.update(workflow_id, updates, updated_by=user.email)

            return WorkflowResponse(
                id=workflow.id,
                name=workflow.name,
                description=workflow.description,
                definition=workflow.definition,
                created_at=workflow.created_at,
                updated_at=workflow.updated_at,
                created_by=workflow.created_by,
                version=workflow.version,
            )

        @self.app.delete("/api/workflows/{workflow_id}")
        async def delete_workflow(
            workflow_id: str,
            user: User = Depends(require_permission("delete:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Delete a workflow"""
            repo = WorkflowRepository(session)
            workflow = repo.get(workflow_id)

            if not workflow or workflow.tenant_id != tenant.id:
                raise HTTPException(status_code=404, detail="Workflow not found")

            repo.delete(workflow_id)

            # Update tenant workflow count
            tenant.max_workflows["current"] -= 1
            session.commit()

            return {"message": "Workflow deleted successfully"}

        # Workflow execution endpoints
        @self.app.post(
            "/api/workflows/{workflow_id}/execute", response_model=ExecutionResponse
        )
        async def execute_workflow(
            workflow_id: str,
            request: ExecutionRequest,
            user: User = Depends(require_permission("execute:workflows")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Execute a workflow"""
            # Check execution limits
            if (
                tenant.max_executions_per_month["current"]
                >= tenant.max_executions_per_month["limit"]
            ):
                raise HTTPException(
                    status_code=403, detail="Monthly execution limit reached for tenant"
                )

            # Get workflow
            workflow_repo = WorkflowRepository(session)
            workflow_model = workflow_repo.get(workflow_id)

            if not workflow_model or workflow_model.tenant_id != tenant.id:
                raise HTTPException(status_code=404, detail="Workflow not found")

            # Create execution record
            exec_repo = ExecutionRepository(session)
            execution = exec_repo.create(
                workflow_id=workflow_id,
                tenant_id=tenant.id,
                parameters=request.parameters,
            )

            # Update tenant execution count
            tenant.max_executions_per_month["current"] += 1
            session.commit()

            # Create workflow from definition
            try:
                workflow = Workflow.from_dict(workflow_model.definition)

                # Create tenant-isolated runtime
                runtime = self._create_tenant_runtime(tenant.id)

                # Start execution in background
                task = asyncio.create_task(
                    self._execute_workflow_async(
                        execution.id,
                        workflow,
                        runtime,
                        request.parameters or {},
                        tenant.id,
                    )
                )
                self.active_executions[execution.id] = task

                return ExecutionResponse(
                    id=execution.id,
                    workflow_id=workflow_id,
                    status=execution.status,
                    started_at=execution.started_at,
                    completed_at=execution.completed_at,
                    result=execution.result,
                    error=execution.error,
                )

            except Exception as e:
                exec_repo.update_status(execution.id, "failed", error=str(e))
                raise HTTPException(
                    status_code=500, detail=f"Execution failed: {str(e)}"
                )

        @self.app.get(
            "/api/executions/{execution_id}", response_model=ExecutionResponse
        )
        async def get_execution(
            execution_id: str,
            user: User = Depends(require_permission("read:executions")),
            tenant: Tenant = Depends(get_current_tenant),
            session: Session = Depends(get_db_session),
        ):
            """Get execution status"""
            repo = ExecutionRepository(session)
            execution = repo.get(execution_id)

            if not execution or execution.tenant_id != tenant.id:
                raise HTTPException(status_code=404, detail="Execution not found")

            return ExecutionResponse(
                id=execution.id,
                workflow_id=execution.workflow_id,
                status=execution.status,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                result=execution.result,
                error=execution.error,
            )

        # WebSocket for real-time updates (with auth)
        @self.app.websocket("/ws/executions/{execution_id}")
        async def websocket_execution(
            websocket: WebSocket, execution_id: str, token: str = Query(...)
        ):
            """WebSocket endpoint for real-time execution updates"""
            # Verify token
            try:
                from .auth import JWTAuth

                auth = JWTAuth()
                token_data = auth.verify_token(token)
            except Exception:
                await websocket.close(code=1008, reason="Unauthorized")
                return

            await websocket.accept()

            # Add to connection pool
            if execution_id not in self.websocket_connections:
                self.websocket_connections[execution_id] = []
            self.websocket_connections[execution_id].append(websocket)

            try:
                # Keep connection alive and send updates
                while True:
                    # Get execution from database
                    with self.SessionLocal() as session:
                        repo = ExecutionRepository(session)
                        execution = repo.get(execution_id)

                        if not execution or execution.tenant_id != token_data.tenant_id:
                            await websocket.send_json({"error": "Execution not found"})
                            break

                        # Send current status
                        await websocket.send_json(
                            {
                                "id": execution.id,
                                "status": execution.status,
                                "result": execution.result,
                                "error": execution.error,
                            }
                        )

                        # If execution is complete, close connection
                        if execution.status in ["completed", "failed"]:
                            break

                    # Wait before next update
                    await asyncio.sleep(1)

            except WebSocketDisconnect:
                pass
            finally:
                # Remove from connection pool
                if execution_id in self.websocket_connections:
                    self.websocket_connections[execution_id].remove(websocket)
                    if not self.websocket_connections[execution_id]:
                        del self.websocket_connections[execution_id]

        # API key endpoints
        @self.app.post("/api/apikeys")
        async def create_api_key(
            name: str = Body(...),
            scopes: List[str] = Body(default=["read:workflows", "execute:workflows"]),
            user: User = Depends(get_current_user),
            session: Session = Depends(get_db_session),
        ):
            """Create a new API key"""
            auth_service = AuthService(session)
            key, api_key_model = auth_service.create_api_key(name, user, scopes)

            return {
                "id": api_key_model.id,
                "key": key,  # Only shown once!
                "name": api_key_model.name,
                "scopes": api_key_model.scopes,
                "created_at": api_key_model.created_at,
            }

        @self.app.get("/api/apikeys")
        async def list_api_keys(
            user: User = Depends(get_current_user),
            session: Session = Depends(get_db_session),
        ):
            """List user's API keys"""
            keys = (
                session.query(APIKey)
                .filter(APIKey.user_id == user.id, APIKey.tenant_id == user.tenant_id)
                .all()
            )

            return [
                {
                    "id": k.id,
                    "name": k.name,
                    "scopes": k.scopes,
                    "is_active": k.is_active,
                    "last_used_at": k.last_used_at,
                    "created_at": k.created_at,
                }
                for k in keys
            ]

        @self.app.delete("/api/apikeys/{key_id}")
        async def delete_api_key(
            key_id: str,
            user: User = Depends(get_current_user),
            session: Session = Depends(get_db_session),
        ):
            """Delete an API key"""
            key = (
                session.query(APIKey)
                .filter(APIKey.id == key_id, APIKey.user_id == user.id)
                .first()
            )

            if not key:
                raise HTTPException(status_code=404, detail="API key not found")

            session.delete(key)
            session.commit()

            return {"message": "API key deleted successfully"}

    def _can_access_node(self, user: User, node_id: str) -> bool:
        """Check if user can access a specific node"""
        # Basic nodes available to all
        basic_nodes = [
            "csv_reader",
            "csv_writer",
            "json_reader",
            "json_writer",
            "text_processor",
            "data_filter",
            "data_aggregator",
        ]

        # Advanced nodes require specific permissions or subscription
        # advanced_nodes = {
        #     "llm_agent": ["ai_features"],
        #     "embedding_generator": ["ai_features"],
        #     "python_code": ["code_execution"],
        #     "api_client": ["external_apis"],
        # }

        if node_id in basic_nodes:
            return True

        # Check subscription tier and features
        # This would be more sophisticated in production
        return True  # For now, allow all nodes

    def _create_tenant_runtime(self, tenant_id: str) -> LocalRuntime:
        """Create a runtime with tenant isolation"""
        # Create tenant-specific storage path
        base_path = Path(f"tenants/{tenant_id}/runtime")
        base_path.mkdir(parents=True, exist_ok=True)

        # Initialize storage backend
        storage = FileSystemStorage(base_path=str(base_path))
        task_manager = TaskManager(storage_backend=storage)

        # Create runtime with tenant context
        runtime = LocalRuntime()
        runtime.task_manager = task_manager

        return runtime

    async def _execute_workflow_async(
        self,
        execution_id: str,
        workflow: Workflow,
        runtime: LocalRuntime,
        parameters: Dict[str, Any],
        tenant_id: str,
    ):
        """Execute workflow asynchronously with tenant isolation"""
        with self.SessionLocal() as session:
            exec_repo = ExecutionRepository(session)

            try:
                # Set tenant context for execution
                with TenantContext(tenant_id):
                    # Execute workflow
                    result, run_id = runtime.execute(workflow, parameters=parameters)

                # Update execution record
                exec_repo.update_status(execution_id, "completed", result=result)

                # Notify WebSocket clients
                await self._notify_websocket_clients(
                    execution_id,
                    {"id": execution_id, "status": "completed", "result": result},
                )

            except Exception as e:
                # Update execution record with error
                exec_repo.update_status(execution_id, "failed", error=str(e))

                # Notify WebSocket clients
                await self._notify_websocket_clients(
                    execution_id,
                    {"id": execution_id, "status": "failed", "error": str(e)},
                )

            finally:
                # Remove from active executions
                if execution_id in self.active_executions:
                    del self.active_executions[execution_id]

    async def _notify_websocket_clients(self, execution_id: str, data: Dict[str, Any]):
        """Notify all WebSocket clients watching this execution"""
        if execution_id in self.websocket_connections:
            for websocket in self.websocket_connections[execution_id]:
                try:
                    await websocket.send_json(data)
                except Exception:
                    pass  # Client disconnected

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the API server"""
        uvicorn.run(self.app, host=host, port=port)


def main():
    """Main entry point for the secure studio API"""
    import argparse

    parser = argparse.ArgumentParser(description="Kailash Workflow Studio API (Secure)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run API
    api = WorkflowStudioAPI()
    api.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
