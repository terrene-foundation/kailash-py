"""
Main FastAPI application for API Gateway Starter Example.

Production-ready application demonstrating complete middleware stack integration:
1. CORS configuration
2. Global error handling (RFC 7807)
3. Rate limiting (token bucket)
4. JWT authentication
5. Role-based access control (RBAC)

Integrates all components from API Gateway Starter template with DataFlow for database operations.
"""

from dataflow import DataFlow
from fastapi import FastAPI, Request
from templates.api_gateway_starter.example_app.config import get_settings
from templates.api_gateway_starter.example_app.models import register_models
from templates.api_gateway_starter.example_app.routes.organizations import (
    create_organization_router,
)
from templates.api_gateway_starter.example_app.routes.users import create_user_router
from templates.api_gateway_starter.middleware.api_key_auth import (
    api_key_auth_middleware,
)
from templates.api_gateway_starter.middleware.cors import configure_cors
from templates.api_gateway_starter.middleware.errors import error_handler_middleware
from templates.api_gateway_starter.middleware.jwt_auth import jwt_auth_middleware
from templates.api_gateway_starter.middleware.rate_limit import (
    InMemoryRateLimiter,
    rate_limit_middleware,
)
from templates.api_gateway_starter.middleware.rbac import require_role
from templates.api_gateway_starter.utils.responses import success_response


def create_app(db: DataFlow = None) -> FastAPI:
    """
    Create and configure FastAPI application with complete middleware stack.

    Args:
        db: Optional DataFlow instance (if None, creates from settings)

    Returns:
        Configured FastAPI application

    Middleware Stack Order (critical):
        1. CORS - Must be first to handle preflight requests
        2. Error Handler - Catches all exceptions from later middleware
        3. Rate Limiting - Prevent abuse before authentication
        4. JWT Authentication - Verify user identity
        5. RBAC - Check permissions (decorator on endpoints)

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow(":memory:")
        >>> app = create_app(db)
        >>> # Run with: uvicorn main:app --reload
    """
    # Load settings
    settings = get_settings()

    # Initialize DataFlow if not provided
    if db is None:
        db = DataFlow(settings.database_url)

    # Register models
    register_models(db)

    # Create FastAPI app
    app = FastAPI(
        title="API Gateway Starter Example",
        description="Production-ready API with complete middleware stack",
        version="1.0.0",
        debug=settings.debug,
    )

    # 1. Configure CORS (MUST be first)
    configure_cors(app, allowed_origins=settings.allowed_origins)

    # 2. Global error handler (MUST be second)
    @app.middleware("http")
    async def error_middleware(request: Request, call_next):
        return await error_handler_middleware(request, call_next)

    # 3. Rate limiting (MUST be third)
    limiter = InMemoryRateLimiter(
        rate=settings.rate_limit_requests, window=settings.rate_limit_window
    )

    @app.middleware("http")
    async def rate_limit_middleware_wrapper(request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)
        return await rate_limit_middleware(request, call_next, limiter)

    # 4. JWT authentication (MUST be fourth)
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth for public endpoints
        public_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
        if request.url.path in public_paths:
            return await call_next(request)

        # Apply JWT authentication for regular endpoints
        if request.url.path.startswith("/api/"):
            # API endpoints use API key authentication
            return await api_key_auth_middleware(request, call_next, db)
        else:
            # Regular endpoints use JWT authentication
            return await jwt_auth_middleware(request, call_next)

    # 5. Add role to request.state for RBAC (extract from JWT claims)
    @app.middleware("http")
    async def role_middleware(request: Request, call_next):
        # Skip for public endpoints
        public_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
        if request.url.path in public_paths:
            return await call_next(request)

        # Extract role from user_claims (set by JWT middleware)
        if hasattr(request.state, "user_claims"):
            # Extract role from JWT claims if present
            user_claims = request.state.user_claims
            request.state.role = user_claims.get(
                "role", "member"
            )  # Default to member if not present
        elif hasattr(request.state, "api_key_data"):
            # For API key authentication - no role concept, default to admin
            request.state.role = "admin"  # API keys have admin access

        return await call_next(request)

    # Health check endpoint (public, no authentication)
    @app.get("/health", tags=["health"])
    async def health_check():
        """
        Health check endpoint.

        Returns:
            200: Service is healthy
        """
        return {"status": "healthy"}

    # Admin endpoints (protected with RBAC)
    @app.post("/admin/settings", tags=["admin"])
    @require_role("admin")
    async def update_settings(request: Request, settings_data: dict):
        """
        Update application settings (admin only).

        Requires:
            - Valid JWT token
            - Admin or owner role

        Request Body:
            settings_data: Settings to update

        Returns:
            200: Settings updated
            401: Authentication error
            403: Authorization error (insufficient permissions)
        """
        return success_response({"updated": True, "settings": settings_data})

    # Register routers
    app.include_router(create_user_router(db))
    app.include_router(create_organization_router(db))

    # API key protected endpoints
    from fastapi import APIRouter
    from templates.api_gateway_starter.middleware.api_key_auth import api_key_required

    api_router = APIRouter(prefix="/api", tags=["api"])

    @api_router.get("/users")
    @api_key_required(required_scopes=["read"])
    async def api_list_users(request: Request, page: int = 1, limit: int = 20):
        """
        List users via API key (requires 'read' scope).

        Query Parameters:
            page: Page number (default: 1)
            limit: Items per page (default: 20)

        Headers:
            X-API-Key: Valid API key with 'read' scope

        Returns:
            200: Paginated user list
            401: Missing or invalid API key
            403: Insufficient scopes
        """
        from templates.api_gateway_starter.utils.responses import paginated_response
        from templates.api_gateway_starter.utils.validation import (
            validate_pagination_params,
        )

        from kailash.runtime import LocalRuntime
        from kailash.workflow.builder import WorkflowBuilder

        # Get organization from API key
        api_key_data = getattr(request.state, "api_key_data", {})
        org_id = api_key_data.get("organization_id")

        # Validate pagination
        offset, limit = validate_pagination_params(page, limit, max_limit=100)

        # Execute DataFlow workflow
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
        total = len(users)

        return paginated_response(users, total, page, limit)

    app.include_router(api_router)

    return app


# Create default app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    # Load environment variables
    from dotenv import load_dotenv

    load_dotenv()

    # Run application
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
