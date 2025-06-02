"""GraphQL client nodes for the Kailash SDK.

This module provides specialized nodes for interacting with GraphQL APIs in both
synchronous and asynchronous modes. These nodes provide a higher-level interface
for constructing and executing GraphQL queries.

Key Components:
- GraphQLClientNode: Synchronous GraphQL API client
- AsyncGraphQLClientNode: Asynchronous GraphQL API client
- GraphQL query building and response handling utilities
"""

from typing import Any, Dict, Optional

from kailash.nodes.api.http import AsyncHTTPRequestNode, HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class GraphQLClientNode(Node):
    """Node for interacting with GraphQL APIs.

    This node provides a specialized interface for executing GraphQL queries
    and mutations, with support for:
    - Query and mutation operations
    - Variables and fragments
    - Response selection and formatting
    - Error handling for GraphQL-specific error formats

    Design Purpose:
    - Simplify GraphQL API integration in workflows
    - Abstract away GraphQL-specific protocol details
    - Provide type-safe variable handling
    - Support all GraphQL operations and features

    Upstream Usage:
    - Workflow: Creates and configures for specific GraphQL APIs
    - API integration workflows: Uses for external service integration

    Downstream Consumers:
    - Data processing nodes: Consume API response data
    - Custom nodes: Process API-specific data formats
    """

    def __init__(self, **kwargs):
        """Initialize the GraphQL client node.

        Args:
            endpoint (str): GraphQL endpoint URL
            headers (dict, optional): Default headers for all requests
            auth (dict, optional): Authentication configuration
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
            "endpoint": NodeParameter(
                name="endpoint",
                type=str,
                required=True,
                description="GraphQL endpoint URL",
            ),
            "query": NodeParameter(
                name="query",
                type=str,
                required=True,
                description="GraphQL query or mutation string",
            ),
            "variables": NodeParameter(
                name="variables",
                type=dict,
                required=False,
                default={},
                description="Variables for the GraphQL query",
            ),
            "operation_name": NodeParameter(
                name="operation_name",
                type=str,
                required=False,
                default=None,
                description="Name of the operation to execute (if query contains multiple)",
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                default={},
                description="HTTP headers to include in the request",
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
            "flatten_response": NodeParameter(
                name="flatten_response",
                type=bool,
                required=False,
                default=False,
                description="Whether to flatten the response data structure",
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
                description="GraphQL response data",
            ),
            "errors": NodeParameter(
                name="errors",
                type=list,
                required=False,
                description="GraphQL errors (if any)",
            ),
            "success": NodeParameter(
                name="success",
                type=bool,
                required=True,
                description="Whether the request was successful (no errors)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Additional metadata about the request and response",
            ),
        }

    def _build_graphql_payload(
        self,
        query: str,
        variables: Dict[str, Any] = None,
        operation_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a GraphQL request payload.

        Args:
            query: GraphQL query or mutation string
            variables: Variables for the query
            operation_name: Name of the operation to execute

        Returns:
            Dictionary containing the GraphQL request payload
        """
        payload = {"query": query}

        if variables:
            payload["variables"] = variables

        if operation_name:
            payload["operationName"] = operation_name

        return payload

    def _process_graphql_response(
        self, response: Dict[str, Any], flatten_response: bool = False
    ) -> Dict[str, Any]:
        """Process a GraphQL response.

        Args:
            response: Raw HTTP response from GraphQL API
            flatten_response: Whether to flatten the response data structure

        Returns:
            Processed GraphQL response with data and errors

        Raises:
            NodeExecutionError: If the response has an invalid format
        """
        content = response.get("content", {})

        # Validate GraphQL response format
        if not isinstance(content, dict):
            raise NodeExecutionError(
                f"Invalid GraphQL response format: expected dict, got {type(content).__name__}"
            )

        # Check for transport-level errors (non-200 responses)
        if response.get("status_code", 200) >= 400:
            error_msg = "GraphQL request failed with status code " + str(
                response.get("status_code")
            )
            if isinstance(content, dict) and "errors" not in content:
                # Add transport error to GraphQL error format
                content = {"data": None, "errors": [{"message": error_msg}]}

        # Extract data and errors
        data = content.get("data")
        errors = content.get("errors", [])
        success = response.get("status_code", 200) < 400 and not errors

        # Optional: Flatten data structure
        if flatten_response and data and isinstance(data, dict):
            # Get the first key in data (usually operation name) and return its value
            if len(data) == 1:
                data = next(iter(data.values()))

        return {"data": data, "errors": errors, "success": success}

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute a GraphQL query or mutation.

        Args:
            endpoint (str): GraphQL endpoint URL
            query (str): GraphQL query or mutation string
            variables (dict, optional): Variables for the query
            operation_name (str, optional): Name of the operation to execute
            headers (dict, optional): HTTP headers
            timeout (int, optional): Request timeout in seconds
            verify_ssl (bool, optional): Whether to verify SSL certificates
            retry_count (int, optional): Number of times to retry failed requests
            retry_backoff (float, optional): Backoff factor for retries
            flatten_response (bool, optional): Whether to flatten the response

        Returns:
            Dictionary containing:
                data: GraphQL response data
                errors: List of GraphQL errors (if any)
                success: Boolean indicating request success
                metadata: Additional request/response metadata

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails
        """
        endpoint = kwargs.get("endpoint")
        query = kwargs.get("query")
        variables = kwargs.get("variables", {})
        operation_name = kwargs.get("operation_name")
        headers = kwargs.get("headers", {})
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        flatten_response = kwargs.get("flatten_response", False)

        # Validate required parameters
        if not endpoint:
            raise NodeValidationError("GraphQL endpoint URL is required")

        if not query:
            raise NodeValidationError("GraphQL query is required")

        # Set content type for GraphQL requests
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        # Build GraphQL payload
        payload = self._build_graphql_payload(query, variables, operation_name)

        # Execute HTTP request
        self.logger.info(f"Executing GraphQL request to {endpoint}")
        if variables:
            self.logger.debug(f"With variables: {variables}")

        http_params = {
            "url": endpoint,
            "method": "POST",
            "headers": headers,
            "json_data": payload,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
        }

        http_result = self.http_node.run(**http_params)

        # Process GraphQL-specific response
        response = http_result["response"]
        graphql_result = self._process_graphql_response(response, flatten_response)

        # Construct metadata
        metadata = {
            "endpoint": endpoint,
            "operation_name": operation_name,
            "response_time_ms": response["response_time_ms"],
            "status_code": response["status_code"],
        }

        return {
            "data": graphql_result["data"],
            "errors": graphql_result["errors"],
            "success": graphql_result["success"],
            "metadata": metadata,
        }


@register_node()
class AsyncGraphQLClientNode(AsyncNode):
    """Asynchronous node for interacting with GraphQL APIs.

    This node provides the same functionality as GraphQLClientNode but uses
    asynchronous I/O for better performance, especially for concurrent requests.

    Design Purpose:
    - Enable efficient, non-blocking GraphQL operations in workflows
    - Provide the same interface as GraphQLClientNode but with async execution
    - Support high-throughput API integrations with minimal overhead

    Upstream Usage:
    - AsyncLocalRuntime: Executes workflow with async support
    - Specialized async API nodes: May extend this node

    Downstream Consumers:
    - Data processing nodes: Consume API response data
    - Decision nodes: Route workflow based on API responses
    """

    def __init__(self, **kwargs):
        """Initialize the async GraphQL client node.

        Args:
            Same as GraphQLClientNode
        """
        super().__init__(**kwargs)
        self.http_node = AsyncHTTPRequestNode(**kwargs)
        self.graphql_node = GraphQLClientNode(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        # Same parameters as the synchronous version
        return self.graphql_node.get_parameters()

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        # Same output schema as the synchronous version
        return self.graphql_node.get_output_schema()

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous version of the GraphQL request, for compatibility.

        This is implemented for compatibility but users should use the
        async_run method for better performance.

        Args:
            Same as GraphQLClientNode.run()

        Returns:
            Same as GraphQLClientNode.run()

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails
        """
        # Forward to the synchronous GraphQL node
        return self.graphql_node.run(**kwargs)

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute a GraphQL query or mutation asynchronously.

        Args:
            Same as GraphQLClientNode.run()

        Returns:
            Same as GraphQLClientNode.run()

        Raises:
            NodeValidationError: If required parameters are missing or invalid
            NodeExecutionError: If the request fails
        """
        endpoint = kwargs.get("endpoint")
        query = kwargs.get("query")
        variables = kwargs.get("variables", {})
        operation_name = kwargs.get("operation_name")
        headers = kwargs.get("headers", {})
        timeout = kwargs.get("timeout", 30)
        verify_ssl = kwargs.get("verify_ssl", True)
        retry_count = kwargs.get("retry_count", 0)
        retry_backoff = kwargs.get("retry_backoff", 0.5)
        flatten_response = kwargs.get("flatten_response", False)

        # Validate required parameters
        if not endpoint:
            raise NodeValidationError("GraphQL endpoint URL is required")

        if not query:
            raise NodeValidationError("GraphQL query is required")

        # Set content type for GraphQL requests
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        # Build GraphQL payload
        payload = self.graphql_node._build_graphql_payload(
            query, variables, operation_name
        )

        # Execute HTTP request asynchronously
        self.logger.info(f"Executing async GraphQL request to {endpoint}")
        if variables:
            self.logger.debug(f"With variables: {variables}")

        http_params = {
            "url": endpoint,
            "method": "POST",
            "headers": headers,
            "json_data": payload,
            "response_format": "json",
            "timeout": timeout,
            "verify_ssl": verify_ssl,
            "retry_count": retry_count,
            "retry_backoff": retry_backoff,
        }

        http_result = await self.http_node.async_run(**http_params)

        # Process GraphQL-specific response
        response = http_result["response"]
        graphql_result = self.graphql_node._process_graphql_response(
            response, flatten_response
        )

        # Construct metadata
        metadata = {
            "endpoint": endpoint,
            "operation_name": operation_name,
            "response_time_ms": response["response_time_ms"],
            "status_code": response["status_code"],
        }

        return {
            "data": graphql_result["data"],
            "errors": graphql_result["errors"],
            "success": graphql_result["success"],
            "metadata": metadata,
        }
