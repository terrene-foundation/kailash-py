"""
Unit tests for response formatting functions.

Tests success, paginated, and created response formatting.
"""

from typing import Any, Dict, List

import pytest


@pytest.mark.unit
class TestResponseFormatting:
    """Test response formatting functions."""

    def test_success_response_basic(self):
        """Test basic success response formatting."""
        from templates.api_gateway_starter.utils.responses import success_response

        data = {"id": "user_123", "name": "Alice"}
        result = success_response(data)

        assert result["status"] == "success"
        assert result["data"] == data
        assert result["message"] == "Success"
        assert "metadata" not in result or result["metadata"] is None

    def test_success_response_with_metadata(self):
        """Test success response with metadata."""
        from templates.api_gateway_starter.utils.responses import success_response

        data = {"id": "user_123"}
        metadata = {"execution_time": "0.05s"}
        result = success_response(data, message="User fetched", metadata=metadata)

        assert result["status"] == "success"
        assert result["data"] == data
        assert result["message"] == "User fetched"
        assert result["metadata"] == metadata

    def test_paginated_response_first_page(self):
        """Test paginated response for first page."""
        from templates.api_gateway_starter.utils.responses import paginated_response

        data = [{"id": f"user_{i}"} for i in range(10)]
        result = paginated_response(data, total=50, page=1, limit=10)

        assert result["status"] == "success"
        assert result["data"] == data
        assert result["pagination"]["total"] == 50
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["limit"] == 10
        assert result["pagination"]["total_pages"] == 5
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is False

    def test_paginated_response_last_page(self):
        """Test paginated response for last page."""
        from templates.api_gateway_starter.utils.responses import paginated_response

        data = [{"id": f"user_{i}"} for i in range(5)]
        result = paginated_response(data, total=25, page=3, limit=10)

        assert result["status"] == "success"
        assert len(result["data"]) == 5
        assert result["pagination"]["page"] == 3
        assert result["pagination"]["has_next"] is False
        assert result["pagination"]["has_prev"] is True

    def test_paginated_response_middle_page(self):
        """Test paginated response for middle page."""
        from templates.api_gateway_starter.utils.responses import paginated_response

        data = [{"id": f"user_{i}"} for i in range(10)]
        result = paginated_response(data, total=50, page=3, limit=10)

        assert result["pagination"]["page"] == 3
        assert result["pagination"]["has_next"] is True
        assert result["pagination"]["has_prev"] is True

    def test_created_response_basic(self):
        """Test 201 Created response formatting."""
        from templates.api_gateway_starter.utils.responses import created_response

        data = {"id": "user_123", "name": "Alice", "email": "alice@example.com"}
        result = created_response(data, resource_id="user_123")

        assert result["status"] == "success"
        assert result["message"] == "Resource created successfully"
        assert result["data"] == data
        assert result["resource_id"] == "user_123"

    def test_success_response_null_data(self):
        """Test success response with null/None data."""
        from templates.api_gateway_starter.utils.responses import success_response

        result = success_response(None, message="No data")

        assert result["status"] == "success"
        assert result["data"] is None
        assert result["message"] == "No data"

    def test_paginated_response_empty_list(self):
        """Test paginated response with empty data list."""
        from templates.api_gateway_starter.utils.responses import paginated_response

        result = paginated_response([], total=0, page=1, limit=10)

        assert result["status"] == "success"
        assert result["data"] == []
        assert result["pagination"]["total"] == 0
        assert result["pagination"]["total_pages"] == 0
        assert result["pagination"]["has_next"] is False
        assert result["pagination"]["has_prev"] is False

    def test_success_response_nested_data(self):
        """Test success response with nested complex data."""
        from templates.api_gateway_starter.utils.responses import success_response

        data = {
            "user": {"id": "user_123", "name": "Alice"},
            "profile": {"bio": "Engineer", "location": "SF"},
        }
        result = success_response(data)

        assert result["status"] == "success"
        assert result["data"]["user"]["id"] == "user_123"
        assert result["data"]["profile"]["location"] == "SF"

    def test_paginated_response_metadata(self):
        """Test paginated response with additional metadata."""
        from templates.api_gateway_starter.utils.responses import paginated_response

        data = [{"id": f"user_{i}"} for i in range(10)]
        metadata = {"query_time": "0.02s", "cache_hit": True}
        result = paginated_response(
            data, total=100, page=2, limit=10, metadata=metadata
        )

        assert result["status"] == "success"
        assert result["metadata"] == metadata
        assert result["pagination"]["page"] == 2
