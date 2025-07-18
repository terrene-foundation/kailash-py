"""Runtime secret management interface and providers.

This module provides the SecretProvider interface and implementations for
injecting secrets at runtime, eliminating the need to embed secrets in
environment variables or workflow parameters.
"""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecretRequirement:
    """Metadata for a required secret."""

    def __init__(
        self,
        name: str,
        parameter_name: str,
        version: Optional[str] = None,
        optional: bool = False,
    ):
        """Initialize secret requirement.

        Args:
            name: Secret name in the provider (e.g., "jwt-signing-key")
            parameter_name: Parameter name in the node (e.g., "secret_key")
            version: Optional version identifier
            optional: Whether this secret is optional
        """
        self.name = name
        self.parameter_name = parameter_name
        self.version = version
        self.optional = optional


class SecretProvider(ABC):
    """Base interface for secret providers."""

    @abstractmethod
    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        """Fetch a secret by name and optional version.

        Args:
            name: Secret name
            version: Optional version identifier

        Returns:
            Secret value as string

        Raises:
            SecretNotFoundError: If secret doesn't exist
            SecretProviderError: If provider operation fails
        """
        pass

    @abstractmethod
    def list_secrets(self) -> List[str]:
        """List available secrets.

        Returns:
            List of secret names
        """
        pass

    def get_secrets(self, requirements: List[SecretRequirement]) -> Dict[str, str]:
        """Fetch multiple secrets based on requirements.

        Args:
            requirements: List of secret requirements

        Returns:
            Dictionary mapping parameter names to secret values
        """
        secrets = {}
        for req in requirements:
            try:
                secret_value = self.get_secret(req.name, req.version)
                secrets[req.parameter_name] = secret_value
            except Exception as e:
                if req.optional:
                    logger.warning(f"Optional secret {req.name} not found: {e}")
                    continue
                else:
                    raise
        return secrets


class EnvironmentSecretProvider(SecretProvider):
    """Secret provider that fetches secrets from environment variables.

    This provider maintains backward compatibility by reading secrets from
    environment variables, but provides a secure interface for runtime injection.
    """

    def __init__(self, prefix: str = "KAILASH_SECRET_"):
        """Initialize environment secret provider.

        Args:
            prefix: Prefix for environment variables containing secrets
        """
        self.prefix = prefix

    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        """Get secret from environment variable.

        Args:
            name: Secret name (will be prefixed and uppercased)
            version: Ignored for environment provider

        Returns:
            Secret value from environment

        Raises:
            SecretNotFoundError: If environment variable not found
        """
        # Convert name to environment variable format
        env_name = f"{self.prefix}{name.upper().replace('-', '_')}"

        secret_value = os.environ.get(env_name)
        if secret_value is None:
            # Try without prefix for backward compatibility
            secret_value = os.environ.get(name.upper().replace("-", "_"))

        if secret_value is None:
            raise SecretNotFoundError(
                f"Secret '{name}' not found in environment variables"
            )

        return secret_value

    def list_secrets(self) -> List[str]:
        """List all secrets available in environment.

        Returns:
            List of secret names (without prefix)
        """
        secrets = []
        for key in os.environ:
            if key.startswith(self.prefix):
                # Remove prefix and convert back to secret name format
                secret_name = key[len(self.prefix) :].lower().replace("_", "-")
                secrets.append(secret_name)
        return secrets


class VaultSecretProvider(SecretProvider):
    """Secret provider for HashiCorp Vault.

    This provider integrates with HashiCorp Vault for enterprise secret management.
    """

    def __init__(self, vault_url: str, vault_token: str, mount_path: str = "secret"):
        """Initialize Vault secret provider.

        Args:
            vault_url: Vault server URL
            vault_token: Vault authentication token
            mount_path: Vault mount path for secrets
        """
        self.vault_url = vault_url
        self.vault_token = vault_token
        self.mount_path = mount_path
        self._client = None

    @property
    def client(self):
        """Lazy initialization of Vault client."""
        if self._client is None:
            try:
                import hvac

                self._client = hvac.Client(url=self.vault_url, token=self.vault_token)
            except ImportError:
                raise RuntimeError(
                    "hvac library not installed. Install with: pip install hvac"
                )
        return self._client

    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        """Get secret from Vault.

        Args:
            name: Secret path in Vault
            version: Optional version (for KV v2)

        Returns:
            Secret value
        """
        try:
            # Try KV v2 first
            response = self.client.secrets.kv.v2.read_secret_version(
                path=name, version=version, mount_point=self.mount_path
            )
            return response["data"]["data"]["value"]
        except Exception:
            # Fall back to KV v1
            response = self.client.secrets.kv.v1.read_secret(
                path=name, mount_point=self.mount_path
            )
            return response["data"]["value"]

    def list_secrets(self) -> List[str]:
        """List all secrets in Vault.

        Returns:
            List of secret paths
        """
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path="", mount_point=self.mount_path
            )
            return response["data"]["keys"]
        except Exception:
            # Fall back to KV v1
            response = self.client.secrets.kv.v1.list_secrets(
                path="", mount_point=self.mount_path
            )
            return response["data"]["keys"]


class AWSSecretProvider(SecretProvider):
    """Secret provider for AWS Secrets Manager.

    This provider integrates with AWS Secrets Manager for cloud-native secret management.
    """

    def __init__(self, region_name: str = "us-east-1"):
        """Initialize AWS secret provider.

        Args:
            region_name: AWS region
        """
        self.region_name = region_name
        self._client = None

    @property
    def client(self):
        """Lazy initialization of AWS client."""
        if self._client is None:
            try:
                import boto3

                self._client = boto3.client(
                    "secretsmanager", region_name=self.region_name
                )
            except ImportError:
                raise RuntimeError(
                    "boto3 library not installed. Install with: pip install boto3"
                )
        return self._client

    def get_secret(self, name: str, version: Optional[str] = None) -> str:
        """Get secret from AWS Secrets Manager.

        Args:
            name: Secret name in AWS
            version: Optional version ID

        Returns:
            Secret value
        """
        kwargs = {"SecretId": name}
        if version:
            kwargs["VersionId"] = version

        response = self.client.get_secret_value(**kwargs)
        return response["SecretString"]

    def list_secrets(self) -> List[str]:
        """List all secrets in AWS Secrets Manager.

        Returns:
            List of secret names
        """
        response = self.client.list_secrets()
        return [secret["Name"] for secret in response["SecretList"]]


class SecretNotFoundError(Exception):
    """Raised when a secret cannot be found."""

    pass


class SecretProviderError(Exception):
    """Raised when a secret provider operation fails."""

    pass
