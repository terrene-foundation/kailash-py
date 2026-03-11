"""
Error Handling middleware for API Gateway.

Provides global error handling with RFC 7807 Problem Details formatting.
"""

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from templates.api_gateway_starter.utils.errors import (
    INTERNAL_ERROR,
    VALIDATION_ERROR,
    ProblemDetail,
)

logger = logging.getLogger(__name__)


async def error_handler_middleware(request: Request, call_next):
    """
    Global error handler with RFC 7807 formatting.

    Catches all exceptions and converts them to standardized RFC 7807 Problem Details.

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler

    Returns:
        JSONResponse with RFC 7807 format for errors, or original response for success

    Example:
        ```python
        from fastapi import FastAPI

        app = FastAPI()

        @app.middleware("http")
        async def error_middleware(request: Request, call_next):
            return await error_handler_middleware(request, call_next)
        ```
    """
    try:
        response = await call_next(request)
        return response

    except ValidationError as exc:
        # Pydantic validation error
        logger.warning(f"Validation error: {exc.errors()}")
        problem = format_validation_error(exc)
        return problem.to_response()

    except HTTPException as exc:
        # FastAPI HTTPException
        logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
        problem = format_http_exception(exc)
        return problem.to_response()

    except Exception as exc:
        # Unexpected exception
        logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
        problem = format_unexpected_error(exc)
        return problem.to_response()


def format_validation_error(exc: ValidationError) -> ProblemDetail:
    """
    Format Pydantic validation error to RFC 7807.

    Args:
        exc: Pydantic ValidationError

    Returns:
        ProblemDetail with validation error details

    Example:
        ```python
        from pydantic import BaseModel, ValidationError

        class User(BaseModel):
            email: str
            age: int

        try:
            User(email="invalid")  # Missing age
        except ValidationError as e:
            problem = format_validation_error(e)
            # Returns RFC 7807 problem with invalid_params extension
        ```
    """
    # Extract validation errors
    errors = exc.errors()
    invalid_params = []

    for error in errors:
        field_path = " -> ".join(str(loc) for loc in error["loc"])
        invalid_params.append({"name": field_path, "reason": error["msg"]})

    # Create detail message
    detail = f"{len(errors)} validation error(s)"
    if errors:
        first_error = errors[0]
        field = " -> ".join(str(loc) for loc in first_error["loc"])
        detail = f"Field '{field}': {first_error['msg']}"

    return ProblemDetail(
        type=VALIDATION_ERROR,
        title="Validation Error",
        status=400,
        detail=detail,
        invalid_params=invalid_params,
    )


def format_http_exception(exc: HTTPException) -> ProblemDetail:
    """
    Format HTTPException to RFC 7807.

    Args:
        exc: FastAPI HTTPException

    Returns:
        ProblemDetail with HTTP error details

    Example:
        ```python
        from fastapi import HTTPException

        exc = HTTPException(status_code=404, detail="User not found")
        problem = format_http_exception(exc)
        # Returns RFC 7807 problem with 404 status
        ```
    """
    # Map status code to title
    status_titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
        502: "Bad Gateway",
        503: "Service Unavailable",
        504: "Gateway Timeout",
    }

    title = status_titles.get(exc.status_code, "HTTP Error")

    return ProblemDetail(
        type="about:blank", title=title, status=exc.status_code, detail=str(exc.detail)
    )


def format_unexpected_error(exc: Exception) -> ProblemDetail:
    """
    Format unexpected exception to RFC 7807.

    Args:
        exc: Python exception

    Returns:
        ProblemDetail with 500 Internal Server Error

    Example:
        ```python
        try:
            raise ValueError("Something went wrong")
        except Exception as e:
            problem = format_unexpected_error(e)
            # Returns RFC 7807 problem with 500 status and error_type extension
        ```
    """
    return ProblemDetail(
        type=INTERNAL_ERROR,
        title="Internal Server Error",
        status=500,
        detail="An unexpected error occurred. Please try again later.",
        error_type=type(exc).__name__,
    )
