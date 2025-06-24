"""Security and secret management for gateway.

This module provides secure credential management with encryption
and multiple backend options for storing secrets.
"""

import asyncio
import base64
import json
import logging
import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class SecretNotFoundError(Exception):
    """Raised when secret is not found."""

    pass


class SecretBackend(ABC):
    """Abstract backend for secret storage."""

    @abstractmethod
    async def get_secret(self, reference: str) -> Dict[str, Any]:
        """Get secret by reference."""
        pass

    @abstractmethod
    async def store_secret(self, reference: str, secret: Dict[str, Any]) -> None:
        """Store a secret."""
        pass

    @abstractmethod
    async def delete_secret(self, reference: str) -> None:
        """Delete a secret."""
        pass


class SecretManager:
    """Manages secrets for resource credentials."""

    def __init__(
        self,
        backend: Optional[SecretBackend] = None,
        encryption_key: Optional[str] = None,
        cache_ttl: int = 300,  # 5 minutes
    ):
        self.backend = backend or EnvironmentSecretBackend()
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._ttl = timedelta(seconds=cache_ttl)
        self._lock = asyncio.Lock()

        # Set up encryption
        if encryption_key:
            self._cipher = Fernet(encryption_key.encode())
        else:
            # Generate key from environment or use default
            key = os.environ.get("KAILASH_ENCRYPTION_KEY")
            if not key:
                # Warning: This is not secure for production!
                logger.warning(
                    "Using default encryption key - not secure for production!"
                )
                # Generate a proper Fernet key
                key = Fernet.generate_key()
            elif isinstance(key, str):
                key = key.encode()
            self._cipher = Fernet(key)

    async def get_secret(self, reference: str) -> Dict[str, Any]:
        """Get secret by reference."""
        async with self._lock:
            # Check cache
            if reference in self._cache:
                value, timestamp = self._cache[reference]
                if datetime.now(UTC) - timestamp < self._ttl:
                    return value
                else:
                    # Expired, remove from cache
                    del self._cache[reference]

        # Fetch from backend
        encrypted_secret = await self.backend.get_secret(reference)

        # Decrypt if needed
        if isinstance(encrypted_secret, str) and encrypted_secret.startswith(
            "encrypted:"
        ):
            decrypted = self._cipher.decrypt(encrypted_secret[10:].encode()).decode()
            secret = json.loads(decrypted)
        elif isinstance(encrypted_secret, dict) and "value" in encrypted_secret:
            # Handle case where backend returns {"value": "encrypted:..."}
            value = encrypted_secret["value"]
            if isinstance(value, str) and value.startswith("encrypted:"):
                decrypted = self._cipher.decrypt(value[10:].encode()).decode()
                secret = json.loads(decrypted)
            else:
                secret = encrypted_secret
        else:
            secret = encrypted_secret

        # Cache it
        async with self._lock:
            self._cache[reference] = (secret, datetime.now(UTC))

        return secret

    async def store_secret(
        self, reference: str, secret: Dict[str, Any], encrypt: bool = True
    ) -> None:
        """Store a secret."""
        if encrypt:
            # Encrypt the secret
            secret_json = json.dumps(secret)
            encrypted = self._cipher.encrypt(secret_json.encode())
            encrypted_value = f"encrypted:{encrypted.decode()}"
            await self.backend.store_secret(reference, encrypted_value)
        else:
            await self.backend.store_secret(reference, secret)

        # Clear from cache
        async with self._lock:
            if reference in self._cache:
                del self._cache[reference]

    async def delete_secret(self, reference: str) -> None:
        """Delete a secret."""
        await self.backend.delete_secret(reference)

        # Clear from cache
        async with self._lock:
            if reference in self._cache:
                del self._cache[reference]

    async def clear_cache(self):
        """Clear the secret cache."""
        async with self._lock:
            self._cache.clear()


class EnvironmentSecretBackend(SecretBackend):
    """Secret backend using environment variables."""

    def __init__(self, prefix: str = "KAILASH_SECRET_"):
        self.prefix = prefix

    async def get_secret(self, reference: str) -> Dict[str, Any]:
        """Get secret from environment."""
        # Convert reference to env var name
        env_var = f"{self.prefix}{reference.upper()}"

        value = os.environ.get(env_var)
        if not value:
            raise SecretNotFoundError(f"Secret {reference} not found")

        # Try to parse as JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Return as simple key-value
            return {"value": value}

    async def store_secret(self, reference: str, secret: Any) -> None:
        """Store secret in environment (not recommended for production)."""
        env_var = f"{self.prefix}{reference.upper()}"

        if isinstance(secret, dict):
            os.environ[env_var] = json.dumps(secret)
        else:
            os.environ[env_var] = str(secret)

    async def delete_secret(self, reference: str) -> None:
        """Delete secret from environment."""
        env_var = f"{self.prefix}{reference.upper()}"
        if env_var in os.environ:
            del os.environ[env_var]


class FileSecretBackend(SecretBackend):
    """Secret backend using encrypted file storage."""

    def __init__(self, secrets_dir: str = "/etc/kailash/secrets"):
        self.secrets_dir = secrets_dir
        os.makedirs(secrets_dir, exist_ok=True)

    async def get_secret(self, reference: str) -> Dict[str, Any]:
        """Get secret from file."""
        file_path = os.path.join(self.secrets_dir, f"{reference}.json")

        if not os.path.exists(file_path):
            raise SecretNotFoundError(f"Secret {reference} not found")

        with open(file_path, "r") as f:
            return json.load(f)

    async def store_secret(self, reference: str, secret: Any) -> None:
        """Store secret in file."""
        file_path = os.path.join(self.secrets_dir, f"{reference}.json")

        with open(file_path, "w") as f:
            if isinstance(secret, str):
                f.write(secret)
            else:
                json.dump(secret, f)

        # Set restrictive permissions
        os.chmod(file_path, 0o600)

    async def delete_secret(self, reference: str) -> None:
        """Delete secret file."""
        file_path = os.path.join(self.secrets_dir, f"{reference}.json")
        if os.path.exists(file_path):
            os.remove(file_path)


# For production, you would implement:
# - VaultSecretBackend for HashiCorp Vault
# - AWSSecretsManagerBackend for AWS Secrets Manager
# - AzureKeyVaultBackend for Azure Key Vault
# - GCPSecretManagerBackend for Google Cloud Secret Manager
