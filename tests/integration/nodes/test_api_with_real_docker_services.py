"""Integration tests for API nodes using real Docker mock API server.

This replaces test_api_with_real_data.py to comply with the "no mocking in integration tests" policy.
All tests use a real HTTP server running in Docker instead of Python mocks.
"""

import json
import os
import time

import pytest
import requests
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.api.auth import OAuth2Node
from kailash.nodes.api.graphql import GraphQLClientNode
from kailash.nodes.api.rest import RESTClientNode

# Mock API server configuration
MOCK_API_HOST = os.getenv("MOCK_API_HOST", "localhost")
MOCK_API_PORT = int(os.getenv("MOCK_API_PORT", "8888"))
MOCK_API_BASE_URL = f"http://{MOCK_API_HOST}:{MOCK_API_PORT}"


@pytest.fixture(scope="module")
def ensure_mock_api_server():
    """Ensure mock API server is running."""
    max_retries = 10
    retry_delay = 2

    for i in range(max_retries):
        try:
            response = requests.get(f"{MOCK_API_BASE_URL}/health", timeout=5)
            if response.status_code == 200:
                return
        except requests.exceptions.RequestException:
            if i < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise ConnectionError(
                    "Mock API server not available. Run: docker-compose -f tests/utils/docker-compose.test.yml up mock-api"
                )


@pytest.mark.integration
@pytest.mark.requires_docker
class TestAPINodesWithRealDockerServices:
    """Integration tests for API nodes with real Docker mock API server."""

    def test_http_request_node_with_real_api(self, ensure_mock_api_server):
        """Test HTTPRequestNode with real HTTP requests to mock API server."""
        node = HTTPRequestNode()

        result = node.execute(
            url=f"{MOCK_API_BASE_URL}/v1/users",
            method="GET",
            headers={"Authorization": "Bearer test_token"},
        )

        assert result["status_code"] == 200
        assert result["success"] is True
        assert "response" in result
        assert "content" in result["response"]
        assert "users" in result["response"]["content"]
        assert len(result["response"]["content"]["users"]) >= 1
        assert result["response"]["content"]["users"][0]["name"] == "Sarah Johnson"

    def test_rest_client_with_pagination(self, ensure_mock_api_server):
        """Test RESTClientNode with paginated responses from real server."""
        node = RESTClientNode()

        # First page
        result1 = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource="/v1/users",
            method="GET",
            query_params={"page": 1, "per_page": 2},
        )

        assert result1["status_code"] == 200
        assert len(result1["data"]["users"]) == 2
        assert result1["data"]["has_next"] is True

        # Second page
        result2 = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource="/v1/users",
            method="GET",
            query_params={"page": 2, "per_page": 2},
        )

        assert result2["status_code"] == 200
        assert len(result2["data"]["users"]) >= 1

    def test_oauth2_node_with_real_flow(self, ensure_mock_api_server):
        """Test OAuth2Node with real OAuth endpoint."""
        node = OAuth2Node()

        result = node.execute(
            token_url=f"{MOCK_API_BASE_URL}/oauth/token",
            client_id="test_client_id",
            client_secret="test_client_secret",
            grant_type="client_credentials",
            scope="read write",
        )

        assert "token_data" in result
        assert result["token_data"]["access_token"] is not None
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 3600
        assert result["refresh_token_present"]

    def test_graphql_client_with_complex_query(self, ensure_mock_api_server):
        """Test GraphQLClientNode with real GraphQL endpoint."""
        node = GraphQLClientNode()

        query = """
        query GetUserWithPosts($userId: ID!) {
            user(id: $userId) {
                id
                name
                email
                posts {
                    id
                    title
                    content
                    publishedAt
                    tags
                }
            }
        }
        """

        result = node.execute(
            endpoint=f"{MOCK_API_BASE_URL}/graphql",
            query=query,
            variables={"userId": "1"},
            headers={"Authorization": "Bearer test_token"},
        )

        assert result["success"] is True
        assert "user" in result["data"]
        user = result["data"]["user"]
        assert user["name"] == "Sarah Johnson"
        assert len(user["posts"]) == 2
        assert user["posts"][0]["title"] == "Building Scalable Microservices"

    def test_error_handling_with_real_errors(self, ensure_mock_api_server):
        """Test error handling with real HTTP errors from server."""
        node = HTTPRequestNode()

        # Test 404 Not Found
        result = node.execute(url=f"{MOCK_API_BASE_URL}/v1/users/999", method="GET")

        assert result["status_code"] == 404
        assert result["success"] is False
        assert "recovery_suggestions" in result

        # Test rate limiting (need to make many requests)
        # First, make enough requests to trigger rate limit
        for _ in range(101):  # Rate limit is 100/minute
            node.execute(url=f"{MOCK_API_BASE_URL}/v1/users", method="GET")

        # This should be rate limited
        result = node.execute(url=f"{MOCK_API_BASE_URL}/v1/users", method="GET")

        if result["status_code"] == 429:  # If rate limiting is triggered
            assert result["success"] is False
            assert "recovery_suggestions" in result
            assert any(
                "rate limit" in s.lower() for s in result["recovery_suggestions"]
            )

    def test_rest_client_crud_operations(self, ensure_mock_api_server):
        """Test full CRUD operations with RESTClientNode against real server."""
        node = RESTClientNode()

        # CREATE - Post new user
        new_user = {
            "name": "John Doe",
            "email": "john.doe@techcorp.com",
            "role": "Developer",
            "department": "Engineering",
        }

        result = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource="/v1/users",
            method="POST",
            data=new_user,
        )

        assert result["status_code"] == 201
        created_user_id = result["data"]["id"]
        assert result["data"]["name"] == "John Doe"

        # READ - Get user
        result = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource=f"/v1/users/{created_user_id}",
            method="GET",
        )

        assert result["status_code"] == 200
        assert result["data"]["id"] == created_user_id

        # UPDATE - Patch user
        update_data = {"role": "Senior Developer"}
        result = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource=f"/v1/users/{created_user_id}",
            method="PATCH",
            data=update_data,
        )

        assert result["status_code"] == 200
        assert result["data"]["role"] == "Senior Developer"

        # DELETE - Remove user
        result = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource=f"/v1/users/{created_user_id}",
            method="DELETE",
        )

        assert result["status_code"] == 204
        assert result["success"] is True

        # Verify deletion
        result = node.execute(
            base_url=MOCK_API_BASE_URL,
            resource=f"/v1/users/{created_user_id}",
            method="GET",
        )
        assert result["status_code"] == 404

    def test_api_aggregation_endpoints(self, ensure_mock_api_server):
        """Test API aggregation endpoints for complex workflows."""
        node = HTTPRequestNode()

        # Test multiple endpoints
        endpoints = ["/users", "/posts", "/comments"]
        results = {}

        for endpoint in endpoints:
            result = node.execute(url=f"{MOCK_API_BASE_URL}{endpoint}", method="GET")
            assert result["success"] is True
            results[endpoint] = result["response"]["content"]

        # Verify data relationships
        users = results["/users"]
        posts = results["/posts"]
        comments = results["/comments"]

        assert len(users) >= 2
        assert len(posts) >= 3
        assert len(comments) >= 3

        # Check data consistency
        user_ids = {u["id"] for u in users}
        post_user_ids = {p["userId"] for p in posts}
        assert post_user_ids.issubset(user_ids), "Posts reference non-existent users"

        post_ids = {p["id"] for p in posts}
        comment_post_ids = {c["postId"] for c in comments}
        assert comment_post_ids.issubset(
            post_ids
        ), "Comments reference non-existent posts"


@pytest.mark.integration
@pytest.mark.requires_docker
class TestAPIWithOllamaGeneration:
    """Integration tests for API nodes with Ollama-generated test data."""

    def test_generate_and_test_api_responses(self, ensure_mock_api_server):
        """Test API nodes with both mock server and Ollama generation."""
        ollama_url = os.getenv("OLLAMA_TEST_URL", "http://localhost:11435")

        # First test with mock server data
        node = HTTPRequestNode()
        result = node.execute(url=f"{MOCK_API_BASE_URL}/v1/users", method="GET")

        assert result["success"] is True
        assert "users" in result["response"]["content"]

        # If Ollama is available, we could generate additional test scenarios
        # But this is optional - the main test uses the real mock API server
        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            has_ollama = response.status_code == 200
        except:
            has_ollama = False

        if has_ollama:
            from kailash.nodes.ai import LLMAgentNode

            # Generate test scenario
            generator = LLMAgentNode()
            prompt = """Generate a test scenario description for an API that manages users.
            Include what edge cases to test. Return as a brief list."""

            scenario = generator.execute(
                prompt=prompt,
                model="llama3.2:1b",
                api_endpoint=f"{ollama_url}/api/generate",
                temperature=0.7,
            )

            # The test scenario is generated but we still use real API calls
            assert scenario.get("response") is not None
