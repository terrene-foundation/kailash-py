"""
Credential Manager Node for centralized credential handling.

This node provides enterprise-grade credential management with support for
multiple credential sources, validation, and secure handling.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from kailash.nodes.base import Node, NodeParameter


class CredentialManagerNode(Node):
    """
    Node for centralized credential management with validation and masking.

    Supports multiple credential sources:
    - Environment variables
    - JSON files
    - AWS Secrets Manager (simulated)
    - Azure Key Vault (simulated)
    - HashiCorp Vault (simulated)

    Example:
        ```python
        # Basic usage with environment variables
        cred_node = CredentialManagerNode(
            name="get_api_creds",
            credential_name="openai_api",
            credential_type="api_key"
        )

        # Advanced usage with multiple sources
        cred_node = CredentialManagerNode(
            name="get_db_creds",
            credential_name="postgres_prod",
            credential_type="database",
            credential_sources=["vault", "env", "file"],
            validate_on_fetch=True
        )
        ```
    """

    def __init__(
        self,
        credential_name: str,
        credential_type: Literal[
            "api_key", "oauth2", "database", "certificate", "basic_auth", "custom"
        ] = "custom",
        credential_sources: Optional[
            List[Literal["env", "file", "vault", "aws_secrets", "azure_keyvault"]]
        ] = None,
        validate_on_fetch: bool = True,
        mask_in_logs: bool = True,
        cache_duration_seconds: Optional[int] = 300,
        **kwargs,
    ):
        """
        Initialize the CredentialManagerNode.

        Args:
            credential_name: Name/identifier of the credential to fetch
            credential_type: Type of credential for validation
            credential_sources: List of sources to check (default: ["env", "file"])
            validate_on_fetch: Whether to validate credentials when fetched
            mask_in_logs: Whether to mask credential values in logs
            cache_duration_seconds: How long to cache credentials (None = no cache)
        """
        super().__init__(**kwargs)

        self.credential_name = credential_name
        self.credential_type = credential_type
        self.credential_sources = credential_sources or ["env", "file"]
        self.validate_on_fetch = validate_on_fetch
        self.mask_in_logs = mask_in_logs
        self.cache_duration_seconds = cache_duration_seconds

        self._cache = {}
        self._cache_timestamps = {}

        # Define credential validation patterns
        self._validation_patterns = {
            "api_key": r"^[A-Za-z0-9\-_]{20,}$",
            "oauth2": {
                "client_id": r"^[A-Za-z0-9\-_]{10,}$",
                "client_secret": r"^[A-Za-z0-9\-_]{20,}$",
            },
            "database": {
                "host": r"^[A-Za-z0-9\-\._]+$",
                "port": r"^\d{1,5}$",
                "username": r"^[A-Za-z0-9\-_]+$",
                "password": r".{8,}",
            },
            "basic_auth": {"username": r"^[A-Za-z0-9\-_@\.]+$", "password": r".{6,}"},
        }

    def _mask_value(self, value: str, mask_type: str = "partial") -> str:
        """Mask sensitive credential values."""
        if not value or not self.mask_in_logs:
            return value

        if mask_type == "full":
            return "*" * len(value)
        elif mask_type == "partial":
            if len(value) <= 8:
                return value[:2] + "*" * (len(value) - 2)
            else:
                return value[:4] + "*" * (len(value) - 8) + value[-4:]
        return value

    def _fetch_from_env(self, credential_name: str) -> Optional[Dict[str, Any]]:
        """Fetch credentials from environment variables."""
        # Try common patterns
        prefixes = [credential_name.upper(), f"{credential_name.upper()}_", ""]

        if self.credential_type == "api_key":
            for prefix in prefixes:
                key_names = [f"{prefix}API_KEY", f"{prefix}KEY", f"{prefix}TOKEN"]
                for key_name in key_names:
                    if key_name in os.environ:
                        return {"api_key": os.environ[key_name]}

        elif self.credential_type == "oauth2":
            for prefix in prefixes:
                client_id = os.environ.get(f"{prefix}CLIENT_ID")
                client_secret = os.environ.get(f"{prefix}CLIENT_SECRET")
                if client_id and client_secret:
                    return {
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "token_url": os.environ.get(f"{prefix}TOKEN_URL", ""),
                    }

        elif self.credential_type == "database":
            for prefix in prefixes:
                host = os.environ.get(f"{prefix}DB_HOST") or os.environ.get(
                    f"{prefix}HOST"
                )
                if host:
                    return {
                        "host": host,
                        "port": os.environ.get(f"{prefix}DB_PORT", "5432"),
                        "username": os.environ.get(f"{prefix}DB_USER")
                        or os.environ.get(f"{prefix}USER"),
                        "password": os.environ.get(f"{prefix}DB_PASSWORD")
                        or os.environ.get(f"{prefix}PASSWORD"),
                        "database": os.environ.get(f"{prefix}DB_NAME")
                        or os.environ.get(f"{prefix}DATABASE"),
                    }

        elif self.credential_type == "basic_auth":
            for prefix in prefixes:
                username = os.environ.get(f"{prefix}USERNAME") or os.environ.get(
                    f"{prefix}USER"
                )
                password = os.environ.get(f"{prefix}PASSWORD") or os.environ.get(
                    f"{prefix}PASS"
                )
                if username and password:
                    return {"username": username, "password": password}

        # Generic fetch for custom type
        result = {}
        prefix = credential_name.upper() + "_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                result[key[len(prefix) :].lower()] = value

        return result if result else None

    def _fetch_from_file(self, credential_name: str) -> Optional[Dict[str, Any]]:
        """Fetch credentials from JSON file."""
        # Look in common credential file locations
        search_paths = [
            f".credentials/{credential_name}.json",
            f"credentials/{credential_name}.json",
            f".secrets/{credential_name}.json",
            f"config/credentials/{credential_name}.json",
            ".env.json",
        ]

        for path in search_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        # If .env.json, look for the specific credential
                        if path == ".env.json" and credential_name in data:
                            return data[credential_name]
                        elif path != ".env.json":
                            return data
                except Exception:
                    continue

        return None

    def _fetch_from_vault(self, credential_name: str) -> Optional[Dict[str, Any]]:
        """Simulate fetching from HashiCorp Vault."""
        # In production, this would use hvac client
        # For now, return simulated data for testing
        if credential_name == "test_vault_creds":
            return {
                "api_key": "vault_simulated_key_123456",
                "metadata": {
                    "version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            }
        return None

    def _fetch_from_aws_secrets(self, credential_name: str) -> Optional[Dict[str, Any]]:
        """Simulate fetching from AWS Secrets Manager."""
        # In production, this would use boto3 client
        # For now, return simulated data for testing
        if credential_name == "test_aws_creds":
            return {
                "username": "aws_user",
                "password": "aws_simulated_password_123",
                "engine": "postgres",
                "host": "test.rds.amazonaws.com",
            }
        return None

    def _fetch_from_azure_keyvault(
        self, credential_name: str
    ) -> Optional[Dict[str, Any]]:
        """Simulate fetching from Azure Key Vault."""
        # In production, this would use azure-keyvault-secrets client
        # For now, return simulated data for testing
        if credential_name == "test_azure_creds":
            return {
                "client_id": "azure_client_123",
                "client_secret": "azure_secret_456",
                "tenant_id": "azure_tenant_789",
            }
        return None

    def _validate_credential(self, credential: Dict[str, Any]) -> bool:
        """Validate credential format based on type."""
        if not self.validate_on_fetch:
            return True

        patterns = self._validation_patterns.get(self.credential_type)
        if not patterns:
            return True  # No validation for custom type

        if isinstance(patterns, str):
            # Single pattern (e.g., api_key)
            value = credential.get(self.credential_type) or credential.get("value")
            if value and re.match(patterns, value):
                return True
        elif isinstance(patterns, dict):
            # Multiple patterns (e.g., oauth2, database)
            for field, pattern in patterns.items():
                value = credential.get(field)
                if value and not re.match(pattern, str(value)):
                    return False
            return True

        return False

    def _is_cache_valid(self, credential_name: str) -> bool:
        """Check if cached credential is still valid."""
        if not self.cache_duration_seconds:
            return False

        if credential_name not in self._cache_timestamps:
            return False

        elapsed = (
            datetime.now(timezone.utc) - self._cache_timestamps[credential_name]
        ).total_seconds()
        return elapsed < self.cache_duration_seconds

    def run(self, **inputs) -> Dict[str, Any]:
        """
        Fetch and validate credentials from configured sources.

        Returns:
            Dict containing:
            - credentials: The fetched credential data
            - source: Which source provided the credentials
            - validated: Whether credentials passed validation
            - masked_display: Masked version for logging
            - metadata: Additional information about the credentials
        """
        # Check cache first
        if self._is_cache_valid(self.credential_name):
            cached = self._cache[self.credential_name]
            return {
                "credentials": cached["credentials"],
                "source": cached["source"],
                "validated": cached["validated"],
                "masked_display": cached["masked_display"],
                "metadata": {**cached.get("metadata", {}), "from_cache": True},
            }

        # Try each source in order
        credentials = None
        source = None

        source_methods = {
            "env": self._fetch_from_env,
            "file": self._fetch_from_file,
            "vault": self._fetch_from_vault,
            "aws_secrets": self._fetch_from_aws_secrets,
            "azure_keyvault": self._fetch_from_azure_keyvault,
        }

        for src in self.credential_sources:
            if src in source_methods:
                try:
                    result = source_methods[src](self.credential_name)
                    if result:
                        credentials = result
                        source = src
                        break
                except Exception as e:
                    # Log error but continue to next source
                    continue

        if not credentials:
            raise ValueError(
                f"Credential '{self.credential_name}' not found in any configured source"
            )

        # Validate credentials
        validated = self._validate_credential(credentials)

        # Create masked display version
        masked_display = {}
        for key, value in credentials.items():
            if isinstance(value, str) and key.lower() in [
                "password",
                "secret",
                "key",
                "token",
                "api_key",
                "client_secret",
            ]:
                masked_display[key] = self._mask_value(value)
            else:
                masked_display[key] = value

        # Prepare result
        result = {
            "credentials": credentials,
            "source": source,
            "validated": validated,
            "masked_display": masked_display,
            "metadata": {
                "credential_type": self.credential_type,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "rotation_detected": False,  # Placeholder for rotation detection
            },
        }

        # Cache if enabled
        if self.cache_duration_seconds:
            self._cache[self.credential_name] = result
            self._cache_timestamps[self.credential_name] = datetime.now(timezone.utc)

        return result

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """No input parameters required."""
        return {}

    def get_output_schema(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "credentials": NodeParameter(
                name="credentials", type=dict, description="The fetched credential data"
            ),
            "source": NodeParameter(
                name="source",
                type=str,
                description="Which source provided the credentials",
            ),
            "validated": NodeParameter(
                name="validated",
                type=bool,
                description="Whether credentials passed validation",
            ),
            "masked_display": NodeParameter(
                name="masked_display",
                type=dict,
                description="Masked version for safe logging",
            ),
            "metadata": NodeParameter(
                name="metadata", type=dict, description="Additional credential metadata"
            ),
        }

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Async execution method for enterprise integration."""
        return self.execute(**kwargs)
