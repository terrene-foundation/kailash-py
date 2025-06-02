"""Authentication nodes for API requests in the Kailash SDK.

This module provides nodes for handling various authentication methods for API
requests. These nodes can be used in workflows to authenticate requests to
external services.

Key Components:
- BasicAuthNode: Basic authentication (username/password)
- OAuth2Node: OAuth 2.0 authentication flow
- APIKeyNode: API key authentication
"""

import base64
import time
from typing import Any, Dict

import requests

from kailash.nodes.api.http import HTTPRequestNode
from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class BasicAuthNode(Node):
    """Node for adding Basic Authentication to API requests.

    This node generates HTTP headers for Basic Authentication and can be used
    to authenticate requests to APIs that support this method.

    Design Purpose:
    - Provide a simple way to add Basic Auth to API requests
    - Abstract away the encoding details
    - Support secure credential handling

    Upstream Usage:
    - Workflow: Creates and configures with API credentials
    - HTTP/REST nodes: Consume the auth headers

    Downstream Consumers:
    - HTTPRequestNode: Uses auth headers for requests
    - RESTClientNode: Uses auth headers for API calls
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "username": NodeParameter(
                name="username",
                type=str,
                required=True,
                description="Username for Basic Authentication",
            ),
            "password": NodeParameter(
                name="password",
                type=str,
                required=True,
                description="Password for Basic Authentication",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=True,
                description="HTTP headers with Basic Authentication",
            ),
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                required=True,
                description="Authentication type (always 'basic')",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Generate Basic Authentication headers.

        Args:
            username (str): Username for authentication
            password (str): Password for authentication

        Returns:
            Dictionary containing:
                headers: HTTP headers with Basic Authentication
                auth_type: Authentication type ('basic')
        """
        username = kwargs.get("username")
        password = kwargs.get("password")

        # Validate required parameters
        if not username:
            raise NodeValidationError("Username is required for Basic Authentication")

        if not password:
            raise NodeValidationError("Password is required for Basic Authentication")

        # Generate auth string
        auth_string = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()

        # Create headers
        headers = {"Authorization": f"Basic {encoded_auth}"}

        return {"headers": headers, "auth_type": "basic"}


@register_node()
class OAuth2Node(Node):
    """Node for handling OAuth 2.0 authentication flows.

    This node supports various OAuth 2.0 flows including:
    - Client Credentials
    - Password Grant
    - Authorization Code (with PKCE)
    - Refresh Token

    It handles token acquisition, storage, and renewal for API requests.

    Design Purpose:
    - Simplify OAuth 2.0 authentication for API requests
    - Handle token lifecycle (request, store, refresh)
    - Support multiple OAuth flows
    - Abstract away OAuth implementation details

    Upstream Usage:
    - Workflow: Creates and configures with OAuth credentials
    - HTTP/REST nodes: Consume the auth headers

    Downstream Consumers:
    - HTTPRequestNode: Uses auth headers for requests
    - RESTClientNode: Uses auth headers for API calls
    """

    def __init__(self, **kwargs):
        """Initialize the OAuth2 node.

        Args:
            token_url (str): OAuth token endpoint URL
            client_id (str): OAuth client ID
            client_secret (str, optional): OAuth client secret
            grant_type (str): OAuth grant type
            scope (str, optional): OAuth scopes (space-separated)
            username (str, optional): Username for password grant
            password (str, optional): Password for password grant
            refresh_token (str, optional): Refresh token for refresh flow
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.http_node = HTTPRequestNode(**kwargs)
        self.token_data = None  # Will store token information
        self.token_expires_at = 0  # Timestamp when token expires

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "token_url": NodeParameter(
                name="token_url",
                type=str,
                required=True,
                description="OAuth token endpoint URL",
            ),
            "client_id": NodeParameter(
                name="client_id", type=str, required=True, description="OAuth client ID"
            ),
            "client_secret": NodeParameter(
                name="client_secret",
                type=str,
                required=False,
                default=None,
                description="OAuth client secret",
            ),
            "grant_type": NodeParameter(
                name="grant_type",
                type=str,
                required=True,
                default="client_credentials",
                description="OAuth grant type (client_credentials, password, authorization_code, refresh_token)",
            ),
            "scope": NodeParameter(
                name="scope",
                type=str,
                required=False,
                default=None,
                description="OAuth scopes (space-separated)",
            ),
            "username": NodeParameter(
                name="username",
                type=str,
                required=False,
                default=None,
                description="Username (for password grant)",
            ),
            "password": NodeParameter(
                name="password",
                type=str,
                required=False,
                default=None,
                description="Password (for password grant)",
            ),
            "refresh_token": NodeParameter(
                name="refresh_token",
                type=str,
                required=False,
                default=None,
                description="Refresh token (for refresh_token grant)",
            ),
            "token_storage": NodeParameter(
                name="token_storage",
                type=dict,
                required=False,
                default=None,
                description="Token storage configuration",
            ),
            "auto_refresh": NodeParameter(
                name="auto_refresh",
                type=bool,
                required=False,
                default=True,
                description="Whether to automatically refresh expired tokens",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=True,
                description="HTTP headers with OAuth token",
            ),
            "token_data": NodeParameter(
                name="token_data",
                type=dict,
                required=True,
                description="Complete token response data",
            ),
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                required=True,
                description="Authentication type (always 'oauth2')",
            ),
            "expires_in": NodeParameter(
                name="expires_in",
                type=int,
                required=False,
                description="Seconds until token expiration",
            ),
        }

    def _get_token(self, **kwargs) -> Dict[str, Any]:
        """Get an OAuth token using the configured grant type.

        This method handles different grant types with appropriate parameters.

        Args:
            kwargs: Parameters from run method

        Returns:
            Dictionary containing token response data

        Raises:
            NodeExecutionError: If token acquisition fails
        """
        token_url = kwargs.get("token_url")
        client_id = kwargs.get("client_id")
        client_secret = kwargs.get("client_secret")
        grant_type = kwargs.get("grant_type", "client_credentials")
        scope = kwargs.get("scope")
        username = kwargs.get("username")
        password = kwargs.get("password")
        refresh_token = (
            kwargs.get("refresh_token")
            or self.token_data
            and self.token_data.get("refresh_token")
        )

        # Build request data based on grant type
        data = {"grant_type": grant_type, "client_id": client_id}

        if client_secret:
            data["client_secret"] = client_secret

        if scope:
            data["scope"] = scope

        # Add grant-specific parameters
        if grant_type == "password":
            if not username or not password:
                raise NodeValidationError(
                    "Username and password are required for password grant type"
                )
            data["username"] = username
            data["password"] = password

        elif grant_type == "refresh_token":
            if not refresh_token:
                raise NodeValidationError(
                    "Refresh token is required for refresh_token grant type"
                )
            data["refresh_token"] = refresh_token

        # Make token request
        self.logger.info(
            f"Requesting OAuth token from {token_url} using {grant_type} grant"
        )

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        # Some OAuth servers require Basic auth with client credentials
        if client_id and client_secret:
            auth_string = f"{client_id}:{client_secret}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()
            headers["Authorization"] = f"Basic {encoded_auth}"

            # Remove from form body if using auth header
            if "client_secret" in data:
                del data["client_secret"]

        try:
            response = requests.post(token_url, data=data, headers=headers, timeout=30)

            response.raise_for_status()
            token_data = response.json()

            # Check for required fields in response
            if "access_token" not in token_data:
                raise NodeExecutionError(
                    f"Invalid OAuth response: missing access_token. Response: {token_data}"
                )

            return token_data

        except requests.RequestException as e:
            raise NodeExecutionError(f"Failed to acquire OAuth token: {str(e)}") from e
        except ValueError as e:
            raise NodeExecutionError(
                f"Failed to parse OAuth token response: {str(e)}"
            ) from e

    def run(self, **kwargs) -> Dict[str, Any]:
        """Get OAuth authentication headers.

        This method handles token acquisition, caching, and renewal based on
        the configured OAuth flow.

        Args:
            token_url (str): OAuth token endpoint URL
            client_id (str): OAuth client ID
            client_secret (str, optional): OAuth client secret
            grant_type (str): OAuth grant type
            scope (str, optional): OAuth scopes
            username (str, optional): Username for password grant
            password (str, optional): Password for password grant
            refresh_token (str, optional): Refresh token for refresh flow
            token_storage (dict, optional): Token storage configuration
            auto_refresh (bool, optional): Whether to auto-refresh expired tokens

        Returns:
            Dictionary containing:
                headers: HTTP headers with OAuth token
                token_data: Complete token response
                auth_type: Authentication type ('oauth2')
                expires_in: Seconds until token expiration
        """
        force_refresh = kwargs.get("force_refresh", False)
        auto_refresh = kwargs.get("auto_refresh", True)

        current_time = time.time()

        # Check if we need to refresh the token
        if (
            not self.token_data
            or force_refresh
            or (auto_refresh and current_time >= self.token_expires_at)
        ):

            # Get new token
            self.token_data = self._get_token(**kwargs)

            # Calculate expiration time
            expires_in = self.token_data.get("expires_in", 3600)  # Default 1 hour
            self.token_expires_at = current_time + expires_in

            self.logger.info(
                f"Acquired new OAuth token, expires in {expires_in} seconds"
            )

        # Calculate current expiration time
        current_expires_in = max(0, int(self.token_expires_at - current_time))

        # Create headers
        headers = {"Authorization": f"Bearer {self.token_data['access_token']}"}

        return {
            "headers": headers,
            "token_data": self.token_data,
            "auth_type": "oauth2",
            "expires_in": current_expires_in,
        }


@register_node()
class APIKeyNode(Node):
    """Node for API key authentication.

    This node handles API key authentication in various formats:
    - Header-based (e.g., "X-API-Key: key123")
    - Query parameter (e.g., "?api_key=key123")
    - Request body parameter

    Design Purpose:
    - Simplify API key authentication for API requests
    - Support different API key placement formats
    - Abstract away implementation details

    Upstream Usage:
    - Workflow: Creates and configures with API key
    - HTTP/REST nodes: Consume the auth data

    Downstream Consumers:
    - HTTPRequestNode: Uses auth data for requests
    - RESTClientNode: Uses auth data for API calls
    """

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "api_key": NodeParameter(
                name="api_key", type=str, required=True, description="API key value"
            ),
            "location": NodeParameter(
                name="location",
                type=str,
                required=True,
                default="header",
                description="Where to place the API key (header, query, body)",
            ),
            "param_name": NodeParameter(
                name="param_name",
                type=str,
                required=True,
                default="X-API-Key",
                description="Parameter name for the API key",
            ),
            "prefix": NodeParameter(
                name="prefix",
                type=str,
                required=False,
                default=None,
                description="Prefix for the API key value (e.g., 'Bearer')",
            ),
        }

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                description="HTTP headers with API key (if location=header)",
            ),
            "query_params": NodeParameter(
                name="query_params",
                type=dict,
                required=False,
                description="Query parameters with API key (if location=query)",
            ),
            "body_params": NodeParameter(
                name="body_params",
                type=dict,
                required=False,
                description="Body parameters with API key (if location=body)",
            ),
            "auth_type": NodeParameter(
                name="auth_type",
                type=str,
                required=True,
                description="Authentication type (always 'api_key')",
            ),
        }

    def run(self, **kwargs) -> Dict[str, Any]:
        """Generate API key authentication data.

        Args:
            api_key (str): API key value
            location (str): Where to place the API key (header, query, body)
            param_name (str): Parameter name for the API key
            prefix (str, optional): Prefix for the API key value

        Returns:
            Dictionary containing:
                headers: HTTP headers with API key (if location=header)
                query_params: Query parameters with API key (if location=query)
                body_params: Body parameters with API key (if location=body)
                auth_type: Authentication type ('api_key')
        """
        api_key = kwargs.get("api_key")
        location = kwargs.get("location", "header").lower()
        param_name = kwargs.get("param_name", "X-API-Key")
        prefix = kwargs.get("prefix")

        # Validate required parameters
        if not api_key:
            raise NodeValidationError("API key is required")

        if location not in ("header", "query", "body"):
            raise NodeValidationError(
                f"Invalid API key location: {location}. "
                "Must be one of: header, query, body"
            )

        # Format API key value
        key_value = api_key
        if prefix:
            key_value = f"{prefix} {api_key}"

        # Create result based on location
        result = {"auth_type": "api_key"}

        if location == "header":
            result["headers"] = {param_name: key_value}
            result["query_params"] = {}
            result["body_params"] = {}

        elif location == "query":
            result["headers"] = {}
            result["query_params"] = {param_name: key_value}
            result["body_params"] = {}

        elif location == "body":
            result["headers"] = {}
            result["query_params"] = {}
            result["body_params"] = {param_name: key_value}

        return result
