"""
SaaS Starter Template - Multi-Tenant Isolation

Simplified multi-tenant isolation with direct Python functions.

Functions:
- get_user_organization(db, user_id) - Get user's organization
- filter_by_organization(filters, organization_id) - Add org filter to queries
- list_organization_users(db, organization_id) - List users in org
- check_user_belongs_to_org(db, user_id, organization_id) - Verify user belongs to org
- switch_user_organization(db, user_id, new_org_id) - Move user to different org

Architecture:
- Direct Python functions for isolation logic
- DataFlow workflows ONLY for database operations
- No complex conditionals in workflows
- Simple, testable, fast functions
"""

from typing import Dict, List, Optional

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def get_user_organization(db, user_id: str) -> Optional[Dict]:
    """
    Get user's organization.

    Args:
        db: DataFlow instance
        user_id: User ID

    Returns:
        Organization dict if found, None otherwise

    Example:
        >>> org = get_user_organization(db, "user_123")
        >>> if org:
        ...     print(org["name"])
        Acme Corp
    """
    # First, get the user to find organization_id
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read_user", {"id": user_id})

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    user = results.get("read_user")
    if not user:
        return None

    # Now get the organization
    org_workflow = WorkflowBuilder()
    org_workflow.add_node(
        "OrganizationReadNode", "read_org", {"id": user["organization_id"]}
    )

    org_results, _ = runtime.execute(org_workflow.build())
    return org_results.get("read_org")


def filter_by_organization(filters: Dict, organization_id: str) -> Dict:
    """
    Add organization filter to query filters.

    Args:
        filters: Existing filters dict
        organization_id: Organization ID to filter by

    Returns:
        Updated filters dict with organization_id

    Example:
        >>> filters = {"status": "active"}
        >>> filtered = filter_by_organization(filters, "org_123")
        >>> print(filtered)
        {'status': 'active', 'organization_id': 'org_123'}
    """
    # Create copy to avoid mutating original
    updated_filters = filters.copy()
    updated_filters["organization_id"] = organization_id
    return updated_filters


def list_organization_users(db, organization_id: str) -> List[Dict]:
    """
    List users in an organization.

    Args:
        db: DataFlow instance
        organization_id: Organization ID

    Returns:
        List of user dicts

    Example:
        >>> users = list_organization_users(db, "org_123")
        >>> for user in users:
        ...     print(user["email"])
        alice@example.com
        bob@example.com
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "UserListNode", "list_users", {"filters": {"organization_id": organization_id}}
    )

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    return results.get("list_users", [])


def check_user_belongs_to_org(db, user_id: str, organization_id: str) -> bool:
    """
    Check if user belongs to organization.

    Args:
        db: DataFlow instance
        user_id: User ID
        organization_id: Organization ID to check

    Returns:
        True if user belongs to organization, False otherwise

    Example:
        >>> belongs = check_user_belongs_to_org(db, "user_123", "org_456")
        >>> if belongs:
        ...     print("Access granted")
        Access granted
    """
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read_user", {"id": user_id})

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    user = results.get("read_user")
    if not user:
        return False

    return user["organization_id"] == organization_id


def switch_user_organization(db, user_id: str, new_org_id: str) -> Optional[Dict]:
    """
    Switch user to different organization.

    Args:
        db: DataFlow instance
        user_id: User ID
        new_org_id: New organization ID

    Returns:
        Updated user dict if successful, None otherwise

    Example:
        >>> user = switch_user_organization(db, "user_123", "org_789")
        >>> if user:
        ...     print(user["organization_id"])
        org_789
    """
    # First, verify new organization exists
    org_workflow = WorkflowBuilder()
    org_workflow.add_node("OrganizationReadNode", "read_org", {"id": new_org_id})

    runtime = LocalRuntime()
    org_results, _ = runtime.execute(org_workflow.build())

    org = org_results.get("read_org")
    if not org:
        return None  # Organization doesn't exist

    # Update user's organization_id
    update_workflow = WorkflowBuilder()
    update_workflow.add_node(
        "UserUpdateNode",
        "update_user",
        {"filters": {"id": user_id}, "fields": {"organization_id": new_org_id}},
    )

    update_results, _ = runtime.execute(update_workflow.build())
    return update_results.get("update_user")
