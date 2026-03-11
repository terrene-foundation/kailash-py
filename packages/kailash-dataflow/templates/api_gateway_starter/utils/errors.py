"""
RFC 7807 Problem Details error formatting for API Gateway.

Provides standardized error responses following RFC 7807 specification.
Reference: https://tools.ietf.org/html/rfc7807
"""

from typing import Any, Dict, Optional

from fastapi.responses import JSONResponse

# Standard error type URIs
VALIDATION_ERROR = "https://dataflow.dev/errors/validation-error"
AUTHENTICATION_ERROR = "https://dataflow.dev/errors/authentication-error"
AUTHORIZATION_ERROR = "https://dataflow.dev/errors/authorization-error"
RATE_LIMIT_ERROR = "https://dataflow.dev/errors/rate-limit-error"
NOT_FOUND_ERROR = "https://dataflow.dev/errors/not-found-error"
INTERNAL_ERROR = "https://dataflow.dev/errors/internal-error"


class ProblemDetail:
    """
    RFC 7807 Problem Details for HTTP APIs.

    Provides a standard format for machine-readable error responses.

    Attributes:
        type: A URI reference that identifies the problem type
        title: A short, human-readable summary of the problem type
        status: The HTTP status code
        detail: A human-readable explanation specific to this occurrence
        instance: A URI reference that identifies the specific occurrence
        **extensions: Additional problem-specific extension members
    """

    def __init__(
        self,
        type: str,
        title: str,
        status: int,
        detail: Optional[str] = None,
        instance: Optional[str] = None,
        **extensions,
    ):
        """
        Initialize a ProblemDetail instance.

        Args:
            type: URI reference identifying the problem type
            title: Short summary of the problem
            status: HTTP status code
            detail: Specific explanation for this occurrence
            instance: URI identifying this specific occurrence
            **extensions: Additional custom fields
        """
        self.type = type
        self.title = title
        self.status = status
        self.detail = detail
        self.instance = instance
        self.extensions = extensions

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert ProblemDetail to RFC 7807 compliant dictionary.

        Returns:
            Dictionary representation following RFC 7807 format

        Example:
            >>> problem = ProblemDetail(
            ...     type=VALIDATION_ERROR,
            ...     title="Validation Error",
            ...     status=400,
            ...     detail="Field 'email' is required"
            ... )
            >>> problem.to_dict()
            {
                "type": "https://dataflow.dev/errors/validation-error",
                "title": "Validation Error",
                "status": 400,
                "detail": "Field 'email' is required"
            }
        """
        result = {"type": self.type, "title": self.title, "status": self.status}

        # Only include optional fields if they have values
        if self.detail is not None:
            result["detail"] = self.detail

        if self.instance is not None:
            result["instance"] = self.instance

        # Add extension fields
        result.update(self.extensions)

        return result

    def to_response(self) -> JSONResponse:
        """
        Convert ProblemDetail to FastAPI JSONResponse.

        Returns:
            JSONResponse with application/problem+json media type

        Example:
            >>> problem = ProblemDetail(
            ...     type=NOT_FOUND_ERROR,
            ...     title="Resource Not Found",
            ...     status=404
            ... )
            >>> response = problem.to_response()
            >>> response.status_code
            404
        """
        return JSONResponse(
            status_code=self.status,
            content=self.to_dict(),
            media_type="application/problem+json",
        )
