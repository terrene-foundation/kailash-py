"""REST API client nodes for the Kailash SDK.

This module provides specialized nodes for interacting with REST APIs in both
synchronous and asynchronous modes. These nodes build on the base HTTP nodes
to provide a more convenient interface for working with REST APIs.

Key Components:
    * RESTClientNode: Synchronous REST API client
    * AsyncRESTClientNode: Asynchronous REST API client
    * Resource path builders and response handlers
"""

from typing import Any, Dict, List, Optional

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class RESTClientNode(Node):
    """Node for interacting with REST APIs.

    This node provides a higher-level interface for interacting with REST APIs,
    with built-in support for:
        * Resource-based operations (e.g., GET /users/{id})
        * Common REST patterns (list, get, create, update, delete)
        * Pagination handling
        * Response schema validation
        * Error response handling

    Design Purpose:
        * Simplify REST API integration in workflows
        * Provide consistent interfaces for common REST operations
        * Support standard REST conventions and patterns
        * Handle common REST-specific error cases

    Upstream Usage:
        * Workflow: Creates and configures for specific REST APIs
        * API integration workflows: Uses for external service integration

    Downstream Consumers:
        * Data processing nodes: Consume API response data
        * Custom nodes: Process API-specific data formats
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
        self.http_node = HTTPRequestNode(url="")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "base_url": NodeParameter(
                name="base_url",
                type=str,
                required=False,
                description="Base URL for the REST API (e.g., https://api.example.com)",
            ),
            "resource": NodeParameter(
                name="resource",
                type=str,
                required=False,
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
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                required=False,
                default=None,
                description="Authentication type: bearer, basic, api_key, oauth2",
            ),
            "auth_token": NodeParameter(
                name="auth_token",
                type=str,
                required=False,
                default=None,
                description="Authentication token/key for bearer, api_key, or oauth2",
            ),
            "auth_username": NodeParameter(
                name="auth_username",
                type=str,
                required=False,
                default=None,
                description="Username for basic authentication",
            ),
            "auth_password": NodeParameter(
                name="auth_password",
                type=str,
                required=False,
                default=None,
                description="Password for basic authentication",
            ),
            "api_key_header": NodeParameter(
                name="api_key_header",
                type=str,
                required=False,
                default="X-API-Key",
                description="Header name for API key authentication",
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
            * Page-based: ?page=1&per_page=100
            * Offset-based: ?offset=0&limit=100
            * Cursor-based: ?cursor=abc123

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
        # max_pages = pagination_params.get("max_pages", 10)  # TODO: Implement max pages limit

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
            auth_type (str, optional): Authentication type (bearer, basic, api_key, oauth2)
            auth_token (str, optional): Authentication token/key
            auth_username (str, optional): Username for basic auth
            auth_password (str, optional): Password for basic auth
            api_key_header (str, optional): Header name for API key auth

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
        # Authentication parameters
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")

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
            "auth_type": auth_type,
            "auth_token": auth_token,
            "auth_username": auth_username,
            "auth_password": auth_password,
            "api_key_header": api_key_header,
        }

        # Execute the HTTP request
        self.logger.info(f"Making REST {method} request to {url}")
        result = self.http_node.run(**http_params)

        # Extract response data
        response = result.get("response")
        status_code = result.get("status_code")
        success = result.get("success", False)

        # Handle potential error responses
        if not success:
            error_message = result.get("error", "Unknown error")

            # If we have a response object, try to extract error details
            if response and isinstance(response.get("content"), dict):
                # Try to extract error message from common formats
                content = response["content"]
                # Handle case where error is a string or dict
                error_value = content.get("error")
                if isinstance(error_value, dict):
                    error_message = error_value.get("message") or error_message
                elif isinstance(error_value, str):
                    error_message = error_value
                # Check for message at root level
                if not error_message or error_message == result.get(
                    "error", "Unknown error"
                ):
                    error_message = content.get("message") or error_message

            # If we have a status code, include it
            if status_code:
                error_message = f"{error_message} (status: {status_code})"

            self.logger.error(f"REST API error: {error_message}")

            # Return error response with recovery suggestions if available
            error_result = {
                "data": None,
                "status_code": status_code,
                "success": False,
                "error": error_message,
                "error_type": result.get("error_type", "APIError"),
                "metadata": {},
            }

            # Include recovery suggestions if available
            if "recovery_suggestions" in result:
                error_result["recovery_suggestions"] = result["recovery_suggestions"]

            return error_result

            # Note: We don't raise an exception here, as the caller might want
            # to handle error responses normally. Instead, we set success=False
            # and include error details in the response.

        # Handle pagination if requested
        data = response["content"] if response else None
        if paginate and method == "GET" and success:
            try:
                data = self._handle_pagination(data, query_params, pagination_params)
            except Exception as e:
                self.logger.warning(f"Pagination handling failed: {str(e)}")

        # Return processed results
        metadata = {
            "url": url,
            "method": method,
        }

        # Add response metadata if available
        if response:
            metadata["response_time_ms"] = response.get("response_time_ms", 0)
            metadata["headers"] = response.get("headers", {})
            # Extract additional metadata
            metadata.update(self._extract_metadata(response))

        return {
            "data": data,
            "status_code": status_code,
            "success": success,
            "metadata": metadata,
        }

    # Convenience methods for CRUD operations
    def get(
        self, base_url: str, resource: str, resource_id: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """GET a resource or list of resources.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Optional resource ID for single resource retrieval
            **kwargs: Additional parameters (query_params, headers, etc.)

        Returns:
            API response dictionary
        """
        if resource_id:
            # Single resource retrieval
            path_params = kwargs.pop("path_params", {})
            path_params["id"] = resource_id
            resource_path = f"{resource}/{{id}}"
        else:
            # List resources
            resource_path = resource
            path_params = kwargs.pop("path_params", {})

        return self.run(
            base_url=base_url,
            resource=resource_path,
            method="GET",
            path_params=path_params,
            **kwargs,
        )

    def create(
        self, base_url: str, resource: str, data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """CREATE (POST) a new resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            data: Resource data to create
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        return self.run(
            base_url=base_url, resource=resource, method="POST", data=data, **kwargs
        )

    def update(
        self,
        base_url: str,
        resource: str,
        resource_id: str,
        data: Dict[str, Any],
        partial: bool = False,
        **kwargs,
    ) -> Dict[str, Any]:
        """UPDATE (PUT/PATCH) an existing resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Resource ID to update
            data: Updated resource data
            partial: If True, use PATCH for partial update; if False, use PUT
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        path_params = kwargs.pop("path_params", {})
        path_params["id"] = resource_id

        return self.run(
            base_url=base_url,
            resource=f"{resource}/{{id}}",
            method="PATCH" if partial else "PUT",
            path_params=path_params,
            data=data,
            **kwargs,
        )

    def delete(
        self, base_url: str, resource: str, resource_id: str, **kwargs
    ) -> Dict[str, Any]:
        """DELETE a resource.

        Args:
            base_url: Base API URL
            resource: Resource name (e.g., 'users', 'posts')
            resource_id: Resource ID to delete
            **kwargs: Additional parameters (headers, etc.)

        Returns:
            API response dictionary
        """
        path_params = kwargs.pop("path_params", {})
        path_params["id"] = resource_id

        return self.run(
            base_url=base_url,
            resource=f"{resource}/{{id}}",
            method="DELETE",
            path_params=path_params,
            **kwargs,
        )

    def _extract_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract additional metadata from response.

        Args:
            response: HTTP response dictionary

        Returns:
            Dictionary with extracted metadata
        """
        metadata = {}
        headers = response.get("headers", {})

        # Extract rate limit information
        rate_limit = self._extract_rate_limit_metadata(headers)
        if rate_limit:
            metadata["rate_limit"] = rate_limit

        # Extract pagination metadata
        pagination = self._extract_pagination_metadata(
            headers, response.get("content", {})
        )
        if pagination:
            metadata["pagination"] = pagination

        # Extract HATEOAS links
        links = self._extract_links(response.get("content", {}))
        if links:
            metadata["links"] = links

        return metadata

    def _extract_rate_limit_metadata(
        self, headers: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Extract rate limiting information from response headers.

        Args:
            headers: Response headers dictionary

        Returns:
            Rate limit metadata or None if not found
        """
        rate_limit = {}

        # Common rate limit headers
        rate_limit_headers = {
            "X-RateLimit-Limit": "limit",
            "X-RateLimit-Remaining": "remaining",
            "X-RateLimit-Reset": "reset",
            "X-Rate-Limit-Limit": "limit",
            "X-Rate-Limit-Remaining": "remaining",
            "X-Rate-Limit-Reset": "reset",
            "RateLimit-Limit": "limit",
            "RateLimit-Remaining": "remaining",
            "RateLimit-Reset": "reset",
        }

        for header, key in rate_limit_headers.items():
            value = headers.get(header) or headers.get(header.lower())
            if value:
                try:
                    rate_limit[key] = int(value)
                except ValueError:
                    rate_limit[key] = value

        return rate_limit if rate_limit else None

    def _extract_pagination_metadata(
        self, headers: Dict[str, str], content: Any
    ) -> Optional[Dict[str, Any]]:
        """Extract pagination information from headers and response body.

        Args:
            headers: Response headers dictionary
            content: Response body content

        Returns:
            Pagination metadata or None if not found
        """
        pagination = {}

        # Extract from headers (Link header parsing)
        link_header = headers.get("Link") or headers.get("link")
        if link_header:
            links = self._parse_link_header(link_header)
            pagination.update(links)

        # Extract from response body (common patterns)
        if isinstance(content, dict):
            # Look for common pagination fields
            pagination_fields = {
                "page": ["page", "current_page", "pageNumber"],
                "per_page": ["per_page", "page_size", "pageSize", "limit"],
                "total": ["total", "totalCount", "total_count", "totalRecords"],
                "total_pages": ["total_pages", "totalPages", "pageCount"],
                "has_next": ["has_next", "hasNext", "has_more", "hasMore"],
                "has_prev": ["has_prev", "hasPrev", "has_previous", "hasPrevious"],
            }

            for key, fields in pagination_fields.items():
                for field in fields:
                    # Check in root
                    if field in content:
                        pagination[key] = content[field]
                        break
                    # Check in meta/metadata
                    meta = content.get("meta") or content.get("metadata", {})
                    if isinstance(meta, dict) and field in meta:
                        pagination[key] = meta[field]
                        break

        return pagination if pagination else None

    def _parse_link_header(self, link_header: str) -> Dict[str, str]:
        """Parse Link header for pagination URLs.

        Args:
            link_header: Link header value

        Returns:
            Dictionary of rel -> URL mappings
        """
        links = {}

        # Parse Link header format: <url>; rel="next", <url>; rel="prev"
        for link in link_header.split(","):
            link = link.strip()
            if ";" in link:
                url_part, rel_part = link.split(";", 1)
                url = url_part.strip("<>")
                rel_match = rel_part.split("=", 1)
                if len(rel_match) == 2:
                    rel = rel_match[1].strip("\"'")
                    links[rel] = url

        return links

    def _extract_links(self, content: Any) -> Optional[Dict[str, Any]]:
        """Extract HATEOAS links from response content.

        Args:
            content: Response body content

        Returns:
            Links dictionary or None if not found
        """
        if not isinstance(content, dict):
            return None

        links = {}

        # Check common link locations
        link_fields = ["links", "_links", "link", "href"]

        for field in link_fields:
            if field in content:
                link_data = content[field]
                if isinstance(link_data, dict):
                    # HAL format: {"self": {"href": "..."}, "next": {"href": "..."}}
                    for rel, link_obj in link_data.items():
                        if isinstance(link_obj, dict) and "href" in link_obj:
                            links[rel] = link_obj["href"]
                        elif isinstance(link_obj, str):
                            links[rel] = link_obj
                elif isinstance(link_data, list):
                    # Array of link objects
                    for link_obj in link_data:
                        if isinstance(link_obj, dict):
                            rel = link_obj.get("rel", "related")
                            href = link_obj.get("href") or link_obj.get("url")
                            if href:
                                links[rel] = href

        return links if links else None


@register_node()
class AsyncRESTClientNode(AsyncNode):
    """Asynchronous node for interacting with REST APIs.

    This node provides the same functionality as RESTClientNode but uses
    asynchronous I/O for better performance, especially for concurrent requests.

    Design Purpose:
        * Enable efficient, non-blocking REST API operations in workflows
        * Provide the same interface as RESTClientNode but with async execution
        * Support high-throughput API integrations with minimal overhead

    Upstream Usage:
        * AsyncLocalRuntime: Executes workflow with async support
        * Specialized async API nodes: May extend this node

    Downstream Consumers:
        * Data processing nodes: Consume API response data
        * Decision nodes: Route workflow based on API responses
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
        # Authentication parameters
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")

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
            "auth_type": auth_type,
            "auth_token": auth_token,
            "auth_username": auth_username,
            "auth_password": auth_password,
            "api_key_header": api_key_header,
        }

        # Execute the HTTP request asynchronously
        self.logger.info(f"Making async REST {method} request to {url}")
        result = await self.http_node.async_run(**http_params)

        # Extract response data
        response = result.get("response")
        status_code = result.get("status_code")
        success = result.get("success", False)

        # Handle potential error responses
        if not success:
            error_message = result.get("error", "Unknown error")

            # If we have a response object, try to extract error details
            if response and isinstance(response.get("content"), dict):
                # Try to extract error message from common formats
                content = response["content"]
                # Handle case where error is a string or dict
                error_value = content.get("error")
                if isinstance(error_value, dict):
                    error_message = error_value.get("message") or error_message
                elif isinstance(error_value, str):
                    error_message = error_value
                # Check for message at root level
                if not error_message or error_message == result.get(
                    "error", "Unknown error"
                ):
                    error_message = content.get("message") or error_message

            # If we have a status code, include it
            if status_code:
                error_message = f"{error_message} (status: {status_code})"

            self.logger.error(f"REST API error: {error_message}")

            # Return error response with recovery suggestions if available
            error_result = {
                "data": None,
                "status_code": status_code,
                "success": False,
                "error": error_message,
                "error_type": result.get("error_type", "APIError"),
                "metadata": {},
            }

            # Include recovery suggestions if available
            if "recovery_suggestions" in result:
                error_result["recovery_suggestions"] = result["recovery_suggestions"]

            return error_result

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
