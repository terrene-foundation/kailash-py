"""
Organization CRUD routes with authentication.

All endpoints require JWT authentication.
"""

from dataflow import DataFlow
from fastapi import APIRouter, Request
from templates.api_gateway_starter.middleware.rbac import require_role
from templates.api_gateway_starter.utils.errors import (
    NOT_FOUND_ERROR,
    VALIDATION_ERROR,
    ProblemDetail,
)
from templates.api_gateway_starter.utils.responses import (
    created_response,
    paginated_response,
    success_response,
)
from templates.api_gateway_starter.utils.validation import (
    validate_create_request,
    validate_pagination_params,
)

from kailash.runtime import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


def create_organization_router(db: DataFlow) -> APIRouter:
    """
    Create organization routes with DataFlow integration.

    Args:
        db: DataFlow instance for database operations

    Returns:
        APIRouter with organization CRUD endpoints
    """
    router = APIRouter(prefix="/organizations", tags=["organizations"])

    @router.post("", status_code=201)
    @require_role("admin")
    def create_organization(request: Request, org_data: dict):
        """
        Create new organization (requires admin role).

        Request Body:
            id: Organization ID
            name: Organization name
            status: Organization status (active, inactive)

        Returns:
            201: Created response with organization data
            400: Validation error
            401: Authentication error
            403: Authorization error
        """
        try:
            # Validate request
            validated = validate_create_request("Organization", org_data)

            # Execute DataFlow workflow
            workflow = WorkflowBuilder()
            workflow.add_node("OrganizationCreateNode", "create", validated)

            runtime = LocalRuntime()
            results, _ = runtime.execute(workflow.build())

            org = results.get("create")
            if not org:
                problem = ProblemDetail(
                    type=VALIDATION_ERROR,
                    title="Create Failed",
                    status=400,
                    detail="Failed to create organization",
                )
                return problem.to_response()

            return created_response(org, resource_id=org["id"])

        except ValueError as e:
            problem = ProblemDetail(
                type=VALIDATION_ERROR,
                title="Validation Error",
                status=400,
                detail=str(e),
            )
            return problem.to_response()

    @router.get("")
    @require_role("member")
    def list_organizations(request: Request, page: int = 1, limit: int = 20):
        """
        List organizations with pagination (requires member role).

        Query Parameters:
            page: Page number (default: 1)
            limit: Items per page (default: 20, max: 100)

        Returns:
            200: Paginated organization list
            401: Authentication error
            403: Authorization error
        """
        try:
            # Validate pagination
            offset, limit = validate_pagination_params(page, limit, max_limit=100)

            # Execute DataFlow workflow
            workflow = WorkflowBuilder()
            workflow.add_node(
                "OrganizationListNode", "list", {"limit": limit, "offset": offset}
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(workflow.build())

            organizations = results.get("list", [])

            # Get total count
            total = len(organizations)

            return paginated_response(organizations, total, page, limit)

        except ValueError as e:
            problem = ProblemDetail(
                type=VALIDATION_ERROR,
                title="Validation Error",
                status=400,
                detail=str(e),
            )
            return problem.to_response()

    @router.get("/{org_id}")
    @require_role("member")
    def get_organization(request: Request, org_id: str):
        """
        Get organization by ID (requires member role).

        Path Parameters:
            org_id: Organization ID

        Returns:
            200: Organization data
            404: Organization not found
            401: Authentication error
            403: Authorization error
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node("OrganizationReadNode", "read", {"id": org_id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        org = results.get("read")
        if not org:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"Organization {org_id} not found",
            )
            return problem.to_response()

        return success_response(org)

    @router.put("/{org_id}")
    @require_role("admin")
    def update_organization(request: Request, org_id: str, update_data: dict):
        """
        Update organization (requires admin role).

        Path Parameters:
            org_id: Organization ID

        Request Body:
            fields: Dictionary of fields to update

        Returns:
            200: Updated organization data
            404: Organization not found
            401: Authentication error
            403: Authorization error
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "OrganizationUpdateNode",
            "update",
            {"filter": {"id": org_id}, "fields": update_data},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        org = results.get("update")
        if not org:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"Organization {org_id} not found",
            )
            return problem.to_response()

        return success_response(org)

    @router.delete("/{org_id}")
    @require_role("owner")
    def delete_organization(request: Request, org_id: str):
        """
        Delete organization (requires owner role).

        Path Parameters:
            org_id: Organization ID

        Returns:
            200: Deletion confirmation
            404: Organization not found
            401: Authentication error
            403: Authorization error (non-owner)
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node("OrganizationDeleteNode", "delete", {"id": org_id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        deleted = results.get("delete")
        if not deleted:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"Organization {org_id} not found",
            )
            return problem.to_response()

        return success_response({"deleted": True, "org_id": org_id})

    return router
