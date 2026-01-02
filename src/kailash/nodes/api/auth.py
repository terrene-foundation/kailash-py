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
from typing import Any

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

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def get_output_schema(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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
            refresh_buffer_seconds (int, optional): Seconds before expiry to trigger refresh (default: 300)
            validate_token_response (bool, optional): Whether to validate token response (default: True)
            **kwargs: Additional parameters passed to base Node
        """
        super().__init__(**kwargs)
        self.http_node = HTTPRequestNode(**kwargs)
        self.token_data = None  # Will store token information
        self.token_expires_at = 0  # Timestamp when token expires
        self.refresh_buffer_seconds = kwargs.get("refresh_buffer_seconds", 300)
        self.validate_token_response = kwargs.get("validate_token_response", True)
        self._last_token_request_duration = None

    def get_parameters(self) -> dict[str, NodeParameter]:
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
            "refresh_buffer_seconds": NodeParameter(
                name="refresh_buffer_seconds",
                type=int,
                required=False,
                default=300,
                description="Seconds before token expiry to trigger automatic refresh",
            ),
            "validate_token_response": NodeParameter(
                name="validate_token_response",
                type=bool,
                required=False,
                default=True,
                description="Whether to validate token response structure",
            ),
            "include_token_metadata": NodeParameter(
                name="include_token_metadata",
                type=bool,
                required=False,
                default=False,
                description="Include additional token metadata in response",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
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
            "token_type": NodeParameter(
                name="token_type",
                type=str,
                required=False,
                description="Token type from response (usually 'Bearer')",
            ),
            "scope": NodeParameter(
                name="scope",
                type=str,
                required=False,
                description="Actual granted scopes from response",
            ),
            "refresh_token_present": NodeParameter(
                name="refresh_token_present",
                type=bool,
                required=False,
                description="Whether a refresh token is available",
            ),
            "token_expires_at": NodeParameter(
                name="token_expires_at",
                type=str,
                required=False,
                description="ISO format timestamp of token expiration",
            ),
            "raw_response": NodeParameter(
                name="raw_response",
                type=dict,
                required=False,
                description="Full token response for debugging (if include_raw_response is True)",
            ),
            "token": NodeParameter(
                name="token",
                type=dict,
                required=False,
                description="Structured token information with all components (if include_token_metadata is True)",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=False,
                description="Additional token metadata and health information (if include_token_metadata is True)",
            ),
        }

    def _validate_token_response(self, token_data: dict) -> None:
        """Validate the token response structure.

        Args:
            token_data: Token response from OAuth server

        Raises:
            NodeExecutionError: If token response is invalid
        """
        required_fields = ["access_token"]
        missing_fields = [field for field in required_fields if field not in token_data]

        if missing_fields:
            raise NodeExecutionError(
                f"Invalid token response - missing required fields: {missing_fields}. "
                f"Response contained: {list(token_data.keys())}. "
                "Please verify your OAuth configuration and credentials."
            )

        # Validate token format
        access_token = token_data.get("access_token", "")
        if not access_token or not isinstance(access_token, str):
            raise NodeExecutionError(
                "Invalid access token format. Token must be a non-empty string. "
                "Please check your OAuth server configuration."
            )

    def _calculate_token_health(self, expires_in: int) -> dict[str, Any]:
        """Calculate token health metrics.

        Args:
            expires_in: Seconds until token expiration

        Returns:
            Dictionary with health metrics
        """
        health = {
            "status": "healthy",
            "expires_in_seconds": expires_in,
            "expires_in_minutes": round(expires_in / 60, 1),
            "expires_in_human": self._format_duration(expires_in),
            "should_refresh": expires_in <= self.refresh_buffer_seconds,
            "health_percentage": min(
                100, (expires_in / 3600) * 100
            ),  # Assume 1hr tokens
        }

        # Determine health status
        if expires_in <= 0:
            health["status"] = "expired"
        elif expires_in <= 60:
            health["status"] = "critical"
        elif expires_in <= self.refresh_buffer_seconds:
            health["status"] = "needs_refresh"
        elif expires_in <= 600:  # 10 minutes
            health["status"] = "warning"

        return health

    def _format_duration(self, seconds: int) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds

        Returns:
            Human-readable duration string
        """
        if seconds <= 0:
            return "expired"
        elif seconds < 60:
            return f"{seconds} seconds"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''}"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if minutes > 0:
                return f"{hours} hour{'s' if hours > 1 else ''} {minutes} minute{'s' if minutes > 1 else ''}"
            return f"{hours} hour{'s' if hours > 1 else ''}"

    def _get_token(self, **kwargs) -> dict[str, Any]:
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

        start_time = time.time()

        try:
            response = requests.post(token_url, data=data, headers=headers, timeout=30)

            response.raise_for_status()
            token_data = response.json()

            # Record request duration
            self._last_token_request_duration = int((time.time() - start_time) * 1000)

            # Check for required fields in response
            if "access_token" not in token_data:
                raise NodeExecutionError(
                    f"Invalid OAuth response: missing access_token. Response: {token_data}"
                )

            return token_data

        except requests.RequestException as e:
            # Enhance error message with suggestions
            error_msg = f"Failed to acquire OAuth token: {str(e)}"

            suggestions = []
            if "401" in str(e) or "unauthorized" in str(e).lower():
                suggestions.append(
                    "Verify your client_id and client_secret are correct"
                )
                suggestions.append(
                    "Check if your credentials have the required permissions"
                )
            elif "400" in str(e) or "bad request" in str(e).lower():
                suggestions.append(
                    "Verify the grant_type is supported by your OAuth server"
                )
                suggestions.append("Check if all required parameters are provided")
            elif "connection" in str(e).lower() or "timeout" in str(e).lower():
                suggestions.append("Verify the token_url is correct and accessible")
                suggestions.append(
                    "Check your network connection and firewall settings"
                )

            if suggestions:
                error_msg += "\n\nSuggestions:\n" + "\n".join(
                    f"- {s}" for s in suggestions
                )

            raise NodeExecutionError(error_msg) from e
        except ValueError as e:
            raise NodeExecutionError(
                f"Failed to parse OAuth token response: {str(e)}"
            ) from e

    def run(self, **kwargs) -> dict[str, Any]:
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
                token_type: Token type from response (usually 'Bearer')
                scope: Actual granted scopes from response
                refresh_token_present: Whether a refresh token is available
                token_expires_at: ISO format timestamp of token expiration
                raw_response: Full token response for debugging (if include_raw is True)
        """
        force_refresh = kwargs.get("force_refresh", False)
        auto_refresh = kwargs.get("auto_refresh", True)
        include_raw = kwargs.get("include_raw_response", False)
        include_metadata = kwargs.get("include_token_metadata", False)

        current_time = time.time()

        # Check if we need to refresh the token
        # Consider the refresh buffer when determining if refresh is needed
        needs_refresh = (
            not self.token_data
            or force_refresh
            or (
                auto_refresh
                and current_time
                >= (self.token_expires_at - self.refresh_buffer_seconds)
            )
        )

        if needs_refresh:
            # Get new token
            self.token_data = self._get_token(**kwargs)

            # Validate token response if requested
            if self.validate_token_response:
                self._validate_token_response(self.token_data)

            # Calculate expiration time
            expires_in = self.token_data.get("expires_in", 3600)  # Default 1 hour
            self.token_expires_at = current_time + expires_in

            self.logger.info(
                f"Acquired new OAuth token, expires in {expires_in} seconds"
            )

        # Calculate current expiration time
        current_expires_in = max(0, int(self.token_expires_at - current_time))

        # Create headers
        access_token = self.token_data.get("access_token", "")
        token_type = self.token_data.get("token_type", "Bearer")

        # Format authorization header based on token type
        if token_type.lower() == "bearer":
            headers = {"Authorization": f"Bearer {access_token}"}
        else:
            headers = {"Authorization": f"{token_type} {access_token}"}

        # Calculate expiration timestamp
        from datetime import datetime, timezone

        token_expires_at_dt = datetime.fromtimestamp(
            self.token_expires_at, tz=timezone.utc
        )
        token_expires_at_iso = token_expires_at_dt.isoformat()

        # Build response
        result = {
            "headers": headers,
            "token_data": self.token_data,
            "auth_type": "oauth2",
            "expires_in": current_expires_in,
            "token_type": token_type,
            "scope": self.token_data.get("scope", ""),
            "refresh_token_present": bool(self.token_data.get("refresh_token")),
            "token_expires_at": token_expires_at_iso,
        }

        # Include raw response if requested
        if include_raw:
            result["raw_response"] = self.token_data.copy()

        # Include structured token and metadata if requested
        if include_metadata:
            # Build structured token object
            issued_at_dt = datetime.fromtimestamp(
                self.token_expires_at - self.token_data.get("expires_in", 3600),
                tz=timezone.utc,
            )

            token = {
                "access_token": self.token_data.get("access_token", ""),
                "token_type": token_type,
                "expires_in": current_expires_in,
                "expires_at": token_expires_at_iso,
                "issued_at": issued_at_dt.isoformat(),
                "scope": self.token_data.get("scope", ""),
                "is_valid": current_expires_in > 0,
                "has_refresh_token": bool(self.token_data.get("refresh_token")),
                "headers": headers,  # Include ready-to-use headers
            }

            # Add refresh token hint if present (but not the actual value for security)
            refresh_token = self.token_data.get("refresh_token")
            if refresh_token:
                token["refresh_token_hint"] = (
                    f"...{refresh_token[-4:]}" if len(refresh_token) > 4 else "****"
                )

            result["token"] = token

            # Add health and metadata
            health = self._calculate_token_health(current_expires_in)

            metadata = {
                "health": health,
                "grant_type": kwargs.get("grant_type", "client_credentials"),
                "token_endpoint": kwargs.get("token_url", ""),
                "scopes_requested": (
                    kwargs.get("scope", "").split() if kwargs.get("scope") else []
                ),
                "scopes_granted": (
                    self.token_data.get("scope", "").split()
                    if self.token_data.get("scope")
                    else []
                ),
                "token_size_bytes": len(self.token_data.get("access_token", "")),
                "response_fields": (
                    list(self.token_data.keys()) if self.token_data else []
                ),
            }

            # Add timing information
            if self._last_token_request_duration is not None:
                metadata["last_request_duration_ms"] = self._last_token_request_duration

            result["metadata"] = metadata

        return result


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

    def get_parameters(self) -> dict[str, NodeParameter]:
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

    def get_output_schema(self) -> dict[str, NodeParameter]:
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

    def run(self, **kwargs) -> dict[str, Any]:
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
