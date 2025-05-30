"""Tests for API integration nodes."""

from unittest.mock import MagicMock, patch

import pytest

try:
    import responses

    HAS_RESPONSES = True
except ImportError:
    responses = None
    HAS_RESPONSES = False

# Skip entire module if responses not available
if not HAS_RESPONSES:
    pytest.skip(
        "responses library not available for API tests", allow_module_level=True
    )

from kailash.nodes.api.auth import APIKeyNode, BasicAuthNode, OAuth2Node
from kailash.nodes.api.graphql import GraphQLClientNode
from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode
from kailash.nodes.api.rest import RESTClientNode
from kailash.sdk_exceptions import NodeValidationError


class TestHTTPRequestNode:
    """Tests for the HTTPRequestNode."""

    def test_initialization(self):
        """Test node initialization with valid parameters."""
        node = HTTPRequestNode(
            name="HTTP Request", url="https://example.com/api", method="GET"
        )

        assert node.metadata.name == "HTTP Request"
        assert node.config["url"] == "https://example.com/api"
        assert node.config["method"] == "GET"

    @responses.activate
    def test_get_request(self):
        """Test making a GET request."""
        # Mock the HTTP response
        responses.add(
            responses.GET,
            "https://example.com/api",
            json={"message": "success"},
            status=200,
            content_type="application/json",
        )

        # Create and execute the node
        node = HTTPRequestNode()
        result = node.run(
            url="https://example.com/api",
            method="GET",
            headers={"Accept": "application/json"},
        )

        # Verify the result
        assert result["status_code"] == 200
        assert result["success"] is True
        assert result["response"]["content"]["message"] == "success"

    @responses.activate
    def test_post_request(self):
        """Test making a POST request with JSON data."""
        # Mock the HTTP response
        responses.add(
            responses.POST,
            "https://example.com/api",
            json={"id": 123, "status": "created"},
            status=201,
            content_type="application/json",
        )

        # Create and execute the node
        node = HTTPRequestNode()
        result = node.run(
            url="https://example.com/api",
            method="POST",
            headers={"Content-Type": "application/json"},
            json_data={"name": "Test Item", "value": 42},
        )

        # Verify the result
        assert result["status_code"] == 201
        assert result["success"] is True
        assert result["response"]["content"]["id"] == 123
        assert result["response"]["content"]["status"] == "created"

    @responses.activate
    def test_error_response(self):
        """Test handling error responses."""
        # Mock the HTTP response
        responses.add(
            responses.GET,
            "https://example.com/api/error",
            json={"error": "Not found"},
            status=404,
            content_type="application/json",
        )

        # Create and execute the node
        node = HTTPRequestNode()
        result = node.run(url="https://example.com/api/error", method="GET")

        # Verify the result
        assert result["status_code"] == 404
        assert result["success"] is False
        assert result["response"]["content"]["error"] == "Not found"

    def test_invalid_method(self):
        """Test validation of HTTP method."""
        node = HTTPRequestNode()

        with pytest.raises(NodeValidationError) as excinfo:
            node.run(url="https://example.com/api", method="INVALID")

        assert "Invalid HTTP method" in str(excinfo.value)


class TestRESTClientNode:
    """Tests for the RESTClientNode."""

    def test_initialization(self):
        """Test node initialization with valid parameters."""
        node = RESTClientNode(
            name="REST Client", base_url="https://example.com/api", resource="users"
        )

        assert node.metadata.name == "REST Client"
        assert node.config["base_url"] == "https://example.com/api"
        assert node.config["resource"] == "users"

    def test_build_url(self):
        """Test URL building with path parameters."""
        node = RESTClientNode()

        # Test simple URL
        url = node._build_url(
            base_url="https://example.com/api", resource="users", path_params={}
        )
        assert url == "https://example.com/api/users"

        # Test with path parameter
        url = node._build_url(
            base_url="https://example.com/api",
            resource="users/{id}",
            path_params={"id": 123},
        )
        assert url == "https://example.com/api/users/123"

        # Test with version
        url = node._build_url(
            base_url="https://example.com/api",
            resource="users",
            path_params={},
            version="v1",
        )
        assert url == "https://example.com/api/v1/users"

    def test_missing_path_parameter(self):
        """Test error when required path parameter is missing."""
        node = RESTClientNode()

        with pytest.raises(NodeValidationError) as excinfo:
            node._build_url(
                base_url="https://example.com/api",
                resource="users/{id}/posts",
                path_params={},
            )

        assert "Missing required path parameter" in str(excinfo.value)

    @patch.object(HTTPRequestNode, "run")
    def test_rest_get_request(self, mock_http_run):
        """Test making a REST GET request."""
        # Mock the HTTP response
        mock_http_run.return_value = {
            "response": {
                "status_code": 200,
                "content": [{"id": 1, "name": "Test"}, {"id": 2, "name": "Test 2"}],
                "headers": {"Content-Type": "application/json"},
                "response_time_ms": 150,
                "url": "https://example.com/api/v1/users",
            },
            "status_code": 200,
            "success": True,
        }

        # Create and execute the node
        node = RESTClientNode()
        result = node.run(
            base_url="https://example.com/api",
            resource="users",
            method="GET",
            version="v1",
        )

        # Verify the result
        assert result["status_code"] == 200
        assert result["success"] is True
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 2
        assert result["data"][0]["name"] == "Test"
        assert result["metadata"]["method"] == "GET"


class TestGraphQLClientNode:
    """Tests for the GraphQLClientNode."""

    def test_initialization(self):
        """Test node initialization with valid parameters."""
        node = GraphQLClientNode(
            name="GraphQL Client", endpoint="https://example.com/graphql"
        )

        assert node.metadata.name == "GraphQL Client"
        assert node.config["endpoint"] == "https://example.com/graphql"

    def test_build_graphql_payload(self):
        """Test building GraphQL request payload."""
        node = GraphQLClientNode()

        # Test simple query
        payload = node._build_graphql_payload(query="query { users { id name } }")
        assert payload["query"] == "query { users { id name } }"
        assert "variables" not in payload
        assert "operationName" not in payload

        # Test with variables and operation name
        payload = node._build_graphql_payload(
            query="query GetUser($id: ID!) { user(id: $id) { id name } }",
            variables={"id": "123"},
            operation_name="GetUser",
        )
        assert (
            payload["query"] == "query GetUser($id: ID!) { user(id: $id) { id name } }"
        )
        assert payload["variables"] == {"id": "123"}
        assert payload["operationName"] == "GetUser"

    @patch.object(HTTPRequestNode, "run")
    def test_graphql_query(self, mock_http_run):
        """Test executing a GraphQL query."""
        # Mock the HTTP response
        mock_http_run.return_value = {
            "response": {
                "status_code": 200,
                "content": {
                    "data": {
                        "users": [
                            {"id": "1", "name": "Alice"},
                            {"id": "2", "name": "Bob"},
                        ]
                    }
                },
                "headers": {"Content-Type": "application/json"},
                "response_time_ms": 150,
                "url": "https://example.com/graphql",
            },
            "status_code": 200,
            "success": True,
        }

        # Create and execute the node
        node = GraphQLClientNode()
        result = node.run(
            endpoint="https://example.com/graphql", query="query { users { id name } }"
        )

        # Verify the result
        assert result["success"] is True
        assert "errors" not in result or not result["errors"]
        assert result["data"]["users"][0]["name"] == "Alice"
        assert result["data"]["users"][1]["name"] == "Bob"

    @patch.object(HTTPRequestNode, "run")
    def test_graphql_error_response(self, mock_http_run):
        """Test handling GraphQL error responses."""
        # Mock the HTTP response
        mock_http_run.return_value = {
            "response": {
                "status_code": 200,
                "content": {
                    "data": None,
                    "errors": [
                        {"message": "Field 'user' is missing required argument 'id'"}
                    ],
                },
                "headers": {"Content-Type": "application/json"},
                "response_time_ms": 150,
                "url": "https://example.com/graphql",
            },
            "status_code": 200,
            "success": True,
        }

        # Create and execute the node
        node = GraphQLClientNode()
        result = node.run(
            endpoint="https://example.com/graphql", query="query { user { id name } }"
        )

        # Verify the result
        assert result["success"] is False
        assert len(result["errors"]) == 1
        assert "missing required argument" in result["errors"][0]["message"]
        assert result["data"] is None


class TestAuthNodes:
    """Tests for the authentication nodes."""

    def test_basic_auth(self):
        """Test the BasicAuthNode."""
        node = BasicAuthNode()
        result = node.run(username="testuser", password="testpass")

        assert result["auth_type"] == "basic"
        assert "Authorization" in result["headers"]
        assert result["headers"]["Authorization"].startswith("Basic ")

        # Verify encoded credentials
        import base64

        encoded = result["headers"]["Authorization"].replace("Basic ", "")
        decoded = base64.b64decode(encoded).decode()
        assert decoded == "testuser:testpass"

    def test_api_key_header(self):
        """Test the APIKeyNode with header placement."""
        node = APIKeyNode()
        result = node.run(api_key="abcd1234", location="header", param_name="X-API-Key")

        assert result["auth_type"] == "api_key"
        assert result["headers"]["X-API-Key"] == "abcd1234"
        assert not result["query_params"]
        assert not result["body_params"]

    def test_api_key_query(self):
        """Test the APIKeyNode with query parameter placement."""
        node = APIKeyNode()
        result = node.run(api_key="abcd1234", location="query", param_name="api_key")

        assert result["auth_type"] == "api_key"
        assert not result["headers"]
        assert result["query_params"]["api_key"] == "abcd1234"
        assert not result["body_params"]

    @responses.activate
    def test_oauth2_client_credentials(self):
        """Test the OAuth2Node with client credentials flow."""
        # Mock the token endpoint response
        responses.add(
            responses.POST,
            "https://example.com/oauth/token",
            json={
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
            },
            status=200,
            content_type="application/json",
        )

        # Create and execute the node
        node = OAuth2Node()
        result = node.run(
            token_url="https://example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            grant_type="client_credentials",
        )

        # Verify the result
        assert result["auth_type"] == "oauth2"
        assert "Authorization" in result["headers"]
        assert result["headers"]["Authorization"].startswith("Bearer ")
        assert "token_data" in result
        assert "expires_in" in result
        assert (
            result["token_data"]["access_token"]
            == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        )

        # Token should be cached - verify no new request on second call
        responses.reset()
        result2 = node.run(
            token_url="https://example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            grant_type="client_credentials",
        )

        # Should use cached token
        assert result2["headers"]["Authorization"] == result["headers"]["Authorization"]


# For async nodes, we need to use pytest-asyncio
pytestmark = pytest.mark.asyncio


class TestAsyncNodes:
    """Tests for the asynchronous nodes."""

    async def test_async_http_node(self):
        """Test the AsyncHTTPRequestNode with a mocked response."""
        node = AsyncHTTPRequestNode()

        # Mock the aiohttp ClientSession.request method
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"message": "success"}
        mock_response.url = "https://example.com/api"

        # Create context manager to return mock response
        mock_context = MagicMock()
        mock_context.__aenter__.return_value = mock_response

        # Create mock ClientSession
        mock_session = MagicMock()
        mock_session.request.return_value = mock_context

        # Set up the node with mocked session
        node._session = mock_session

        # Execute the async method
        result = await node.async_run(url="https://example.com/api", method="GET")

        # Verify the result
        assert result["status_code"] == 200
        assert result["success"] is True
        assert result["response"]["content"]["message"] == "success"

        # Verify the session was used correctly
        mock_session.request.assert_called_once()
        call_args = mock_session.request.call_args[1]
        assert call_args["url"] == "https://example.com/api"
        assert call_args["method"] == "GET"
