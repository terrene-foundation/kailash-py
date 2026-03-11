"""
User CRUD routes with authentication and RBAC.

All endpoints require JWT authentication and enforce role-based access control.
"""

from dataflow import DataFlow
from fastapi import APIRouter, HTTPException, Request
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


def create_user_router(db: DataFlow) -> APIRouter:
    """
    Create user routes with DataFlow integration.

    Args:
        db: DataFlow instance for database operations

    Returns:
        APIRouter with user CRUD endpoints
    """
    router = APIRouter(prefix="/users", tags=["users"])

    @router.post("", status_code=201)
    @require_role("member")
    def create_user(request: Request, user_data: dict):
        """
        Create new user (requires member role).

        Request Body:
            id: User ID
            organization_id: Organization ID
            email: User email
            name: User name
            password_hash: Hashed password
            role: User role (owner, admin, member)
            status: User status (active, inactive)

        Returns:
            201: Created response with user data
            400: Validation error
            401: Authentication error
            403: Authorization error
        """
        try:
            # Validate request
            validated = validate_create_request("User", user_data)

            # Execute DataFlow workflow
            workflow = WorkflowBuilder()
            workflow.add_node("UserCreateNode", "create", validated)

            runtime = LocalRuntime()
            results, _ = runtime.execute(workflow.build())

            user = results.get("create")
            if not user:
                problem = ProblemDetail(
                    type=VALIDATION_ERROR,
                    title="Create Failed",
                    status=400,
                    detail="Failed to create user",
                )
                return problem.to_response()

            return created_response(user, resource_id=user["id"])

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
    def list_users(request: Request, page: int = 1, limit: int = 20):
        """
        List users with pagination (requires member role).

        Query Parameters:
            page: Page number (default: 1)
            limit: Items per page (default: 20, max: 100)

        Returns:
            200: Paginated user list
            401: Authentication error
            403: Authorization error
        """
        try:
            # Validate pagination
            offset, limit = validate_pagination_params(page, limit, max_limit=100)

            # Get user's organization from JWT
            user_claims = getattr(request.state, "user_claims", {})
            org_id = user_claims.get("org_id")

            # Filter by organization (multi-tenant isolation)
            workflow = WorkflowBuilder()
            workflow.add_node(
                "UserListNode",
                "list",
                {
                    "filters": {"organization_id": org_id} if org_id else {},
                    "limit": limit,
                    "offset": offset,
                },
            )

            runtime = LocalRuntime()
            results, _ = runtime.execute(workflow.build())

            users = results.get("list", [])

            # Get total count (simplified - in production use CountNode or separate query)
            total = len(
                users
            )  # This is incorrect for pagination, but demonstrates pattern

            return paginated_response(users, total, page, limit)

        except ValueError as e:
            problem = ProblemDetail(
                type=VALIDATION_ERROR,
                title="Validation Error",
                status=400,
                detail=str(e),
            )
            return problem.to_response()

    @router.get("/{user_id}")
    @require_role("member")
    def get_user(request: Request, user_id: str):
        """
        Get user by ID (requires member role).

        Path Parameters:
            user_id: User ID

        Returns:
            200: User data
            404: User not found
            401: Authentication error
            403: Authorization error
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node("UserReadNode", "read", {"id": user_id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        user = results.get("read")
        if not user:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"User {user_id} not found",
            )
            return problem.to_response()

        return success_response(user)

    @router.put("/{user_id}")
    @require_role("member")
    def update_user(request: Request, user_id: str, update_data: dict):
        """
        Update user (requires member role).

        Path Parameters:
            user_id: User ID

        Request Body:
            fields: Dictionary of fields to update

        Returns:
            200: Updated user data
            404: User not found
            401: Authentication error
            403: Authorization error
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "UserUpdateNode",
            "update",
            {"filter": {"id": user_id}, "fields": update_data},
        )

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        user = results.get("update")
        if not user:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"User {user_id} not found",
            )
            return problem.to_response()

        return success_response(user)

    @router.delete("/{user_id}")
    @require_role("admin")
    def delete_user(request: Request, user_id: str):
        """
        Delete user (requires admin role).

        Path Parameters:
            user_id: User ID

        Returns:
            200: Deletion confirmation
            404: User not found
            401: Authentication error
            403: Authorization error (non-admin)
        """
        # Execute DataFlow workflow
        workflow = WorkflowBuilder()
        workflow.add_node("UserDeleteNode", "delete", {"id": user_id})

        runtime = LocalRuntime()
        results, _ = runtime.execute(workflow.build())

        deleted = results.get("delete")
        if not deleted:
            problem = ProblemDetail(
                type=NOT_FOUND_ERROR,
                title="Not Found",
                status=404,
                detail=f"User {user_id} not found",
            )
            return problem.to_response()

        return success_response({"deleted": True, "user_id": user_id})

    return router
