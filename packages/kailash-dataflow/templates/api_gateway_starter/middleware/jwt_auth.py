"""
JWT Authentication Middleware for API Gateway.

Provides JWT verification middleware and decorators for FastAPI endpoints.
Reuses SaaS Starter's verify_token function.
"""

from typing import Callable, Dict

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from templates.saas_starter.auth import jwt_auth

# Import verify_token for test mocking
verify_token = jwt_auth.verify_token


def _auth_error_response(detail: str, status_code: int = 401) -> JSONResponse:
    """Return RFC 7807 problem+json response for auth failures.

    Starlette's ``BaseHTTPMiddleware`` re-raises exceptions outside the outer
    middleware's ``try/except``, so raising HTTPException inside a middleware
    dispatch function propagates past ``error_handler_middleware`` and surfaces
    to the ASGI layer (the client sees an unhandled exception instead of 401).
    Returning a JSONResponse directly is the only reliable way to produce a
    401 from a middleware in the current Starlette/anyio stack.
    """
    status_titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
    }
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


async def jwt_auth_middleware(request: Request, call_next: Callable) -> any:
    """
    Verify JWT token and attach user claims to request.state.

    Args:
        request: FastAPI Request object
        call_next: Next middleware in chain

    Returns:
        Response: A 401 JSONResponse (RFC 7807) on auth failure, or the
        downstream response on success.

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> app.middleware("http")(jwt_auth_middleware)
    """
    # Extract Authorization header
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return _auth_error_response("Missing Authorization header")

    # Validate header format
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return _auth_error_response(
            "Invalid Authorization header format. Expected: Bearer <token>"
        )

    token = parts[1]

    # Verify token using SaaS Starter function
    verification = verify_token(token)

    if not verification.get("valid"):
        error_message = verification.get("error", "Invalid token")
        return _auth_error_response(error_message)

    # Attach user claims to request state
    request.state.user_claims = {
        "user_id": verification["user_id"],
        "org_id": verification.get("org_id"),
        "email": verification.get("email"),
        "role": verification.get("role"),  # Include role if present
        "exp": verification["exp"],
    }
    # Populate request.state.role so @require_role decorators (which run
    # inside the endpoint, AFTER all middlewares on the request path) can
    # gate access. Defaulting to "member" matches the role_middleware's
    # historical behavior for missing role claims.
    request.state.role = request.state.user_claims.get("role") or "member"

    # Continue to next middleware
    response = await call_next(request)
    return response


def jwt_auth_required(allow_expired: bool = False) -> Callable:
    """
    Decorator for JWT-protected endpoints.

    Args:
        allow_expired: If True, allow expired tokens (default: False)

    Returns:
        Decorator function

    Example:
        >>> @jwt_auth_required()
        >>> async def protected_endpoint(request: Request):
        ...     user_id = request.state.user_claims["user_id"]
        ...     return {"user_id": user_id}
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(request: Request, *args, **kwargs):
            # Check if user_claims attached by middleware
            if not hasattr(request.state, "user_claims"):
                raise HTTPException(
                    status_code=401,
                    detail="Missing authentication. JWT middleware required.",
                )

            # Optionally check expiration
            if not allow_expired:
                import time

                exp = request.state.user_claims.get("exp")
                if exp and exp < time.time():
                    raise HTTPException(status_code=401, detail="Token has expired")

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


async def get_current_user(request: Request) -> Dict:
    """
    Extract current user from request.state.

    Args:
        request: FastAPI Request object

    Returns:
        User claims dictionary

    Raises:
        HTTPException: If user_claims not found in request.state

    Example:
        >>> user = await get_current_user(request)
        >>> print(user["user_id"])
        user_123
    """
    if not hasattr(request.state, "user_claims"):
        raise HTTPException(
            status_code=401, detail="User claims not found. JWT middleware required."
        )

    return request.state.user_claims
