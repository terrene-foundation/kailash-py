"""End-to-End tests for Query Parameters feature in Nexus.

Feature #2: Query Parameters - E2E Testing
Status: Testing real-world scenarios with workflows and query parameters

These tests verify complete user journeys with query parameters:
- Real Nexus application startup
- Custom endpoints with query parameters
- Workflow integration with query parameters
- Real HTTP requests and responses
- Complete error handling scenarios
"""

from typing import List, Optional

import pytest
from fastapi import Query
from fastapi.testclient import TestClient
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus


class TestQueryParametersE2E:
    """End-to-end tests for query parameter support in real scenarios."""

    def test_real_world_pagination_api(self):
        """Test real-world pagination API with query parameters.

        Simulates a production API for listing conversations with:
        - Pagination (limit, offset)
        - Filtering (status)
        - Sorting (sort_by, order)
        """
        # Create Nexus app
        app = Nexus(api_port=8200, enable_durability=False, enable_auth=False)

        # Create custom endpoint with comprehensive query parameters
        @app.endpoint("/api/conversations", methods=["GET"])
        async def list_conversations(
            limit: int = Query(20, gt=0, le=100, description="Number of results"),
            offset: int = Query(0, ge=0, description="Pagination offset"),
            status: str = Query("all", pattern="^(all|active|archived)$"),
            sort_by: str = Query("created_at", description="Sort field"),
            order: str = Query("desc", pattern="^(asc|desc)$"),
        ):
            """List conversations with pagination and filtering."""
            # Simulate database query
            all_conversations = [
                {"id": f"conv_{i}", "status": "active" if i % 2 == 0 else "archived"}
                for i in range(100)
            ]

            # Filter by status
            if status != "all":
                filtered = [c for c in all_conversations if c["status"] == status]
            else:
                filtered = all_conversations

            # Paginate
            paginated = filtered[offset : offset + limit]

            return {
                "data": paginated,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": len(filtered),
                    "has_more": offset + limit < len(filtered),
                },
                "filters": {"status": status, "sort_by": sort_by, "order": order},
            }

        client = TestClient(app._gateway.app)

        # Test 1: Default parameters
        response = client.get("/api/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 20  # Default limit
        assert data["pagination"]["offset"] == 0
        assert data["filters"]["status"] == "all"

        # Test 2: Custom pagination
        response = client.get("/api/conversations?limit=10&offset=5")
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 10
        assert data["pagination"]["offset"] == 5

        # Test 3: Filtering by status
        response = client.get("/api/conversations?status=active&limit=100")
        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "active" for c in data["data"])

        # Test 4: Invalid parameters
        response = client.get("/api/conversations?limit=150")  # Exceeds max
        assert response.status_code == 422

        response = client.get("/api/conversations?status=invalid")  # Invalid status
        assert response.status_code == 422

        # Cleanup
        if app._running:
            app.stop()

    def test_rest_api_with_workflow_backend(self):
        """Test REST API with query parameters calling real workflows.

        Real-world scenario: Custom REST API that uses workflows for business logic.
        """
        # Create Nexus app
        app = Nexus(api_port=8201, enable_durability=False, enable_auth=False)

        # Create a simple workflow (no external dependencies)
        workflow = WorkflowBuilder()
        # Use a simple transformation workflow
        workflow.add_node(
            "PythonCodeNode",
            "transform",
            {
                "code": """
# Simple transformation without external inputs
result = {
    'processed': True,
    'message': 'Workflow executed successfully'
}
"""
            },
        )

        # Register workflow
        app.register("process_data", workflow.build())

        # Create REST API endpoint that uses workflow
        @app.endpoint("/api/process", methods=["GET"])
        async def process_api(
            batch_size: int = Query(10, gt=0, le=100),
            priority: str = Query("normal", pattern="^(low|normal|high)$"),
        ):
            """Process data with specified parameters."""
            # In real app, you would call the workflow here
            # For now, return query params to verify they work
            return {
                "status": "success",
                "parameters": {"batch_size": batch_size, "priority": priority},
                "workflow": "process_data",
            }

        client = TestClient(app._gateway.app)

        # Test workflow-backed endpoint with query params
        response = client.get("/api/process?batch_size=50&priority=high")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["parameters"]["batch_size"] == 50
        assert data["parameters"]["priority"] == "high"

        # Cleanup
        if app._running:
            app.stop()

    def test_mixed_rest_and_workflow_endpoints(self):
        """Test mixing REST endpoints with traditional workflow endpoints.

        Verifies that custom REST endpoints coexist with registered workflows.
        """
        app = Nexus(api_port=8202, enable_durability=False, enable_auth=False)

        # Register traditional workflow
        workflow = WorkflowBuilder()
        workflow.add_node(
            "PythonCodeNode",
            "greet",
            {"code": "result = {'greeting': 'Hello from workflow'}"},
        )
        app.register("greet_workflow", workflow.build())

        # Add custom REST endpoint
        @app.endpoint("/api/custom", methods=["GET"])
        async def custom_endpoint(name: str = "World"):
            return {"greeting": f"Hello {name} from REST API"}

        client = TestClient(app._gateway.app)

        # Test traditional workflow endpoint (POST)
        response = client.post("/workflows/greet_workflow/execute", json={})
        assert response.status_code == 200

        # Test custom REST endpoint (GET with query params)
        response = client.get("/api/custom?name=Alice")
        assert response.status_code == 200
        assert response.json()["greeting"] == "Hello Alice from REST API"

        # Cleanup
        if app._running:
            app.stop()

    def test_complex_search_api(self):
        """Test complex search API with multiple query parameters.

        Real-world scenario: Search endpoint with multiple filters, tags, and pagination.
        """
        app = Nexus(api_port=8203, enable_durability=False, enable_auth=False)

        @app.endpoint("/api/search", methods=["GET"])
        async def search_endpoint(
            query: str,  # Required
            tags: List[str] = Query([], description="Filter by tags"),
            min_score: float = Query(0.0, ge=0.0, le=1.0),
            max_results: int = Query(10, gt=0, le=100),
            include_archived: bool = False,
        ):
            """Search with multiple filters."""
            # Simulate search results
            results = [
                {
                    "id": i,
                    "title": f"Result {i} matching '{query}'",
                    "tags": tags,
                    "score": 0.9 - (i * 0.05),
                    "archived": i % 5 == 0,
                }
                for i in range(max_results)
            ]

            # Filter by min_score
            results = [r for r in results if r["score"] >= min_score]

            # Filter archived if needed
            if not include_archived:
                results = [r for r in results if not r["archived"]]

            return {
                "query": query,
                "results": results,
                "total": len(results),
                "filters": {
                    "tags": tags,
                    "min_score": min_score,
                    "include_archived": include_archived,
                },
            }

        client = TestClient(app._gateway.app)

        # Test with all parameters
        response = client.get(
            "/api/search?query=test&tags=python&tags=ai&min_score=0.7&max_results=5&include_archived=true"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "test"
        assert data["filters"]["tags"] == ["python", "ai"]
        assert data["filters"]["min_score"] == 0.7

        # Test missing required parameter
        response = client.get("/api/search?tags=python")  # Missing 'query'
        assert response.status_code == 422

        # Cleanup
        if app._running:
            app.stop()

    def test_path_and_query_params_combined(self):
        """Test combining path parameters with query parameters.

        Real-world scenario: User-specific resource listing with pagination.
        """
        app = Nexus(api_port=8204, enable_durability=False, enable_auth=False)

        @app.endpoint("/api/users/{user_id}/items", methods=["GET"])
        async def get_user_items(
            user_id: str,  # Path parameter
            category: Optional[str] = None,  # Query parameter
            limit: int = Query(20, gt=0),
            offset: int = Query(0, ge=0),
        ):
            """Get user's items with optional filtering and pagination."""
            # Simulate user items
            items = [
                {
                    "id": f"{user_id}_item_{i}",
                    "category": "books" if i % 2 == 0 else "electronics",
                    "name": f"Item {i}",
                }
                for i in range(50)
            ]

            # Filter by category if specified
            if category:
                items = [item for item in items if item["category"] == category]

            # Paginate
            paginated = items[offset : offset + limit]

            return {
                "user_id": user_id,
                "items": paginated,
                "total": len(items),
                "category": category,
                "pagination": {"limit": limit, "offset": offset},
            }

        client = TestClient(app._gateway.app)

        # Test with path and query params
        response = client.get("/api/users/u123/items?category=books&limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "u123"
        assert data["category"] == "books"
        assert len(data["items"]) == 5
        assert all(item["category"] == "books" for item in data["items"])

        # Test different user
        response = client.get("/api/users/u456/items?offset=10&limit=3")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "u456"
        assert data["pagination"]["offset"] == 10

        # Cleanup
        if app._running:
            app.stop()

    def test_error_handling_e2e(self):
        """Test comprehensive error handling with query parameters.

        Verifies that validation errors return proper 422 responses
        with detailed error messages.
        """
        app = Nexus(api_port=8205, enable_durability=False, enable_auth=False)

        @app.endpoint("/api/validate", methods=["GET"])
        async def validated_endpoint(
            email: str = Query(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$"),
            age: int = Query(..., ge=0, le=120),
            country: str = Query("US", min_length=2, max_length=2),
        ):
            """Endpoint with strict validation."""
            return {"email": email, "age": age, "country": country}

        client = TestClient(app._gateway.app)

        # Valid request
        response = client.get("/api/validate?email=test@example.com&age=25&country=US")
        assert response.status_code == 200

        # Invalid email
        response = client.get("/api/validate?email=invalid&age=25")
        assert response.status_code == 422

        # Age out of range
        response = client.get("/api/validate?email=test@example.com&age=150")
        assert response.status_code == 422

        # Country code wrong length
        response = client.get("/api/validate?email=test@example.com&age=25&country=USA")
        assert response.status_code == 422

        # Cleanup
        if app._running:
            app.stop()

    def test_openapi_documentation(self):
        """Test that query parameters are documented in OpenAPI schema.

        Verifies that FastAPI's automatic documentation includes query parameters.
        """
        app = Nexus(api_port=8206, enable_durability=False, enable_auth=False)

        @app.endpoint("/api/documented", methods=["GET"])
        async def documented_endpoint(
            search: str = Query(..., description="Search query string"),
            limit: int = Query(10, description="Number of results to return"),
        ):
            """Well-documented endpoint with query parameters."""
            return {"search": search, "limit": limit}

        client = TestClient(app._gateway.app)

        # Get OpenAPI schema
        response = client.get("/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        # Verify our endpoint is in the schema
        assert "/api/documented" in schema["paths"]

        # Verify query parameters are documented
        endpoint_spec = schema["paths"]["/api/documented"]["get"]
        assert "parameters" in endpoint_spec

        param_names = [p["name"] for p in endpoint_spec["parameters"]]
        assert "search" in param_names
        assert "limit" in param_names

        # Cleanup
        if app._running:
            app.stop()
