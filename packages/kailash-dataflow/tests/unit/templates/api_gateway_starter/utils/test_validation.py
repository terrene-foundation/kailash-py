"""
Unit tests for request validation functions.

Tests validation logic for CREATE, UPDATE, LIST requests and pagination parameters.
"""

from typing import Dict

import pytest


@pytest.mark.unit
class TestRequestValidation:
    """Test request validation functions."""

    def test_validate_create_request_valid(self):
        """Test valid CREATE request validation."""
        from templates.api_gateway_starter.utils.validation import (
            validate_create_request,
        )

        data = {"id": "user_123", "name": "Alice", "email": "alice@example.com"}
        result = validate_create_request("User", data)

        assert result == data
        assert "id" in result
        assert "name" in result
        assert "email" in result

    def test_validate_create_request_missing_required(self):
        """Test CREATE request with missing required field (id)."""
        from templates.api_gateway_starter.utils.validation import (
            validate_create_request,
        )

        data = {"name": "Alice", "email": "alice@example.com"}

        with pytest.raises(ValueError) as exc_info:
            validate_create_request("User", data)

        assert "id" in str(exc_info.value).lower()
        assert "required" in str(exc_info.value).lower()

    def test_validate_create_request_invalid_type(self):
        """Test CREATE request with invalid data type (None)."""
        from templates.api_gateway_starter.utils.validation import (
            validate_create_request,
        )

        with pytest.raises(ValueError) as exc_info:
            validate_create_request("User", None)

        assert (
            "empty" in str(exc_info.value).lower()
            or "none" in str(exc_info.value).lower()
        )

    def test_validate_update_request_valid(self):
        """Test valid UPDATE request validation."""
        from templates.api_gateway_starter.utils.validation import (
            validate_update_request,
        )

        data = {"filter": {"id": "user_123"}, "fields": {"name": "Alice Updated"}}
        result = validate_update_request("User", data)

        assert result == data
        assert "filter" in result
        assert "fields" in result
        assert result["filter"]["id"] == "user_123"

    def test_validate_update_request_missing_filter(self):
        """Test UPDATE request without filter."""
        from templates.api_gateway_starter.utils.validation import (
            validate_update_request,
        )

        data = {"fields": {"name": "Alice Updated"}}

        with pytest.raises(ValueError) as exc_info:
            validate_update_request("User", data)

        assert "filter" in str(exc_info.value).lower()
        assert "required" in str(exc_info.value).lower()

    def test_validate_list_request_valid(self):
        """Test valid LIST request validation."""
        from templates.api_gateway_starter.utils.validation import validate_list_request

        params = {"limit": 10, "offset": 0, "filters": {"active": True}}
        result = validate_list_request(params)

        assert result == params
        assert result["limit"] == 10
        assert result["offset"] == 0

    def test_validate_list_request_invalid_limit(self):
        """Test LIST request with invalid limit (negative)."""
        from templates.api_gateway_starter.utils.validation import validate_list_request

        params = {"limit": -5, "offset": 0}

        with pytest.raises(ValueError) as exc_info:
            validate_list_request(params)

        assert "limit" in str(exc_info.value).lower()
        assert (
            "positive" in str(exc_info.value).lower()
            or "greater" in str(exc_info.value).lower()
        )

    def test_validate_pagination_params_valid(self):
        """Test valid pagination parameter validation."""
        from templates.api_gateway_starter.utils.validation import (
            validate_pagination_params,
        )

        offset, limit = validate_pagination_params(page=1, limit=20)

        assert offset == 0  # Page 1 starts at offset 0
        assert limit == 20

    def test_validate_pagination_params_negative_page(self):
        """Test pagination with negative page number."""
        from templates.api_gateway_starter.utils.validation import (
            validate_pagination_params,
        )

        with pytest.raises(ValueError) as exc_info:
            validate_pagination_params(page=-1, limit=10)

        assert "page" in str(exc_info.value).lower()
        assert (
            "positive" in str(exc_info.value).lower()
            or "greater" in str(exc_info.value).lower()
        )

    def test_validate_pagination_params_exceeds_max_limit(self):
        """Test pagination with limit exceeding max_limit."""
        from templates.api_gateway_starter.utils.validation import (
            validate_pagination_params,
        )

        offset, limit = validate_pagination_params(page=1, limit=200, max_limit=100)

        # Should cap at max_limit
        assert limit == 100
        assert offset == 0
