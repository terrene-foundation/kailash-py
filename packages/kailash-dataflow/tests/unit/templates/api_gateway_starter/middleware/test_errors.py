"""
Unit tests for Error Handling middleware.
Tests RFC 7807 error formatting for various exception types.
"""

from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from templates.api_gateway_starter.middleware.errors import (
    error_handler_middleware,
    format_http_exception,
    format_unexpected_error,
    format_validation_error,
)
from templates.api_gateway_starter.utils.errors import ProblemDetail


class TestErrorHandlerMiddleware:
    """Test global error handler middleware."""

    async def test_error_handler_validation_error(self):
        """Test middleware handles Pydantic validation errors."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/users"

        async def call_next(req):
            # Simulate validation error
            class TestModel(BaseModel):
                name: str
                age: int

            # This will raise ValidationError
            TestModel(name="John")  # Missing required 'age' field

        # Middleware catches ValidationError and returns JSON response
        response = await error_handler_middleware(request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

        import json

        body = json.loads(response.body)
        assert body["title"] == "Validation Error"
        assert body["status"] == 400

    async def test_error_handler_http_exception(self):
        """Test middleware handles HTTPException."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/users/123"

        async def call_next(req):
            raise HTTPException(status_code=404, detail="User not found")

        response = await error_handler_middleware(request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404

        # Response body should be RFC 7807 format
        import json

        body = json.loads(response.body)
        assert body["type"] == "about:blank"
        assert body["title"] == "Not Found"
        assert body["status"] == 404
        assert "User not found" in body["detail"]

    async def test_error_handler_unexpected_error(self):
        """Test middleware handles unexpected exceptions."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/process"

        async def call_next(req):
            raise ValueError("Unexpected error occurred")

        response = await error_handler_middleware(request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500

        import json

        body = json.loads(response.body)
        assert body["type"] == "https://dataflow.dev/errors/internal-error"
        assert body["title"] == "Internal Server Error"
        assert body["status"] == 500

    def test_format_validation_error_missing_field(self):
        """Test formatting validation error for missing required field."""

        class TestModel(BaseModel):
            name: str
            email: str

        try:
            TestModel(name="John")  # Missing email
        except ValidationError as e:
            problem = format_validation_error(e)

            assert isinstance(problem, ProblemDetail)
            assert problem.status == 400
            assert problem.title == "Validation Error"
            assert "email" in str(problem.detail).lower()
            assert "invalid_params" in problem.extensions

    def test_format_validation_error_type_error(self):
        """Test formatting validation error for type mismatch."""

        class TestModel(BaseModel):
            age: int

        try:
            TestModel(age="not a number")  # Wrong type
        except ValidationError as e:
            problem = format_validation_error(e)

            assert isinstance(problem, ProblemDetail)
            assert problem.status == 400
            assert "age" in str(problem.detail).lower()

    def test_format_http_exception_401(self):
        """Test formatting 401 Unauthorized exception."""
        exc = HTTPException(status_code=401, detail="Invalid credentials")
        problem = format_http_exception(exc)

        assert isinstance(problem, ProblemDetail)
        assert problem.status == 401
        assert problem.title == "Unauthorized"
        assert "Invalid credentials" in problem.detail

    def test_format_http_exception_404(self):
        """Test formatting 404 Not Found exception."""
        exc = HTTPException(status_code=404, detail="Resource not found")
        problem = format_http_exception(exc)

        assert isinstance(problem, ProblemDetail)
        assert problem.status == 404
        assert problem.title == "Not Found"
        assert "Resource not found" in problem.detail

    def test_format_unexpected_error(self):
        """Test formatting unexpected Python exception."""
        exc = ValueError("Something went wrong")
        problem = format_unexpected_error(exc)

        assert isinstance(problem, ProblemDetail)
        assert problem.status == 500
        assert problem.title == "Internal Server Error"
        assert "error_type" in problem.extensions
        assert problem.extensions["error_type"] == "ValueError"

    async def test_error_handler_middleware_success(self):
        """Test middleware passes through successful responses."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/users"

        mock_response = Mock()
        mock_response.status_code = 200

        async def call_next(req):
            return mock_response

        response = await error_handler_middleware(request, call_next)
        assert response.status_code == 200

    async def test_error_handler_middleware_error(self):
        """Test middleware converts all errors to RFC 7807 format."""
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/error"

        async def call_next(req):
            raise RuntimeError("Critical error")

        response = await error_handler_middleware(request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500

        import json

        body = json.loads(response.body)
        assert "type" in body
        assert "title" in body
        assert "status" in body
        assert "detail" in body
