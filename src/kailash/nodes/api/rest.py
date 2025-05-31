"""REST API client nodes for the Kailash SDK.

This module provides specialized nodes for interacting with REST APIs in both
synchronous and asynchronous modes. These nodes build on the base HTTP nodes
to provide a more convenient interface for working with REST APIs.

Key Components:
- RESTClientNode: Synchronous REST API client
- AsyncRESTClientNode: Asynchronous REST API client
- Resource path builders and response handlers
"""

from typing import Any, Dict, List, Optional

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node(alias="RESTClient")
class RESTClientNode(Node):
    """Node for interacting with REST APIs.

    This node provides a higher-level interface for interacting with REST APIs,
    with built-in support for:
    - Resource-based operations (e.g., GET /users/{id})
    - Common REST patterns (list, get, create, update, delete)
    - Pagination handling
    - Response schema validation
    - Error response handling

    Design Purpose:
    - Simplify REST API integration in workflows
    - Provide consistent interfaces for common REST operations
    - Support standard REST conventions and patterns
    - Handle common REST-specific error cases

    Upstream Usage:
    - Workflow: Creates and configures for specific REST APIs
    - API integration workflows: Uses for external service integration

    Downstream Consumers:
    - Data processing nodes: Consume API response data
    - Custom nodes: Process API-specific data formats
    """

    def __init__(self, **kwargs):
        """Initialize the REST client node.

        Args:
            base_url (str): Base URL for the REST API
            headers (dict, optional): Default headers for all requests
            auth (dict, optional): Authentication configuration
            version (str, optional): API version to use
            timeout (int, optional): Default request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.http_node = HTTPRequestNode(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "base_url": NodeParameter(
                name="base_url",
                type=str,
                required=True,
                description="Base URL for the REST API (e.g., https://api.example.com)",
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=True,
                description="API resource path (e.g., 'users' or 'products/{id}')",
            ),
            "method": NodeParameter(
                name="method",
                type=str,
                required=False,
                default="GET",
                description="HTTP method (GET, POST, PUT, PATCH, DELETE)",
            ),
            "path_params": NodeParameter(
                name="path_params",
                type=dict,
                required=False,
                default={},
                description="Parameters to substitute in resource path (e.g., {'id': 123})",
            ),
            "query_params": NodeParameter(
                name="query_params",
                type=dict,
                required=False,
                default={},
                description="Query parameters to include in the URL",
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                default={},
                description="HTTP headers to include in the request",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                default=None,
                description="Request body data (for POST, PUT, etc.)",
            ),
            "version": NodeParameter(
                name="version",
                type=str,
                required=False,
                default=None,
                description="API version to use (e.g., 'v1')",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                default=30,
                description="Request timeout in seconds",
            ),
            "verify_ssl": NodeParameter(
                name="verify_ssl",
                type=bool,
                required=False,
                default=True,
                description="Whether to verify SSL certificates",
            ),
            "paginate": NodeParameter(
                name="paginate",
                type=bool,
                required=False,
                default=False,
                description="Whether to handle pagination automatically (for GET requests)",
            ),
            "pagination_params": NodeParameter(
                name="pagination_params",
                type=dict,
                required=False,
                default=None,
                description="Pagination configuration parameters",
            ),
            "retry_count": NodeParameter(
                name="retry_count",
                type=int,
                required=False,
                default=0,
                description="Number of times to retry failed requests",
            ),
            "retry_backoff": NodeParameter(
                name="retry_backoff",
                type=float,
                required=False,
                default=0.5,
                description="Backoff factor for retries",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "data": NodeParameter(
                name="data",
                type=Any,
                required=True,
                description="Parsed response data from the API",
            ),
            "status_code": NodeParameter(
                name="status_code",
                type=int,
                required=True,
                description="HTTP status code",
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=True,
                description="Whether the request was successful (status code 200-299)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Additional metadata about the request and response",
            ),
        }

    def _build_url(
        self,
        base_url: str,
        resource: str,
        path_params: Dict[str, Any],
        version: Optional[str] = None,
    ) -> str:
        """Build the full URL for a REST API request.

        Args:
            base_url: Base API URL
            resource: Resource path pattern
            path_params: Parameters to substitute in the path
            version: API version to include in the URL

        Returns:
            Complete URL with path parameters substituted

        Raises:
            NodeValidationError: If a required path parameter is missing
        """
        # Remove trailing slash from base URL if present
        base_url = base_url.rstrip("/")

        # Add version to URL if specified
        if version:
            base_url = f"{base_url}/{version}"

        # Substitute path parameters
        try:
            # Extract required path parameters from the resource pattern
            required_params = [
                param.strip("{}")
                for param in resource.split("/")
                if param.startswith("{") and param.endswith("}")
            ]

            # Check if all required parameters are provided
            for param in required_params:
                if param not in path_params:
                    raise NodeValidationError(
                        f"Missing required path parameter '{param}' for resource '{resource}'"
                    )

            # Substitute parameters in the resource path
            resource_path = resource
            for param, value in path_params.items():
                placeholder = f"{{{param}}}"
                if placeholder in resource_path:
                    resource_path = resource_path.replace(placeholder, str(value))

            # Ensure path starts without a slash
            resource_path = resource_path.lstrip("/")

            # Build complete URL
            return f"{base_url}/{resource_path}"

        except Exception as e:
            if not isinstance(e, NodeValidationError):
                raise NodeValidationError(f"Failed to build URL: {str(e)}") from e
            raise

    def _handle_pagination(
        self,
        initial_response: Dict[str, Any],
        query_params: Dict[str, Any],
        pagination_params: Dict[str, Any],
    ) -> List[Any]:
        """Handle pagination for REST API responses.

        This method supports common pagination patterns:
        - Page-based: ?page=1&per_page=100
        - Offset-based: ?offset=0&limit=100
        - Cursor-based: ?cursor=abc123

        Args:
            initial_response: Response from the first API call
            query_params: Original query parameters
            pagination_params: Configuration for pagination handling

        Returns:
            Combined list of items from all pages

        Raises:
            NodeExecutionError: If pagination fails
        """
        if not pagination_params:
            # Default pagination configuration
            pagination_params = {
                "type": "page",  # page, offset, or cursor
                "page_param": "page",  # query parameter for page number
                "limit_param": "per_page",  # query parameter for items per page
                "items_path": "data",  # path to items in response
                "total_path": "meta.total",  # path to total count in response
                "next_page_path": "meta.next_page",  # path to next page in response
                "max_pages": 10,  # maximum number of pages to fetch
            }

        pagination_type = pagination_params.get("type", "page")
        items_path = pagination_params.get("items_path", "data")
        max_pages = pagination_params.get("max_pages", 10)

        # Extract items from initial response
        all_items = self._get_nested_value(initial_response, items_path, [])
        if not isinstance(all_items, list):
            raise NodeExecutionError(
                f"Pagination items path '{items_path}' did not return a list in response"
            )

        # Return immediately if no additional pages
        if pagination_type == "page":
            current_page = int(
                query_params.get(pagination_params.get("page_param", "page"), 1)
            )
            total_path = pagination_params.get("total_path")
            per_page = int(
                query_params.get(pagination_params.get("limit_param", "per_page"), 20)
            )

            # If we have total info, check if more pages exist
            if total_path:
                total_items = self._get_nested_value(initial_response, total_path, 0)
                if not total_items or current_page * per_page >= total_items:
                    return all_items

        elif pagination_type == "cursor":
            next_cursor_path = pagination_params.get("next_page_path", "meta.next")
            next_cursor = self._get_nested_value(initial_response, next_cursor_path)
            if not next_cursor:
                return all_items

        # TODO: Implement actual pagination fetching for different types
        # This would involve making additional HTTP requests to fetch subsequent pages
        # and combining the results, but for brevity we're omitting the implementation

        self.logger.warning("Pagination is not fully implemented in this example")
        return all_items

    def _get_nested_value(
        self, obj: Dict[str, Any], path: str, default: Any = None
    ) -> Any:
        """Get a nested value from a dictionary using a dot-separated path.

        Args:
            obj: Dictionary to extract value from
            path: Dot-separated path to the value (e.g., "meta.pagination.next")
            default: Value to return if path doesn't exist

        Returns:
            Value at the specified path or default if not found
        """
        if not path:
            return obj

        parts = path.split(".")
        current = obj

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute a REST API request.

        Args:
            base_url (str): Base URL for the REST API
            resource (str): API resource path template
            method (str, optional): HTTP method to use
            path_params (dict, optional): Path parameters to substitute
            query_params (dict, optional): Query parameters
            headers (dict, optional): HTTP headers
            data (dict/str, optional): Request body data
            version (str, optional): API version
            timeout (int, optional): Request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            paginate (bool, optional): Whether to handle pagination
            pagination_params (dict, optional): Pagination configuration
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries

        Returns:
            Dictionary containing:
                data: Parsed response data
                status_code: HTTP status code
                success: Boolean indicating request success
                metadata: Additional request/response metadata

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails or returns an error status
        """
        base_url = kwargs.get("base_url")
        resource = kwargs.get("resource")
        method = kwargs.get("method", "GET").upper()
        path_params = kwargs.get("path_params", {})
        query_params = kwargs.get("query_params", {})
        headers = kwargs.get("headers", {})
        data = kwargs.get("data")
        version = kwargs.get("version")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        paginate = kwargs.get("paginate", False)
        pagination_params = kwargs.get("pagination_params")
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)

        # Build full URL with path parameters
        url = self._build_url(base_url, resource, path_params, version)

        # Set default Content-Type header for requests with body
        if (
            method in ("POST", "PUT", "PATCH")
            and data
            and "Content-Type" not in headers
        ):
            headers["Content-Type"] = "application/json"

        # Accept JSON responses by default
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Build HTTP request parameters
        http_params = {
            "url": url,
            "method": method,
            "headers": headers,
            "params": query_params,
            "json_data": data if isinstance(data, dict) else None,
            "data": data if not isinstance(data, dict) else None,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
        }

        # Execute the HTTP request
        self.logger.info(f"Making REST {method} request to {url}")
        result = self.http_node.run(**http_params)

        # Extract response data
        response = result["response"]
        status_code = result["status_code"]
        success = result["success"]

        # Handle potential error responses
        if not success:
            error_message = "Unknown error"
            if isinstance(response["content"], dict):
                # Try to extract error message from common formats
                error_message = (
                    response["content"].get("error", {}).get("message")
                    or response["content"].get("message")
                    or response["content"].get("error")
                    or f"API returned error status: {status_code}"
                )

            self.logger.error(f"REST API error: {error_message}")

            # Note: We don't raise an exception here, as the caller might want
            # to handle error responses normally. Instead, we set success=False
            # and include error details in the response.

        # Handle pagination if requested
        data = response["content"]
        if paginate and method == "GET" and success:
            try:
                data = self._handle_pagination(data, query_params, pagination_params)
            except Exception as e:
                self.logger.warning(f"Pagination handling failed: {str(e)}")

        # Return processed results
        metadata = {
            "url": url,
            "method": method,
            "response_time_ms": response["response_time_ms"],
            "headers": response["headers"],
        }

        return {
            "data": data,
            "status_code": status_code,
            "success": success,
            "metadata": metadata,
        }


@register_node(alias="AsyncRESTClient")
class AsyncRESTClientNode(AsyncNode):
    """Asynchronous node for interacting with REST APIs.

    This node provides the same functionality as RESTClientNode but uses
    asynchronous I/O for better performance, especially for concurrent requests.

    Design Purpose:
    - Enable efficient, non-blocking REST API operations in workflows
    - Provide the same interface as RESTClientNode but with async execution
    - Support high-throughput API integrations with minimal overhead

    Upstream Usage:
    - AsyncLocalRuntime: Executes workflow with async support
    - Specialized async API nodes: May extend this node

    Downstream Consumers:
    - Data processing nodes: Consume API response data
    - Decision nodes: Route workflow based on API responses
    """

    def __init__(self, **kwargs):
        """Initialize the async REST client node.

        Args:
            Same as RESTClientNode
        """
        super().__init__(**kwargs)
        self.http_node = AsyncHTTPRequestNode(**kwargs)
        self.rest_node = RESTClientNode(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        # Same parameters as the synchronous version
        return self.rest_node.get_parameters()

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        # Same output schema as the synchronous version
        return self.rest_node.get_output_schema()

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous version of the REST request, for compatibility.

        This is implemented for compatibility but users should use the
        async_run method for better performance.

        Args:
            Same as RESTClientNode.run()

        Returns:
            Same as RESTClientNode.run()

        Raises:
            NodeExecutionError: If the request fails or returns an error status
        """
        # Forward to the synchronous REST node
        return self.rest_node.run(**kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute a REST API request asynchronously.

        Args:
            Same as RESTClientNode.run()

        Returns:
            Same as RESTClientNode.run()

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails or returns an error status
        """
        base_url = kwargs.get("base_url")
        resource = kwargs.get("resource")
        method = kwargs.get("method", "GET").upper()
        path_params = kwargs.get("path_params", {})
        query_params = kwargs.get("query_params", {})
        headers = kwargs.get("headers", {})
        data = kwargs.get("data")
        version = kwargs.get("version")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        paginate = kwargs.get("paginate", False)
        pagination_params = kwargs.get("pagination_params")
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)

        # Build full URL with path parameters (reuse from synchronous version)
        url = self.rest_node._build_url(base_url, resource, path_params, version)

        # Set default Content-Type header for requests with body
        if (
            method in ("POST", "PUT", "PATCH")
            and data
            and "Content-Type" not in headers
        ):
            headers["Content-Type"] = "application/json"

        # Accept JSON responses by default
        if "Accept" not in headers:
            headers["Accept"] = "application/json"

        # Build HTTP request parameters
        http_params = {
            "url": url,
            "method": method,
            "headers": headers,
            "params": query_params,
            "json_data": data if isinstance(data, dict) else None,
            "data": data if not isinstance(data, dict) else None,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
        }

        # Execute the HTTP request asynchronously
        self.logger.info(f"Making async REST {method} request to {url}")
        result = await self.http_node.async_run(**http_params)

        # Extract response data
        response = result["response"]
        status_code = result["status_code"]
        success = result["success"]

        # Handle potential error responses
        if not success:
            error_message = "Unknown error"
            if isinstance(response["content"], dict):
                # Try to extract error message from common formats
                error_message = (
                    response["content"].get("error", {}).get("message")
                    or response["content"].get("message")
                    or response["content"].get("error")
                    or f"API returned error status: {status_code}"
                )

            self.logger.error(f"REST API error: {error_message}")

        # Handle pagination if requested (simplified for now)
        data = response["content"]
        if paginate and method == "GET" and success:
            try:
                data = self.rest_node._handle_pagination(
                    data, query_params, pagination_params
                )
            except Exception as e:
                self.logger.warning(f"Pagination handling failed: {str(e)}")

        # Return processed results
        metadata = {
            "url": url,
            "method": method,
            "response_time_ms": response["response_time_ms"],
            "headers": response["headers"],
        }

        return {
            "data": data,
            "status_code": status_code,
            "success": success,
            "metadata": metadata,
        }
