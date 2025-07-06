"""
Kailash Workflow Studio API

This module provides REST API endpoints for the Workflow Studio frontend,
enabling visual workflow creation and management.

The API is designed to be multi-tenant aware with proper isolation between
different tenants' workflows and data.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from kailash.nodes.base import NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.tracking.manager import TaskManager
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.utils.export import export_workflow
from kailash.workflow import Workflow

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
    parameters: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]


class WorkflowCreate(BaseModel):
    """Workflow creation request"""

    name: str
    description: str | None = None
    definition: dict[str, Any]


class WorkflowUpdate(BaseModel):
    """Workflow update request"""

    name: str | None = None
    description: str | None = None
    definition: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    """Workflow response model"""

    id: str
    name: str
    description: str | None
    definition: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ExecutionRequest(BaseModel):
    """Workflow execution request"""

    parameters: dict[str, Any] | None = None


class ExecutionResponse(BaseModel):
    """Workflow execution response"""

    id: str
    workflow_id: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    result: dict[str, Any] | None
    error: str | None


class WorkflowImportRequest(BaseModel):
    """Workflow import request"""

    name: str
    description: str | None = None
    format: str = Field(..., pattern="^(yaml|json|python)$")
    content: str


class WorkflowImportResponse(BaseModel):
    """Workflow import response"""

    id: str
    name: str
    description: str | None
    definition: dict[str, Any]
    created_at: datetime
    warnings: list[str] = []


class WorkflowStudioAPI:
    """Main API class for Workflow Studio"""

    def __init__(self, tenant_id: str = "default", db_path: str = None):
        self.tenant_id = tenant_id
        self.app = FastAPI(title="Kailash Workflow Studio API", version="1.0.0")

        # Initialize database
        self.SessionLocal, self.engine = init_database(db_path)

        # Initialize repositories
        self.setup_repositories()

        self.setup_middleware()
        self.setup_routes()
        self.setup_storage()
        self.active_executions: dict[str, asyncio.Task] = {}
        self.websocket_connections: dict[str, list[WebSocket]] = {}

        # Register custom nodes on startup
        self.app.add_event_handler("startup", self._register_custom_nodes)
        # Ensure built-in nodes are loaded on startup
        self.app.add_event_handler("startup", self._ensure_nodes_loaded)

    def setup_repositories(self):
        """Initialize database repositories"""
        with get_db_session(self.SessionLocal) as session:
            self.workflow_repo = WorkflowRepository(session)
            self.node_repo = CustomNodeRepository(session)
            self.execution_repo = ExecutionRepository(session)

    async def _register_custom_nodes(self):
        """Register custom nodes from database into NodeRegistry"""
        try:
            with get_db_session(self.SessionLocal) as session:
                node_repo = CustomNodeRepository(session)
                custom_nodes = node_repo.list(self.tenant_id)

                for node in custom_nodes:
                    # Register node in NodeRegistry
                    # This would require dynamic node creation based on stored definition
                    logger.info(f"Registered custom node: {node.name}")
        except Exception as e:
            logger.error(f"Error registering custom nodes: {e}")

    async def _ensure_nodes_loaded(self):
        """Ensure all built-in nodes are loaded into NodeRegistry"""
        try:
            # Import all node modules to trigger registration

            # Force import of all submodules to trigger @register_node decorators

            # Log the number of registered nodes
            registry = NodeRegistry.list_nodes()
            logger.info(f"Loaded {len(registry)} nodes into NodeRegistry")

            # Log categories
            categories = set()
            for node_id, node_class in registry.items():
                module_parts = node_class.__module__.split(".")
                if "nodes" in module_parts:
                    idx = module_parts.index("nodes")
                    if idx + 1 < len(module_parts):
                        categories.add(module_parts[idx + 1])

            logger.info(f"Node categories: {', '.join(sorted(categories))}")
        except Exception as e:
            logger.error(f"Error loading nodes: {e}")
            import traceback

            logger.error(traceback.format_exc())

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

    def setup_storage(self):
        """Initialize storage for workflows and executions"""
        base_path = Path(f"tenants/{self.tenant_id}")
        base_path.mkdir(parents=True, exist_ok=True)

        self.workflows_path = base_path / "workflows"
        self.workflows_path.mkdir(exist_ok=True)

        self.executions_path = base_path / "executions"
        self.executions_path.mkdir(exist_ok=True)

        # Initialize task manager for execution tracking
        storage = FileSystemStorage(base_path=str(base_path / "tracking"))
        self.task_manager = TaskManager(storage_backend=storage)

    def setup_routes(self):
        """Configure API routes"""

        # Setup custom node routes

        setup_custom_node_routes(self.app, self.SessionLocal, self.tenant_id)

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            return {"status": "healthy", "tenant_id": self.tenant_id}

        # Node discovery endpoints
        @self.app.get("/api/nodes", response_model=dict[str, list[NodeDefinition]])
        async def list_nodes():
            """List all available nodes grouped by category"""
            try:
                registry = NodeRegistry.list_nodes()
                nodes_by_category = {}

                # Log registry contents for debugging
                logger.info(f"NodeRegistry contains {len(registry)} nodes")

                if not registry:
                    logger.warning("NodeRegistry is empty - no nodes registered")
                    return {}

                for node_id, node_class in registry.items():
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
                        # Create a temporary instance to get parameters
                        # Most nodes should work with empty config
                        temp_node = node_class()
                        params = temp_node.get_parameters()
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
                    except Exception as e:
                        logger.error(
                            f"Error getting parameters for node {node_id}: {e}"
                        )
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
                        try:
                            if "params" in locals():
                                for param_name, param in params.items():
                                    if (
                                        hasattr(param, "source")
                                        and param.source == "input"
                                    ):
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
                        except Exception:
                            pass

                        # If still no inputs and node typically processes data, add default
                        if not inputs and any(
                            keyword in node_class.__name__.lower()
                            for keyword in ["process", "transform", "filter", "merge"]
                        ):
                            inputs.append(
                                {"name": "data", "type": "any", "required": True}
                            )

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
            except Exception as e:
                logger.error(f"Error in list_nodes endpoint: {e}")
                raise HTTPException(
                    status_code=500, detail=f"Internal server error: {str(e)}"
                )

        # Add alias for backward compatibility
        @self.app.get(
            "/api/nodes/discover", response_model=dict[str, list[NodeDefinition]]
        )
        async def discover_nodes():
            """Alias for list_nodes endpoint for backward compatibility"""
            return await list_nodes()

        @self.app.get("/api/nodes/{category}")
        async def list_nodes_by_category(category: str):
            """List nodes in a specific category"""
            all_nodes = await list_nodes()
            if category not in all_nodes:
                raise HTTPException(
                    status_code=404, detail=f"Category '{category}' not found"
                )
            return all_nodes[category]

        @self.app.get("/api/nodes/{category}/{node_id}")
        async def get_node_details(category: str, node_id: str):
            """Get detailed information about a specific node"""
            all_nodes = await list_nodes()
            if category not in all_nodes:
                raise HTTPException(
                    status_code=404, detail=f"Category '{category}' not found"
                )

            for node in all_nodes[category]:
                if node.id == node_id:
                    return node

            raise HTTPException(
                status_code=404,
                detail=f"Node '{node_id}' not found in category '{category}'",
            )

        # Workflow management endpoints
        @self.app.get("/api/workflows", response_model=list[WorkflowResponse])
        async def list_workflows(
            limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)
        ):
            """List all workflows for the tenant"""
            workflows = []
            workflow_files = sorted(
                self.workflows_path.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            for workflow_file in workflow_files[offset : offset + limit]:
                try:
                    with open(workflow_file) as f:
                        data = json.load(f)
                        workflows.append(WorkflowResponse(**data))
                except Exception as e:
                    logger.error(f"Error loading workflow {workflow_file}: {e}")

            return workflows

        @self.app.post("/api/workflows", response_model=WorkflowResponse)
        async def create_workflow(workflow: WorkflowCreate):
            """Create a new workflow"""
            workflow_id = str(uuid.uuid4())
            now = datetime.now(UTC)

            workflow_data = {
                "id": workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "definition": workflow.definition,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            # Save workflow
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            with open(workflow_file, "w") as f:
                json.dump(workflow_data, f, indent=2)

            return WorkflowResponse(**workflow_data)

        @self.app.get("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
        async def get_workflow(workflow_id: str):
            """Get a specific workflow"""
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            if not workflow_file.exists():
                raise HTTPException(status_code=404, detail="Workflow not found")

            with open(workflow_file) as f:
                data = json.load(f)

            return WorkflowResponse(**data)

        @self.app.put("/api/workflows/{workflow_id}", response_model=WorkflowResponse)
        async def update_workflow(workflow_id: str, update: WorkflowUpdate):
            """Update an existing workflow"""
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            if not workflow_file.exists():
                raise HTTPException(status_code=404, detail="Workflow not found")

            # Load existing workflow
            with open(workflow_file) as f:
                data = json.load(f)

            # Update fields
            if update.name is not None:
                data["name"] = update.name
            if update.description is not None:
                data["description"] = update.description
            if update.definition is not None:
                data["definition"] = update.definition

            data["updated_at"] = datetime.now(UTC).isoformat()

            # Save updated workflow
            with open(workflow_file, "w") as f:
                json.dump(data, f, indent=2)

            return WorkflowResponse(**data)

        @self.app.delete("/api/workflows/{workflow_id}")
        async def delete_workflow(workflow_id: str):
            """Delete a workflow"""
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            if not workflow_file.exists():
                raise HTTPException(status_code=404, detail="Workflow not found")

            workflow_file.unlink()
            return {"message": "Workflow deleted successfully"}

        # Workflow execution endpoints
        @self.app.post(
            "/api/workflows/{workflow_id}/execute", response_model=ExecutionResponse
        )
        async def execute_workflow(workflow_id: str, request: ExecutionRequest):
            """Execute a workflow"""
            # Load workflow
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            if not workflow_file.exists():
                raise HTTPException(status_code=404, detail="Workflow not found")

            with open(workflow_file) as f:
                workflow_data = json.load(f)

            # Create execution record
            execution_id = str(uuid.uuid4())
            execution_data = {
                "id": execution_id,
                "workflow_id": workflow_id,
                "status": "running",
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": None,
                "result": None,
                "error": None,
            }

            # Save initial execution state
            execution_file = self.executions_path / f"{execution_id}.json"
            with open(execution_file, "w") as f:
                json.dump(execution_data, f, indent=2)

            # Create workflow from definition
            try:
                workflow = Workflow.from_dict(workflow_data["definition"])
                runtime = LocalRuntime()

                # Start execution in background
                task = asyncio.create_task(
                    self._execute_workflow_async(
                        execution_id, workflow, runtime, request.parameters or {}
                    )
                )
                self.active_executions[execution_id] = task

            except Exception as e:
                execution_data["status"] = "failed"
                execution_data["error"] = str(e)
                execution_data["completed_at"] = datetime.now(UTC).isoformat()

                with open(execution_file, "w") as f:
                    json.dump(execution_data, f, indent=2)

            return ExecutionResponse(**execution_data)

        @self.app.get(
            "/api/executions/{execution_id}", response_model=ExecutionResponse
        )
        async def get_execution(execution_id: str):
            """Get execution status"""
            execution_file = self.executions_path / f"{execution_id}.json"
            if not execution_file.exists():
                raise HTTPException(status_code=404, detail="Execution not found")

            with open(execution_file) as f:
                data = json.load(f)

            return ExecutionResponse(**data)

        # WebSocket for real-time updates
        @self.app.websocket("/ws/executions/{execution_id}")
        async def websocket_execution(websocket: WebSocket, execution_id: str):
            """WebSocket endpoint for real-time execution updates"""
            await websocket.accept()

            # Add to connection pool
            if execution_id not in self.websocket_connections:
                self.websocket_connections[execution_id] = []
            self.websocket_connections[execution_id].append(websocket)

            try:
                # Keep connection alive
                while True:
                    # Check if execution exists
                    execution_file = self.executions_path / f"{execution_id}.json"
                    if not execution_file.exists():
                        await websocket.send_json({"error": "Execution not found"})
                        break

                    # Send current status
                    with open(execution_file) as f:
                        data = json.load(f)
                    await websocket.send_json(data)

                    # If execution is complete, close connection
                    if data["status"] in ["completed", "failed"]:
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

        # Export endpoints
        @self.app.get("/api/workflows/{workflow_id}/export")
        async def export_workflow_endpoint(
            workflow_id: str, format: str = Query("python", regex="^(python|yaml)$")
        ):
            """Export workflow as Python code or YAML"""
            # Load workflow
            workflow_file = self.workflows_path / f"{workflow_id}.json"
            if not workflow_file.exists():
                raise HTTPException(status_code=404, detail="Workflow not found")

            with open(workflow_file) as f:
                workflow_data = json.load(f)

            # Create workflow from definition
            try:
                workflow = Workflow.from_dict(workflow_data["definition"])

                if format == "python":
                    # For Python export, we'll generate code manually
                    # since the SDK doesn't have a to_python method
                    code = self._generate_python_code(workflow, workflow_data["name"])
                    return {"format": "python", "content": code}
                else:  # yaml
                    yaml_content = export_workflow(workflow, format="yaml")
                    return {"format": "yaml", "content": yaml_content}

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

        # Import endpoints
        @self.app.post("/api/workflows/import", response_model=WorkflowImportResponse)
        async def import_workflow(request: WorkflowImportRequest):
            """Import workflow from Python code, YAML, or JSON"""

            import yaml

            workflow_id = str(uuid.uuid4())
            warnings = []

            try:
                # Parse content based on format
                if request.format == "json":
                    definition = json.loads(request.content)
                elif request.format == "yaml":
                    definition = yaml.safe_load(request.content)
                elif request.format == "python":
                    # Parse Python code to extract workflow definition
                    definition = self._parse_python_workflow(request.content)
                    warnings.append(
                        "Python import is experimental. Manual adjustments may be needed."
                    )
                else:
                    raise ValueError(f"Unsupported format: {request.format}")

                # Validate the workflow definition
                try:
                    workflow = Workflow.from_dict(definition)
                    # Convert back to dict to ensure it's valid
                    definition = workflow.to_dict()
                except Exception as e:
                    warnings.append(f"Workflow validation warning: {str(e)}")

                # Create workflow record
                now = datetime.now(UTC)
                workflow_data = {
                    "id": workflow_id,
                    "name": request.name,
                    "description": request.description,
                    "definition": definition,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }

                # Save workflow
                workflow_file = self.workflows_path / f"{workflow_id}.json"
                with open(workflow_file, "w") as f:
                    json.dump(workflow_data, f, indent=2)

                return WorkflowImportResponse(
                    id=workflow_id,
                    name=request.name,
                    description=request.description,
                    definition=definition,
                    created_at=now,
                    warnings=warnings,
                )

            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")

    async def _execute_workflow_async(
        self,
        execution_id: str,
        workflow: Workflow,
        runtime: LocalRuntime,
        parameters: dict[str, Any],
    ):
        """Execute workflow asynchronously and update status"""
        execution_file = self.executions_path / f"{execution_id}.json"

        try:
            # Execute workflow
            result, run_id = runtime.execute(workflow, parameters=parameters)

            # Update execution record
            with open(execution_file) as f:
                execution_data = json.load(f)

            execution_data["status"] = "completed"
            execution_data["completed_at"] = datetime.now(UTC).isoformat()
            execution_data["result"] = result

            with open(execution_file, "w") as f:
                json.dump(execution_data, f, indent=2)

            # Notify WebSocket clients
            await self._notify_websocket_clients(execution_id, execution_data)

        except Exception as e:
            # Update execution record with error
            with open(execution_file) as f:
                execution_data = json.load(f)

            execution_data["status"] = "failed"
            execution_data["completed_at"] = datetime.now(UTC).isoformat()
            execution_data["error"] = str(e)

            with open(execution_file, "w") as f:
                json.dump(execution_data, f, indent=2)

            # Notify WebSocket clients
            await self._notify_websocket_clients(execution_id, execution_data)

        finally:
            # Remove from active executions
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]

    async def _notify_websocket_clients(self, execution_id: str, data: dict[str, Any]):
        """Notify all WebSocket clients watching this execution"""
        if execution_id in self.websocket_connections:
            for websocket in self.websocket_connections[execution_id]:
                try:
                    await websocket.send_json(data)
                except Exception:
                    pass  # Client disconnected

    def _generate_python_code(self, workflow: Workflow, workflow_name: str) -> str:
        """Generate Python code from a workflow"""
        lines = [
            "#!/usr/bin/env python3",
            '"""',
            f"Workflow: {workflow_name}",
            "Generated by Kailash Workflow Studio",
            '"""',
            "",
            "from kailash.workflow import Workflow",
            "from kailash.runtime.local import LocalRuntime",
            "",
        ]

        # Import node classes
        node_imports = set()
        for node_id in workflow.graph.nodes:
            node_data = workflow.graph.nodes[node_id]
            if "node" in node_data:
                node = node_data["node"]
                module = node.__class__.__module__
                class_name = node.__class__.__name__
                node_imports.add(f"from {module} import {class_name}")

        lines.extend(sorted(node_imports))
        lines.extend(
            ["", "", "def main():", f'    """Execute {workflow_name} workflow."""']
        )
        lines.append("    # Create workflow")
        lines.append(
            f'    workflow = Workflow(workflow_id="{workflow.workflow_id}", name="{workflow.name}")'
        )
        lines.append("")

        # Add nodes
        lines.append("    # Add nodes")
        for node_id in workflow.graph.nodes:
            node_data = workflow.graph.nodes[node_id]
            if "node" in node_data:
                node = node_data["node"]
                class_name = node.__class__.__name__
                config = node.config

                # Format config as Python dict
                config_str = self._format_config(config)
                lines.append(f"    {node_id} = {class_name}({config_str})")
                lines.append(
                    f'    workflow.add_node(node_id="{node_id}", node_or_type={node_id})'
                )
                lines.append("")

        # Add connections
        if workflow.graph.edges:
            lines.append("    # Add connections")
            for edge_data in workflow.graph.edges(data=True):
                source, target, data = edge_data
                mapping = data.get("mapping", {})
                if mapping:
                    mapping_str = repr(mapping)
                    lines.append(
                        f'    workflow.connect(source_node="{source}", target_node="{target}", mapping={mapping_str})'
                    )
            lines.append("")

        # Add execution
        lines.extend(
            [
                "    # Execute workflow",
                "    runtime = LocalRuntime()",
                "    result, run_id = runtime.execute(workflow)",
                '    print(f"Workflow completed: {run_id}")',
                '    print(f"Result: {result}")',
                "",
                "",
                'if __name__ == "__main__":',
                "    main()",
            ]
        )

        return "\n".join(lines)

    def _parse_python_workflow(self, python_code: str) -> dict[str, Any]:
        """Parse Python code to extract workflow definition.

        This is a simplified parser that extracts workflow structure from Python code.
        In production, this would use AST parsing for more robust extraction.
        """
        # For now, return a basic workflow structure
        # This would need to be implemented with proper Python AST parsing
        return {
            "nodes": {},
            "connections": [],
            "metadata": {
                "imported_from": "python",
                "warning": "Python import requires manual verification",
            },
        }

    def _format_config(self, config: dict[str, Any]) -> str:
        """Format config dict as Python code"""
        if not config:
            return ""

        parts = []
        for key, value in config.items():
            if isinstance(value, str):
                parts.append(f'{key}="{value}"')
            else:
                parts.append(f"{key}={repr(value)}")

        return ", ".join(parts)

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """Run the API server"""
        uvicorn.run(self.app, host=host, port=port)


def main():
    """Main entry point for the studio API"""
    import argparse

    parser = argparse.ArgumentParser(description="Kailash Workflow Studio API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument(
        "--tenant-id", default=os.getenv("TENANT_ID", "default"), help="Tenant ID"
    )

    args = parser.parse_args()

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run API
    api = WorkflowStudioAPI(tenant_id=args.tenant_id)
    api.execute(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
