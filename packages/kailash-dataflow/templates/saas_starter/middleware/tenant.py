"""
SaaS Starter Template - Tenant Middleware

Multi-tenant isolation middleware for SaaS applications.
"""

from typing import Any, Dict

import jwt
from kailash.workflow.builder import WorkflowBuilder

# JWT Configuration
JWT_SECRET = "test-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"


def inject_tenant_context(token: str) -> Dict[str, Any]:
    """
    Inject tenant context from JWT token.

    Args:
        token: JWT token containing org_id

    Returns:
        Dict with tenant_id extracted from token
    """
    decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    return {"tenant_id": decoded.get("org_id")}


def build_tenant_scoped_read_workflow(
    model_name: str, record_id: str, tenant_token: str
) -> WorkflowBuilder:
    """
    Build tenant-scoped read workflow.

    Only returns record if it belongs to the tenant.
    """
    workflow = WorkflowBuilder()

    # Decode token to get org_id
    decoded = jwt.decode(tenant_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    org_id = decoded.get("org_id")

    # Read record with tenant filter
    workflow.add_node(
        f"{model_name}ListNode",
        "user",
        {
            "filter": {"id": record_id, "organization_id": org_id},
            "limit": 1,
        },
    )

    return workflow.build()


def build_tenant_scoped_update_workflow(
    model_name: str, record_id: str, updates: Dict[str, Any], tenant_token: str
) -> WorkflowBuilder:
    """
    Build tenant-scoped update workflow.

    Only updates record if it belongs to the tenant.
    """
    workflow = WorkflowBuilder()

    # Decode token to get org_id
    decoded = jwt.decode(tenant_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    org_id = decoded.get("org_id")

    # First check if record belongs to tenant
    workflow.add_node(
        f"{model_name}ListNode",
        "check_ownership",
        {
            "filter": {"id": record_id, "organization_id": org_id},
            "limit": 1,
        },
    )

    # Add Python code to check ownership and raise if not found
    # ListNode returns dict with 'records' key, so we check that
    code = """
ownership_data = inputs.get('check_ownership', {})
records = ownership_data.get('records', []) if isinstance(ownership_data, dict) else []
if len(records) == 0:
    raise Exception("Permission denied: Access denied - record does not belong to tenant")
result = True
"""

    workflow.add_node(
        "PythonCodeNode",
        "verify_ownership",
        {"code": code, "inputs": {"check_ownership": "{{check_ownership}}"}},
    )

    return workflow.build()


def build_tenant_scoped_delete_workflow(
    model_name: str, record_id: str, tenant_token: str
) -> WorkflowBuilder:
    """
    Build tenant-scoped delete workflow.

    Only deletes record if it belongs to the tenant.
    """
    workflow = WorkflowBuilder()

    # Decode token to get org_id
    decoded = jwt.decode(tenant_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    org_id = decoded.get("org_id")

    # First check if record belongs to tenant
    workflow.add_node(
        f"{model_name}ListNode",
        "check_ownership",
        {
            "filter": {"id": record_id, "organization_id": org_id},
            "limit": 1,
        },
    )

    # Add Python code to check ownership and raise if not found
    # ListNode returns dict with 'records' key, so we check that
    code = """
ownership_data = inputs.get('check_ownership', {})
records = ownership_data.get('records', []) if isinstance(ownership_data, dict) else []
if len(records) == 0:
    raise Exception("Permission denied: Access denied - record does not belong to tenant")
result = True
"""

    workflow.add_node(
        "PythonCodeNode",
        "verify_ownership",
        {"code": code, "inputs": {"check_ownership": "{{check_ownership}}"}},
    )

    return workflow.build()


def build_tenant_scoped_list_workflow(
    model_name: str, tenant_token: str
) -> WorkflowBuilder:
    """
    Build tenant-scoped list workflow.

    Only returns records belonging to the tenant.
    """
    workflow = WorkflowBuilder()

    # Decode token to get org_id
    decoded = jwt.decode(tenant_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    org_id = decoded.get("org_id")

    # List records with tenant filter
    workflow.add_node(
        f"{model_name}ListNode",
        "users",
        {
            "filter": {"organization_id": org_id},
            "limit": 100,
        },
    )

    return workflow.build()


def build_org_switching_workflow(
    user_id: str, target_org_id: str, operation: str
) -> WorkflowBuilder:
    """
    Build organization switching workflow.

    Allows user to switch context to a different org they belong to.
    """
    workflow = WorkflowBuilder()

    if operation == "list_users":
        # List users in target org
        workflow.add_node(
            "UserListNode",
            "users",
            {
                "filter": {"organization_id": target_org_id},
                "limit": 100,
            },
        )

    return workflow.build()


def build_tenant_scoped_bulk_update_workflow(
    model_name: str, updates: Dict[str, Any], tenant_token: str
) -> WorkflowBuilder:
    """
    Build tenant-scoped bulk update workflow.

    Only updates records belonging to the tenant.
    """
    workflow = WorkflowBuilder()

    # Decode token to get org_id
    decoded = jwt.decode(tenant_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    org_id = decoded.get("org_id")

    # Bulk update with tenant filter
    workflow.add_node(
        f"{model_name}BulkUpdateNode",
        "bulk_update",
        {
            "filter": {"organization_id": org_id},
            "fields": updates,
        },
    )

    return workflow.build()
