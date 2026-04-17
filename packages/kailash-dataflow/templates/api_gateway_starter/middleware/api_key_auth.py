"""
API Key Authentication Middleware for API Gateway.

Provides API key verification middleware and scope checking.
Reuses SaaS Starter's verify_api_key function.
"""

from typing import Callable, Dict, List

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from templates.saas_starter.security import api_keys

# Import verify_api_key for test mocking
verify_api_key = api_keys.verify_api_key


def _auth_error_response(detail: str, status_code: int = 401) -> JSONResponse:
    """Return RFC 7807 problem+json response for auth failures.

    Middleware cannot raise HTTPException in Starlette's BaseHTTPMiddleware
    stack — exceptions propagate past ``error_handler_middleware`` to the
    ASGI layer. Returning a JSONResponse directly is the only reliable way
    to produce a 401 from a middleware.
    """
    status_titles = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden"}
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "about:blank",
            "title": status_titles.get(status_code, "HTTP Error"),
            "status": status_code,
            "detail": detail,
        },
        media_type="application/problem+json",
    )


async def api_key_auth_middleware(request: Request, call_next: Callable, db) -> any:
    """
    Verify API key and attach organization + scopes to request.state.

    Args:
        request: FastAPI Request object
        call_next: Next middleware in chain
        db: DataFlow instance for API key verification

    Returns:
        Response: A 401 JSONResponse (RFC 7807) on auth failure, or the
        downstream response on success.

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> @app.middleware("http")
        >>> async def api_key_middleware(request, call_next):
        ...     return await api_key_auth_middleware(request, call_next, db)
    """
    # Extract X-API-Key header
    api_key = request.headers.get("X-API-Key")

    if not api_key:
        return _auth_error_response("Missing X-API-Key header")

    # Verify API key using SaaS Starter function
    verification = verify_api_key(db, api_key)

    if not verification.get("valid"):
        error_message = verification.get("error", "Invalid API key")
        return _auth_error_response(error_message)

    # Attach API key data to request state
    request.state.api_key_data = {
        "organization_id": verification["organization_id"],
        "scopes": verification["scopes"],
    }

    # Include optional fields if present
    if "rate_limit" in verification:
        request.state.api_key_data["rate_limit"] = verification["rate_limit"]

    # Continue to next middleware
    response = await call_next(request)
    return response


def api_key_required(required_scopes: List[str] = None) -> Callable:
    """
    Decorator for API key protected endpoints.

    Args:
        required_scopes: List of required scopes (default: None = no scope check)

    Returns:
        Decorator function

    Example:
        >>> @api_key_required(required_scopes=["read:users"])
        >>> async def list_users(request: Request):
        ...     org_id = request.state.api_key_data["organization_id"]
        ...     return {"organization_id": org_id}
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(request: Request, *args, **kwargs):
            # Check if api_key_data attached by middleware
            if not hasattr(request.state, "api_key_data"):
                raise HTTPException(
                    status_code=401,
                    detail="Missing API key. API key middleware required.",
                )

            # Check required scopes if specified
            if required_scopes:
                key_scopes = request.state.api_key_data.get("scopes", [])

                for required_scope in required_scopes:
                    if required_scope not in key_scopes:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Missing required scope: {required_scope}",
                        )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


async def check_scope_permission(request: Request, required_scope: str) -> bool:
    """
    Check if API key has required scope.

    Args:
        request: FastAPI Request object
        required_scope: Scope to check (e.g., "read:users")

    Returns:
        True if scope is present, False otherwise

    Example:
        >>> has_permission = await check_scope_permission(request, "write:users")
        >>> if has_permission:
        ...     # Proceed with write operation
        ...     pass
    """
    if not hasattr(request.state, "api_key_data"):
        return False

    scopes = request.state.api_key_data.get("scopes", [])
    return required_scope in scopes
