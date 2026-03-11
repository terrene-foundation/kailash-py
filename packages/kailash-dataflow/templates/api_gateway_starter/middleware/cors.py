"""
CORS configuration middleware for API Gateway.

Provides Cross-Origin Resource Sharing (CORS) configuration with environment-based settings.
"""

from typing import Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def configure_cors(app: FastAPI, allowed_origins: List[str] = None):
    """
    Configure CORS middleware with allowed origins.

    Args:
        app: FastAPI application instance
        allowed_origins: List of allowed origin URLs or ["*"] for wildcard

    Example:
        ```python
        from fastapi import FastAPI

        app = FastAPI()

        # Allow specific origins
        configure_cors(app, allowed_origins=["https://app.example.com", "https://admin.example.com"])

        # Allow all origins (development only)
        configure_cors(app, allowed_origins=["*"])

        # Environment-based configuration
        import os
        origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
        configure_cors(app, allowed_origins=origins)
        ```
    """
    if allowed_origins is None:
        allowed_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )


def get_cors_headers(origin: str, allowed_origins: List[str]) -> Dict:
    """
    Get CORS headers for manual responses.

    Args:
        origin: Request origin
        allowed_origins: List of allowed origins

    Returns:
        Dictionary of CORS headers if origin is allowed, empty dict otherwise

    Example:
        ```python
        from fastapi import Request

        @app.get("/api/data")
        async def get_data(request: Request):
            origin = request.headers.get("Origin")
            cors_headers = get_cors_headers(origin, ["https://app.example.com"])

            return JSONResponse(
                content={"data": "value"},
                headers=cors_headers
            )
        ```
    """
    if not is_origin_allowed(origin, allowed_origins):
        return {}

    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }


def is_origin_allowed(origin: str, allowed_origins: List[str]) -> bool:
    """
    Check if origin is in allowed list.

    Args:
        origin: Request origin URL
        allowed_origins: List of allowed origin URLs

    Returns:
        True if origin is allowed, False otherwise

    Example:
        ```python
        # Exact match
        is_allowed = is_origin_allowed("https://app.example.com", ["https://app.example.com"])
        assert is_allowed is True

        # Wildcard
        is_allowed = is_origin_allowed("https://anything.com", ["*"])
        assert is_allowed is True

        # Not allowed
        is_allowed = is_origin_allowed("https://evil.com", ["https://app.example.com"])
        assert is_allowed is False
        ```
    """
    # Wildcard allows all origins
    if "*" in allowed_origins:
        return True

    # Exact match required (no subdomain matching)
    return origin in allowed_origins
