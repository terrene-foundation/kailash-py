"""
Unit tests for RFC 7807 Problem Details error formatting.

Tests ProblemDetail class and standard error type constants.
"""

from typing import Any, Dict

import pytest


@pytest.mark.unit
class TestErrorFormatting:
    """Test RFC 7807 Problem Details error formatting."""

    def test_problem_detail_to_dict(self):
        """Test converting ProblemDetail to dict."""
        from templates.api_gateway_starter.utils.errors import ProblemDetail

        problem = ProblemDetail(
            type="https://dataflow.dev/errors/validation-error",
            title="Validation Error",
            status=400,
            detail="Field 'email' is required",
            instance="/api/users",
        )

        result = problem.to_dict()

        assert result["type"] == "https://dataflow.dev/errors/validation-error"
        assert result["title"] == "Validation Error"
        assert result["status"] == 400
        assert result["detail"] == "Field 'email' is required"
        assert result["instance"] == "/api/users"

    def test_problem_detail_to_response(self):
        """Test converting ProblemDetail to FastAPI JSONResponse."""
        from templates.api_gateway_starter.utils.errors import ProblemDetail

        problem = ProblemDetail(
            type="https://dataflow.dev/errors/not-found-error",
            title="Resource Not Found",
            status=404,
            detail="User with id 'user_123' not found",
        )

        response = problem.to_response()

        # Check response is FastAPI JSONResponse
        assert hasattr(response, "status_code")
        assert response.status_code == 404
        assert response.media_type == "application/problem+json"

    def test_problem_detail_with_extensions(self):
        """Test ProblemDetail with custom extension fields."""
        from templates.api_gateway_starter.utils.errors import ProblemDetail

        problem = ProblemDetail(
            type="https://dataflow.dev/errors/validation-error",
            title="Validation Error",
            status=400,
            detail="Invalid input",
            errors=[
                {"field": "email", "message": "Invalid format"},
                {"field": "age", "message": "Must be positive"},
            ],
            request_id="req_abc123",
        )

        result = problem.to_dict()

        assert "errors" in result
        assert len(result["errors"]) == 2
        assert result["errors"][0]["field"] == "email"
        assert result["request_id"] == "req_abc123"

    def test_validation_error_type(self):
        """Test VALIDATION_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import VALIDATION_ERROR

        assert VALIDATION_ERROR == "https://dataflow.dev/errors/validation-error"

    def test_authentication_error_type(self):
        """Test AUTHENTICATION_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import AUTHENTICATION_ERROR

        assert (
            AUTHENTICATION_ERROR == "https://dataflow.dev/errors/authentication-error"
        )

    def test_authorization_error_type(self):
        """Test AUTHORIZATION_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import AUTHORIZATION_ERROR

        assert AUTHORIZATION_ERROR == "https://dataflow.dev/errors/authorization-error"

    def test_rate_limit_error_type(self):
        """Test RATE_LIMIT_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import RATE_LIMIT_ERROR

        assert RATE_LIMIT_ERROR == "https://dataflow.dev/errors/rate-limit-error"

    def test_not_found_error_type(self):
        """Test NOT_FOUND_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import NOT_FOUND_ERROR

        assert NOT_FOUND_ERROR == "https://dataflow.dev/errors/not-found-error"

    def test_internal_error_type(self):
        """Test INTERNAL_ERROR constant."""
        from templates.api_gateway_starter.utils.errors import INTERNAL_ERROR

        assert INTERNAL_ERROR == "https://dataflow.dev/errors/internal-error"

    def test_problem_detail_minimal(self):
        """Test ProblemDetail with minimal required fields."""
        from templates.api_gateway_starter.utils.errors import ProblemDetail

        problem = ProblemDetail(
            type="https://dataflow.dev/errors/internal-error",
            title="Internal Server Error",
            status=500,
        )

        result = problem.to_dict()

        assert result["type"] == "https://dataflow.dev/errors/internal-error"
        assert result["title"] == "Internal Server Error"
        assert result["status"] == 500
        assert "detail" not in result or result.get("detail") is None
        assert "instance" not in result or result.get("instance") is None
