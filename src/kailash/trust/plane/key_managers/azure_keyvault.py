# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Azure Key Vault key manager for TrustPlane.

Uses Azure Key Vault for signing operations with EC P-256.

Requires azure-keyvault-keys and azure-identity:
    pip install kailash[azure-secrets]

Example:
    from kailash.trust.plane.key_managers.azure_keyvault import AzureKeyVaultKeyManager

    manager = AzureKeyVaultKeyManager(
        vault_url="https://my-vault.vault.azure.net",
        key_name="trustplane-signing-key",
    )
    signature = manager.sign(b"data to sign")
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from kailash.trust.plane.exceptions import (
    KeyManagerError,
    KeyNotFoundError,
    SigningError,
)

logger = logging.getLogger(__name__)

__all__ = [
    "AzureKeyVaultKeyManager",
]

try:
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.keys import KeyClient
    from azure.keyvault.keys.crypto import CryptographyClient, SignatureAlgorithm

    _AZURE_AVAILABLE = True
except ImportError:
    _AZURE_AVAILABLE = False


class AzureKeyVaultKeyManager:
    """Azure Key Vault key manager implementing TrustPlaneKeyManager protocol.

    Uses EC P-256 for signing operations via Azure Key Vault's
    CryptographyClient.

    Args:
        vault_url: The Azure Key Vault URL (e.g. "https://my-vault.vault.azure.net").
        key_name: Name of the key in the vault.

    Raises:
        ImportError: If azure-keyvault-keys is not installed.
    """

    ALGORITHM = "ecdsa-p256"

    def __init__(self, vault_url: str, key_name: str) -> None:
        if not _AZURE_AVAILABLE:
            raise ImportError(
                "azure-keyvault-keys and azure-identity are required for "
                "Azure Key Vault key management. "
                "Install with: pip install kailash[azure-secrets]"
            )

        self._vault_url = vault_url
        self._key_name = key_name

        credential = DefaultAzureCredential()
        self._key_client: Any = KeyClient(vault_url=vault_url, credential=credential)

        try:
            key = self._key_client.get_key(key_name)
        except Exception as exc:
            raise KeyNotFoundError(
                f"Failed to retrieve key '{key_name}' from vault: {exc}",
                provider="azure_keyvault",
                key_id=key_name,
            ) from exc
        self._crypto_client: Any = CryptographyClient(key, credential=credential)
        self._public_key_cache: bytes | None = None

        logger.info(
            "Initialized Azure Key Vault key manager for key %s in vault %s",
            key_name,
            vault_url,
        )

    def sign(self, data: bytes) -> bytes:
        """Sign data using Azure Key Vault.

        Uses ES256 (ECDSA with P-256 and SHA-256).

        Args:
            data: Bytes to sign.

        Returns:
            Raw ECDSA signature bytes.

        Raises:
            SigningError: If Azure signing operation fails.
        """
        try:
            result = self._crypto_client.sign(SignatureAlgorithm.es256, data)
        except Exception as exc:
            raise SigningError(
                f"Azure Key Vault signing failed: {exc}",
                provider="azure_keyvault",
                key_id=self._key_name,
            ) from exc
        return result.signature

    def get_public_key(self) -> bytes:
        """Retrieve the public key from Azure Key Vault.

        Returns:
            The public key component bytes from the Key Vault key.

        Raises:
            KeyManagerError: If the public key cannot be retrieved.
        """
        if self._public_key_cache is None:
            try:
                key = self._key_client.get_key(self._key_name)
            except Exception as exc:
                raise KeyManagerError(
                    f"Failed to retrieve public key: {exc}",
                    provider="azure_keyvault",
                    key_id=self._key_name,
                ) from exc
            # Azure returns the key with .key property containing the JWK
            jwk = key.key
            # Concatenate x and y coordinates for the raw EC public key
            self._public_key_cache = jwk.x + jwk.y
        return self._public_key_cache

    def key_id(self) -> str:
        """Return SHA-256 hex fingerprint of the public key.

        Returns:
            64-character hex string.

        Raises:
            KeyManagerError: If the public key cannot be retrieved.
        """
        return hashlib.sha256(self.get_public_key()).hexdigest()

    def algorithm(self) -> str:
        """Return the signing algorithm identifier.

        Returns:
            Always "ecdsa-p256" for Azure Key Vault.
        """
        return self.ALGORITHM
