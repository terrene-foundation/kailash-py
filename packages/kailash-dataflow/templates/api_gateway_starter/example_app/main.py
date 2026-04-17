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
        FastAPI registers middleware in LIFO order — the LAST
        ``@app.middleware("http")`` registered becomes the OUTERMOST
        middleware (runs first on request ingress / last on egress).

        Registration order below is arranged so request processing runs:
          1. CORS (via configure_cors, added via add_middleware) — handles
             preflight OPTIONS requests before anything else
          2. Rate Limiting — reject abusive clients before auth work
          3. JWT / API key Authentication — verify identity
          4. RBAC role attachment — extract role from JWT claims
          5. Error Handler (registered LAST = outermost) — catches
             HTTPExceptions / ValidationErrors raised by all inner
             middleware and handlers, formats to RFC 7807

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

    # Configure CORS (via add_middleware — always runs first on ingress)
    configure_cors(app, allowed_origins=settings.allowed_origins)

    # Rate limiting — registered FIRST among @app.middleware so it runs
    # LAST on request ingress (innermost), i.e. after auth has resolved
    # the caller. Order below (bottom-up = outer-first) is:
    #   error -> role -> auth -> rate_limit -> (handler)
    limiter = InMemoryRateLimiter(
        rate=settings.rate_limit_requests, window=settings.rate_limit_window
    )

    @app.middleware("http")
    async def rate_limit_middleware_wrapper(request: Request, call_next):
        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)
        # CORS preflight requests bypass rate limiting — they don't
        # represent billable work and rejecting them starves the browser
        # client of the preflight response it needs to make the real call.
        if request.method == "OPTIONS":
            return await call_next(request)
        return await rate_limit_middleware(request, call_next, limiter)

    # Authentication (JWT for regular, API key for /api/*). Sets both
    # ``request.state.user_claims`` / ``api_key_data`` AND
    # ``request.state.role`` so downstream ``@require_role`` decorators
    # can read the role without a separate pass. The role must be set
    # after the underlying auth middleware has populated claims, so it
    # lives in a small wrapper around ``call_next``.
    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth for public endpoints
        public_paths = ["/health", "/docs", "/openapi.json", "/redoc"]
        if request.url.path in public_paths:
            return await call_next(request)

        # CORS preflight requests MUST bypass auth — browsers send OPTIONS
        # without credentials, and the CORSMiddleware handles them
        # downstream. Rejecting preflight with 401 breaks every browser
        # client before the real request even reaches auth.
        if request.method == "OPTIONS":
            return await call_next(request)

        async def call_next_with_role(inner_request: Request):
            # At this point jwt_auth / api_key_auth have populated
            # request.state.user_claims or request.state.api_key_data.
            # Extract the caller's role for the RBAC decorator.
            if hasattr(inner_request.state, "user_claims"):
                claims = inner_request.state.user_claims
                inner_request.state.role = claims.get("role", "member")
            elif hasattr(inner_request.state, "api_key_data"):
                # API keys have admin access (no per-key role concept).
                inner_request.state.role = "admin"
            return await call_next(inner_request)

        # Apply JWT authentication for regular endpoints
        if request.url.path.startswith("/api/"):
            # API endpoints use API key authentication
            return await api_key_auth_middleware(request, call_next_with_role, db)
        else:
            # Regular endpoints use JWT authentication
            return await jwt_auth_middleware(request, call_next_with_role)

    # Global error handler — registered LAST so it becomes the OUTERMOST
    # middleware and catches HTTPException / ValidationError raised
    # anywhere below (auth, rate limit, role, route handlers), formatting
    # them to RFC 7807 Problem Details.
    @app.middleware("http")
    async def error_middleware(request: Request, call_next):
        return await error_handler_middleware(request, call_next)

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
