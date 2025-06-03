"""Enhanced HTTP client nodes with authentication and advanced features.

This module provides an enhanced version of HTTPRequestNode that incorporates
the best features from both the original HTTPRequestNode and HTTPClientNode.
"""

import asyncio
import base64
import time
from enum import Enum
from typing import Any, Dict, Optional

import aiohttp
import requests
from pydantic import BaseModel

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


class HTTPMethod(str, Enum):
    """HTTP methods supported by the HTTPRequestNode."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class ResponseFormat(str, Enum):
    """Response formats supported by the HTTPRequestNode."""

    JSON = "json"
    TEXT = "text"
    BINARY = "binary"
    AUTO = "auto"  # Determine based on Content-Type header


class HTTPResponse(BaseModel):
    """Model for HTTP response data.

    This model provides a consistent structure for HTTP responses
    returned by the HTTPRequestNode.
    """

    status_code: int
    headers: Dict[str, str]
    content_type: Optional[str] = None
    content: Any  # Can be dict, str, bytes depending on response format
    response_time_ms: float
    url: str


@register_node()
class HTTPRequestNode(Node):
    """Enhanced node for making HTTP requests to external APIs.

    This node provides a flexible interface for making HTTP requests with support for:
        * All common HTTP methods (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
        * Multiple authentication methods (Bearer, Basic, API Key, OAuth2)
        * JSON, form, and multipart request bodies
        * Custom headers and query parameters
        * Response parsing (JSON, text, binary)
        * Error handling and retries with recovery suggestions
        * Rate limiting support
        * Request/response logging

    Design Purpose:
        * Enable workflow integration with external HTTP APIs
        * Provide a consistent interface for HTTP operations
        * Support common authentication patterns
        * Handle response parsing and error handling
        * Offer enterprise-grade features like rate limiting

    Upstream Usage:
        * Workflow: Creates and configures node for API integration
        * Specialized API nodes: May extend this node for specific APIs

    Downstream Consumers:
        * Data processing nodes: Consume API response data
        * Decision nodes: Route workflow based on API responses
        * Custom nodes: Process API-specific data formats
    """

    def __init__(self, **kwargs):
        """Initialize the HTTP request node.

        Args:
            url (str): The URL to send the request to
            method (str): HTTP method to use (GET, POST, PUT, etc.)
            headers (dict, optional): HTTP headers to include in the request
            params (dict, optional): Query parameters to include in the URL
            data (dict/str, optional): Request body data (for POST, PUT, etc.)
            json_data (dict, optional): JSON data to send (automatically sets Content-Type)
            response_format (str, optional): Format to parse response as (json, text, binary, auto)
            timeout (int, optional): Request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            auth_type (str, optional): Authentication type (bearer, basic, api_key, oauth2)
            auth_token (str, optional): Authentication token/key
            auth_username (str, optional): Username for basic auth
            auth_password (str, optional): Password for basic auth
            api_key_header (str, optional): Header name for API key auth
            rate_limit_delay (float, optional): Delay between requests for rate limiting
            log_requests (bool, optional): Whether to log request/response details
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.session = requests.Session()

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "url": NodeParameter(
                name="url",
                type=str,
                required=False,
                description="URL to send the request to",
            ),
            "method": NodeParameter(
                name="method",
                type=str,
                required=True,
                default="GET",
                description="HTTP method (GET, POST, PUT, PATCH, DELETE)",
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                default={},
                description="HTTP headers to include in the request",
            ),
            "params": NodeParameter(
                name="params",
                type=dict,
                required=False,
                default={},
                description="Query parameters to include in the URL",
            ),
            "data": NodeParameter(
                name="data",
                type=Any,
                required=False,
                default=None,
                description="Request body data (for POST, PUT, etc.)",
            ),
            "json_data": NodeParameter(
                name="json_data",
                type=dict,
                required=False,
                default=None,
                description="JSON data to send (automatically sets Content-Type)",
            ),
            "response_format": NodeParameter(
                name="response_format",
                type=str,
                required=False,
                default="auto",
                description="Format to parse response as (json, text, binary, auto)",
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
            "rate_limit_delay": NodeParameter(
                name="rate_limit_delay",
                type=float,
                required=False,
                default=0,
                description="Delay between requests to respect rate limits (seconds)",
            ),
            "log_requests": NodeParameter(
                name="log_requests",
                type=bool,
                required=False,
                default=False,
                description="Log request and response details for debugging",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "response": NodeParameter(
                name="response",
                type=dict,
                required=True,
                description="HTTP response data including status, headers, and content",
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
        }

    def _apply_authentication(
        self,
        headers: dict,
        auth_type: Optional[str],
        auth_token: Optional[str],
        auth_username: Optional[str],
        auth_password: Optional[str],
        api_key_header: str,
    ) -> dict:
        """Apply authentication to request headers.

        Args:
            headers: Existing headers dictionary
            auth_type: Type of authentication (bearer, basic, api_key, oauth2)
            auth_token: Token for bearer/api_key/oauth2 authentication
            auth_username: Username for basic authentication
            auth_password: Password for basic authentication
            api_key_header: Header name for API key authentication

        Returns:
            Updated headers dictionary with authentication
        """
        if not auth_type:
            return headers

        auth_headers = headers.copy()

        if auth_type.lower() == "bearer" and auth_token:
            auth_headers["Authorization"] = f"Bearer {auth_token}"

        elif auth_type.lower() == "basic" and auth_username and auth_password:
            credentials = f"{auth_username}:{auth_password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            auth_headers["Authorization"] = f"Basic {encoded}"

        elif auth_type.lower() == "api_key" and auth_token:
            auth_headers[api_key_header] = auth_token

        elif auth_type.lower() == "oauth2" and auth_token:
            auth_headers["Authorization"] = f"Bearer {auth_token}"

        return auth_headers

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute an HTTP request.

        Args:
            url (str): The URL to send the request to
            method (str): HTTP method to use
            headers (dict, optional): HTTP headers
            params (dict, optional): Query parameters
            data (dict/str, optional): Request body data
            json_data (dict, optional): JSON data to send
            response_format (str, optional): Format to parse response as
            timeout (int, optional): Request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            auth_type (str, optional): Authentication type
            auth_token (str, optional): Authentication token
            auth_username (str, optional): Username for basic auth
            auth_password (str, optional): Password for basic auth
            api_key_header (str, optional): Header name for API key
            rate_limit_delay (float, optional): Rate limit delay
            log_requests (bool, optional): Log request/response details

        Returns:
            Dictionary containing:
                response: HTTPResponse object
                status_code: HTTP status code
                success: Boolean indicating request success

        Raises:
            NodeExecutionError: If the request fails or returns an error status
        """
        url = kwargs.get("url")
        if not url:
            raise NodeValidationError("URL parameter is required")
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers", {})
        params = kwargs.get("params", {})
        data = kwargs.get("data")
        json_data = kwargs.get("json_data")
        response_format = kwargs.get("response_format", "auto")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")
        rate_limit_delay = kwargs.get("rate_limit_delay", 0)
        log_requests = kwargs.get("log_requests", False)

        # Apply authentication to headers
        if auth_type:
            headers = self._apply_authentication(
                headers,
                auth_type,
                auth_token,
                auth_username,
                auth_password,
                api_key_header,
            )

        # Validate method
        try:
            method = HTTPMethod(method)
        except ValueError:
            raise NodeValidationError(
                f"Invalid HTTP method: {method}. "
                f"Supported methods: {', '.join([m.value for m in HTTPMethod])}"
            )

        # Validate response format
        try:
            response_format = ResponseFormat(response_format)
        except ValueError:
            raise NodeValidationError(
                f"Invalid response format: {response_format}. "
                f"Supported formats: {', '.join([f.value for f in ResponseFormat])}"
            )

        # Apply rate limit delay if configured
        if rate_limit_delay > 0:
            time.sleep(rate_limit_delay)

        # Prepare request kwargs
        request_kwargs = {
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
            "verify": verify_ssl,
        }

        # Add data or json based on what was provided
        if json_data is not None:
            request_kwargs["json"] = json_data
        elif data is not None:
            request_kwargs["data"] = data

        # Execute request with retries
        if log_requests:
            self.logger.info(f"Request: {method} {url}")
            self.logger.info(f"Headers: {headers}")
            if data or json_data:
                self.logger.info(f"Body: {json_data or data}")
        else:
            self.logger.info(f"Making {method} request to {url}")

        response = None

        for attempt in range(retry_count + 1):
            if attempt > 0:
                wait_time = retry_backoff * (2 ** (attempt - 1))
                self.logger.info(
                    f"Retry attempt {attempt}/{retry_count} after {wait_time:.2f}s"
                )
                time.sleep(wait_time)

            try:
                start_time = time.time()
                response = self.session.request(method=method.value, **request_kwargs)
                response_time = (time.time() - start_time) * 1000  # Convert to ms

                # Log response if enabled
                if log_requests:
                    self.logger.info(f"Response: {response.status_code}")
                    self.logger.info(f"Headers: {dict(response.headers)}")
                    self.logger.info(f"Body: {response.text[:500]}...")

                # Success, break the retry loop
                break

            except requests.RequestException as e:
                self.logger.warning(f"Request failed: {str(e)}")

                # Last attempt, no more retries
                if attempt == retry_count:
                    # Enhanced error response with recovery suggestions
                    return {
                        "response": None,
                        "status_code": None,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "recovery_suggestions": [
                            "Check network connectivity",
                            "Verify URL is correct and accessible",
                            "Check authentication credentials",
                            "Increase timeout or retry settings",
                            "Check API rate limits",
                        ],
                    }

        # Parse response based on format
        content_type = response.headers.get("Content-Type", "")

        if response_format == ResponseFormat.AUTO:
            if "application/json" in content_type:
                response_format = ResponseFormat.JSON
            elif "text/" in content_type:
                response_format = ResponseFormat.TEXT
            else:
                response_format = ResponseFormat.BINARY

        try:
            if response_format == ResponseFormat.JSON:
                content = response.json()
            elif response_format == ResponseFormat.TEXT:
                content = response.text
            elif response_format == ResponseFormat.BINARY:
                content = response.content
            else:
                content = response.text  # Fallback to text
        except Exception as e:
            self.logger.warning(
                f"Failed to parse response as {response_format}: {str(e)}"
            )
            content = response.text  # Fallback to text

        # Create response object
        http_response = HTTPResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            content_type=content_type,
            content=content,
            response_time_ms=response_time,
            url=response.url,
        ).model_dump()

        # Return results
        success = 200 <= response.status_code < 300

        # Add recovery suggestions for error responses
        result = {
            "response": http_response,
            "status_code": response.status_code,
            "success": success,
        }

        if not success:
            result["recovery_suggestions"] = self._get_recovery_suggestions(
                response.status_code
            )

        return result

    def _get_recovery_suggestions(self, status_code: int) -> list:
        """Get recovery suggestions based on status code.

        Args:
            status_code: HTTP status code

        Returns:
            List of recovery suggestions
        """
        if status_code == 401:
            return [
                "Check authentication credentials",
                "Verify API key or token is valid",
                "Ensure authentication method matches API requirements",
            ]
        elif status_code == 403:
            return [
                "Verify you have permission to access this resource",
                "Check API key permissions/scopes",
                "Ensure IP address is whitelisted if required",
            ]
        elif status_code == 404:
            return [
                "Verify the URL path is correct",
                "Check if resource ID exists",
                "Ensure API version in URL is correct",
            ]
        elif status_code == 429:
            return [
                "API rate limit exceeded - wait before retrying",
                "Implement rate limiting in your requests",
                "Check rate limit headers for reset time",
            ]
        elif status_code >= 500:
            return [
                "Server error - retry after a delay",
                "Check API service status page",
                "Contact API support if issue persists",
            ]
        else:
            return [
                "Check API documentation for this status code",
                "Verify request format and parameters",
                "Review response body for error details",
            ]


@register_node()
class AsyncHTTPRequestNode(AsyncNode):
    """Asynchronous enhanced node for making HTTP requests to external APIs.

    This node provides the same functionality as HTTPRequestNode but uses
    asynchronous I/O for better performance, especially for concurrent requests.

    Design Purpose:
    - Enable efficient, non-blocking HTTP operations in workflows
    - Provide the same interface as HTTPRequestNode but with async execution
    - Support high-throughput API integrations with minimal overhead

    Upstream Usage:
    - AsyncLocalRuntime: Executes workflow with async support
    - Specialized async API nodes: May extend this node

    Downstream Consumers:
    - Data processing nodes: Consume API response data
    - Decision nodes: Route workflow based on API responses
    """

    def __init__(self, **kwargs):
        """Initialize the async HTTP request node.

        Args:
            Same as HTTPRequestNode
        """
        super().__init__(**kwargs)
        self._session = None  # Will be created when needed

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        # Same parameters as the synchronous version
        return HTTPRequestNode().get_parameters()

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        # Same output schema as the synchronous version
        return HTTPRequestNode().get_output_schema()

    def _apply_authentication(
        self,
        headers: dict,
        auth_type: Optional[str],
        auth_token: Optional[str],
        auth_username: Optional[str],
        auth_password: Optional[str],
        api_key_header: str,
    ) -> dict:
        """Apply authentication to request headers.

        Args:
            headers: Existing headers dictionary
            auth_type: Type of authentication (bearer, basic, api_key, oauth2)
            auth_token: Token for bearer/api_key/oauth2 authentication
            auth_username: Username for basic authentication
            auth_password: Password for basic authentication
            api_key_header: Header name for API key authentication

        Returns:
            Updated headers dictionary with authentication
        """
        if not auth_type:
            return headers

        auth_headers = headers.copy()

        if auth_type.lower() == "bearer" and auth_token:
            auth_headers["Authorization"] = f"Bearer {auth_token}"

        elif auth_type.lower() == "basic" and auth_username and auth_password:
            credentials = f"{auth_username}:{auth_password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            auth_headers["Authorization"] = f"Basic {encoded}"

        elif auth_type.lower() == "api_key" and auth_token:
            auth_headers[api_key_header] = auth_token

        elif auth_type.lower() == "oauth2" and auth_token:
            auth_headers["Authorization"] = f"Bearer {auth_token}"

        return auth_headers

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous version of the request, for compatibility.

        This is implemented for compatibility but users should use the
        async_run method for better performance.

        Args:
            Same as HTTPRequestNode.run()

        Returns:
            Same as HTTPRequestNode.run()

        Raises:
            NodeExecutionError: If the request fails or returns an error status
        """
        # For compatibility, create a requests.Session() and use it
        http_node = HTTPRequestNode(**self.config)
        return http_node.run(**kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute an HTTP request asynchronously.

        Args:
            Same as HTTPRequestNode.run()

        Returns:
            Same as HTTPRequestNode.run()

        Raises:
            NodeExecutionError: If the request fails or returns an error status
        """
        url = kwargs.get("url")
        if not url:
            raise NodeValidationError("URL parameter is required")
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers", {})
        params = kwargs.get("params", {})
        data = kwargs.get("data")
        json_data = kwargs.get("json_data")
        response_format = kwargs.get("response_format", "auto")
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        auth_type = kwargs.get("auth_type")
        auth_token = kwargs.get("auth_token")
        auth_username = kwargs.get("auth_username")
        auth_password = kwargs.get("auth_password")
        api_key_header = kwargs.get("api_key_header", "X-API-Key")
        rate_limit_delay = kwargs.get("rate_limit_delay", 0)
        log_requests = kwargs.get("log_requests", False)

        # Apply authentication to headers
        if auth_type:
            headers = self._apply_authentication(
                headers,
                auth_type,
                auth_token,
                auth_username,
                auth_password,
                api_key_header,
            )

        # Validate method
        try:
            method = HTTPMethod(method)
        except ValueError:
            raise NodeValidationError(
                f"Invalid HTTP method: {method}. "
                f"Supported methods: {', '.join([m.value for m in HTTPMethod])}"
            )

        # Validate response format
        try:
            response_format = ResponseFormat(response_format)
        except ValueError:
            raise NodeValidationError(
                f"Invalid response format: {response_format}. "
                f"Supported formats: {', '.join([f.value for f in ResponseFormat])}"
            )

        # Apply rate limit delay if configured
        if rate_limit_delay > 0:
            await asyncio.sleep(rate_limit_delay)

        # Create session if needed
        if self._session is None:
            self._session = aiohttp.ClientSession()

        # Prepare request kwargs
        request_kwargs = {
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": aiohttp.ClientTimeout(total=timeout),
            "ssl": verify_ssl,
        }

        # Add data or json based on what was provided
        if json_data is not None:
            request_kwargs["json"] = json_data
        elif data is not None:
            request_kwargs["data"] = data

        # Execute request with retries
        if log_requests:
            self.logger.info(f"Request: {method} {url}")
            self.logger.info(f"Headers: {headers}")
            if data or json_data:
                self.logger.info(f"Body: {json_data or data}")
        else:
            self.logger.info(f"Making async {method} request to {url}")

        response = None

        for attempt in range(retry_count + 1):
            if attempt > 0:
                wait_time = retry_backoff * (2 ** (attempt - 1))
                self.logger.info(
                    f"Retry attempt {attempt}/{retry_count} after {wait_time:.2f}s"
                )
                await asyncio.sleep(wait_time)

            try:
                start_time = time.time()

                async with self._session.request(
                    method=method.value, **request_kwargs
                ) as response:
                    response_time = (time.time() - start_time) * 1000  # Convert to ms

                    # Get content type
                    content_type = response.headers.get("Content-Type", "")

                    # Log response if enabled
                    if log_requests:
                        self.logger.info(f"Response: {response.status}")
                        self.logger.info(f"Headers: {dict(response.headers)}")
                        text_preview = await response.text()
                        self.logger.info(f"Body: {text_preview[:500]}...")

                    # Determine response format
                    actual_format = response_format
                    if actual_format == ResponseFormat.AUTO:
                        if "application/json" in content_type:
                            actual_format = ResponseFormat.JSON
                        elif "text/" in content_type:
                            actual_format = ResponseFormat.TEXT
                        else:
                            actual_format = ResponseFormat.BINARY

                    # Parse response
                    try:
                        if actual_format == ResponseFormat.JSON:
                            content = await response.json()
                        elif actual_format == ResponseFormat.TEXT:
                            content = await response.text()
                        elif actual_format == ResponseFormat.BINARY:
                            content = await response.read()
                        else:
                            content = await response.text()  # Fallback to text
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to parse response as {actual_format}: {str(e)}"
                        )
                        content = await response.text()  # Fallback to text

                    # Create response object
                    http_response = HTTPResponse(
                        status_code=response.status,
                        headers=dict(response.headers),
                        content_type=content_type,
                        content=content,
                        response_time_ms=response_time,
                        url=str(response.url),
                    ).model_dump()

                    # Return results
                    success = 200 <= response.status < 300

                    result = {
                        "response": http_response,
                        "status_code": response.status,
                        "success": success,
                    }

                    if not success:
                        result["recovery_suggestions"] = self._get_recovery_suggestions(
                            response.status
                        )

                    return result

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                self.logger.warning(f"Async request failed: {str(e)}")

                # Last attempt, no more retries
                if attempt == retry_count:
                    # Enhanced error response with recovery suggestions
                    return {
                        "response": None,
                        "status_code": None,
                        "success": False,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "recovery_suggestions": [
                            "Check network connectivity",
                            "Verify URL is correct and accessible",
                            "Check authentication credentials",
                            "Increase timeout or retry settings",
                            "Check API rate limits",
                        ],
                    }

        # Should not reach here, but just in case
        raise NodeExecutionError(
            f"Async HTTP request failed after {retry_count + 1} attempts."
        )

    def _get_recovery_suggestions(self, status_code: int) -> list:
        """Get recovery suggestions based on status code.

        Args:
            status_code: HTTP status code

        Returns:
            List of recovery suggestions
        """
        if status_code == 401:
            return [
                "Check authentication credentials",
                "Verify API key or token is valid",
                "Ensure authentication method matches API requirements",
            ]
        elif status_code == 403:
            return [
                "Verify you have permission to access this resource",
                "Check API key permissions/scopes",
                "Ensure IP address is whitelisted if required",
            ]
        elif status_code == 404:
            return [
                "Verify the URL path is correct",
                "Check if resource ID exists",
                "Ensure API version in URL is correct",
            ]
        elif status_code == 429:
            return [
                "API rate limit exceeded - wait before retrying",
                "Implement rate limiting in your requests",
                "Check rate limit headers for reset time",
            ]
        elif status_code >= 500:
            return [
                "Server error - retry after a delay",
                "Check API service status page",
                "Contact API support if issue persists",
            ]
        else:
            return [
                "Check API documentation for this status code",
                "Verify request format and parameters",
                "Review response body for error details",
            ]

    async def __aenter__(self):
        """Context manager support for 'async with' statements."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up session when exiting context."""
        if self._session is not None:
            await self._session.close()
            self._session = None
