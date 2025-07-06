"""
Custom Node API endpoints for Kailash Workflow Studio with authentication.

This module provides secure endpoints for users to:
- Create custom nodes with visual configuration
- Implement nodes using Python code, workflows, or API calls
- Manage and version custom nodes
- Share nodes within a tenant
"""

from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .auth import Tenant, User, get_current_tenant, require_permission
from .database import CustomNode, CustomNodeRepository, get_db_session


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


def setup_custom_node_routes(app, SessionLocal):
    """Setup custom node API routes with authentication"""

    @app.get("/api/custom-nodes", response_model=list[CustomNodeResponse])
    async def list_custom_nodes(
        user: User = Depends(require_permission("read:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """List all custom nodes for the tenant"""
        repo = CustomNodeRepository(session)
        nodes = repo.list(tenant.id)

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
    async def create_custom_node(
        request: CustomNodeCreate,
        user: User = Depends(require_permission("write:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """Create a new custom node"""
        repo = CustomNodeRepository(session)

        # Check if node name already exists for this tenant
        existing_nodes = repo.list(tenant.id)
        if any(node.name == request.name for node in existing_nodes):
            raise HTTPException(
                status_code=400,
                detail=f"Custom node with name '{request.name}' already exists",
            )

        # Create node
        node_data = request.dict()
        node_data["created_by"] = user.email
        node = repo.create(tenant.id, node_data)

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
    async def get_custom_node(
        node_id: str,
        user: User = Depends(require_permission("read:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """Get a specific custom node"""
        repo = CustomNodeRepository(session)
        node = repo.get(node_id)

        if not node or node.tenant_id != tenant.id:
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
    async def update_custom_node(
        node_id: str,
        request: CustomNodeUpdate,
        user: User = Depends(require_permission("write:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """Update a custom node"""
        repo = CustomNodeRepository(session)
        node = repo.get(node_id)

        if not node or node.tenant_id != tenant.id:
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
    async def delete_custom_node(
        node_id: str,
        user: User = Depends(require_permission("delete:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """Delete a custom node"""
        repo = CustomNodeRepository(session)
        node = repo.get(node_id)

        if not node or node.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Custom node not found")

        repo.delete(node_id)
        return {"message": "Custom node deleted successfully"}

    @app.post("/api/custom-nodes/{node_id}/test")
    async def test_custom_node(
        node_id: str,
        test_data: dict[str, Any],
        user: User = Depends(require_permission("execute:nodes")),
        tenant: Tenant = Depends(get_current_tenant),
        session: Session = Depends(get_db_session),
    ):
        """Test a custom node with sample data"""
        repo = CustomNodeRepository(session)
        node = repo.get(node_id)

        if not node or node.tenant_id != tenant.id:
            raise HTTPException(status_code=404, detail="Custom node not found")

        # Execute node based on implementation type
        try:
            if node.implementation_type == "python":
                # Execute Python code in sandboxed environment
                result = await _execute_python_node(node, test_data, tenant.id)
            elif node.implementation_type == "workflow":
                # Execute workflow
                result = await _execute_workflow_node(node, test_data, tenant.id)
            elif node.implementation_type == "api":
                # Execute API call
                result = await _execute_api_node(node, test_data, tenant.id)
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


async def _execute_python_node(
    node: CustomNode, test_data: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    """Execute a Python-based custom node with security sandboxing"""
    from kailash.nodes.code.python import PythonCodeNode
    from kailash.security import SecurityConfig, TenantContext

    # Create security config for tenant
    security_config = SecurityConfig(
        allowed_directories=[f"tenants/{tenant_id}/sandbox"],
        execution_timeout=30.0,  # 30 seconds max
        memory_limit=256 * 1024 * 1024,  # 256MB
    )

    # Execute in tenant context
    with TenantContext(tenant_id):
        # Create Python code node with custom implementation
        python_node = PythonCodeNode(
            code=node.implementation.get("code", ""),
            inputs=node.implementation.get("inputs", []),
            outputs=node.implementation.get("outputs", []),
            security_config=security_config,
        )

        # Run the node
        result = python_node.execute(**test_data)

    return result


async def _execute_workflow_node(
    node: CustomNode, test_data: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    """Execute a workflow-based custom node"""
    from kailash.runtime.local import LocalRuntime
    from kailash.security import TenantContext
    from kailash.workflow import Workflow

    # Execute in tenant context
    with TenantContext(tenant_id):
        # Create workflow from stored definition
        workflow_def = node.implementation.get("workflow", {})
        workflow = Workflow.from_dict(workflow_def)

        # Create tenant-isolated runtime
        runtime = LocalRuntime()

        # Execute workflow
        result, run_id = runtime.execute(workflow, parameters=test_data)

    return result


async def _execute_api_node(
    node: CustomNode, test_data: dict[str, Any], tenant_id: str
) -> dict[str, Any]:
    """Execute an API-based custom node"""

    from kailash.nodes.api.http import HTTPRequestNode
    from kailash.security import TenantContext

    # Execute in tenant context
    with TenantContext(tenant_id):
        # Get API configuration
        api_config = node.implementation.get("api", {})

        # Create HTTP client node
        http_node = HTTPRequestNode(
            url=api_config.get("url", ""),
            method=api_config.get("method", "GET"),
            headers=api_config.get("headers", {}),
            timeout=api_config.get("timeout", 30),
        )

        # Prepare request data
        if api_config.get("method") in ["POST", "PUT", "PATCH"]:
            # Include test data in body
            result = await http_node.execute(json_data=test_data)
        else:
            # Include test data as query params
            result = await http_node.execute(params=test_data)

    return result
