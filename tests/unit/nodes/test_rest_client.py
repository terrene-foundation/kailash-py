"""Tests for RESTClient node."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import pytest
from kailash.nodes.api.rest import RESTClientNode
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeValidationError
from kailash.workflow import Workflow


class TestRESTClient(unittest.TestCase):
    """Test cases for RESTClient node."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = RESTClientNode()

    def test_node_parameters(self):
        """Test node parameter definitions."""
        params = self.client.get_parameters()

        # Check parameters exist (all are optional in new implementation)
        self.assertIn("base_url", params)
        self.assertFalse(params["base_url"].required)
        self.assertIn("resource", params)
        self.assertFalse(params["resource"].required)
        self.assertIn("method", params)
        self.assertFalse(params["method"].required)
        self.assertEqual(params["method"].default, "GET")

        # Check optional parameters
        self.assertIn("path_params", params)
        self.assertFalse(params["path_params"].required)
        self.assertIn("data", params)
        self.assertFalse(params["data"].required)
        self.assertIn("version", params)
        self.assertFalse(params["version"].required)

    def test_build_url_simple(self):
        """Test simple resource URL building."""
        url = self.client._build_url("https://api.example.com", "users", {}, None)
        self.assertEqual(url, "https://api.example.com/users")

    def test_build_url_with_path_params(self):
        """Test resource URL with path parameters."""
        url = self.client._build_url(
            "https://api.example.com", "users/{id}", {"id": "123"}, None
        )
        self.assertEqual(url, "https://api.example.com/users/123")

    def test_build_url_with_version(self):
        """Test resource URL with API version."""
        url = self.client._build_url("https://api.example.com", "users", {}, "v2")
        self.assertEqual(url, "https://api.example.com/v2/users")

    def test_build_url_nested(self):
        """Test nested resource URL."""
        url = self.client._build_url(
            "https://api.example.com",
            "posts/{post_id}/comments",
            {"post_id": "456"},
            None,
        )
        self.assertEqual(url, "https://api.example.com/posts/456/comments")

    def test_build_url_cleanup(self):
        """Test URL cleanup (trailing slashes, etc.)."""
        url = self.client._build_url(
            "https://api.example.com/", "/users/{id}", {"id": "123"}, "v1"
        )
        self.assertEqual(url, "https://api.example.com/v1/users/123")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_get_operation(self, mock_http_execute):
        """Test GET operation for single resource."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 200,
            "response": {
                "content": {"id": 123, "name": "Test User"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 500,
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users/{id}",
            path_params={"id": "123"},
            method="GET",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["data"], {"id": 123, "name": "Test User"})

        # Verify HTTP client was called correctly
        mock_http_execute.assert_called_once()
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args["method"], "GET")
        self.assertEqual(call_args["url"], "https://api.example.com/users/123")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_list_operation(self, mock_http_execute):
        """Test LIST operation for collection."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 200,
            "response": {
                "content": [{"id": 1, "name": "User 1"}, {"id": 2, "name": "User 2"}],
                "headers": {
                    "content-type": "application/json",
                    "x-total-count": "50",
                    "x-page": "1",
                    "x-per-page": "2",
                },
                "response_time_ms": 300,
                "url": "https://api.example.com/users",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users",
            method="GET",
            query_params={"status": "active"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(len(result["data"]), 2)
        # Operation is no longer tracked

        # Check metadata - pagination from headers is not extracted by default
        # The REST client would need to be enhanced to extract x- headers
        self.assertIn("headers", result["metadata"])
        # The headers are passed through in metadata
        self.assertEqual(result["metadata"]["headers"]["x-total-count"], "50")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_create_operation(self, mock_http_execute):
        """Test CREATE operation."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 201,
            "response": {
                "content": {"id": 456, "name": "New User", "email": "new@example.com"},
                "headers": {
                    "content-type": "application/json",
                    "location": "https://api.example.com/users/456",
                },
                "response_time_ms": 800,
                "url": "https://api.example.com/users",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users",
            method="POST",
            data={"name": "New User", "email": "new@example.com"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 201)
        self.assertEqual(result["data"]["id"], 456)
        # Location header handling tested separately
        # Message handling tested separately

        # Verify HTTP client was called with POST
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args["method"], "POST")
        self.assertEqual(
            call_args.get("json_data") or call_args.get("data"),
            {"name": "New User", "email": "new@example.com"},
        )

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_update_operation(self, mock_http_execute):
        """Test UPDATE operation (PUT)."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 200,
            "response": {
                "content": {
                    "id": 123,
                    "name": "Updated User",
                    "email": "updated@example.com",
                },
                "headers": {"content-type": "application/json"},
                "response_time_ms": 600,
                "url": "https://api.example.com/users/123",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users/{id}",
            path_params={"id": "123"},
            method="PUT",
            data={"name": "Updated User", "email": "updated@example.com"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["data"]["name"], "Updated User")

        # Verify HTTP client was called with PUT
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args["method"], "PUT")
        self.assertEqual(call_args["url"], "https://api.example.com/users/123")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_patch_operation(self, mock_http_execute):
        """Test PATCH operation."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 200,
            "response": {
                "content": {"id": 123, "status": "inactive"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 400,
                "url": "https://api.example.com/users/123",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users/{id}",
            path_params={"id": "123"},
            method="PATCH",
            data={"status": "inactive"},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 200)
        self.assertEqual(result["data"]["status"], "inactive")

        # Verify HTTP client was called with PATCH
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args["method"], "PATCH")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_delete_operation(self, mock_http_execute):
        """Test DELETE operation."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 204,
            "response": {
                "content": "",
                "headers": {},
                "response_time_ms": 300,
                "url": "https://api.example.com/users/123",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users/{id}",
            path_params={"id": "123"},
            method="DELETE",
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["status_code"], 204)
        # Message handling tested separately
        # Empty string content becomes empty string data
        self.assertEqual(result["data"], "")

        # Verify HTTP client was called with DELETE
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args["method"], "DELETE")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_error_handling_404(self, mock_http_execute):
        """Test 404 error handling."""
        mock_http_execute.return_value = {
            "success": False,
            "status_code": 404,
            "response": {
                "content": {"error": "User not found"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 500,
                "url": "https://api.example.com/users/999",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users/{id}",
            path_params={"id": "999"},
            method="GET",
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 404)
        # RESTClientNode now returns generic error types
        self.assertIn("error", result)

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_error_handling_401(self, mock_http_execute):
        """Test 401 authentication error handling."""
        mock_http_execute.return_value = {
            "success": False,
            "status_code": 401,
            "response": {
                "content": {"error": "Invalid token"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 500,
                "url": "https://api.example.com/users",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com", resource="users", method="GET"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 401)
        self.assertIn("error", result)

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_error_handling_validation(self, mock_http_execute):
        """Test 400 validation error handling."""
        mock_http_execute.return_value = {
            "success": False,
            "status_code": 400,
            "response": {
                "content": {
                    "errors": {
                        "email": ["Invalid email format"],
                        "age": ["Must be positive"],
                    }
                },
                "headers": {"content-type": "application/json"},
                "response_time_ms": 500,
                "url": "https://api.example.com/users",
            },
        }

        result = self.client.execute(
            base_url="https://api.example.com",
            resource="users",
            method="POST",
            data={"email": "invalid", "age": -5},
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["status_code"], 400)
        self.assertIn("error", result)
        # Validation errors are now in the response content

    def test_extract_pagination_metadata_headers(self):
        """Test extraction of pagination from headers (via Link header)."""
        headers = {
            "Link": '<https://api.example.com/users?page=3>; rel="next", <https://api.example.com/users?page=1>; rel="prev"'
        }

        metadata = self.client._extract_pagination_metadata(headers, {})

        # The method extracts pagination URLs from Link header
        self.assertIsNotNone(metadata)
        self.assertIn("next", metadata)
        self.assertIn("prev", metadata)
        self.assertEqual(metadata["next"], "https://api.example.com/users?page=3")
        self.assertEqual(metadata["prev"], "https://api.example.com/users?page=1")

    def test_extract_pagination_metadata_body(self):
        """Test extraction of pagination from response body."""
        body = {
            "data": [],
            "total": 50,
            "page": 1,
            "per_page": 10,
        }

        metadata = self.client._extract_pagination_metadata({}, body)

        # The method extracts pagination data from the body
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["total"], 50)
        self.assertEqual(metadata["page"], 1)
        # The method doesn't extract URLs from the body links structure

    def test_extract_rate_limit_metadata(self):
        """Test extraction of rate limit information."""
        headers = {
            "x-ratelimit-limit": "1000",
            "x-ratelimit-remaining": "999",
            "x-ratelimit-reset": "1234567890",
            "retry-after": "60",
        }

        metadata = self.client._extract_rate_limit_metadata(headers)

        self.assertEqual(metadata["limit"], 1000)
        self.assertEqual(metadata["remaining"], 999)
        self.assertEqual(metadata["reset"], 1234567890)
        # retry-after is a separate header, not part of rate limit metadata

    def test_extract_hateoas_links(self):
        """Test extraction of HATEOAS links."""
        body = {
            "id": 123,
            "name": "Test",
            "_links": {
                "self": {"href": "/api/users/123"},
                "posts": {"href": "/api/users/123/posts"},
                "avatar": {"href": "/api/users/123/avatar"},
            },
        }

        links = self.client._extract_links(body)

        self.assertEqual(links["self"], "/api/users/123")
        self.assertEqual(links["posts"], "/api/users/123/posts")
        self.assertEqual(links["avatar"], "/api/users/123/avatar")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_authentication_passthrough(self, mock_http_execute):
        """Test authentication parameters are passed through."""
        mock_http_execute.return_value = {
            "success": True,
            "status_code": 200,
            "body": {"authenticated": True},
            "headers": {},
        }

        self.client.execute(
            base_url="https://api.example.com",
            resource="protected",
            method="GET",
            auth_type="bearer",
            auth_token="secret-token",
        )

        # Verify auth params were passed to HTTPRequestNode
        call_args = mock_http_execute.call_args[1]
        self.assertEqual(call_args.get("auth_type"), "bearer")
        self.assertEqual(call_args.get("auth_token"), "secret-token")

    @patch("kailash.nodes.api.http.HTTPRequestNode.execute")
    def test_invalid_operation(self, mock_http_execute):
        """Test error handling for invalid operations."""
        # Mock the HTTP node returning an error for invalid method
        mock_http_execute.side_effect = NodeValidationError(
            "Invalid HTTP method: INVALID_METHOD. Supported methods: GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS"
        )

        # Test with an invalid method - this should raise an exception
        with self.assertRaises(NodeValidationError):
            self.client.execute(
                base_url="https://api.example.com",
                resource="users",
                method="INVALID_METHOD",
            )


# Async tests for 070-upgrade-components
class TestRESTClientAsyncUpgrade:
    """Test async upgrades for RESTClientNode (070-upgrade-components)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = RESTClientNode(name="rest_client_async")

    @pytest.mark.asyncio
    async def test_rest_client_async_run_exists(self):
        """Test that RESTClientNode has async_run method."""
        assert hasattr(
            self.client, "async_run"
        ), "RESTClientNode missing async_run method"

    @pytest.mark.asyncio
    async def test_rest_client_async_get_request(self):
        """Test async GET request execution."""
        # Mock the AsyncHTTPRequestNode that RESTClientNode uses internally
        with patch("kailash.nodes.api.http.AsyncHTTPRequestNode") as mock_async_http:
            mock_instance = AsyncMock()
            mock_async_http.return_value = mock_instance

            # Mock async_run return value (match AsyncHTTPRequestNode response format)
            mock_instance.async_run.return_value = {
                "success": True,
                "status_code": 200,
                "content": {"id": 123, "name": "Test User"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 150,
                "url": "https://api.example.com/users/123",
            }

            # Execute async_run
            result = await self.client.async_run(
                base_url="https://api.example.com",
                resource="users/{id}",
                path_params={"id": "123"},
                method="GET",
            )

            # Verify results
            assert result["success"] is True
            assert result["status_code"] == 200
            assert result["data"] == {"id": 123, "name": "Test User"}

            # Verify async HTTP was called
            mock_instance.async_run.assert_called_once()
            call_args = mock_instance.async_run.call_args[1]
            assert call_args["method"] == "GET"
            assert call_args["url"] == "https://api.example.com/users/123"

    @pytest.mark.asyncio
    async def test_rest_client_async_runtime_integration(self):
        """Test RESTClientNode with LocalRuntime async detection."""
        # Mock the HTTP request (RESTClientNode uses HTTPRequestNode, not AsyncHTTPRequestNode)
        with patch("kailash.nodes.api.rest.HTTPRequestNode") as mock_http:
            mock_instance = Mock()  # Use Mock, not AsyncMock for sync method
            mock_http.return_value = mock_instance

            mock_instance.execute.return_value = {
                "success": True,
                "status_code": 200,
                "response": {
                    "content": [
                        {"id": 1, "name": "User 1"},
                        {"id": 2, "name": "User 2"},
                    ],
                    "headers": {"content-type": "application/json"},
                    "response_time_ms": 300,
                    "url": "https://api.example.com/users",
                },
            }

            # Create workflow with REST client (after patching)
            workflow = Workflow(workflow_id="rest_async_test", name="REST Async Test")
            rest_client = RESTClientNode(name="client")
            workflow.add_node("client", rest_client)

            # Test with async-enabled runtime
            runtime = LocalRuntime(enable_async=True, debug=True)

            # Use execute_async which returns a tuple (results, run_id)
            results, run_id = await runtime.execute_async(
                workflow,
                parameters={
                    "client": {
                        "base_url": "https://api.example.com",
                        "resource": "users",
                        "method": "GET",
                    }
                },
            )

            # Verify results
            assert "client" in results
            assert results["client"]["success"] is True
            assert len(results["client"]["data"]) == 2
            assert results["client"]["data"][0]["name"] == "User 1"

    @pytest.mark.asyncio
    async def test_rest_client_async_graceful_fallback(self):
        """Test graceful fallback when network request fails."""
        # Mock the async HTTP request to simulate network failure that should still return success=False gracefully
        with patch("kailash.nodes.api.http.AsyncHTTPRequestNode") as mock_async_http:
            mock_instance = AsyncMock()
            mock_async_http.return_value = mock_instance

            # Mock network failure with graceful error response
            mock_instance.async_run.return_value = {
                "success": False,
                "status_code": 0,
                "error": "Cannot connect to host api.example.com:443 ssl:default [nodename nor servname provided, or not known]",
                "content": None,
                "headers": {},
                "response_time_ms": 0,
                "url": "https://api.example.com/test",
            }

            result = await self.client.async_run(
                base_url="https://api.example.com", resource="test", method="GET"
            )

            # Should handle network failure gracefully
            assert result["success"] is False
            assert result["status_code"] == 0
            assert result["data"] is None
            mock_instance.async_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_rest_client_async_run_exists(self):
        """Test that RESTClientNode has async_run method (from 070-upgrade-components)."""
        client = RESTClientNode(name="rest_client_async")
        assert hasattr(client, "async_run"), "RESTClientNode missing async_run method"

    @pytest.mark.asyncio
    async def test_rest_client_async_fallback(self):
        """Test async execution with proper mocking (from 070-upgrade-components)."""
        client = RESTClientNode(name="rest_client_async")

        # Mock the AsyncHTTPRequestNode that RESTClientNode uses internally
        from unittest.mock import AsyncMock

        with patch("kailash.nodes.api.http.AsyncHTTPRequestNode") as mock_async_http:
            mock_instance = AsyncMock()
            mock_async_http.return_value = mock_instance

            # Mock successful async HTTP response
            mock_instance.async_run.return_value = {
                "success": True,
                "status_code": 200,
                "content": {"test": "async works"},
                "headers": {"content-type": "application/json"},
                "response_time_ms": 100,
                "url": "https://api.example.com/test",
            }

            # Execute async_run
            result = await client.async_run(
                base_url="https://api.example.com", resource="test", method="GET"
            )

            # Verify results
            assert result["success"] is True
            assert result["status_code"] == 200
            assert result["data"]["test"] == "async works"

            # Verify async HTTP was called
            mock_instance.async_run.assert_called_once()
