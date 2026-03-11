"""
JWT Authentication Middleware for API Gateway.

Provides JWT verification middleware and decorators for FastAPI endpoints.
Reuses SaaS Starter's verify_token function.
"""

from typing import Callable, Dict

from fastapi import HTTPException, Request
from templates.saas_starter.auth import jwt_auth

# Import verify_token for test mocking
verify_token = jwt_auth.verify_token


async def jwt_auth_middleware(request: Request, call_next: Callable) -> any:
    """
    Verify JWT token and attach user claims to request.state.

    Args:
        request: FastAPI Request object
        call_next: Next middleware in chain

    Raises:
        HTTPException: If token is missing, invalid, or expired

    Example:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> app.middleware("http")(jwt_auth_middleware)
    """
    # Extract Authorization header
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Validate header format
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
        )

    token = parts[1]

    # Verify token using SaaS Starter function
    verification = verify_token(token)

    if not verification.get("valid"):
        error_message = verification.get("error", "Invalid token")
        raise HTTPException(status_code=401, detail=error_message)

    # Attach user claims to request state
    request.state.user_claims = {
        "user_id": verification["user_id"],
        "org_id": verification.get("org_id"),
        "email": verification.get("email"),
        "role": verification.get("role"),  # Include role if present
        "exp": verification["exp"],
    }

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
