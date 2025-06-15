"""
Custom Node API endpoints for Kailash Workflow Studio.

This module provides endpoints for users to:
- Create custom nodes with visual configuration
- Implement nodes using Python code, workflows, or API calls
- Manage and version custom nodes
- Share nodes within a tenant
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CustomNodeCreate(BaseModel):
    """Request model for creating a custom node"""

    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(default="custom", max_length=100)
    description: str | None = None
    icon: str | None = Field(None, max_length=50)
    color: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")

    # Node configuration
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)

    # Implementation
    implementation_type: str = Field(..., pattern="^(python|workflow|api)$")
    implementation: dict[str, Any]


class CustomNodeUpdate(BaseModel):
    """Request model for updating a custom node"""

    name: str | None = Field(None, min_length=1, max_length=255)
    category: str | None = Field(None, max_length=100)
    description: str | None = None
    icon: str | None = Field(None, max_length=50)
    color: str | None = Field(None, pattern="^#[0-9A-Fa-f]{6}$")

    # Node configuration
    parameters: list[dict[str, Any]] | None = None
    inputs: list[dict[str, Any]] | None = None
    outputs: list[dict[str, Any]] | None = None

    # Implementation
    implementation_type: str | None = Field(None, pattern="^(python|workflow|api)$")
    implementation: dict[str, Any] | None = None

    # Publishing
    is_published: bool | None = None


class CustomNodeResponse(BaseModel):
    """Response model for custom node"""

    id: str
    tenant_id: str
    name: str
    category: str
    description: str | None
    icon: str | None
    color: str | None

    # Node configuration
    parameters: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]

    # Implementation
    implementation_type: str
    implementation: dict[str, Any]

    # Metadata
    is_published: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime


def setup_custom_node_routes(app, SessionLocal, tenant_id: str):
    """Setup custom node API routes"""
    from fastapi import HTTPException

    from .database import CustomNodeRepository, get_db_session

    @app.get("/api/custom-nodes", response_model=list[CustomNodeResponse])
    async def list_custom_nodes():
        """List all custom nodes for the tenant"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)
            nodes = repo.list(tenant_id)

            return [
                CustomNodeResponse(
                    id=node.id,
                    tenant_id=node.tenant_id,
                    name=node.name,
                    category=node.category,
                    description=node.description,
                    icon=node.icon,
                    color=node.color,
                    parameters=node.parameters or [],
                    inputs=node.inputs or [],
                    outputs=node.outputs or [],
                    implementation_type=node.implementation_type,
                    implementation=node.implementation or {},
                    is_published=node.is_published,
                    created_by=node.created_by,
                    created_at=node.created_at,
                    updated_at=node.updated_at,
                )
                for node in nodes
            ]

    @app.post("/api/custom-nodes", response_model=CustomNodeResponse)
    async def create_custom_node(request: CustomNodeCreate):
        """Create a new custom node"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)

            # Check if node name already exists
            existing_nodes = repo.list(tenant_id)
            if any(node.name == request.name for node in existing_nodes):
                raise HTTPException(
                    status_code=400,
                    detail=f"Custom node with name '{request.name}' already exists",
                )

            # Create node
            node_data = request.dict()
            node = repo.create(tenant_id, node_data)

            return CustomNodeResponse(
                id=node.id,
                tenant_id=node.tenant_id,
                name=node.name,
                category=node.category,
                description=node.description,
                icon=node.icon,
                color=node.color,
                parameters=node.parameters or [],
                inputs=node.inputs or [],
                outputs=node.outputs or [],
                implementation_type=node.implementation_type,
                implementation=node.implementation or {},
                is_published=node.is_published,
                created_by=node.created_by,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )

    @app.get("/api/custom-nodes/{node_id}", response_model=CustomNodeResponse)
    async def get_custom_node(node_id: str):
        """Get a specific custom node"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)
            node = repo.get(node_id)

            if not node or node.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Custom node not found")

            return CustomNodeResponse(
                id=node.id,
                tenant_id=node.tenant_id,
                name=node.name,
                category=node.category,
                description=node.description,
                icon=node.icon,
                color=node.color,
                parameters=node.parameters or [],
                inputs=node.inputs or [],
                outputs=node.outputs or [],
                implementation_type=node.implementation_type,
                implementation=node.implementation or {},
                is_published=node.is_published,
                created_by=node.created_by,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )

    @app.put("/api/custom-nodes/{node_id}", response_model=CustomNodeResponse)
    async def update_custom_node(node_id: str, request: CustomNodeUpdate):
        """Update a custom node"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)
            node = repo.get(node_id)

            if not node or node.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Custom node not found")

            # Update node
            updates = request.dict(exclude_unset=True)
            node = repo.update(node_id, updates)

            return CustomNodeResponse(
                id=node.id,
                tenant_id=node.tenant_id,
                name=node.name,
                category=node.category,
                description=node.description,
                icon=node.icon,
                color=node.color,
                parameters=node.parameters or [],
                inputs=node.inputs or [],
                outputs=node.outputs or [],
                implementation_type=node.implementation_type,
                implementation=node.implementation or {},
                is_published=node.is_published,
                created_by=node.created_by,
                created_at=node.created_at,
                updated_at=node.updated_at,
            )

    @app.delete("/api/custom-nodes/{node_id}")
    async def delete_custom_node(node_id: str):
        """Delete a custom node"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)
            node = repo.get(node_id)

            if not node or node.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Custom node not found")

            repo.delete(node_id)
            return {"message": "Custom node deleted successfully"}

    @app.post("/api/custom-nodes/{node_id}/test")
    async def test_custom_node(node_id: str, test_data: dict[str, Any]):
        """Test a custom node with sample data"""
        with get_db_session(SessionLocal) as session:
            repo = CustomNodeRepository(session)
            node = repo.get(node_id)

            if not node or node.tenant_id != tenant_id:
                raise HTTPException(status_code=404, detail="Custom node not found")

            # Execute node based on implementation type
            try:
                if node.implementation_type == "python":
                    # Execute Python code
                    result = _execute_python_node(node, test_data)
                elif node.implementation_type == "workflow":
                    # Execute workflow
                    result = _execute_workflow_node(node, test_data)
                elif node.implementation_type == "api":
                    # Execute API call
                    result = _execute_api_node(node, test_data)
                else:
                    raise ValueError(
                        f"Unknown implementation type: {node.implementation_type}"
                    )

                return {
                    "success": True,
                    "result": result,
                    "execution_time_ms": 0,  # TODO: Track actual execution time
                }
            except Exception as e:
                return {"success": False, "error": str(e), "execution_time_ms": 0}


def _execute_python_node(node, test_data):
    """Execute a Python-based custom node"""
    # This would execute the Python code in a sandboxed environment
    # For now, return mock result
    return {"output": f"Executed {node.name} with Python implementation"}


def _execute_workflow_node(node, test_data):
    """Execute a workflow-based custom node"""
    # This would create and execute a workflow from the stored definition
    # For now, return mock result
    return {"output": f"Executed {node.name} with Workflow implementation"}


def _execute_api_node(node, test_data):
    """Execute an API-based custom node"""
    # This would make HTTP requests based on the API configuration
    # For now, return mock result
    return {"output": f"Executed {node.name} with API implementation"}
