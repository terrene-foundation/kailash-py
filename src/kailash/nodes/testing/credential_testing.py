"""Credential testing node for workflow authentication testing.

This module provides a specialized node for testing credential flows in workflows,
including mock credential generation, validation simulation, and error scenarios.
"""

import base64
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from kailash.nodes.base import Node, NodeParameter, register_node
from kailash.sdk_exceptions import NodeExecutionError, NodeValidationError


@register_node()
class CredentialTestingNode(Node):
    """Node for testing credential flows in workflows.

    This node simulates various credential scenarios for testing authentication
    workflows without requiring actual external services. It can generate mock
    credentials, simulate validation, test expiration scenarios, and inject
    various error conditions.

    Design Purpose:
    - Enable comprehensive testing of authentication flows
    - Simulate various credential types and scenarios
    - Test error handling and edge cases
    - Validate security patterns in workflows

    Use Cases:
    - Unit testing authentication workflows
    - Integration testing with mock services
    - Security pattern validation
    - Error scenario testing
    - Token lifecycle simulation

    Example:
        >>> # Test OAuth2 token expiration
        >>> tester = CredentialTestingNode()
        >>> result = tester.execute(
        ...     credential_type='oauth2',
        ...     scenario='expired',
        ...     mock_data={'client_id': 'test_client'}
        ... )
        >>> assert result['expired'] is True
        >>> assert 'expired_token' in result['error_details']
        >>>
        >>> # Test successful API key validation
        >>> result = tester.execute(
        ...     credential_type='api_key',
        ...     scenario='success',
        ...     validation_rules={'key_length': 32}
        ... )
        >>> assert result['valid'] is True
        >>> assert len(result['credentials']['api_key']) == 32
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define the parameters this node accepts.

        Returns:
            Dictionary of parameter definitions
        """
        return {
            "credential_type": NodeParameter(
                name="credential_type",
                type=str,
                required=True,
                description="Type of credential to test: oauth2, api_key, basic, jwt",
            ),
            "scenario": NodeParameter(
                name="scenario",
                type=str,
                required=True,
                default="success",
                description="Test scenario: success, expired, invalid, network_error, rate_limit",
            ),
            "mock_data": NodeParameter(
                name="mock_data",
                type=dict,
                required=False,
                default={},
                description="Custom mock data for the test scenario",
            ),
            "validation_rules": NodeParameter(
                name="validation_rules",
                type=dict,
                required=False,
                default={},
                description="Rules to validate generated credentials",
            ),
            "delay_ms": NodeParameter(
                name="delay_ms",
                type=int,
                required=False,
                default=0,
                description="Simulated network delay in milliseconds",
            ),
            "ttl_seconds": NodeParameter(
                name="ttl_seconds",
                type=int,
                required=False,
                default=3600,
                description="Time-to-live for generated credentials in seconds",
            ),
        }

    def get_output_schema(self) -> dict[str, NodeParameter]:
        """Define the output schema for this node.

        Returns:
            Dictionary of output parameter definitions
        """
        return {
            "valid": NodeParameter(
                name="valid",
                type=bool,
                required=True,
                description="Whether the credential validation succeeded",
            ),
            "credentials": NodeParameter(
                name="credentials",
                type=dict,
                required=False,
                description="Generated mock credentials (if successful)",
            ),
            "headers": NodeParameter(
                name="headers",
                type=dict,
                required=False,
                description="HTTP headers for the credentials (if applicable)",
            ),
            "expires_at": NodeParameter(
                name="expires_at",
                type=str,
                required=False,
                description="ISO format expiration timestamp",
            ),
            "expired": NodeParameter(
                name="expired",
                type=bool,
                required=False,
                description="Whether the credentials are expired",
            ),
            "error": NodeParameter(
                name="error",
                type=str,
                required=False,
                description="Error message if validation failed",
            ),
            "error_details": NodeParameter(
                name="error_details",
                type=dict,
                required=False,
                description="Detailed error information",
            ),
            "metadata": NodeParameter(
                name="metadata",
                type=dict,
                required=True,
                description="Test metadata including scenario details",
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """Execute credential testing based on the specified scenario.

        Args:
            credential_type: Type of credential to test
            scenario: Test scenario to simulate
            mock_data: Custom mock data
            validation_rules: Validation rules to apply
            delay_ms: Simulated network delay
            ttl_seconds: Credential time-to-live

        Returns:
            Dictionary containing test results and generated credentials

        Raises:
            NodeValidationError: If parameters are invalid
            NodeExecutionError: If simulating execution errors
        """
        credential_type = kwargs.get("credential_type")
        scenario = kwargs.get("scenario", "success")
        mock_data = kwargs.get("mock_data", {})
        validation_rules = kwargs.get("validation_rules", {})
        delay_ms = kwargs.get("delay_ms", 0)
        ttl_seconds = kwargs.get("ttl_seconds", 3600)

        # Validate credential type
        valid_types = ["oauth2", "api_key", "basic", "jwt"]
        if credential_type not in valid_types:
            raise NodeValidationError(
                f"Invalid credential_type: {credential_type}. Must be one of: {valid_types}"
            )

        # Simulate network delay
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        # Handle different scenarios
        if scenario == "network_error":
            raise NodeExecutionError("Simulated network error: Connection timeout")

        elif scenario == "rate_limit":
            return {
                "valid": False,
                "error": "Rate limit exceeded",
                "error_details": {
                    "error_code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": 60,
                    "limit": 100,
                    "remaining": 0,
                },
                "metadata": {
                    "scenario": scenario,
                    "credential_type": credential_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }

        # Generate credentials based on type
        if credential_type == "oauth2":
            result = self._generate_oauth2_credentials(
                scenario, mock_data, validation_rules, ttl_seconds
            )
        elif credential_type == "api_key":
            result = self._generate_api_key_credentials(
                scenario, mock_data, validation_rules, ttl_seconds
            )
        elif credential_type == "basic":
            result = self._generate_basic_credentials(
                scenario, mock_data, validation_rules, ttl_seconds
            )
        elif credential_type == "jwt":
            result = self._generate_jwt_credentials(
                scenario, mock_data, validation_rules, ttl_seconds
            )

        # Add common metadata
        result["metadata"] = {
            "scenario": scenario,
            "credential_type": credential_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_id": str(uuid4()),
        }

        return result

    def _generate_oauth2_credentials(
        self, scenario: str, mock_data: dict, validation_rules: dict, ttl_seconds: int
    ) -> dict[str, Any]:
        """Generate OAuth2 mock credentials."""
        now = datetime.now(timezone.utc)

        if scenario == "expired":
            # Generate expired token
            expires_at = now - timedelta(hours=1)
            return {
                "valid": False,
                "expired": True,
                "error": "Token expired",
                "error_details": {
                    "error_code": "expired_token",
                    "expired_at": expires_at.isoformat(),
                },
                "expires_at": expires_at.isoformat(),
            }

        elif scenario == "invalid":
            return {
                "valid": False,
                "error": "Invalid client credentials",
                "error_details": {
                    "error_code": "invalid_client",
                    "error_description": "Client authentication failed",
                },
            }

        else:  # success scenario
            expires_at = now + timedelta(seconds=ttl_seconds)
            access_token = f"mock_access_{uuid4().hex[:16]}"
            refresh_token = f"mock_refresh_{uuid4().hex[:16]}"

            credentials = {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": ttl_seconds,
                "refresh_token": refresh_token,
                "scope": mock_data.get("scope", "read write"),
            }

            # Apply custom mock data
            credentials.update(mock_data)

            # Validate if rules provided
            if validation_rules:
                valid, error = self._validate_oauth2(credentials, validation_rules)
                if not valid:
                    return {
                        "valid": False,
                        "error": error,
                        "error_details": {"validation_failed": True},
                    }

            return {
                "valid": True,
                "credentials": credentials,
                "headers": {"Authorization": f"Bearer {access_token}"},
                "expires_at": expires_at.isoformat(),
                "expired": False,
            }

    def _generate_api_key_credentials(
        self, scenario: str, mock_data: dict, validation_rules: dict, ttl_seconds: int
    ) -> dict[str, Any]:
        """Generate API key mock credentials."""
        if scenario == "invalid":
            return {
                "valid": False,
                "error": "Invalid API key",
                "error_details": {
                    "error_code": "invalid_api_key",
                    "status_code": 401,
                },
            }

        else:  # success or expired scenario
            key_length = validation_rules.get("key_length", 32)
            api_key = f"sk_test_{uuid4().hex[:key_length]}"

            credentials = {
                "api_key": api_key,
                "key_prefix": mock_data.get("key_prefix", "sk_test"),
            }

            # Apply custom mock data
            credentials.update(mock_data)

            header_name = validation_rules.get("header_name", "X-API-Key")

            if scenario == "expired":
                return {
                    "valid": False,
                    "expired": True,
                    "error": "API key expired",
                    "error_details": {
                        "error_code": "expired_api_key",
                        "key_id": api_key[:12] + "...",
                    },
                    "credentials": credentials,
                }

            return {
                "valid": True,
                "credentials": credentials,
                "headers": {header_name: api_key},
                "expired": False,
            }

    def _generate_basic_credentials(
        self, scenario: str, mock_data: dict, validation_rules: dict, ttl_seconds: int
    ) -> dict[str, Any]:
        """Generate Basic Auth mock credentials."""
        username = mock_data.get("username", "test_user")
        password = mock_data.get("password", "test_pass123")

        if scenario == "invalid":
            return {
                "valid": False,
                "error": "Invalid username or password",
                "error_details": {
                    "error_code": "invalid_credentials",
                    "status_code": 401,
                },
            }

        else:  # success scenario
            credentials = {
                "username": username,
                "password": password,
            }

            # Generate Basic Auth header
            auth_string = f"{username}:{password}"
            encoded_auth = base64.b64encode(auth_string.encode()).decode()

            return {
                "valid": True,
                "credentials": credentials,
                "headers": {"Authorization": f"Basic {encoded_auth}"},
                "expired": False,
            }

    def _generate_jwt_credentials(
        self, scenario: str, mock_data: dict, validation_rules: dict, ttl_seconds: int
    ) -> dict[str, Any]:
        """Generate JWT mock credentials."""
        now = datetime.now(timezone.utc)

        # Mock JWT structure (not cryptographically valid)
        header = {"alg": "HS256", "typ": "JWT"}

        if scenario == "expired":
            payload = {
                "sub": mock_data.get("subject", "1234567890"),
                "name": mock_data.get("name", "Test User"),
                "iat": int((now - timedelta(hours=2)).timestamp()),
                "exp": int((now - timedelta(hours=1)).timestamp()),
            }

            return {
                "valid": False,
                "expired": True,
                "error": "JWT token expired",
                "error_details": {
                    "error_code": "jwt_expired",
                    "expired_at": datetime.fromtimestamp(
                        payload["exp"], tz=timezone.utc
                    ).isoformat(),
                },
            }

        elif scenario == "invalid":
            return {
                "valid": False,
                "error": "Invalid JWT signature",
                "error_details": {
                    "error_code": "invalid_signature",
                    "status_code": 401,
                },
            }

        else:  # success scenario
            expires_at = now + timedelta(seconds=ttl_seconds)
            payload = {
                "sub": mock_data.get("subject", "1234567890"),
                "name": mock_data.get("name", "Test User"),
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
                "iss": mock_data.get("issuer", "test_issuer"),
                "aud": mock_data.get("audience", "test_audience"),
            }

            # Apply additional claims from mock_data
            for key, value in mock_data.items():
                if key not in payload:
                    payload[key] = value

            # Create mock JWT (base64 encoded parts separated by dots)
            header_b64 = (
                base64.urlsafe_b64encode(str(header).encode()).decode().rstrip("=")
            )
            payload_b64 = (
                base64.urlsafe_b64encode(str(payload).encode()).decode().rstrip("=")
            )
            signature = uuid4().hex[:32]

            jwt_token = f"{header_b64}.{payload_b64}.{signature}"

            credentials = {
                "jwt": jwt_token,
                "header": header,
                "payload": payload,
            }

            return {
                "valid": True,
                "credentials": credentials,
                "headers": {"Authorization": f"Bearer {jwt_token}"},
                "expires_at": expires_at.isoformat(),
                "expired": False,
            }

    def _validate_oauth2(self, credentials: dict, rules: dict) -> tuple[bool, str]:
        """Validate OAuth2 credentials against rules."""
        # Check required fields
        required_fields = rules.get("required_fields", ["access_token", "token_type"])
        for field in required_fields:
            if field not in credentials:
                return False, f"Missing required field: {field}"

        # Check token format
        if "token_format" in rules:
            token = credentials.get("access_token", "")
            if not token.startswith(rules["token_format"]):
                return False, "Invalid token format"

        # Check scope requirements
        if "required_scopes" in rules:
            granted_scopes = set(credentials.get("scope", "").split())
            required_scopes = set(rules["required_scopes"])
            if not required_scopes.issubset(granted_scopes):
                missing = required_scopes - granted_scopes
                return False, f"Missing required scopes: {missing}"

        return True, ""
