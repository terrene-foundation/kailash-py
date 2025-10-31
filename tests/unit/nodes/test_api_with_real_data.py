"""API tests using real data patterns and Docker services.

NOTE: These tests use mocked responses that simulate real API patterns.
They do not require actual network connectivity.
"""

import json
import os
from unittest.mock import Mock, patch

import pytest
import requests
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.api.auth import OAuth2Node
from kailash.nodes.api.graphql import GraphQLClientNode
from kailash.nodes.api.rest import RESTClientNode

# Use real API response patterns
REAL_USER_API_RESPONSE = {
    "users": [
        {
            "id": 1,
            "name": "Sarah Johnson",
            "email": "sarah.johnson@techcorp.com",
            "role": "Senior Developer",
            "department": "Engineering",
            "created_at": "2024-01-15T10:30:00Z",
        },
        {
            "id": 2,
            "name": "Michael Chen",
            "email": "michael.chen@techcorp.com",
            "role": "Product Manager",
            "department": "Product",
            "created_at": "2024-02-20T14:45:00Z",
        },
        {
            "id": 3,
            "name": "Emily Rodriguez",
            "email": "emily.rodriguez@techcorp.com",
            "role": "Data Scientist",
            "department": "Analytics",
            "created_at": "2024-03-10T09:15:00Z",
        },
    ],
    "total": 3,
    "page": 1,
    "per_page": 10,
}

REAL_PRODUCT_API_RESPONSE = {
    "products": [
        {
            "id": "prod_001",
            "name": "Enterprise Analytics Suite",
            "description": "Advanced analytics platform for business intelligence",
            "price": 4999.99,
            "category": "Software",
            "features": ["Real-time dashboards", "ML predictions", "Data integration"],
            "available": True,
        },
        {
            "id": "prod_002",
            "name": "Cloud Storage Pro",
            "description": "Secure cloud storage with advanced encryption",
            "price": 299.99,
            "category": "Infrastructure",
            "features": ["256-bit encryption", "Auto-backup", "Version control"],
            "available": True,
        },
    ]
}

# Real OAuth token response
REAL_OAUTH_RESPONSE = {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "refresh_token_value",
    "scope": "read write",
}

# Real GraphQL response
REAL_GRAPHQL_RESPONSE = {
    "data": {
        "user": {
            "id": "1",
            "name": "Sarah Johnson",
            "email": "sarah.johnson@techcorp.com",
            "posts": [
                {
                    "id": "101",
                    "title": "Building Scalable Microservices",
                    "content": "In this post, we'll explore best practices for building scalable microservices...",
                    "publishedAt": "2024-11-20T10:00:00Z",
                    "tags": ["microservices", "architecture", "scalability"],
                },
                {
                    "id": "102",
                    "title": "Kubernetes in Production",
                    "content": "Learn from our experience running Kubernetes in production for 2 years...",
                    "publishedAt": "2024-11-25T14:30:00Z",
                    "tags": ["kubernetes", "devops", "containers"],
                },
            ],
        }
    }
}


class MockResponse:
    """Mock response object that mimics requests.Response."""

    def __init__(self, json_data, status_code=200, headers=None, url=None):
        self.json_data = json_data
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "application/json"}
        self.text = json.dumps(json_data)
        self.content = self.text.encode()
        self.ok = 200 <= status_code < 300
        self.url = url or "https://api.techcorp.com"

    def json(self):
        return self.json_data

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"{self.status_code} Error")


@pytest.mark.unit
class TestAPINodesWithRealData:
    """Test API nodes with realistic data patterns using local mocking."""

    def test_http_request_node_with_real_api(self):
        """Test HTTPRequestNode with real-world API response."""
        node = HTTPRequestNode()

        # Mock the session pool's request method
        mock_session = Mock()
        mock_session.request.return_value = MockResponse(REAL_USER_API_RESPONSE)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session

            result = node.execute(
                url="https://api.techcorp.com/v1/users",
                method="GET",
                headers={"Authorization": "Bearer test_token"},
            )

            assert result["status_code"] == 200
            assert result["success"] is True
            assert "response" in result
            assert "content" in result["response"]
            assert "users" in result["response"]["content"]
            assert len(result["response"]["content"]["users"]) == 3
            assert result["response"]["content"]["users"][0]["name"] == "Sarah Johnson"

            # Verify the request was made correctly
            mock_session.request.assert_called_once()
            call_args = mock_session.request.call_args
            assert call_args[1]["url"] == "https://api.techcorp.com/v1/users"
            assert call_args[1]["headers"] == {"Authorization": "Bearer test_token"}

    def test_rest_client_with_pagination(self):
        """Test RESTClientNode with paginated responses."""
        node = RESTClientNode()

        # Mock paginated responses
        page1_response = {
            "users": REAL_USER_API_RESPONSE["users"][:2],
            "total": 3,
            "page": 1,
            "per_page": 2,
            "has_next": True,
        }

        page2_response = {
            "users": REAL_USER_API_RESPONSE["users"][2:],
            "total": 3,
            "page": 2,
            "per_page": 2,
            "has_next": False,
        }

        # Mock the session pool for RESTClientNode
        mock_session = Mock()
        mock_session.request.side_effect = [
            MockResponse(page1_response),
            MockResponse(page2_response),
        ]

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session

            # First page
            result1 = node.execute(
                base_url="https://api.techcorp.com",
                resource="/v1/users",
                method="GET",
                query_params={"page": 1, "per_page": 2},
            )

            assert result1["status_code"] == 200
            assert len(result1["data"]["users"]) == 2
            assert result1["data"]["has_next"] is True

            # Second page
            result2 = node.execute(
                base_url="https://api.techcorp.com",
                resource="/v1/users",
                method="GET",
                query_params={"page": 2, "per_page": 2},
            )

            assert result2["status_code"] == 200
            assert len(result2["data"]["users"]) == 1
            assert result2["data"]["has_next"] is False

    def test_oauth2_node_with_real_flow(self):
        """Test OAuth2Node with realistic OAuth flow."""
        node = OAuth2Node()

        with patch("kailash.nodes.api.auth.requests.post") as mock_post:
            mock_post.return_value = MockResponse(REAL_OAUTH_RESPONSE)

            result = node.execute(
                token_url="https://auth.techcorp.com/oauth/token",
                client_id="test_client_id",
                client_secret="test_client_secret",
                grant_type="client_credentials",
                scope="read write",
            )

            assert (
                result["token_data"]["access_token"]
                == REAL_OAUTH_RESPONSE["access_token"]
            )
            assert result["token_type"] == "Bearer"
            assert result["expires_in"] == 3600
            assert result["refresh_token_present"]

            # Verify OAuth request
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://auth.techcorp.com/oauth/token"
            assert call_args[1]["data"]["grant_type"] == "client_credentials"

    def test_graphql_client_with_complex_query(self):
        """Test GraphQLClientNode with complex nested query."""
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

        # Mock the session pool for GraphQL which uses HTTPRequestNode internally
        mock_session = Mock()
        mock_session.request.return_value = MockResponse(REAL_GRAPHQL_RESPONSE)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session

            result = node.execute(
                endpoint="https://api.techcorp.com/graphql",
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

            # Verify GraphQL request
            mock_session.request.assert_called_once()
            call_args = mock_session.request.call_args
            assert call_args[1]["url"] == "https://api.techcorp.com/graphql"

    def test_error_handling_with_real_errors(self):
        """Test error handling with realistic API errors."""
        node = HTTPRequestNode()

        # Test 404 Not Found
        mock_session = Mock()
        error_response = {
            "error": {
                "code": "NOT_FOUND",
                "message": "User not found",
                "details": "No user exists with ID: 999",
            }
        }
        mock_session.request.return_value = MockResponse(
            error_response, status_code=404
        )

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session

            result = node.execute(
                url="https://api.techcorp.com/v1/users/999", method="GET"
            )

            assert result["status_code"] == 404
            assert result["success"] is False
            assert "recovery_suggestions" in result

        # Test 429 Rate Limit with simpler validation
        mock_session2 = Mock()
        rate_limit_response = {"error": "Rate limit exceeded", "retry_after": 60}
        mock_session2.request.return_value = MockResponse(
            rate_limit_response,
            status_code=429,
            headers={
                "X-RateLimit-Limit": "100",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1234567890",
                "Content-Type": "application/json",
            },
        )

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session2

            result = node.execute(url="https://api.techcorp.com/v1/users", method="GET")

            assert result["status_code"] == 429
            assert result["success"] is False
            assert "recovery_suggestions" in result
            assert any(
                "rate limit" in s.lower() for s in result["recovery_suggestions"]
            )

    def test_rest_client_crud_operations(self):
        """Test full CRUD operations with RESTClientNode."""
        node = RESTClientNode()
        base_url = "https://api.techcorp.com"

        # CREATE - Post new user
        new_user = {
            "name": "John Doe",
            "email": "john.doe@techcorp.com",
            "role": "Developer",
        }

        mock_session = Mock()
        created_user = {**new_user, "id": 4, "created_at": "2024-12-01T10:00:00Z"}
        mock_session.request.return_value = MockResponse(created_user, status_code=201)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session

            result = node.execute(
                base_url=base_url, resource="/v1/users", method="POST", data=new_user
            )

            assert result["status_code"] == 201
            assert result["data"]["id"] == 4
            assert result["data"]["name"] == "John Doe"

        # READ - Get user
        mock_session2 = Mock()
        mock_session2.request.return_value = MockResponse(created_user)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session2

            result = node.execute(
                base_url=base_url, resource="/v1/users/4", method="GET"
            )

            assert result["status_code"] == 200
            assert result["data"]["id"] == 4

        # UPDATE - Patch user
        update_data = {"role": "Senior Developer"}
        mock_session3 = Mock()
        updated_user = {**created_user, **update_data}
        mock_session3.request.return_value = MockResponse(updated_user)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session3

            result = node.execute(
                base_url=base_url,
                resource="/v1/users/4",
                method="PATCH",
                data=update_data,
            )

            assert result["status_code"] == 200
            assert result["data"]["role"] == "Senior Developer"

        # DELETE - Remove user
        mock_session4 = Mock()
        mock_session4.request.return_value = MockResponse({}, status_code=204)

        with patch("kailash.nodes.api.http._http_session_pool.acquire") as mock_acquire:
            mock_acquire.return_value.__enter__.return_value = mock_session4

            result = node.execute(
                base_url=base_url, resource="/v1/users/4", method="DELETE"
            )

            assert result["status_code"] == 204
            assert result["success"] is True


# NOTE: Tests requiring Ollama for test data generation have been moved
# to tests/integration/nodes/test_api_with_real_data.py
