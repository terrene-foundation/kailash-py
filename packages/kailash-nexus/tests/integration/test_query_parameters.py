"""Integration tests for Query Parameter support in Nexus.

Feature #2: Query Parameters - Test-First Development
Status: RED PHASE - Tests written before implementation

These tests verify that Nexus supports FastAPI query parameters for:
- Basic query parameters with defaults
- Optional query parameters
- Query parameter type validation
- Multiple values (list query params)
- Query parameters with pattern validation (regex patterns)
- Invalid query parameters (422 errors)
- Missing required query parameters
- Query params combined with path params
- Query params with workflow execution

Note: Uses FastAPI 'pattern' parameter (not deprecated 'regex').
"""

from typing import List, Optional

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


class TestQueryParameters:
    """Test suite for query parameter support in Nexus."""

    def setup_method(self):
        """Setup test instance with disabled durability."""
        self.app = Nexus(
            api_port=8100,
            enable_durability=False,  # Disable caching for tests
            enable_auth=False,
            enable_monitoring=False,
        )

    def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "app") and self.app._running:
            self.app.stop()

    def test_basic_query_parameters(self):
        """Test basic query parameter extraction with defaults.

        Acceptance Criteria AC-2.1:
        - Given endpoint with query parameter limit: int = 20
        - When I request /api/test?limit=50
        - Then function receives limit=50
        - When I request /api/test (no query param)
        - Then function receives limit=20 (default)
        """

        # Register custom endpoint with query parameters
        @self.app.endpoint("/api/test", methods=["GET"])
        async def test_endpoint(limit: int = 20, offset: int = 0):
            return {"limit": limit, "offset": offset}

        # Get TestClient
        client = TestClient(self.app._gateway.app)

        # Test with query parameters
        response = client.get("/api/test?limit=50&offset=10")
        assert response.status_code == 200
        assert response.json() == {"limit": 50, "offset": 10}

        # Test with partial query parameters (should use defaults)
        response = client.get("/api/test?limit=30")
        assert response.status_code == 200
        assert response.json() == {"limit": 30, "offset": 0}

        # Test with no query parameters (should use all defaults)
        response = client.get("/api/test")
        assert response.status_code == 200
        assert response.json() == {"limit": 20, "offset": 0}

    def test_query_parameters_with_defaults(self):
        """Test that default values work correctly.

        Verifies that when query parameters are not provided,
        default values from function signature are used.
        """

        @self.app.endpoint("/api/items", methods=["GET"])
        async def list_items(
            page: int = 1, page_size: int = 25, sort: str = "created_at"
        ):
            return {"page": page, "page_size": page_size, "sort": sort}

        client = TestClient(self.app._gateway.app)

        # No parameters - all defaults
        response = client.get("/api/items")
        assert response.status_code == 200
        assert response.json() == {"page": 1, "page_size": 25, "sort": "created_at"}

    def test_optional_query_parameters(self):
        """Test optional query parameters using Optional type hint.

        Acceptance Criteria AC-2.5:
        - Given endpoint with filter: Optional[str] = None
        - When I request /api/test (no filter param)
        - Then function receives filter=None
        - When I request /api/test?filter=hello
        - Then function receives filter="hello"
        """

        @self.app.endpoint("/api/search", methods=["GET"])
        async def search_items(
            query: str,  # Required
            filter: Optional[str] = None,  # Optional
            category: Optional[str] = None,  # Optional
        ):
            return {"query": query, "filter": filter, "category": category}

        client = TestClient(self.app._gateway.app)

        # With all parameters
        response = client.get("/api/search?query=test&filter=active&category=books")
        assert response.status_code == 200
        assert response.json() == {
            "query": "test",
            "filter": "active",
            "category": "books",
        }

        # With only required parameter
        response = client.get("/api/search?query=test")
        assert response.status_code == 200
        assert response.json() == {"query": "test", "filter": None, "category": None}

        # Missing required parameter should fail
        response = client.get("/api/search")
        assert response.status_code == 422

    def test_query_parameter_type_validation(self):
        """Test query parameter type validation.

        Acceptance Criteria AC-2.2:
        - Given endpoint with limit: int parameter
        - When I request /api/test?limit=abc (non-integer)
        - Then returns 422 Unprocessable Entity
        - And response includes validation error details
        """

        @self.app.endpoint("/api/paginated", methods=["GET"])
        async def paginated_endpoint(limit: int, offset: int, active: bool = True):
            return {"limit": limit, "offset": offset, "active": active}

        client = TestClient(self.app._gateway.app)

        # Valid types
        response = client.get("/api/paginated?limit=10&offset=0")
        assert response.status_code == 200
        assert response.json() == {"limit": 10, "offset": 0, "active": True}

        # Invalid integer type
        response = client.get("/api/paginated?limit=abc&offset=0")
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail

        # Invalid boolean type
        response = client.get("/api/paginated?limit=10&offset=0&active=notabool")
        assert response.status_code == 422

    def test_multiple_value_query_parameters(self):
        """Test query parameters with multiple values (list).

        Acceptance Criteria AC-2.4:
        - Given endpoint with tags: List[str] = Query([])
        - When I request /api/test?tags=python&tags=api
        - Then function receives tags=["python", "api"]
        """

        @self.app.endpoint("/api/filter", methods=["GET"])
        async def filter_items(tags: List[str] = Query([])):
            return {"tags": tags, "count": len(tags)}

        client = TestClient(self.app._gateway.app)

        # Multiple values
        response = client.get("/api/filter?tags=python&tags=api&tags=workflow")
        assert response.status_code == 200
        assert response.json() == {"tags": ["python", "api", "workflow"], "count": 3}

        # Single value
        response = client.get("/api/filter?tags=python")
        assert response.status_code == 200
        assert response.json() == {"tags": ["python"], "count": 1}

        # No values (empty list)
        response = client.get("/api/filter")
        assert response.status_code == 200
        assert response.json() == {"tags": [], "count": 0}

    def test_query_parameter_with_regex_validation(self):
        """Test query parameter with pattern validation.

        Verifies that FastAPI Query validation with regex patterns works.
        Note: Using 'pattern' parameter (regex is deprecated in FastAPI).
        """

        @self.app.endpoint("/api/status", methods=["GET"])
        async def get_status(
            status: str = Query("active", pattern="^(active|archived|deleted)$")
        ):
            return {"status": status}

        client = TestClient(self.app._gateway.app)

        # Valid values
        for valid_status in ["active", "archived", "deleted"]:
            response = client.get(f"/api/status?status={valid_status}")
            assert response.status_code == 200
            assert response.json() == {"status": valid_status}

        # Invalid value (doesn't match pattern)
        response = client.get("/api/status?status=invalid")
        assert response.status_code == 422

    def test_query_parameter_range_validation(self):
        """Test query parameter with range validation.

        Acceptance Criteria AC-2.3:
        - Given endpoint with limit: int = Query(20, gt=0, le=100)
        - When I request /api/test?limit=150 (exceeds max)
        - Then returns 422 Unprocessable Entity
        - And error message mentions maximum value
        """

        @self.app.endpoint("/api/range", methods=["GET"])
        async def range_endpoint(
            limit: int = Query(20, gt=0, le=100, description="Number of results"),
            page: int = Query(1, ge=1, description="Page number"),
        ):
            return {"limit": limit, "page": page}

        client = TestClient(self.app._gateway.app)

        # Valid range
        response = client.get("/api/range?limit=50&page=1")
        assert response.status_code == 200
        assert response.json() == {"limit": 50, "page": 1}

        # Exceeds maximum
        response = client.get("/api/range?limit=150")
        assert response.status_code == 422

        # Below minimum (limit must be > 0)
        response = client.get("/api/range?limit=0")
        assert response.status_code == 422

        # Page below minimum (must be >= 1)
        response = client.get("/api/range?page=0")
        assert response.status_code == 422

    def test_invalid_query_parameters(self):
        """Test that invalid query parameters return 422 errors.

        Verifies comprehensive validation error handling.
        """

        @self.app.endpoint("/api/validated", methods=["GET"])
        async def validated_endpoint(
            count: int = Query(..., gt=0, le=1000),
            name: str = Query(..., min_length=3, max_length=50),
        ):
            return {"count": count, "name": name}

        client = TestClient(self.app._gateway.app)

        # Missing required parameters
        response = client.get("/api/validated")
        assert response.status_code == 422

        # Invalid count (string instead of int)
        response = client.get("/api/validated?count=abc&name=test")
        assert response.status_code == 422

        # Name too short
        response = client.get("/api/validated?count=10&name=ab")
        assert response.status_code == 422

        # Name too long
        long_name = "a" * 51
        response = client.get(f"/api/validated?count=10&name={long_name}")
        assert response.status_code == 422

    def test_missing_required_query_parameters(self):
        """Test that missing required query parameters return 422.

        Required parameters are those without default values or Optional.
        """

        @self.app.endpoint("/api/required", methods=["GET"])
        async def required_endpoint(
            required_param: str,  # No default = required
            optional_param: Optional[int] = None,
        ):
            return {"required": required_param, "optional": optional_param}

        client = TestClient(self.app._gateway.app)

        # Valid request with required parameter
        response = client.get("/api/required?required_param=value")
        assert response.status_code == 200
        assert response.json() == {"required": "value", "optional": None}

        # Missing required parameter
        response = client.get("/api/required")
        assert response.status_code == 422

    def test_query_params_with_path_params(self):
        """Test mixing query parameters with path parameters.

        Acceptance Criteria AC-2.6:
        - Given endpoint /api/users/{user_id}/items?limit=10
        - When I request /api/users/u123/items?limit=5
        - Then function receives user_id="u123" and limit=5
        """

        @self.app.endpoint("/api/users/{user_id}/items", methods=["GET"])
        async def get_user_items(
            user_id: str,  # Path parameter
            limit: int = 10,  # Query parameter
            offset: int = 0,  # Query parameter
            filter: Optional[str] = None,  # Query parameter
        ):
            return {
                "user_id": user_id,
                "limit": limit,
                "offset": offset,
                "filter": filter,
            }

        client = TestClient(self.app._gateway.app)

        # Path param + query params
        response = client.get("/api/users/u123/items?limit=5&offset=10")
        assert response.status_code == 200
        assert response.json() == {
            "user_id": "u123",
            "limit": 5,
            "offset": 10,
            "filter": None,
        }

        # Path param + all query params
        response = client.get("/api/users/u456/items?limit=20&offset=0&filter=active")
        assert response.status_code == 200
        assert response.json() == {
            "user_id": "u456",
            "limit": 20,
            "offset": 0,
            "filter": "active",
        }

        # Path param only (query params use defaults)
        response = client.get("/api/users/u789/items")
        assert response.status_code == 200
        assert response.json() == {
            "user_id": "u789",
            "limit": 10,
            "offset": 0,
            "filter": None,
        }

    def test_query_params_workflow_execution(self):
        """Test query params passed to custom endpoint that simulates workflow.

        Verifies that query parameters can be extracted and used
        to drive business logic (simulating workflow execution).
        """

        # Create custom endpoint that uses query params (without actual workflow)
        @self.app.endpoint("/api/items", methods=["GET"])
        async def list_items_api(
            limit: int = Query(10, gt=0, le=100),
            offset: int = Query(0, ge=0),
            filter: Optional[str] = None,
        ):
            """List items with pagination and filtering."""
            # Simulate workflow processing
            items = list(range(offset, offset + limit))
            return {
                "items": items,
                "limit": limit,
                "offset": offset,
                "filter": filter,
                "count": len(items),
            }

        client = TestClient(self.app._gateway.app)

        # Test with query params
        response = client.get("/api/items?limit=5&offset=10&filter=active")
        assert response.status_code == 200

        result = response.json()
        assert result["limit"] == 5
        assert result["offset"] == 10
        assert result["filter"] == "active"
        assert result["items"] == [10, 11, 12, 13, 14]
        assert result["count"] == 5

    def test_query_params_complex_types(self):
        """Test query parameters with complex type validation.

        Verifies that complex types (enums, nested validation) work.
        """
        from enum import Enum

        class SortOrder(str, Enum):
            ASC = "asc"
            DESC = "desc"

        @self.app.endpoint("/api/sorted", methods=["GET"])
        async def sorted_endpoint(
            sort_by: str = "created_at",
            order: SortOrder = SortOrder.ASC,
            include_deleted: bool = False,
        ):
            return {
                "sort_by": sort_by,
                "order": order,
                "include_deleted": include_deleted,
            }

        client = TestClient(self.app._gateway.app)

        # Valid enum value
        response = client.get("/api/sorted?order=desc")
        assert response.status_code == 200
        assert response.json()["order"] == "desc"

        # Invalid enum value
        response = client.get("/api/sorted?order=invalid")
        assert response.status_code == 422

    def test_query_params_get_vs_post(self):
        """Test that GET uses query params while POST uses body.

        Verifies that the same endpoint path can have different
        parameter sources based on HTTP method.
        """

        # GET endpoint with query params
        @self.app.endpoint("/api/data", methods=["GET"])
        async def get_data(id: str, format: str = "json"):
            return {"method": "GET", "id": id, "format": format}

        # POST endpoint with body
        from pydantic import BaseModel

        class DataRequest(BaseModel):
            id: str
            format: str = "json"

        @self.app.endpoint("/api/data", methods=["POST"])
        async def post_data(request: DataRequest):
            return {"method": "POST", "id": request.id, "format": request.format}

        client = TestClient(self.app._gateway.app)

        # GET with query params
        response = client.get("/api/data?id=123&format=xml")
        assert response.status_code == 200
        assert response.json() == {"method": "GET", "id": "123", "format": "xml"}

        # POST with body
        response = client.post("/api/data", json={"id": "456", "format": "csv"})
        assert response.status_code == 200
        assert response.json() == {"method": "POST", "id": "456", "format": "csv"}
